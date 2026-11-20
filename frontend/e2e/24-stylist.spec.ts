import type { Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';


const current = (page: Page) => page.getByTestId('current-outfit');
const waiting = (page: Page) => page.getByTestId('stylist-waiting');
const read = (page: Page) => page.getByTestId('stylist-read');

async function setUp(page: Page, url: string) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url + '/');
  await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
  await page.getByLabel('Type it again').fill(PASS);
  await page.getByRole('button', { name: 'Set passphrase' }).click();
  await page.getByRole('button', { name: 'Start with my own closet' }).click();
}

/** A forecast, as 10-today.spec.ts gives one (home's weather is out of reach in a test), so Today looks as it does on
 * an ordinary day: no notice that the weather could not be fetched. Claude is told the same day. */
async function aDay(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { ...body, low_c: 3.2, high_c: 9.8, rain: true } });
    const json = await response.json();
    if (response.ok()) {
      Object.assign(json.context, { source: 'forecast', place: 'Brooklyn, New York, United States', rain_chance: 70, summary: 'rain', old: false, message: null });
    }
    await route.fulfill({ response, json });
  });
}

/** Claude's outfits are on screen: the first is Claude's, with the stand-in's sentence and its reading of the day. */
async function claudes(page: Page) {
  await expect(waiting(page)).toHaveCount(0, { timeout: 15_000 });
  await expect(current(page).getByTestId('outfit-by')).toHaveText('Chosen by Claude');
  await expect(current(page).getByRole('list', { name: 'Why this works' })).toContainText('Chosen by the stand-in: these go together.');
  // Claude's reading of the day is said in the outfit's "Why this works", under who chose it, not in a line of its own
  await expect(current(page).getByTestId('outfit-read')).toHaveText('It is a made-up day, so the stand-in chose by number.');
  await expect(page.getByText(/^Claude on today/)).toHaveCount(0);
  await expect(read(page).getByRole('button', { name: 'Ask Claude again' })).toBeEnabled();
}

