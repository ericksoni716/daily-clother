import { resolve } from 'node:path';
import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

const BROOKLYN = 'Brooklyn, New York, United States';
const SHOTS = resolve(import.meta.dirname, '..', '..', 'docs', 'screenshots');

test.afterEach(async ({ page, context }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await context.setOffline(false);
  await page.request.put('/api/settings', { data: { place: null } });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/**
 * The weather is faked here: Open-Meteo is never called from a test. Today's outfits are asked of the real server
 * with a cold, rainy day filled in (unless the test typed its own), and the answer says it came from the forecast for
 * Brooklyn, as it would with a saved place.
 */
async function fakeWeather(page: Page, asked: Record<string, unknown>[] = []) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    asked.push(body);
    const typed = body.low_c !== undefined;
    const response = await route.fetch({ postData: typed ? body : { ...body, low_c: 3.2, high_c: 9.8, rain: true } });
    const json = await response.json();
    if (response.ok() && !typed) {
      Object.assign(json.context, { source: 'forecast', place: BROOKLYN, rain_chance: 70, summary: 'rain', old: false, message: null });
    }
    await route.fulfill({ response, json });
  });
  return asked;
}

async function openToday(page: Page) {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
}

const current = (page: Page) => page.getByTestId('current-outfit');
const pieceNames = (page: Page) => current(page).locator('.today-piece-name').allTextContents();
const pieceIds = async (page: Page) =>
  (await current(page).getByTestId('piece').evaluateAll((links) => links.map((a) => a.getAttribute('href')))).map((h) => h!.split('/').pop()!);

test('today: the day, an outfit with its reasons, and the occasion changes the outfits', async ({ page }) => {
  const asked = await fakeWeather(page);
  await openToday(page);

  const day = page.getByTestId('day-line');
  await expect(day).toContainText('Brooklyn');
  await expect(day).toContainText('3–10°C');
  await expect(day).toContainText('rain 70%');
  await expect(page.getByTestId('no-weather')).toHaveCount(0);

  const outfit = current(page);
  await expect(outfit.getByTestId('piece').first()).toBeVisible();
  expect((await outfit.getByRole('list', { name: 'Why this works' }).getByRole('listitem').count())).toBeGreaterThan(1);
  // the rain warning is set apart from the reasons
  await expect(outfit.getByRole('note', { name: 'Be aware' }).getByText(/umbrella|rain/i).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: /Best for today/ })).toBeVisible();
  const casual = await pieceNames(page);
  expect(casual.length).toBeGreaterThanOrEqual(3);

  // pieces in the order they are put on
  const places = await outfit.locator('.today-piece-place').allTextContents();
  const order = ['Outer layer', 'Mid layer', 'Top', 'Bottom', 'Shoes', 'Extra'];
  expect(places.map((p) => order.indexOf(p))).toEqual([...places.map((p) => order.indexOf(p))].sort((a, b) => a - b));

  // a different occasion asks again and gives different clothes
  const occasion = page.getByRole('group', { name: 'Occasion' });
  await occasion.getByRole('button', { name: 'Business' }).click();
  await expect(occasion.getByRole('button', { name: 'Business' })).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => asked.at(-1)?.occasion).toBe('business');
  await expect.poll(() => pieceNames(page)).not.toEqual(casual);

  // remembered on this device
  await page.reload();
  await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Business' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('group', { name: 'Mood' }).getByRole('button', { name: 'Sharp' }).click();
  await expect.poll(() => asked.at(-1)).toMatchObject({ occasion: 'business', mood: 'sharp' });
});

