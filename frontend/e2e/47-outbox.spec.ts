import type { Page, Request, Route } from '@playwright/test';
import { expect, goToCloset, serviceWorkerInCharge, test, useProfile } from './fixtures';

/**
 * Wearing while the computer is off: "I'm wearing this", how an outfit went and a tick on a packing list, done while
 * Nines cannot be reached, show as done at once with one line in the banner, survive a reload, and reach Nines once,
 * in order, when it answers again. A refusal when it finally gets one is said, and the screen shows what Nines has.
 */

test.afterEach(async ({ page, context }) => {
  for (const tab of context.pages()) await tab.unrouteAll({ behavior: 'ignoreErrors' });
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

const PLACE = { name: 'Harbour Town, Nowhere', latitude: 38.7, longitude: -9.1, timezone: 'Europe/Lisbon' };
const banner = (page: Page) => page.locator('.banner-offline');
const keptLine = (page: Page) => page.getByTestId('kept-line');
const current = (page: Page) => page.getByTestId('current-outfit');
const pieceIds = async (page: Page) =>
  (await current(page).getByTestId('piece').evaluateAll((links) => links.map((a) => a.getAttribute('href')))).map((h) => h!.split('/').pop()!);

function localDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Today's outfits for a whole day given, so the weather is never looked up (as 10-today does). */
async function fakeWeather(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: body.low_c !== undefined ? body : { ...body, low_c: 8, high_c: 14, rain: false } }) });
  });
}

/**
 * The changes the page sends from now on, by method and path: every one handed to the network (`tried`), those Nines
 * answered (`answered`), and those that never reached it (`lost`: the browser still had the network down). A kept
 * action is tried again after a try that never reached Nines; what must happen exactly once is Nines getting it.
 */
function changesSent(page: Page) {
  const tried: string[] = [];
  const answered: string[] = [];
  const lost: string[] = [];
  const name = (r: Request) => {
    const path = new URL(r.url()).pathname;
    return r.method() !== 'GET' && path.startsWith('/api/') && path !== '/api/outfits/today' && path !== '/api/outfits/figure'
      ? `${r.method()} ${path}` : null;
  };
  // only what is handed on from now: a try begun while the network was still down may fail after this
  const seen = new Set<Request>();
  page.on('request', (r) => { const n = name(r); if (n) { seen.add(r); tried.push(n); } });
  page.on('response', (r) => { const n = name(r.request()); if (n && seen.has(r.request())) answered.push(n); });
  page.on('requestfailed', (r) => { const n = name(r); if (n && seen.has(r)) lost.push(n); });
  return { tried, answered, lost };
}

/** Nines got `change` exactly once; any other try of it never reached Nines (and so recorded nothing). */
async function onceToNines(sent: ReturnType<typeof changesSent>, change: string) {
  await expect.poll(() => sent.answered.filter((s) => s === change)).toHaveLength(1);
  const of = (list: string[]) => list.filter((s) => s === change).length;
  expect(of(sent.tried)).toBe(of(sent.answered) + of(sent.lost));
}

/** Today with its outfits saved on this device, then Nines out of reach and the page loaded again. */
async function todayOffline(page: Page, context: import('@playwright/test').BrowserContext) {
  await fakeWeather(page);
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  await page.goto('/today');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.unroute('**/api/outfits/today');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
}

async function wornOn(page: Page, day: string) {
  const list = (await (await page.request.get('/api/outfits/worn?limit=100')).json()).outfits as { id: string; worn_on: string; pieces: Record<string, string | string[] | null> }[];
  return list.filter((o) => o.worn_on === day);
}