// Its own backend, with a stand-in for Claude choosing the outfits (tests/e2e_backend.py): it answers after 1.5
// seconds with the rules' second and first outfits. The owner's closet starts as a copy of the demo closet, because
// Claude never chooses in the demo closet. Home's weather is out of reach in a test, so Today dresses for a mild day.
test.describe('outfits chosen by Claude', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo', stylist: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('Today waits for Claude, shows its outfits, keeps them, asks again, and wears them', async ({ page }) => {
    test.setTimeout(180_000);
    await aDay(page);   // before the first page: logging in can show Today, whose request must be for this day too
    await setUp(page, backend.url);

    // hold Claude's answer as "still choosing" until the waiting state has been looked at
    let hold = true;
    await page.route('**/api/style/answers/*', async (route) => {
      if (!hold) return route.continue();
      const id = new URL(route.request().url()).pathname.split('/').pop();
      return route.fulfill({ json: { id, state: 'working', message: null } });
    });

    await page.goto(backend.url + '/today');
    await expect(page.getByTestId('day-line')).toContainText('Brooklyn');
    // the closet copied from the demo asks about yesterday's outfit: not now
    await page.getByTestId('worn-question').getByRole('button', { name: 'Not now' }).click();
    await expect(waiting(page)).toBeVisible();
    await expect(waiting(page)).toHaveAttribute('role', 'status');
    await expect(waiting(page).getByRole('heading', { name: "Claude is choosing today's outfits…" })).toBeVisible();
    await expect(waiting(page)).toContainText('This usually takes under a minute. They are kept for the rest of the day.');
    await expect(page.getByTestId('current-outfit')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /Best for today/ })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('today-stylist-waiting.png') });

    // the rules' outfits meanwhile, below the card, as they always look (and nothing yet says who chose them)
    await waiting(page).getByRole('button', { name: "Show Closet's own picks meanwhile" }).click();
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect(waiting(page)).toBeVisible();
    expect((await waiting(page).boundingBox())!.y).toBeLessThan((await current(page).boundingBox())!.y);
    await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeEnabled();
    await expect(current(page).getByTestId('outfit-by')).toHaveCount(0);
    await expect(waiting(page).getByRole('button', { name: "Show Closet's own picks meanwhile" })).toHaveCount(0);
    const rulesFirst = await current(page).getByTestId('piece').allTextContents();

    // then Claude's arrive by themselves
    hold = false;
    await claudes(page);
    expect(await current(page).getByTestId('piece').allTextContents()).not.toEqual(rulesFirst);

    // "I'm wearing this" is still on the first phone screen, above the tab bar
    const wear = current(page).getByRole('button', { name: "I'm wearing this" });
    const box = (await wear.boundingBox())!;
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(tabbar.y);
    // who chose it is below the button, with the reasons
    expect((await current(page).getByTestId('outfit-by').boundingBox())!.y).toBeGreaterThan(box.y + box.height);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('today-stylist.png') });

    // the second outfit is Claude's too, with its caution; after Claude's come the rules'
    await page.getByRole('button', { name: 'Outfit 2', exact: true }).click();
    await expect(page.getByRole('heading', { name: /2 of/ })).toBeVisible();
    await expect(current(page).getByTestId('outfit-by')).toHaveText('Chosen by Claude');
    await expect(current(page).getByRole('note', { name: 'Be aware' })).toContainText('The stand-in has no eye for colour.');
    await page.getByRole('button', { name: 'Outfit 3', exact: true }).click();
    await expect(page.getByRole('heading', { name: /3 of/ })).toBeVisible();
    await expect(current(page).getByTestId('outfit-by')).toHaveText("From Closet's rules");
    await page.getByRole('button', { name: 'Outfit 1', exact: true }).click();

    // the answer is kept: a reload shows Claude's outfits at once
    await page.reload();
    await expect(current(page).getByTestId('outfit-by')).toHaveText('Chosen by Claude');
    await expect(waiting(page)).toHaveCount(0);
    await claudes(page);

    // Ask Claude again: Claude chooses afresh
    const posted: unknown[] = [];
    page.on('request', (r) => {
      if (r.url().endsWith('/api/outfits/today') && r.method() === 'POST') posted.push(r.postDataJSON());
    });
    await read(page).getByRole('button', { name: 'Ask Claude again' }).click();
    await expect(waiting(page)).toBeVisible();
    await claudes(page);
    expect(posted[0]).toMatchObject({ ask_again: true });
    expect(posted.slice(1).every((b) => !(b as { ask_again?: boolean }).ask_again)).toBe(true);

    // another occasion is asked once: Claude chooses for it, and going back is at once
    const occasion = page.getByRole('group', { name: 'Occasion' });
    await occasion.getByRole('button', { name: 'Smart casual' }).click();
    await expect(waiting(page)).toBeVisible();
    await claudes(page);
    await occasion.getByRole('button', { name: 'Casual', exact: true }).click();
    await expect(occasion.getByRole('button', { name: 'Casual', exact: true, pressed: true })).toBeVisible();
    await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
    await expect(waiting(page)).toHaveCount(0);
    await claudes(page);

    // Settings → Your style: switched off, Today is Closet's own rules with nothing about Claude
    await page.goto(backend.url + '/settings');
    const section = page.locator('section[aria-labelledby="s-style"]');
    const toggle = section.getByRole('switch', { name: 'Let Claude choose my outfits' });
    await expect(toggle).toBeChecked();
    await expect(section).toContainText("When this is off, or Claude can't be reached, Closet's own rules choose.");
    await toggle.click();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(toggle).not.toBeChecked();
    await section.getByRole('button', { name: 'Edit the text' }).click();
    await expect(section.getByRole('textbox', { name: 'About how I dress' })).toBeEnabled();
    await page.goto(backend.url + '/today');
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect(waiting(page)).toHaveCount(0);
    await expect(page.getByTestId('outfit-by')).toHaveCount(0);
    await expect(read(page)).toHaveCount(0);
    await expect(page.getByTestId('stylist-failed')).toHaveCount(0);

    // switched on again, Claude's outfits are back
    await page.goto(backend.url + '/settings');
    await toggle.click();
    await expect(toggle).toBeChecked();
    await page.goto(backend.url + '/today');
    await claudes(page);

    // wearing Claude's outfit records it, and it is under Worn
    const pieces = await current(page).getByTestId('piece').count();
    await current(page).getByRole('button', { name: "I'm wearing this" }).click();
    await expect(page.getByText("Noted: you're wearing this today")).toBeVisible();
    await page.getByTestId('recent-outfits').getByRole('link', { name: 'See all' }).click();
    await expect(page).toHaveURL(/\/today\/worn$/);
    const todays = page.getByTestId('worn-outfit').first();
    await expect(todays.getByRole('heading', { name: 'Today' })).toBeVisible();
    await expect(todays.getByRole('list', { name: 'Pieces' }).getByRole('listitem')).toHaveCount(pieces);
  });
});

test.describe('when Claude cannot be reached', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo', stylist: 'fails' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test("Today shows Closet's own outfits, says why, and offers to try again", async ({ page }) => {
    test.setTimeout(120_000);
    await setUp(page, backend.url);
    await page.goto(backend.url + '/today');
    const failed = page.getByTestId('stylist-failed');
    await expect(failed).toContainText("Claude couldn't be reached, so these are from Closet's own rules.", { timeout: 15_000 });
    await expect(waiting(page)).toHaveCount(0);
    await expect(current(page).getByTestId('outfit-by')).toHaveText("From Closet's rules");
    await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeEnabled();
    await expect(failed.getByRole('button', { name: 'Try again' })).toBeEnabled();
    expect(await axeViolations(page)).toEqual([]);

    // trying again asks once more, and says the same when Claude is still out of reach
    await failed.getByRole('button', { name: 'Try again' }).click();
    await expect(failed).toContainText("Claude couldn't be reached", { timeout: 15_000 });
    await expect(waiting(page)).toHaveCount(0);
  });
});
