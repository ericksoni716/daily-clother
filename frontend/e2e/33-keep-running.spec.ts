import type { APIRequestContext, Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test } from './fixtures';
import type { Backend } from './server';

/**
 * Windows keeping Nines running, under Settings › Phone. The test backend runs from source on Linux, where it is not
 * available, so Windows' side is stood in for in the browser: the settings' `background` and the three buttons.
 */

const PHONE_HOST = 'closet-phone.example-tailnet.ts.net';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
test.use({
  launchOptions: { ...(executablePath ? { executablePath } : {}), args: [`--host-resolver-rules=MAP ${PHONE_HOST} 127.0.0.1`] },
});

type State = { available: boolean; on: boolean; starts: 'startup' | 'logon' | null; running: boolean; port: number; problem: string | null };
const OFF: State = { available: true, on: false, starts: null, running: false, port: 8766, problem: null };
const DECLINED = "Windows asked for permission on this computer's screen and it was not given, so nothing changed.";

/** Windows as the page sees it: `state` in the settings, and what each button answers. */
async function fakeWindows(page: Page, state: State, answers: Record<string, (route: Route) => Promise<void>> = {}) {
  const now = { ...state };
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const original = await (await page.request.get('/api/settings')).json();
    await route.fulfill({ json: { ...original, background: now } });
  });
  await page.route('**/api/background**', async (route) => {
    const which = new URL(route.request().url()).pathname.split('/').pop() ?? '';
    if (answers[which]) return answers[which](route);
    return route.fulfill({ json: now });
  });
  return now;
}

test('on the computer: what it is, the port, and turning it on hands over to Windows', async ({ page }) => {
  let asked = 0;
  await fakeWindows(page, OFF, {
    on: (route) => { asked += 1; return route.fulfill({ json: { ...OFF, on: true, starts: 'startup', handing_over: true } }); },
  });
  await goToCloset(page);
  await page.goto('/settings');
  const card = page.getByRole('region', { name: 'Phone', exact: true }).getByTestId('keep-running');
  await expect(card.getByRole('heading', { name: 'Keep Nines running' })).toBeVisible();
  await expect(card.getByTestId('keep-running-status')).toHaveText('This is off, so your phone reaches Nines only while it is open on this computer.');
  await expect(card.getByText('It takes the place of Start Nines when I log in, and updates then go to the copy Windows runs.', { exact: false })).toBeVisible();
  await expect(card.getByTestId('keep-running-port')).toHaveText('Nines answers on port 8766 on this computer.');
  expect(await axeViolations(page)).toEqual([]);
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: test.info().outputPath('keep-running-off.png') });
  await page.setViewportSize({ width: 375, height: 812 });   // the narrowest phone: nothing wider than the screen
  await card.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await card.screenshot({ path: test.info().outputPath('keep-running-off-375.png') });
  await card.getByRole('button', { name: 'Keep Nines running' }).click();
  await expect(card.getByTestId('keep-running-status')).toHaveText('Windows keeps Nines running now. This window closes and opens again in a moment.');
  await expect(card.getByRole('button')).toHaveCount(0);
  expect(asked).toBe(1);
});

test('a declined prompt is said in plain words, and nothing changes', async ({ page }) => {
  await fakeWindows(page, OFF, { on: (route) => route.fulfill({ status: 409, json: { detail: DECLINED } }) });
  await goToCloset(page);
  await page.goto('/settings');
  const card = page.getByTestId('keep-running');
  await card.getByRole('button', { name: 'Keep Nines running' }).click();
  await expect(card.getByRole('alert')).toHaveText(DECLINED);
  await expect(card.getByRole('button', { name: 'Keep Nines running' })).toBeEnabled();
});

test('on but not running: start it again or turn it off, with the port that stays put', async ({ page }) => {
  const stopped: State = { ...OFF, on: true, starts: 'logon', running: false };
  let restarted = 0;
  await fakeWindows(page, stopped, {
    restart: (route) => { restarted += 1; return route.fulfill({ json: { ...stopped, handing_over: true } }); },
  });
  await goToCloset(page);
  await page.goto('/settings');
  const card = page.getByTestId('keep-running');
  await expect(card.getByTestId('keep-running-status')).toHaveText('Nines is set to start when you sign in to this computer, but it is not running in the background now.');
  await expect(card.getByTestId('keep-running-port')).toContainText('the port does not change, so Tailscale and Cloudflare stay pointed at it');
  await expect(card.getByRole('button', { name: 'Turn this off' })).toBeVisible();
  await card.getByRole('button', { name: 'Start it again' }).click();
  await expect(card.getByTestId('keep-running-status')).toContainText('This window closes and opens again in a moment.');
  expect(restarted).toBe(1);
});

