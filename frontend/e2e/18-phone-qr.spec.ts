import jsQR from 'jsqr';
import type { APIRequestContext, Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, login, PASS, test } from './fixtures';

/** Phone access: a QR code of the address that reaches Closet, only when there is one. Tailscale is faked. */

const ADDRESS = 'https://closet-pc.example-tailnet.ts.net:8443';

// The phone reaches Closet by a name of its own (Tailscale's, which the server lets in), not 127.0.0.1. Here a made-up
// Tailscale name leads the browser to the same backend, so the page sees what it sees on the phone: an address that is
// not this computer's.
const PHONE_HOST = 'closet-phone.example-tailnet.ts.net';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
test.use({
  launchOptions: { ...(executablePath ? { executablePath } : {}), args: [`--host-resolver-rules=MAP ${PHONE_HOST} 127.0.0.1`] },
});

async function fakePhone(page: Page, address: string | null) {
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const original = await (await page.request.get('/api/settings')).json();
    await route.fulfill({
      json: {
        ...original,
        phone: address
          ? { tailscale_installed: true, running: true, address, command: 'tailscale serve --bg --https=8443 8765',
            stop_command: 'tailscale serve --https=8443 off', others_share: true }
          : { tailscale_installed: true, running: true, address: null, command: 'tailscale serve --bg --https=8443 8765',
            stop_command: null, others_share: true },
      },
    });
  });
}

/** Reads the code as it is drawn on screen, the way a camera would. */
async function readCode(page: Page): Promise<string | undefined> {
  const png = await page.locator('.phone-qr').screenshot();
  const { width, height, data } = await page.evaluate(async (src) => {
    const img = new Image();
    img.src = src;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    // a margin of the page's own background around it, as the camera sees it
    return { width: img.width, height: img.height, data: Array.from(ctx.getImageData(0, 0, img.width, img.height).data) };
  }, `data:image/png;base64,${png.toString('base64')}`);
  return jsQR(Uint8ClampedArray.from(data), width, height)?.data;
}

for (const theme of ['light', 'dark'] as const) {
  test(`phone access in ${theme}: a QR code of Nines' address, readable, with the address as text below`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await fakePhone(page, ADDRESS);
    await login(page);
    await page.goto('/settings');
    const section = page.getByRole('region', { name: 'Phone', exact: true });
    // once a share reaches Closet the group is one line, with the code folded under it
    await expect(section.getByTestId('phone-address')).toHaveText(ADDRESS);
    const code = section.getByRole('img', { name: `QR code of ${ADDRESS}` });
    await expect(code).toBeHidden();
    await section.getByText('Show the QR code').click();
    await expect(code).toBeVisible();
    await expect(code).toHaveAttribute('data-payload', ADDRESS);
    const box = (await code.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(180);
    expect(box.width).toBeLessThanOrEqual(220);
    expect(box.height).toBeCloseTo(box.width, 0);
    expect(await readCode(page)).toBe(ADDRESS);
    // the address stays copyable text, below the code
    const link = section.getByRole('link', { name: ADDRESS });
    await expect(link).toBeVisible();
    const [drawn, text] = [(await code.boundingBox())!, (await link.boundingBox())!];
    expect(text.y).toBeGreaterThan(drawn.y + drawn.height);
    expect(await axeViolations(page)).toEqual([]);
  });
}

test('phone access: no code when no share reaches Nines, only the plain explanation', async ({ page }) => {
  await fakePhone(page, null);
  await login(page);
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'Phone', exact: true });
  await expect(section.getByText('Nines is not shared with your phone yet.')).toBeVisible();
  await expect(section.getByText('tailscale serve --bg --https=8443 8765')).toBeVisible();
  await expect(section.locator('.phone-qr')).toHaveCount(0);
  await expect(section.getByRole('img')).toHaveCount(0);
});

test('the door through Cloudflare: folded under Phone on the computer, filled in and turned off again', async ({ page }) => {
  await login(page);
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'Phone', exact: true });
  const door = section.getByTestId('cloudflare-door');
  await door.getByText('Without Tailscale, through Cloudflare').click();
  await expect(door.getByTestId('cloudflare-status')).toHaveText('This is off until all three are filled in.');
  await door.getByLabel('Your Cloudflare team').fill('yourteam');
  await door.getByLabel("The Access application's audience tag").fill('a1b2c3d4e5f60718293a4b5c6d7e8f90');
  await door.getByLabel("Nines' address on Cloudflare").fill('closet example.com');
  await door.getByRole('button', { name: 'Save' }).click();
  await expect(door.getByRole('alert')).toContainText('closet.example.com');   // the server's sentence, as typed wrong
  await door.getByLabel("Nines' address on Cloudflare").fill('https://closet.example.com/');
  await door.getByRole('button', { name: 'Save' }).click();
  await expect(door.getByText('Also through Cloudflare, at closet.example.com')).toBeVisible();
  await expect(door.getByTestId('cloudflare-status')).toHaveText('Nines answers at https://closet.example.com once Cloudflare has checked who you are.');
  await expect(door.getByLabel('Your Cloudflare team')).toHaveValue('yourteam.cloudflareaccess.com');
  expect(await axeViolations(page)).toEqual([]);
  await door.scrollIntoViewIfNeeded();
  await door.screenshot({ path: test.info().outputPath('cloudflare-door.png') });
  await door.getByLabel("The Access application's audience tag").fill('');
  await door.getByRole('button', { name: 'Save' }).click();
  await expect(door.getByText('Without Tailscale, through Cloudflare')).toBeVisible();
  await expect(page.getByTestId('came-in')).toHaveCount(0);   // on the computer itself, nothing about how it came in
});

