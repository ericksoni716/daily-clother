import type { Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { danglingDots, expect, goToCloset, hitArea, test, useProfile } from './fixtures';

// A trip covers today, on a phone: a saved trip whose days hold today moves Today to its place by itself. The line
// over the outfits names the day of the trip and leads to it, the trip's own outfit is first, a piece's choices come
// from the bag, "I'm wearing this" records the wear, "Not on this trip today" (behind Change) goes home for the day and
// Undo comes back; and the first screen still holds five pieces and the button on the smallest phone.

const PHONE = { width: 375, height: 740 };
const PLACE = { name: 'Lisbon, Portugal', latitude: 38.7167, longitude: -9.1333, timezone: 'Europe/Lisbon' };

function localDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

interface SavedTrip { id: string; plan: { days: { date: string; outfit: { pieces: Record<string, string | string[] | null> } | null }[] } }

let trip: SavedTrip | null = null;

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  if (trip) await page.request.delete(`/api/trips/${trip.id}`);
  trip = null;
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** The demo closet, with a four-day trip to Lisbon that starts today (its weather given: the tests reach no forecast). */
async function onATrip(page: Page): Promise<SavedTrip> {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.request.delete(`/api/plans/${localDay(3)}`);   // the demo's plan three days ahead
  const weather = [0, 1, 2, 3].map((i) => ({ date: localDay(i), low_c: 14, high_c: 20, rain: false }));
  const r = await page.request.post('/api/trips', { data: { place: PLACE, first_day: localDay(0), last_day: localDay(3), weather } });
  expect(r.ok()).toBeTruthy();
  trip = (await r.json()) as SavedTrip;
  return trip;
}

const current = (page: Page) => page.getByTestId('current-outfit');
const tripLine = (page: Page) => page.getByTestId('trip-line');

async function shownIds(page: Page): Promise<string[]> {
  const hrefs = await current(page).getByTestId('piece').evaluateAll((els) => els.map((el) => el.getAttribute('href') ?? ''));
  return hrefs.map((h) => decodeURIComponent(h.split('/').pop() ?? '')).sort();
}

function idsOf(pieces: Record<string, string | string[] | null>): string[] {
  return Object.values(pieces).flat().filter((v): v is string => !!v).sort();
}

test('a trip covers today: its place, its outfit first, the bag only, a wear, and "Not on this trip today" with Undo', async ({ page }) => {
  const saved = await onATrip(page);
  await page.goto('/today');
  await expect(tripLine(page)).toHaveText('Day 1 of 4 of your trip to Lisbon.');
  await expect(page.getByTestId('day-line')).toContainText('Lisbon');
  await expect(page.getByTestId('no-weather')).toHaveCount(0);   // the trip's own weather stands
  // the trip's own outfit for today first, saying so under its button
  const planned = saved.plan.days[0].outfit!;
  await expect.poll(() => shownIds(page)).toEqual(idsOf(planned.pieces));
  await expect(current(page).getByTestId('plan-swapped')).toHaveText('Your trip planned this outfit for today.');
  // the line leads to the trip, where today is marked; the row about packing is not said twice
  await expect(page.getByTestId('today-trip')).toHaveCount(0);
  expect(await axeViolations(page)).toEqual([]);
  await tripLine(page).getByRole('link').click();
  await expect(page).toHaveURL(new RegExp(`/trips/${saved.id}$`));
  await expect(page.getByTestId('trip-today')).toHaveCount(1);
  await page.goBack();
  await expect(tripLine(page)).toBeVisible();

  // a piece's choices: another piece comes from what you packed
  const name = (await current(page).locator('.today-piece-name').first().textContent())!.trim();
  await current(page).getByRole('button', { name: `Choices for ${name}` }).click();
  const sheet = page.getByRole('dialog', { name });
  await expect(sheet.getByTestId('trip-piece-hint')).toHaveText('Another piece comes from what you packed.');
  await page.screenshot({ path: test.info().outputPath('trip-piece-choices.png') });
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);

  // "I'm wearing this" records the wear as at home
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(current(page).getByTestId('worn-today')).toBeVisible();
  const worn = (await (await page.request.get('/api/outfits/worn?limit=1')).json()).outfits as { worn_on: string; pieces: Record<string, string | string[] | null> }[];
  expect(worn[0].worn_on).toBe(localDay(0));
  expect(idsOf(worn[0].pieces)).toEqual(idsOf(planned.pieces));
  await current(page).getByRole('button', { name: 'Undo' }).click();
  await expect(current(page).getByTestId('worn-today')).toHaveCount(0);

  // the way home for the day, behind Change; the outfit holds its place under the line (the weather over it is home's
  // then, and may take another number of lines)
  const offset = async () => (await current(page).boundingBox())!.y - (await tripLine(page).boundingBox())!.y;
  const before = await offset();
  await page.getByTestId('day-line').getByRole('button', { name: 'Change' }).click();
  const where = page.getByRole('dialog', { name: 'Where you are' });
  await expect(where.getByTestId('trip-aside')).toContainText("You're on your trip to Lisbon, so Today dresses you there from what you packed.");
  // the place saved is home's, and changing it is said to change home, not the trip
  await expect(where.getByText('At home:')).toBeVisible();
  await expect(where.getByLabel('Change where home is')).toBeVisible();
  await where.getByRole('button', { name: 'Not on this trip today' }).click();
  await expect(where).toHaveCount(0);
  await expect(tripLine(page)).toHaveText("You're not on your trip today. Undo");
  await expect(page.getByTestId('day-line')).not.toContainText('Lisbon');
  await expect(current(page).getByTestId('plan-swapped')).toHaveCount(0);
  await expect.poll(offset).toBe(before);
  await page.screenshot({ path: test.info().outputPath('trip-set-aside.png') });
  // kept on the server for the day: a reload says the same
  await page.reload();
  await expect(tripLine(page)).toHaveText("You're not on your trip today. Undo");
  await tripLine(page).getByRole('button', { name: 'Undo' }).click();
  await expect(tripLine(page)).toHaveText('Day 1 of 4 of your trip to Lisbon.');
  await expect.poll(() => shownIds(page)).toEqual(idsOf(planned.pieces));
  expect(await axeViolations(page)).toEqual([]);
});