test("today: \"I'm wearing this\" records a wear for every piece, and undo removes them", async ({ page }) => {
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const ids = await pieceIds(page);

  const lastWorn = async () => {
    const items = (await (await page.request.get('/api/items?status=active')).json()).items as { id: string; last_worn: string | null }[];
    return ids.map((id) => items.find((i) => i.id === id)!.last_worn);
  };
  const before = await lastWorn();

  const wore = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  const day = (await (await wore).json()).worn_on as string;
  await expect(current(page).getByTestId('worn-today')).toHaveText("You're wearing this today");
  expect(await lastWorn()).toEqual(ids.map(() => day));

  // still said after coming back to the screen later the same day (the outfits may have changed now these are worn)
  await page.reload();
  await expect(page.getByText(/^You're wearing this today/).first()).toBeVisible();

  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText(/^You're wearing this today/)).toHaveCount(0);
  await expect.poll(lastWorn).toEqual(before);
});

test('today: "Not this piece" leaves it out, "Start from this piece" builds around it, and both clear', async ({ page }) => {
  const asked = await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const [first] = await pieceIds(page);
  const [name] = await pieceNames(page);

  const answer = page.waitForResponse('**/api/outfits/today');
  await current(page).getByRole('button', { name: `Choices for ${name}` }).click();
  await current(page).getByRole('button', { name: 'Not this piece' }).click();
  const outfits = (await (await answer).json()).outfits as { pieces: Record<string, unknown> }[];
  expect(asked.at(-1)?.leave_out).toEqual([first]);
  expect(outfits.length).toBeGreaterThan(0);
  for (const o of outfits) expect(JSON.stringify(o.pieces)).not.toContain(first);
  await expect.poll(() => pieceIds(page)).not.toContain(first);
  const putBack = page.getByRole('button', { name: `Put back ${name}` });
  await expect(putBack).toBeVisible();

  // build around another piece
  const [, second] = await pieceIds(page);
  const [, secondName] = await pieceNames(page);
  await current(page).getByRole('button', { name: `Choices for ${secondName}` }).click();
  await current(page).getByRole('button', { name: 'Start from this piece' }).click();
  await expect.poll(() => asked.at(-1)).toMatchObject({ build_around: second, leave_out: [first] });
  await expect(page.getByRole('button', { name: `Stop building around ${secondName}` })).toBeVisible();
  await expect(current(page).locator('.today-piece.is-base')).toContainText(secondName);

  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect.poll(() => asked.at(-1)).toEqual({ occasion: 'casual', mood: 'usual' });
  await expect(putBack).toHaveCount(0);
});

test('today on a phone: swipe to another outfit, open a piece, and come back to the same outfit', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeWeather(page);
  await openToday(page);
  await expect(page.locator('nav.tabbar').getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();

  // the outfit leads: its pieces are big enough to see and "I'm wearing this" is on the first screen, above the tab bar
  const wear = current(page).getByRole('button', { name: "I'm wearing this" });
  const box = (await wear.boundingBox())!;
  const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(tabbar.y);
  expect(box.width).toBeGreaterThan(300);
  for (const w of await current(page).locator('.today-piece-card').evaluateAll((cards) => cards.map((c) => c.getBoundingClientRect().width))) {
    expect(w).toBeGreaterThanOrEqual(100);
  }
  for (const name of ['Previous outfit', 'Next outfit']) {
    const arrow = (await page.getByRole('button', { name }).boundingBox())!;
    expect(arrow.width).toBeGreaterThanOrEqual(44);
    expect(arrow.height).toBeGreaterThanOrEqual(44);
  }

  // swipe (a sideways scroll of the outfits)
  await page.locator('.today-track').evaluate((el) => el.scrollTo({ left: el.clientWidth, behavior: 'instant' }));
  await expect(page.getByRole('heading', { name: /2 of/ })).toBeVisible();
  const names = await pieceNames(page);

  await current(page).getByTestId('piece').first().click();
  await expect(page).toHaveURL(/\/today\/item\//);
  await expect(page.locator('#today-title')).toHaveCount(0);
  await page.getByRole('link', { name: 'Today' }).first().click();
  await expect(page.getByRole('heading', { name: /2 of/ })).toBeVisible();
  expect(await pieceNames(page)).toEqual(names);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('today when the forecast cannot be fetched: an outfit for a mild day, a notice, and typed temperatures behind it', async ({ page }) => {
  // no faked weather: the test backend never reaches the weather service, so the forecast for New York fails
  await openToday(page);
  const notice = page.getByTestId('no-weather');
  await expect(notice).toContainText('The weather could not be fetched');
  await expect(page.getByTestId('day-line')).toContainText('a mild day');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();

  const retried = page.waitForResponse('**/api/outfits/today');
  await notice.getByRole('button', { name: 'Try again' }).click();
  await retried;
  await expect(notice).toBeVisible();

  await notice.getByRole('button', { name: 'Type temperatures' }).click();
  const panel = page.getByRole('region', { name: 'Where are you?' });
  await expect(panel.getByText('Using: New York, United States')).toBeVisible();
  await panel.getByLabel('Low °C').fill('18');
  await panel.getByLabel('High °C').fill('26');
  await panel.getByRole('button', { name: 'Dress me for this' }).click();
  const day = page.getByTestId('day-line');
  await expect(day).toContainText('your temperatures');
  await expect(day).toContainText('18–26°C');
  await expect(day).toContainText('no rain');
  await expect(page.getByTestId('no-weather')).toHaveCount(0);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();

  // "Use the forecast again" goes back to the forecast (still the mild day here)
  await page.getByRole('button', { name: 'Change' }).click();
  await panel.getByRole('button', { name: 'Use the forecast again' }).click();
  await expect(page.getByTestId('day-line')).toContainText('a mild day');
});

test('today: "Use my location" asks the browser only on a tap and saves the place it names', async ({ page, context }) => {
  await context.grantPermissions(['geolocation']);
  await context.setGeolocation({ latitude: 40.6782, longitude: -73.9442 });
  const near: string[] = [];
  await page.route('**/api/places/near*', async (route) => {
    near.push(route.request().url());
    await route.fulfill({ json: { place: { name: BROOKLYN, latitude: 40.68, longitude: -73.94, timezone: 'America/New_York' } } });
  });
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  expect(near).toEqual([]);

  await page.getByRole('button', { name: 'Change' }).click();
  await page.getByRole('button', { name: 'Use my location' }).click();
  await expect(page.getByText(`Saved: ${BROOKLYN}`).first()).toBeVisible();
  expect(near).toHaveLength(1);
  expect(near[0]).toContain('latitude=40.6782');
  const settings = await (await page.request.get('/api/settings')).json();
  expect(settings.place.name).toBe(BROOKLYN);
});

test('today offline: the outfits fetched earlier are shown as saved, and the buttons say why they are off', async ({ page, context }) => {
  await fakeWeather(page);
  await openToday(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.reload();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const names = await pieceNames(page);
  await page.waitForLoadState('networkidle');

  // the faked weather is answered outside the browser, so stop faking it to let the request fail like the others
  await page.unroute('**/api/outfits/today');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  expect(await pieceNames(page)).toEqual(names);
  const wear = current(page).getByRole('button', { name: "I'm wearing this" });
  await expect(wear).toBeDisabled();
  await expect(wear).toHaveAttribute('title', /needs Closet on your computer/i);
  await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Formal' })).toBeDisabled();
});

test("today in a closet that can't dress the owner yet: says what is needed, what to add first, and a link to add", async ({ page }) => {
  await fakeWeather(page);
  await login(page);
  await page.goto('/today');
  const empty = page.getByTestId('today-empty');
  await expect(empty).toContainText('Add a top, something for your legs and shoes, and Today can dress you');
  await expect(page.getByTestId('add-first')).toContainText('Still to add:');
  await expect(empty.getByRole('link', { name: 'Add clothes' })).toHaveAttribute('href', '/add');
  // nothing to dress, so no weather or occasion either
  await expect(page.getByTestId('day-line')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Occasion' })).toHaveCount(0);
});

test('the app opens on Today once the closet can dress the owner', async ({ page, context }) => {
  await fakeWeather(page);
  await login(page);
  await useProfile(page, 'demo');
  // tapping Closet stays on the closet in the same tab
  await page.locator('nav.sidebar').getByRole('link', { name: 'Closet' }).click();
  await expect(page.locator('#closet-title')).toBeVisible();

  const fresh = await context.newPage();
  await fakeWeather(fresh);
  await fresh.goto('/');
  await expect(fresh.locator('#today-title')).toBeVisible();
  await expect(fresh).toHaveURL(/\/today$/);
  await expect(fresh.locator('nav.sidebar').getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page');
});

for (const [label, viewport] of [['phone', { width: 390, height: 844 }], ['computer', { width: 1280, height: 800 }]] as const) {
  test(`screenshot of Today on a ${label} (${viewport.width}×${viewport.height})`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await fakeWeather(page);
    await openToday(page);
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect.poll(() => current(page).locator('img').evaluateAll((imgs) => imgs.every((i) => (i as HTMLImageElement).complete))).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    const path = resolve(SHOTS, `today-${label}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`Today on a ${label}`, { path, contentType: 'image/png' });
  });
}
