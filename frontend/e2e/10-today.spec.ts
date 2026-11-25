import type { Locator, Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { danglingDots, expect, goToCloset, hitArea, serviceWorkerInCharge, stayOnCloset, test, useProfile } from './fixtures';
import { startBackend, type Backend } from './server';

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
  await goToCloset(page);
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

test('today: "Not this piece" leaves it out, "Build around this piece" builds around it, and both clear', async ({ page }) => {
  const asked = await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const [first] = await pieceIds(page);
  const [name] = await pieceNames(page);

  const answer = page.waitForResponse('**/api/outfits/today');
  // a piece's choices open in a sheet over the page, named for the piece
  await current(page).getByRole('button', { name: `Choices for ${name}` }).click();
  await page.getByRole('dialog', { name }).getByRole('button', { name: 'Not this piece' }).click();
  const outfits = (await (await answer).json()).outfits as { pieces: Record<string, unknown> }[];
  expect(asked.at(-1)?.leave_out).toEqual([first]);
  expect(outfits.length).toBeGreaterThan(0);
  for (const o of outfits) expect(JSON.stringify(o.pieces)).not.toContain(first);
  await expect.poll(() => pieceIds(page)).not.toContain(first);
  const putBack = page.getByRole('button', { name: `Without ${name}, put it back` });
  await expect(putBack).toBeVisible();

  // build around another piece
  const [, second] = await pieceIds(page);
  const [, secondName] = await pieceNames(page);
  await current(page).getByRole('button', { name: `Choices for ${secondName}` }).click();
  await page.getByRole('dialog', { name: secondName }).getByRole('button', { name: 'Build around this piece' }).click();
  await expect.poll(() => asked.at(-1)).toMatchObject({ build_around: second, leave_out: [first] });
  await expect(page.getByRole('button', { name: `Stop building around ${secondName}` })).toBeVisible();
  await expect(current(page).locator('.today-piece.is-base')).toContainText(secondName);

  // both are kept for the rest of the day, a reload included
  await page.reload();
  await expect(page.getByRole('button', { name: `Stop building around ${secondName}` })).toBeVisible();
  await expect(putBack).toBeVisible();
  await expect.poll(() => asked.at(-1)).toMatchObject({ build_around: second, leave_out: [first] });

  await page.getByRole('button', { name: 'Clear all' }).click();
  // nothing left of the changes; the occasion is still the one this device kept, not tapped today (`occasion_kept`)
  await expect.poll(() => asked.at(-1)).toEqual({ occasion: 'casual', mood: 'usual', occasion_kept: true });
  await expect(putBack).toHaveCount(0);
  await page.reload();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(putBack).toHaveCount(0);
});

test("today: wearing an outfit built around a piece shows what you are wearing, not \"No outfit today yet\"", async ({ page }) => {
  // found in the review: a tee is washed after one wear, so the outfits asked for next were built around a piece in the
  // laundry, and Today said there was no outfit and offered Add clothes
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const names = await pieceNames(page);
  const ids = await pieceIds(page);
  const items = (await (await page.request.get('/api/items?status=active')).json()).items as { id: string; category: string }[];
  const top = ids.findIndex((id) => ['tee', 'shirt', 'polo'].includes(items.find((i) => i.id === id)!.category));
  expect(top).toBeGreaterThanOrEqual(0);
  let worn: string | undefined;
  try {
    await current(page).getByRole('button', { name: `Choices for ${names[top]}` }).click();
    await page.getByRole('dialog', { name: names[top] }).getByRole('button', { name: 'Build around this piece' }).click();
    await expect(page.getByRole('button', { name: `Stop building around ${names[top]}` })).toBeVisible();
    await expect(current(page).locator('.today-piece.is-base')).toBeVisible();
    const wore = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
    await current(page).getByRole('button', { name: "I'm wearing this" }).click();
    worn = (await (await wore).json()).outfit.id;
    await expect(page.getByText(/^You're wearing this today/).first()).toBeVisible();
    await expect(page.getByRole('button', { name: `Stop building around ${names[top]}` })).toHaveCount(0);
    await expect(page.getByText('No outfit today yet')).toHaveCount(0);
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
  } finally {
    if (worn) await page.request.delete(`/api/outfits/worn/${worn}`);
    for (const id of ids) await page.request.post(`/api/items/${id}/laundry`, { data: { state: 'clean' } });
  }
});

test('today on a phone: swipe to another outfit, open a piece, and come back to the same outfit', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeWeather(page);
  await openToday(page);
  await expect(page.locator('nav.tabbar').getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();

  // the outfit leads: its pieces are big enough to see (four to a row) and "I'm wearing this" is on the first screen,
  // above the tab bar
  const wear = current(page).getByRole('button', { name: "I'm wearing this" });
  const box = (await wear.boundingBox())!;
  const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(tabbar.y);
  expect(box.width).toBeGreaterThan(300);
  for (const w of await current(page).locator('.today-piece-card').evaluateAll((cards) => cards.map((c) => c.getBoundingClientRect().width))) {
    expect(w).toBeGreaterThanOrEqual(72);
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


for (const weather of ['a forecast', 'no forecast']) {
  test(`today on the smallest phone, with ${weather}: five pieces and "I'm wearing this" are on the first screen`, async ({ page }) => {
    // the phone check's smallest phone (an iPhone 13 mini with Safari's bars: 375x629); before, with five pieces in Pieces
    // view, the button was under the tab bar on it, and on a 393px phone too
    await page.setViewportSize({ width: 375, height: 629 });
    // a mild day (from a forecast, or for want of one), and only its outfits of five pieces
    await page.route('**/api/outfits/today', async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const response = await route.fetch(weather === 'a forecast' ? { postData: { ...body, low_c: 14, high_c: 20, rain: false } } : undefined);
      const json = await response.json();
      if (response.ok()) {
        json.outfits = json.outfits.filter((o: { pieces: Record<string, unknown> }) => Object.values(o.pieces).flat().filter(Boolean).length === 5);
        if (weather === 'a forecast') Object.assign(json.context, { source: 'forecast', place: BROOKLYN, rain_chance: 10, old: false, message: null });
      }
      await route.fulfill({ response, json });
    });
    await openToday(page);
    await expect(current(page).getByTestId('piece')).toHaveCount(5);
    await expect(page.getByTestId('no-weather')).toHaveCount(weather === 'a forecast' ? 0 : 1);
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
    expect(wear.y + wear.height).toBeLessThanOrEqual(tabbar.y);
    for (const piece of await current(page).getByTestId('piece').all()) {
      const b = (await piece.boundingBox())!;
      expect(b.y + b.height).toBeLessThanOrEqual(wear.y);
    }
    await page.screenshot({ path: test.info().outputPath(`today-first-screen-${weather.replace(' ', '-')}.png`) });
    // a piece's choices: a sheet over the page, above the tab bar
    const name = (await current(page).locator('.today-piece-name').first().textContent())!.trim();
    await current(page).getByRole('button', { name: `Choices for ${name}` }).click();
    const sheet = page.getByRole('dialog', { name });
    const notThis = (await sheet.getByRole('button', { name: 'Not this piece' }).boundingBox())!;
    expect(notThis.y + notThis.height).toBeLessThanOrEqual(629);
    expect(await axeViolations(page)).toEqual([]);
  });
}

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


test('today reports an offline error even when the item list cannot load', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, serviceWorkers: 'block' });
  const page = await context.newPage();
  try {
    await goToCloset(page);
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
  // the first outfit asked for (the demo's outfit worn on the day the clock is set to is on a card of its own, first:
  // second review of the screens, finding 1)
  const ids = (Object.values(outfit.pieces).flat().filter(Boolean) as string[]);
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


test('today when the forecast cannot be fetched: an outfit for a mild day, one line about it, and typed temperatures behind it', async ({ page }) => {
  // no faked weather: the test backend never reaches the weather service, so the forecast for New York fails
  await openToday(page);
  const notice = page.getByTestId('no-weather');
  await expect(notice).toContainText('No forecast.');
  await expect(page.getByTestId('day-line')).toContainText('a mild day');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();

  const retried = page.waitForResponse('**/api/outfits/today');
  await notice.getByRole('button', { name: 'Try again' }).click();
  await retried;
  await expect(notice).toBeVisible();

  // one line, said once: the day line says it is a mild day, and the line beside it what to do about it
  expect((await notice.boundingBox())!.height).toBeLessThanOrEqual(48);
  await expect(page.getByText('No forecast.')).toHaveCount(1);

  // today's temperatures are typed behind Change, on the weather line (the line about no forecast has only Try again;
  // second review of the screens, the reading load)
  await expect(notice.getByRole('button')).toHaveCount(1);
  await page.getByTestId('day-line').getByRole('button', { name: 'Change', exact: true }).click();
  const panel = page.getByRole('dialog', { name: 'Where you are' });
  await expect(panel.getByRole('heading', { name: "Or type today's temperatures" })).toBeVisible();
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

  await expect(panel).toHaveCount(0);

  // "Use the forecast again" goes back to the forecast (still the mild day here); Escape closes the sheet
  const change = page.getByRole('button', { name: 'Change', exact: true });
  await change.click();
  await expect(panel).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(change).toBeFocused();
  await change.click();
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

test('today offline: the outfits fetched earlier are shown as saved, and the buttons that wait for Nines say why they are off', async ({ page, context }) => {
  await fakeWeather(page);
  await openToday(page);
  await serviceWorkerInCharge(page);
  await page.reload();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const names = await pieceNames(page);
  await page.waitForLoadState('networkidle');

  // the faked weather is answered outside the browser, so stop faking it to let the request fail like the others
  await page.unroute('**/api/outfits/today');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  // when they were saved, in a few words where Change is (the banner says offline, once: second review, finding 9)
  await expect(page.getByTestId('saved-at')).toHaveText(/^saved at \d\d:\d\d$/);
  expect(await pieceNames(page)).toEqual(names);
  // wearing is kept on this phone and sent when Nines answers (47-outbox), so it stays on; changing the outfits waits
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeEnabled();
  const keep = current(page).getByRole('button', { name: 'Keep this outfit' });
  await expect(keep).toBeDisabled();
  await expect(keep).toHaveAttribute('title', /needs Nines on your computer/i);
  await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Formal' })).toBeDisabled();
});

test("today in a closet that can't dress the owner yet: says what is needed, what to add first, and a link to add", async ({ page }) => {
  await fakeWeather(page);
  await goToCloset(page);
  await page.goto('/today');
  const empty = page.getByTestId('today-empty');
  // the headline names what is still to add, once (second review of the screens, finding 54; the unit test has a
  // closet of tops), and no day ahead is offered while no day can be dressed
  await expect(empty).toContainText('Add a top, something for your legs and a pair of shoes, and Today can dress you');
  await expect(page.getByTestId('add-first')).toHaveCount(0);
  await expect(page.getByTestId('another-day')).toHaveCount(0);
  await expect(empty.getByRole('link', { name: 'Add clothes' })).toHaveAttribute('href', '/add');
  // nothing to dress, so no weather or occasion either
  await expect(page.getByTestId('day-line')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Occasion' })).toHaveCount(0);
});

test('the app opens on Today once the closet can dress the owner', async ({ page, context }) => {
  await fakeWeather(page);
  await goToCloset(page);
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


// ------------------------------------------------------------------ the second review of the screens (24 November)

const PHONE = { width: 375, height: 667 };
const dots = (page: Page) => page.getByRole('group', { name: 'Choose an outfit' }).getByRole('button');
/** Taps outfit `i`'s dot and waits for the outfits to stop sliding (a tap on an outfit still sliding in can miss it). */
async function toOutfit(page: Page, i: number) {
  await dots(page).nth(i).click();
  await expect(current(page)).toHaveAttribute('aria-label', new RegExp(`^Outfit ${i + 1} of`));
  await expect.poll(() => page.locator('.today-track').evaluate((el, n) => Math.round(el.scrollLeft) === Math.round(n * el.clientWidth), i)).toBe(true);
}
/** Where something is on the page (not on the screen), so a scroll does not count as a move. */
const onPage = (l: Locator) => l.evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
const fiveOrMore = (json: { outfits: { pieces: Record<string, unknown> }[] }) =>
  json.outfits.filter((o) => Object.values(o.pieces).flat().filter(Boolean).length === 5);

test('finding 1: "I\'m wearing this" turns the card you tapped into what you wear, where it is, with nothing put in above', async ({ page }) => {
  await page.setViewportSize(PHONE);
  const asked = await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  // the second outfit, so that staying where it is is not the same as going back to the first
  await toOutfit(page, 1);
  const ids = await pieceIds(page);
  const button = current(page).getByRole('button', { name: "I'm wearing this" });
  const cardAt = await onPage(current(page));
  const buttonAt = await onPage(button);
  const headAt = await onPage(page.locator('.today-outfits-head'));
  let worn: string | undefined;
  try {
    const before = asked.length;
    const wore = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
    await button.click();
    worn = (await (await wore).json()).outfit.id;
    // the closet changed (wears, the laundry): the outfits are asked for again, and the card stays as it is
    await expect.poll(() => asked.length).toBeGreaterThan(before);
    await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
    await expect(current(page).getByTestId('worn-today')).toHaveText("You're wearing this today");
    expect(await pieceIds(page)).toEqual(ids);
    await expect(current(page)).toHaveAttribute('aria-label', /^Outfit 2 of/);
    expect(await onPage(page.locator('.today-outfits-head'))).toBe(headAt);
    expect(await onPage(current(page))).toBe(cardAt);
    expect(Math.abs(await onPage(current(page).getByTestId('worn-today')) - buttonAt)).toBeLessThanOrEqual(2);
    await expect(page.getByText(/^You're wearing this today:/)).toHaveCount(0);
    // the other outfits stay behind the dots, to wear instead
    await toOutfit(page, 0);
    await expect(current(page).getByRole('button', { name: 'Wear this instead' })).toBeVisible();
  } finally {
    if (worn) await page.request.delete(`/api/outfits/worn/${worn}`);
    for (const id of ids) await page.request.post(`/api/items/${id}/laundry`, { data: { state: 'clean' } });
  }
});

test('finding 8: "Not this piece" and "Build around this piece" leave the outfit and its button where they were', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const buttonAt = async () => onPage(current(page).getByRole('button', { name: "I'm wearing this" }));
  const at = await buttonAt();
  const [first] = await pieceIds(page);
  const [name] = await pieceNames(page);
  await current(page).getByRole('button', { name: `Choices for ${name}` }).click();
  await page.getByRole('dialog', { name }).getByRole('button', { name: 'Not this piece' }).click();
  await expect.poll(() => pieceIds(page)).not.toContain(first);
  await expect(page.getByRole('button', { name: `Without ${name}, put it back` })).toBeVisible();
  expect(await buttonAt()).toBe(at);
  const [, secondName] = await pieceNames(page);
  await current(page).getByRole('button', { name: `Choices for ${secondName}` }).click();
  await page.getByRole('dialog', { name: secondName }).getByRole('button', { name: 'Build around this piece' }).click();
  const stop = page.getByRole('button', { name: `Stop building around ${secondName}` });
  await expect(stop).toBeVisible();
  await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
  expect(await buttonAt()).toBe(at);
  // what was changed is said under the outfits, beside "Changing an outfit", with the way to undo each and all
  const outfitsEnd = await page.locator('.today-outfits').evaluate((el) => el.getBoundingClientRect().bottom + window.scrollY);
  expect(await onPage(stop)).toBeGreaterThan(outfitsEnd);
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect(stop).toHaveCount(0);
  await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
  expect(await buttonAt()).toBe(at);
});

test('finding 11: the dots are in the outfits\' heading and hold still from outfit to outfit', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const group = page.getByRole('group', { name: 'Choose an outfit' });
  await expect(page.locator('.today-outfits-head').getByRole('group', { name: 'Choose an outfit' })).toHaveCount(1);
  // "1 of 3" is not shown (the dots say it); a screen reader still hears which outfit is in front
  const shown = (h: Element) => [...h.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE || (n as Element).getBoundingClientRect().width > 1)
    .map((n) => n.textContent).join('').trim();
  expect(await page.locator('.today-outfits-head h2').evaluate(shown)).toBe('Best for today');
  await expect(page.getByRole('heading', { name: /^Best for today\W+1 of 3$/ })).toBeVisible();
  const where: number[] = [];
  for (let i = 0; i < 3; i++) {
    await toOutfit(page, i);
    where.push(await onPage(group));
  }
  expect(new Set(where).size).toBe(1);
  await expect(dots(page).nth(2)).toHaveAttribute('aria-pressed', 'true');
});

test('finding 12: the row under the button is one line on the last outfit and once the outfit is kept', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const row = () => current(page).locator('.today-wear-more');
  const oneLine = async () => expect((await row().boundingBox())!.height).toBeLessThanOrEqual(48);
  await oneLine();
  await toOutfit(page, 2);
  await oneLine();
  await toOutfit(page, 0);
  await current(page).getByRole('button', { name: 'Keep this outfit' }).click();
  await expect(current(page).getByTestId('kept-mark')).toBeVisible();
  try {
    await oneLine();
  } finally {
    const kept = (await (await page.request.get('/api/outfits/kept')).json()).outfits as { id: string }[];
    for (const k of kept.slice(0, kept.length - 2)) await page.request.delete(`/api/outfits/kept/${k.id}`);
  }
});

test('findings 13 and 18: with a trip coming, Today points to it once, in a row with no question; the links under the outfits take 44px', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  // the demo's trip starts in twelve days
  const row = page.getByTestId('today-trip');
  await expect(row).toBeVisible();
  await expect(row).not.toContainText('Packing for a trip?');
  await expect(row).toContainText(/in \d+ days · \d+ of \d+ packed/);
  await expect(page.locator('.today-more')).toHaveCount(0);
  // the demo's plan three days ahead: the whole line leads to that day
  const soon = page.getByTestId('plans-soon');
  await expect(soon).toContainText(/is planned\.$/);
  expect((await hitArea(soon.getByRole('link'))).height).toBeGreaterThanOrEqual(44);
});

test('finding 18: with no forecast, Try again takes 44px and Type temperatures is left to Change', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await openToday(page);
  const notice = page.getByTestId('no-weather');
  await expect(notice).toHaveText('No forecast. Try again');
  expect((await hitArea(notice.getByRole('button', { name: 'Try again' }))).height).toBeGreaterThanOrEqual(44);
});

test('finding 13: with no trip coming, the foot line leads to Trips, the whole line 44px to tap', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await page.route('**/api/trips', (route) => (route.request().method() === 'GET' ? route.fulfill({ json: { trips: [] } }) : route.fallback()));
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const foot = page.locator('.today-more');
  await expect(foot.getByRole('link')).toHaveText('Going away? Trips says what to pack.');
  expect((await hitArea(foot.getByRole('link'))).height).toBeGreaterThanOrEqual(44);
});

test('finding 21: a failed read is said once, in the shared words, and one Try again brings everything back', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await fakeWeather(page);
  await goToCloset(page);
  await useProfile(page, 'demo');
  let failing = true;
  const fail = (route: Route) => (failing ? route.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }) : route.fallback());
  await page.route('**/api/plans', fail);
  await page.route('**/api/outfits/today', fail);
  await page.goto('/today');
  const failed = page.getByTestId('failed');
  await expect(failed).toHaveCount(1);
  await expect(failed).toContainText("Couldn't load today's outfits.");
  await expect(failed).toContainText('Nines on your computer answered with a fault. Trying again usually helps.');
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(1);
  await expect(page.getByText(/Couldn't choose/)).toHaveCount(0);
  // finding 23: where the weather goes, a sentence rather than a label
  await expect(page.getByTestId('day-line')).toContainText("The weather isn't known yet.");
  await page.screenshot({ path: test.info().outputPath('today-failed.png') });
  failing = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(page.getByTestId('plans-soon')).toBeVisible();
  await expect(failed).toHaveCount(0);
});

test('finding 25: the weather line never leaves a dot at the end of a line', async ({ page }) => {
  // no forecast at home in the tests: "14–20°C · no rain · a mild day" is longer than its line at 320
  await page.setViewportSize({ width: 320, height: 568 });
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  expect(await danglingDots(page)).toEqual([]);
});

test('finding 27: while the outfits are chosen, what is under them is already where it will be', async ({ page }) => {
  await page.setViewportSize(PHONE);
  let release: () => void = () => undefined;
  const held = new Promise<void>((r) => { release = r; });
  await page.route('**/api/outfits/today', async (route) => {
    await held;
    const response = await route.fetch({ postData: { ...route.request().postDataJSON(), low_c: 14, high_c: 20, rain: false } });
    const json = await response.json();
    if (response.ok()) Object.assign(json.context, { source: 'forecast', place: BROOKLYN, rain_chance: 10, old: false, message: null });
    await route.fulfill({ response, json });
  });
  await openToday(page);
  const recent = page.getByTestId('recent-outfits');
  await expect(page.locator('.today-loading')).toBeVisible();
  await expect(recent).toBeVisible();
  const waiting = await onPage(recent);
  release();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const shown = await onPage(recent);
  expect(Math.abs(shown - waiting), `Recent outfits at ${waiting} while waiting, ${shown} once shown`).toBeLessThanOrEqual(60);
});


// The review measured these in the owner's own closet (the phone check's copy of the demo closet), which has no ribbon
// saying it is the demo: here too, on a backend of their own whose owner's closet starts as that copy.
test.describe("in the owner's closet, a copy of the demo closet", () => {
  let own: Backend;
  test.beforeAll(async ({ playwright }) => {
    own = await startBackend({ fakes: true, seed: 'demo' });
    // the demo's price drops are news in a copy of it: marked seen, as the phone check does, so no banner is over Today
    const api = await playwright.request.newContext({ baseURL: own.url, extraHTTPHeaders: { 'X-Closet-Client': '1' } });
    const { news } = await (await api.get('/api/wishlist/news')).json();
    await api.post('/api/wishlist/news/seen', { data: { wish_ids: news.map((n: { wish_id: string }) => n.wish_id) } });
    await api.dispose();
  });
  test.afterAll(async () => {
    await own?.stop();
  });

  test('finding 9: offline, it is said once, the saved time is a few words beside the weather, and the button is on the first screen', async ({ page, context }) => {
    await page.setViewportSize(PHONE);
    await stayOnCloset(page, own.url);
    // no faked weather: home has no forecast in the tests, so the "No forecast" line is there online
    await page.goto(own.url + '/today');
    await serviceWorkerInCharge(page);
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect(page.getByTestId('no-weather')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
    await expect(current(page).getByTestId('piece').first()).toBeVisible();
    await expect(page.getByTestId('saved-at')).toHaveText(/^saved at \d\d:\d\d$/);
    await expect(page.getByText(/You're offline, so these can't be changed/)).toHaveCount(0);
    await expect(page.getByTestId('no-weather')).toHaveCount(0);
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
    await page.screenshot({ path: test.info().outputPath('today-offline.png') });
    expect(wear.y + wear.height).toBeLessThanOrEqual(tabbar.y);
    await context.setOffline(false);
  });

  test('finding 26: at 320 by 568 the first screen still holds five pieces and "I\'m wearing this"', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.route('**/api/outfits/today', async (route) => {
      const response = await route.fetch();
      const json = await response.json();
      if (response.ok()) json.outfits = fiveOrMore(json);
      await route.fulfill({ response, json });
    });
    await stayOnCloset(page, own.url);
    await page.goto(own.url + '/today');
    await expect(current(page).getByTestId('piece')).toHaveCount(5);
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
    await page.screenshot({ path: test.info().outputPath('today-320.png') });
    expect(wear.y + wear.height).toBeLessThanOrEqual(tabbar.y);
    // and nothing wider than the phone
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    expect(await current(page).evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  });
});