test("worn while Nines can't be reached: worn at once, still after a reload, sent once when it answers", async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await todayOffline(page, context);
  const ids = await pieceIds(page);
  const day = localDay();
  const before = await wornOn(page, day);
  const bannerHeight = (await banner(page).boundingBox())!.height;
  await expect(keptLine(page)).toHaveCount(0);

  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(current(page).getByTestId('worn-today')).toHaveText("You're wearing this today");
  await expect(keptLine(page)).toHaveText(/kept on this phone and will be sent when Nines answers/);
  // the line takes the place of the banner's last words: nothing on the page moves
  expect((await banner(page).boundingBox())!.height).toBe(bannerHeight);
  await expect(current(page).getByRole('button', { name: 'Undo' })).toBeEnabled();
  // everything else still waits, and says why
  await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Formal' })).toBeDisabled();
  expect(await wornOn(page, day)).toEqual(before);

  await page.reload();
  await expect(current(page).getByTestId('worn-today')).toBeVisible();
  await expect(keptLine(page)).toBeVisible();

  const sent = changesSent(page);
  await context.setOffline(false);
  await expect(banner(page)).toBeHidden({ timeout: 15_000 });
  await expect.poll(async () => (await wornOn(page, day)).length).toBe(before.length + 1);
  const recorded = (await wornOn(page, day)).filter((o) => !before.some((b) => b.id === o.id));
  expect(Object.values(recorded[0].pieces).flat().filter(Boolean).sort()).toEqual([...ids].sort());
  for (const id of ids) {
    const wears = (await (await page.request.get(`/api/items/${id}/wears`)).json()).wears as { worn_on: string }[];
    expect(wears.filter((w) => w.worn_on === day)).toHaveLength(1);
  }
  await onceToNines(sent, 'POST /api/wears');
  expect(await page.evaluate(() => localStorage.getItem('closet-today-saved:outbox:demo'))).toBeNull();
  // Today now knows the outfit Nines recorded (on its card, or in the line over the outfits asked for again): taking it
  // back takes it off Nines
  await expect(page.getByText(/You're wearing this today/).first()).toBeVisible();
  await page.getByRole('button', { name: 'Undo' }).first().click();
  await expect.poll(async () => (await wornOn(page, day)).length).toBe(before.length);
});

test("with something kept on the phone, Today's first screen on the smallest phone still holds the outfit and its button", async ({ page, context }) => {
  // as 10-today's first-screen test: an iPhone 13 mini with Safari's bars, a mild day, outfits of five pieces
  await page.setViewportSize({ width: 375, height: 629 });
  await page.route('**/api/outfits/today', async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { ...body, low_c: 14, high_c: 20, rain: false } });
    const json = await response.json();
    if (response.ok()) json.outfits = json.outfits.filter((o: { pieces: Record<string, unknown> }) => Object.values(o.pieces).flat().filter(Boolean).length === 5);
    await route.fulfill({ response, json });
  });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  await page.goto('/today');
  await expect(current(page).getByTestId('piece')).toHaveCount(5);
  await page.waitForLoadState('networkidle');
  await page.unroute('**/api/outfits/today');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(keptLine(page)).toBeVisible();
  const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
  const undo = (await current(page).getByRole('button', { name: 'Undo' }).boundingBox())!;
  expect(undo.y + undo.height).toBeLessThanOrEqual(tabbar.y);
  for (const piece of await current(page).getByTestId('piece').all()) {
    const b = (await piece.boundingBox())!;
    expect(b.y + b.height).toBeLessThanOrEqual(undo.y);
  }
  await page.screenshot({ path: test.info().outputPath('today-first-screen-kept.png') });
  // taken back, so nothing reaches Nines when the next test brings it back
  await current(page).getByRole('button', { name: 'Undo' }).click();
  await expect(keptLine(page)).toHaveCount(0);
});

