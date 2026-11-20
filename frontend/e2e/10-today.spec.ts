import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

const BROOKLYN = 'Brooklyn, New York, United States';

test.afterEach(async ({ page, context }) => {
  // every tab the test opened, not only `page`: a faked request still in flight fails once its tab closes, and the
  // error lands in the next test. Nothing reads those late answers, so their errors are ignored.
  for (const tab of context.pages()) await tab.unrouteAll({ behavior: 'ignoreErrors' });
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
  // a swipe or a dot reaches the other outfits (the arrows are gone): each dot is a 44px target
  const dots = page.getByRole('group', { name: 'Choose an outfit' }).getByRole('button');
  expect(await dots.count()).toBeGreaterThan(1);
  for (const dot of await dots.all()) {
    const b = (await dot.boundingBox())!;
    expect(b.width).toBeGreaterThanOrEqual(44);
    expect(b.height).toBeGreaterThanOrEqual(44);
  }
  await expect(page.getByRole('button', { name: 'Next outfit' })).toHaveCount(0);

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


test('today on a phone on a Wednesday: the longest day name still fits on one line, so the outfit is not pushed down', async ({ page }) => {
  // found on Wednesday 18 November: "Wednesday 18 Nov" wrapped beside Worn and Trips and pushed "I'm wearing this"
  // under the tab bar. The page's clock is set to a Wednesday so this is checked on every day of the week.
  await page.clock.setFixedTime(new Date(2026, 10, 25, 10, 0, 0));
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const date = page.locator('.today-header .count');
  await expect(date).toContainText('Wed 25 Nov');
  const lines = await date.evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
  expect(lines).toBeLessThan(1.5);
  const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
  expect(wear.y + wear.height).toBeLessThanOrEqual((await page.locator('nav.tabbar').boundingBox())!.y);
  // a computer has the room for the whole name
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.locator('.today-header .count .date-long')).toBeVisible();
  await expect(page.locator('.today-header .count .date-long')).toHaveText('Wednesday 25 Nov');
});

test('today refreshes suggestions when a piece is put in the laundry', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const asked = await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const [id] = await pieceIds(page);
  const before = asked.length;

  try {
    await current(page).getByTestId('piece').first().click();
    await page.getByRole('button', { name: 'Put in the laundry' }).click();
    await expect(page.getByTestId('laundry-state')).toHaveText(/^In the laundry/);
    await page.getByRole('link', { name: 'Today', exact: true }).first().click();
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect(page.locator(`.today-track a[data-testid="piece"][href$="/${id}"]`)).toHaveCount(0);
    expect(asked.length).toBeGreaterThan(before);
  } finally {
    await page.request.post(`/api/items/${id}/laundry`, { data: { state: 'clean' } });
  }
});


test('today reports an offline error even when the item list cannot load', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL, serviceWorkers: 'block' });
  const page = await context.newPage();
  try {
    await login(page);
    await page.evaluate(() => localStorage.removeItem('closet-today-saved:outfits:main'));
    await page.route('**/api/items?*', (route) => route.abort());
    await page.route('**/api/outfits/today', (route) => route.abort());
    await page.goto('/today');
    await expect(page.getByText("You're offline, and no outfits were saved on this device today.", { exact: false })).toBeVisible();
    await expect(page.locator('.today-loading')).toHaveCount(0);
  } finally {
    await context.close();
  }
});


test('today kept open overnight does not undo yesterday when wearing another outfit', async ({ page }) => {
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  await page.clock.setFixedTime(yesterday);
  const asked = await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('closet-today-saved:outfits:demo')!));
  const outfit = saved.answer.outfits[0];
  const ids = await pieceIds(page);
  const recorded = await (await page.request.post('/api/wears', {
    data: { item_ids: ids, worn_on: saved.day, outfit: { pieces: outfit.pieces } },
  })).json();
  let nextId: string | undefined;
  try {
    await page.evaluate(({ saved, outfit, ids, recorded }) => {
      localStorage.setItem('closet-today-saved:worn:demo', JSON.stringify({
        day: saved.day, worn_on: recorded.worn_on, ids, recorded: recorded.recorded, outfit, outfit_id: recorded.outfit.id,
      }));
    }, { saved, outfit, ids, recorded });
    await page.reload();
    await expect(page.getByText(/^You're wearing this today/).first()).toBeVisible();

    await page.clock.setFixedTime(now);
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByText(/^You're wearing this today/)).toHaveCount(0);
    await page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Business' }).click();
    await expect.poll(() => asked.at(-1)?.occasion).toBe('business');
    await expect.poll(() => pieceIds(page)).not.toEqual(ids);
    const wearing = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
    await current(page).getByRole('button', { name: /I'm wearing this|Wear this instead/ }).click();
    nextId = (await (await wearing).json()).outfit.id;
    const history = await (await page.request.get('/api/outfits/worn')).json();
    expect(history.outfits.map((o: { id: string }) => o.id)).toContain(recorded.outfit.id);
  } finally {
    if (nextId) await page.request.delete(`/api/outfits/worn/${nextId}`);
    await page.request.delete(`/api/outfits/worn/${recorded.outfit.id}`);
  }
});


test('a wear response arriving after midnight keeps the day it was started', async ({ page }) => {
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  await page.clock.setFixedTime(yesterday);
  await fakeWeather(page);
  // the demo closet has an outfit worn yesterday, which Today would show as already worn on that day; this test is
  // about a wear of its own crossing midnight, so it starts from no outfit worn
  await page.route('**/api/outfits/worn?*', (route) =>
    route.request().method() === 'GET' ? route.fulfill({ json: { outfits: [], next: null } }) : route.fallback());
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const day = await page.evaluate(() => JSON.parse(localStorage.getItem('closet-today-saved:outfits:demo')!).day);
  let outfitId: string | undefined;
  await page.route('**/api/wears', async (route) => {
    const response = await route.fetch({ postData: { ...route.request().postDataJSON(), worn_on: day } });
    outfitId = (await response.json()).outfit.id;
    await page.clock.setFixedTime(now);
    await route.fulfill({ response });
  });
  try {
    await current(page).getByRole('button', { name: "I'm wearing this" }).click();
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('closet-today-saved:worn:demo') ?? 'null')?.day)).toBe(day);
  } finally {
    if (outfitId) await page.request.delete(`/api/outfits/worn/${outfitId}`);
  }
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
  await page.getByRole('button', { name: 'Change', exact: true }).click();
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

  await page.getByRole('button', { name: 'Change', exact: true }).click();
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
  // the new tab asked for today's outfits: let that answer arrive and its faked route finish before the test ends
  await expect(current(fresh).getByTestId('piece').first()).toBeVisible();
  await fresh.unrouteAll({ behavior: 'wait' });
});