test.describe('opened on the phone', () => {
  test.use({
    viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true,
    // eslint-disable-next-line no-empty-pattern -- Playwright fixtures take their dependencies as a pattern
    baseURL: async ({}, use) => {
      await use(process.env.E2E_BASE_URL!.replace('127.0.0.1', PHONE_HOST));
    },
  });

  /** Logs in through the page by the phone's name. The test runner itself cannot resolve that name, so the settings
   * the page is shown are fetched from 127.0.0.1 and given the share's address. */
  async function openSettings(page: Page, request: APIRequestContext, cameIn?: object) {
    const local = process.env.E2E_BASE_URL!;
    const s = await (await request.get(`${local}/api/session`)).json();
    if (s.setup_required) expect((await request.post(`${local}/api/setup`, { data: { passphrase: PASS } })).status()).toBe(204);
    else expect((await request.post(`${local}/api/login`, { data: { passphrase: PASS } })).status()).toBe(204);
    const original = await (await request.get(`${local}/api/settings`)).json();
    await page.route('**/api/settings', (route) => route.request().method() === 'GET'
      ? route.fulfill({ json: { ...original, ...(cameIn ? { came_in: cameIn } : {}), phone: { tailscale_installed: true, running: true, address: ADDRESS,
        command: 'tailscale serve --bg --https=8443 8765', stop_command: 'tailscale serve --https=8443 off', others_share: true } } })
      : route.fallback());
    await page.goto('/');
    expect(new URL(page.url()).hostname).toBe(PHONE_HOST);
    const field = page.getByLabel('Passphrase');
    await expect(field.or(page.locator('#closet-title, #today-title'))).toBeVisible();
    if (await field.isVisible()) {
      await field.fill(PASS);
      await page.getByRole('button', { name: 'Open my closet' }).click();
    }
    await expect(page.locator('#closet-title, #today-title')).toBeVisible();
    await page.goto('/settings');
    await expect(page.getByRole('region', { name: 'Updates', exact: true })).toBeVisible();
  }

  test('in Safari: no code, address or commands, only how to add Nines to the Home Screen', async ({ page, request }) => {
    await openSettings(page, request);
    const section = page.getByRole('region', { name: 'Phone', exact: true });
    await expect(section.getByText('tap Share in Safari and then Add to Home Screen')).toBeVisible();
    await expect(section.locator('.phone-qr')).toHaveCount(0);
    await expect(section.getByRole('img')).toHaveCount(0);
    await expect(section.getByRole('link')).toHaveCount(0);
    await expect(section.locator('code')).toHaveCount(0);
    await expect(page.getByText(ADDRESS)).toHaveCount(0);
    await expect(page.getByText('tailscale serve')).toHaveCount(0);
    await expect(page.getByTestId('cloudflare-door')).toHaveCount(0);   // set up on the computer, where its connector is
  });

  test('This device says how the phone came in: through Tailscale, and as whom', async ({ page, request }) => {
    await openSettings(page, request, { via: 'tailscale', login: 'owner@example.com', name: 'Sam Owner' });
    const device = page.getByRole('region', { name: 'This device', exact: true });
    await expect(device.getByTestId('came-in')).toHaveText('This device came in through Tailscale as Sam Owner (owner@example.com).');
  });

  test('what only makes sense on the computer is not offered: Quit, start at login, folders and files', async ({ page, request }) => {
    await openSettings(page, request);
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Quit Nines' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Choose a backup folder' })).toHaveCount(0);
    await page.getByRole('link', { name: 'Advanced settings' }).click();
    await expect(page.getByRole('heading', { name: 'Advanced', level: 1 })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Backups' })).toBeVisible();
    await expect(page.getByRole('switch', { name: /Show the demo closet/ })).toBeVisible();
    await expect(page.getByRole('switch', { name: /Start Nines when I log in/ })).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: 'Backup folder' })).toHaveCount(0);
    await expect(page.getByText('Put the files in place by hand')).toHaveCount(0);
    await expect(page.getByText('Your closet is stored in')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Quit Nines' })).toHaveCount(0);
  });

  test('from the Home Screen: no Phone group at all', async ({ page, request }) => {
    await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await openSettings(page, request);
    await expect(page.getByRole('heading', { name: 'Phone', exact: true })).toHaveCount(0);
    await expect(page.locator('.phone-qr')).toHaveCount(0);
    await expect(page.getByText('Add to Home Screen')).toHaveCount(0);
  });
});

test.describe('pictures', () => {
  for (const [layout, viewport] of [['phone', { width: 390, height: 844 }], ['computer', { width: 1440, height: 900 }]] as const) {
    test(`phone access with its code, on a ${layout}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await fakePhone(page, ADDRESS);
      await login(page);
      await page.goto('/settings');
      const section = page.getByRole('region', { name: 'Phone', exact: true });
      await section.scrollIntoViewIfNeeded();
      await section.getByText('Show the QR code').click();
      await expect(section.locator('.phone-qr')).toBeVisible();
      await page.evaluate(() => document.getElementById('s-phone')?.scrollIntoView({ block: 'start' }));
      // the code and the address under it are both in the picture, above the phone's tab bar
      const bar = await page.locator('nav.tabbar').boundingBox();
      const link = (await section.getByRole('link', { name: ADDRESS }).boundingBox())!;
      expect(link.y + link.height).toBeLessThanOrEqual(bar && bar.height ? bar.y : viewport.height);
      expect((await section.locator('.phone-qr').boundingBox())!.y).toBeGreaterThanOrEqual(0);
      await page.screenshot({ path: test.info().outputPath(`phone-access-qr-${layout}.png`) });
    });
  }
});