test('a wear taken back before Nines answers is never sent', async ({ page, context }) => {
  await todayOffline(page, context);
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(keptLine(page)).toBeVisible();
  await current(page).getByRole('button', { name: 'Undo' }).click();
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();
  await expect(keptLine(page)).toHaveCount(0);
  const sent = changesSent(page);
  await context.setOffline(false);
  await expect(banner(page)).toBeHidden({ timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  expect(sent.tried.filter((s) => s.includes('/api/wears'))).toEqual([]);
});

test('a wear Nines refuses when it finally gets it is said once, and Today shows what Nines has', async ({ page, context }) => {
  await todayOffline(page, context);
  const day = localDay();
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(keptLine(page)).toBeVisible();
  // meanwhile another outfit is recorded for today, on the computer
  const items = (await (await page.request.get('/api/items?status=active')).json()).items as { id: string; category: string }[];
  const other = [items.find((i) => i.category === 'tee')!.id, items.find((i) => i.category === 'jeans')!.id, items.find((i) => i.category === 'sneakers')!.id];
  const elsewhere = await (await page.request.post('/api/outfits/worn', { data: { item_ids: other, worn_on: day } })).json();
  try {
    await context.setOffline(false);
    await expect(page.getByText('The outfit you wore today was not recorded. Another outfit was recorded for that day in the meantime.')).toBeVisible({ timeout: 15_000 });
    await expect(banner(page)).toBeHidden();
    expect((await wornOn(page, day)).map((o) => o.id)).toEqual([elsewhere.id]);
    // the outfit tapped here is no longer said to be worn; the one Nines has is
    await expect(current(page).getByTestId('worn-today')).toHaveCount(0);
    await expect(page.getByText(/^You're wearing this today:/)).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('closet-today-saved:outbox:demo'))).toBeNull();
  } finally {
    await page.request.delete(`/api/outfits/worn/${elsewhere.id}`);
  }
});

test("rated while Nines can't be reached: shown at once, still after a reload, sent once when it answers", async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  await page.goto('/today/worn');
  const first = page.getByTestId('worn-outfit').first();
  await expect(first).toBeVisible();
  const id = (await (await page.request.get('/api/outfits/worn')).json()).outfits[0].id as string;
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  const change = first.getByRole('button', { name: 'Change rating' });
  if (await change.count()) await change.click();
  const was = await first.getByRole('button', { name: 'Loved it', exact: true }).getAttribute('aria-pressed');
  const want = was === 'true' ? 'Fine' : 'Loved it';
  await first.getByRole('button', { name: want, exact: true }).click();
  await expect(first.getByRole('button', { name: want, exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(keptLine(page)).toBeVisible();

  await page.reload();
  await expect(page.getByTestId('worn-outfit').first().getByTestId('worn-rating')).toHaveText(new RegExp(`^${want}`));
  await expect(keptLine(page)).toBeVisible();

  const sent = changesSent(page);
  await context.setOffline(false);
  await expect(banner(page)).toBeHidden({ timeout: 15_000 });
  const rating = want === 'Fine' ? 'fine' : 'loved';
  await expect.poll(async () => (await (await page.request.get('/api/outfits/worn')).json()).outfits[0].rating).toBe(rating);
  await onceToNines(sent, `PUT /api/outfits/worn/${id}/rating`);
  await expect(page.getByTestId('worn-outfit').first().getByTestId('worn-rating')).toHaveText(new RegExp(`^${want}`));
});

test("a packing tick while Nines can't be reached: ticked at once, still after a reload, sent once; a refusal is said", async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const day = localDay(8);
  const made = await page.request.post('/api/trips', {
    data: { place: PLACE, first_day: day, last_day: localDay(9), weather: [day, localDay(9)].map((date) => ({ date, low_c: 13, high_c: 21, rain: false })) },
  });
  const trip = await made.json();
  try {
    await serviceWorkerInCharge(page);
    await page.goto(`/trips/${trip.id}`);
    const ticks = page.getByRole('checkbox', { name: /^Packed:/ });
    await expect(ticks.first()).toBeVisible();
    await page.waitForLoadState('networkidle');

    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
    await expect(page.getByText('You can tick what you pack; changing the trip waits')).toBeVisible();
    const plan = page.getByRole('region', { name: 'Change the trip' }).getByRole('button', { name: 'Plan again' });
    await expect(plan).toBeDisabled();
    await expect(plan).toHaveAttribute('title', /needs Nines on your computer/i);
    await ticks.nth(0).check();
    await ticks.nth(1).check();
    await ticks.nth(1).uncheck();   // taken back before it was sent: it never goes
    await expect(ticks.nth(0)).toBeChecked();
    await expect(page.getByTestId('trip-progress')).toContainText('1 of');
    await expect(keptLine(page)).toBeVisible();

    await page.reload();
    await expect(page.getByRole('checkbox', { name: /^Packed:/ }).nth(0)).toBeChecked();
    await expect(page.getByRole('checkbox', { name: /^Packed:/ }).nth(1)).not.toBeChecked();

    const sent = changesSent(page);
    await context.setOffline(false);
    await expect(banner(page)).toBeHidden({ timeout: 15_000 });
    await expect.poll(async () => (await (await page.request.get(`/api/trips/${trip.id}`)).json()).packed).toEqual([trip.lines[0]]);
    await onceToNines(sent, `PATCH /api/trips/${trip.id}`);

    // a tick Nines refuses later: the trip was deleted meanwhile (the tick itself finds Nines out of reach)
    await context.setOffline(true);
    const name = (await ticks.nth(2).getAttribute('aria-label'))!.replace(/^Packed: /, '');
    await ticks.nth(2).check();
    await expect(keptLine(page)).toBeVisible();
    await page.request.delete(`/api/trips/${trip.id}`);
    await context.setOffline(false);
    await expect(page.getByText(new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} was not ticked as packed for Harbour Town\\.`))).toBeVisible({ timeout: 15_000 });
    await expect(banner(page)).toBeHidden();
  } finally {
    await page.request.delete(`/api/trips/${trip.id}`).catch(() => undefined);
  }
});
