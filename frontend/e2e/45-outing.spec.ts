import type { Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test, useProfile } from './fixtures';

// Give it an outing, on a phone: Today's last outfit is built around a piece you like and have not worn in a while,
// with one sentence saying so; the first screen still holds the best outfit and its button; wearing it records the
// wear; "Not this piece" takes it away for the day, a reload included. The demo closet's plaid flannel shirt (rated
// like) is made the neglected piece: its wears are taken away and one is put forty days back. The tests share one
// backend and build on each other, in order.

const SMALLEST = { width: 375, height: 629 };   // the smallest phone, as Today's first-screen test
const PHONE = { width: 375, height: 812 };      // taller, so a button low on the last outfit is not under the tab bar
const SHIRT = 'Plaid flannel shirt';

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

function localDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** A mild, dry day from the forecast (the browser tests never ask the weather service). */
async function mildDay(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { ...body, low_c: 14, high_c: 20, rain: false } });
    const json = await response.json();
    if (response.ok()) Object.assign(json.context, { source: 'forecast', place: 'Brooklyn, New York, United States', rain_chance: 10, old: false, message: null });
    await route.fulfill({ response, json });
  });
}

async function shirtId(page: Page): Promise<string> {
  const items = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  return items.find((i) => i.name === SHIRT)!.id;
}

async function openToday(page: Page, size = PHONE) {
  await page.setViewportSize(size);
  // the dots jump straight to an outfit: a smooth scroll still under way moves which outfit is in front as it goes
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await mildDay(page);
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
}

const current = (page: Page) => page.getByTestId('current-outfit');
const outingLine = (page: Page) => page.getByTestId('outing-line');
const dots = (page: Page) => page.getByRole('group', { name: 'Choose an outfit' }).getByRole('button');

test('an outing: the last outfit is built around a piece not worn in a while, says so, and the first screen holds', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const id = await shirtId(page);
  for (const w of (await (await page.request.get(`/api/items/${id}/wears`)).json()).wears as { worn_on: string }[]) {
    expect((await page.request.delete(`/api/items/${id}/wears/${w.worn_on}`)).ok()).toBe(true);
  }
  expect((await page.request.post(`/api/items/${id}/wears`, { data: { worn_on: localDay(-40) } })).ok()).toBe(true);

  await openToday(page, SMALLEST);
  // the first screen: the best outfit and its button above the tab bar, and no sentence about an outing on it
  const wear = current(page).getByRole('button', { name: "I'm wearing this" });
  await expect(wear).toBeVisible();
  const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
  const button = (await wear.boundingBox())!;
  expect(button.y + button.height).toBeLessThanOrEqual(tabbar.y);
  await expect(current(page).getByTestId('outing-line')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('outing-first-screen.png') });

  // the last outfit is the outing, its piece among its pieces, with one sentence under its button
  const count = await dots(page).count();
  expect(count).toBe(3);
  await dots(page).nth(count - 1).click();
  await expect(current(page).locator('.today-piece-name', { hasText: SHIRT })).toBeVisible();
  const d = new Date(localDay(-40) + 'T12:00:00');
  const month = d.toLocaleString('en-GB', { month: 'short' }).slice(0, 3);
  const year = d.getFullYear() === new Date().getFullYear() ? '' : ` ${d.getFullYear()}`;
  await expect(current(page).getByTestId('outing-line'))
    .toHaveText(`An outing for your plaid flannel shirt: you like it and have not worn it since ${d.getDate()} ${month}${year}.`);
  await expect(outingLine(page)).toHaveCount(1);   // once, on the outing alone
  await current(page).getByTestId('outing-line').scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath('outing-last-outfit.png') });
  expect(await axeViolations(page)).toEqual([]);

  // a reload offers the same outing
  await page.reload();
  await dots(page).nth(2).click();
  await expect(current(page).getByTestId('outing-line')).toContainText('plaid flannel shirt');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('an outing: wearing it records the wear like any outfit', async ({ page }) => {
  await openToday(page);
  await dots(page).nth(2).click();
  await expect(current(page).getByTestId('outing-line')).toBeVisible();
  const id = await shirtId(page);
  const wore = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  const day = (await (await wore).json()).worn_on as string;
  await expect(current(page).getByTestId('worn-today')).toHaveText("You're wearing this today");
  const shirt = await (await page.request.get(`/api/items/${id}`)).json();
  expect(shirt.last_worn).toBe(day);
  // taken back, for the next test: the shirt is out of the laundry again and the outing back in its place
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText(/^You're wearing this today/)).toHaveCount(0);
  await expect.poll(async () => (await (await page.request.get(`/api/items/${id}`)).json()).last_worn).not.toBe(day);
});

test('an outing: "Not this piece" takes it away for the day, and it stays away after a reload', async ({ page }) => {
  await openToday(page);
  await dots(page).nth(2).click();
  await expect(current(page).getByTestId('outing-line')).toBeVisible();
  const answer = page.waitForResponse('**/api/outfits/today');
  await current(page).getByRole('button', { name: `Choices for ${SHIRT}` }).click();
  await page.getByRole('dialog', { name: SHIRT }).getByRole('button', { name: 'Not this piece' }).click();
  const outfits = (await (await answer).json()).outfits as { outing?: unknown }[];
  expect(outfits).toHaveLength(3);   // an ordinary outfit takes its place
  expect(outfits.some((o) => o.outing)).toBe(false);
  await expect(outingLine(page)).toHaveCount(0);

  await page.reload();
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();
  await expect(outingLine(page)).toHaveCount(0);
  // even with "Not this piece" cleared, the day's outing was turned down
  await page.getByRole('button', { name: `Without ${SHIRT}, put it back` }).click();
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();
  await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
  await expect(outingLine(page)).toHaveCount(0);
});