test('a trip day opens with one ask, for the trip\'s occasion, when this device kept another', async ({ page }) => {
  const saved = await onATrip(page);
  // this device last chose Smart casual; the trip's day is casual
  await page.evaluate(() => localStorage.setItem('closet-today-choice', JSON.stringify({ occasion: 'smart_casual', mood: 'usual' })));
  const asked: Record<string, unknown>[] = [];
  page.on('request', (r) => {
    if (r.url().endsWith('/api/outfits/today') && r.method() === 'POST') asked.push(r.postDataJSON() as Record<string, unknown>);
  });
  await page.goto('/today');
  await expect(tripLine(page)).toBeVisible();
  const planned = saved.plan.days[0].outfit!;
  await expect.poll(() => shownIds(page)).toEqual(idsOf(planned.pieces));
  const occasions = page.getByRole('group', { name: 'Occasion' });
  await expect(occasions.getByRole('button', { name: 'Casual', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(occasions.getByRole('button', { name: 'Smart casual' })).toHaveAttribute('aria-pressed', 'false');
  // the page holds still: nothing more is asked, so the outfits are never replaced
  await page.waitForLoadState('networkidle');
  expect(asked).toHaveLength(1);
  expect(asked[0]).toMatchObject({ occasion: 'smart_casual', occasion_kept: true });
  // the kept choice on this device is not changed; a tap is the owner's own and is sent as such
  expect(await page.evaluate(() => localStorage.getItem('closet-today-choice'))).toContain('smart_casual');
  await occasions.getByRole('button', { name: 'Smart casual' }).click();
  await expect.poll(() => asked.length).toBe(2);
  expect(asked[1].occasion).toBe('smart_casual');
  expect(asked[1].occasion_kept).toBeUndefined();
  await expect(occasions.getByRole('button', { name: 'Smart casual' })).toHaveAttribute('aria-pressed', 'true');
  await expect(current(page).getByTestId('plan-swapped')).toHaveCount(0);
});

for (const width of [375, 320]) {
  test(`a trip day on the smallest phone, ${width} wide: the trip's line is one line, and five pieces and the button are on the first screen`, async ({ page }) => {
    // as Today's own first screen (10-today.spec.ts): the phone check's smallest phone, an iPhone 13 mini with Safari's
    // bars, and the first iPhone SE's width; a mild day's weather in one line, and only outfits of five pieces
    await onATrip(page);
    await page.setViewportSize({ width, height: 629 });
    await page.route('**/api/outfits/today', async (route: Route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const response = await route.fetch({ postData: { ...body, low_c: 14, high_c: 20, rain: false } });
      const json = await response.json();
      if (response.ok()) {
        json.outfits = json.outfits.filter((o: { pieces: Record<string, unknown> }) => Object.values(o.pieces).flat().filter(Boolean).length === 5);
      }
      await route.fulfill({ response, json });
    });
    await page.goto('/today');
    await expect(tripLine(page)).toBeVisible();
    await expect(current(page).getByTestId('piece')).toHaveCount(5);
    const lines = await tripLine(page).evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
    expect(lines).toBeLessThan(1.5);
    await page.screenshot({ path: test.info().outputPath(`trip-first-screen-${width}.png`) });
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
    expect(wear.y + wear.height).toBeLessThanOrEqual(tabbar.y);
    for (const piece of await current(page).getByTestId('piece').all()) {
      const b = (await piece.boundingBox())!;
      expect(b.y + b.height).toBeLessThanOrEqual(wear.y);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}


test('findings 14, 18 and 25: on a trip day the foot line is gone, the trip line takes 44px, and the weather line leaves no dot at a line\'s end', async ({ page }) => {
  await onATrip(page);
  await page.goto('/today');
  await expect(tripLine(page)).toHaveText('Day 1 of 4 of your trip to Lisbon.');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(page.getByTestId('recent-outfits')).toBeVisible();
  await expect(page.locator('.today-more')).toHaveCount(0);
  expect((await hitArea(tripLine(page).getByRole('link'))).height).toBeGreaterThanOrEqual(44);
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await danglingDots(page)).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('trip-day.png') });
});