test('turning it off from the window waits for Windows, and says why when it was not allowed', async ({ page }) => {
  const running: State = { ...OFF, on: true, starts: 'startup', running: true };
  let reads = 0;
  await fakeWindows(page, running, {
    off: (route) => route.fulfill({ json: { ...running, turning_off: true } }),
    background: (route) => { reads += 1; return route.fulfill({ json: reads < 2 ? running : { ...running, problem: DECLINED } }); },
  });
  await goToCloset(page);
  await page.goto('/settings');
  const card = page.getByTestId('keep-running');
  await expect(card.getByTestId('keep-running-status')).toHaveText('Nines starts when this computer turns on, and it is running now.');
  await card.getByRole('button', { name: 'Turn this off' }).click();
  await expect(card.getByTestId('keep-running-status')).toContainText('Windows is asking for permission on this screen.');
  await expect(card.getByTestId('keep-running-status')).toHaveText(DECLINED, { timeout: 15_000 });
  await expect(card.getByRole('button', { name: 'Turn this off' })).toBeVisible();
});

test('turned off in an ordinary copy, it says where the program that carries on is', async ({ page }) => {
  const stopped: State = { ...OFF, on: true, starts: 'startup', running: false };
  const note = 'Windows had kept Nines up to date, so your Nines.exe in C:\\Users\\you\\Apps\\Nines is now Nines 0.13.0.';
  await fakeWindows(page, stopped, { off: (route) => route.fulfill({ json: { ...OFF, turning_off: false, note } }) });
  await goToCloset(page);
  await page.goto('/settings');
  const card = page.getByTestId('keep-running');
  await card.getByRole('button', { name: 'Turn this off' }).click();
  await expect(card.getByTestId('keep-running-note')).toHaveText(note);
  await expect(card.getByRole('button', { name: 'Keep Nines running' })).toBeVisible();
});

test('where Windows cannot do it (here, from source), Settings shows nothing about it', async ({ page }) => {
  await goToCloset(page);
  await page.goto('/settings');
  await expect(page.getByRole('region', { name: 'Phone', exact: true })).toBeVisible();
  await expect(page.getByTestId('keep-running')).toHaveCount(0);
  expect((await (await page.request.get('/api/background')).json()).available).toBe(false);
});

test.describe('opened on the phone', () => {
  test.use({
    viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true,
    // Tailscale Serve says who is asking; the page by the phone's name is refused without it (backend/closet/gate.py)
    extraHTTPHeaders: { 'Tailscale-User-Login': 'owner@example.com', 'Tailscale-User-Name': 'Sam Owner' },
    baseURL: async ({ backend }, use) => {
      await use(backend.url.replace('127.0.0.1', PHONE_HOST));
    },
  });

  async function openSettings(page: Page, request: APIRequestContext, backend: Backend, background: State) {
    const original = await (await request.get(`${backend.url}/api/settings`)).json();
    await page.route('**/api/settings', (route) => route.request().method() === 'GET'
      ? route.fulfill({ json: { ...original, background } }) : route.fallback());
    await page.goto('/');
    await expect(page.locator('#closet-title, #today-title')).toBeVisible();
    await page.goto('/settings');
    await expect(page.getByRole('region', { name: 'Updates', exact: true })).toBeVisible();
  }

  test('from the Home Screen: one sentence on whether the computer keeps Nines running, and no buttons', async ({ page, request, backend }) => {
    await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await openSettings(page, request, backend, { ...OFF, on: true, starts: 'startup', running: true });
    const section = page.getByRole('region', { name: 'Phone', exact: true });
    await expect(section.getByTestId('keep-running')).toHaveText(
      'Your computer keeps Nines running, so your phone can reach it whenever the computer is awake. You change this in Settings on the computer.');
    await expect(section.getByRole('button')).toHaveCount(0);
    await expect(page.getByText('Add to Home Screen')).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
  });
});
