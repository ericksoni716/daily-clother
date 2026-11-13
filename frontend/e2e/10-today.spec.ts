import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

const BROOKLYN = 'Brooklyn, New York, United States';

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

test('today: Pieces / As worn draws the real demo outfit, remembers the view, and fits both screens', async ({ page }, testInfo) => {
  await fakeWeather(page);
  await openToday(page);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  const ids = await pieceIds(page);
  const view = page.getByRole('group', { name: 'Outfit view' });
  const response = page.waitForResponse('**/api/outfits/figure');
  await view.getByRole('button', { name: 'As worn', exact: true }).click();
  const figure = await response;
  expect(figure.ok()).toBe(true);
  expect(figure.headers()['content-type']).toContain('image/svg+xml');
  const slots = figure.request().postDataJSON() as Record<string, string | null>;
  expect(Object.keys(slots).sort()).toEqual(['base', 'bottom', 'mid', 'outer', 'shoes']);
  expect(Object.values(slots).filter(Boolean).every((id) => ids.includes(id!))).toBe(true);
  const image = current(page).getByRole('img', { name: 'Outfit as worn', exact: true });
  await expect(image).toHaveAttribute('src', /^blob:/);
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(current(page).getByTestId('piece')).toHaveCount(0);
  for (const [label, viewport] of [['computer', { width: 1280, height: 800 }], ['phone', { width: 390, height: 844 }]] as const) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    if (label === 'computer') await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeInViewport();
    const box = await image.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(400);
    expect(box!.width).toBeGreaterThan(240);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    const path = testInfo.outputPath(`today-as-worn-${label}.png`);
    await page.screenshot({ path, fullPage: true });
    await testInfo.attach(`As worn on ${label}`, { path, contentType: 'image/png' });
  }
  await page.reload();
  await expect(view.getByRole('button', { name: 'As worn', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(image).toBeVisible();
  await view.getByRole('button', { name: 'Pieces', exact: true }).click();
  await expect(image).toHaveCount(0);
  expect(await pieceIds(page)).toEqual(ids);
});

test('today: a drawing failure can be retried, and offline offers Pieces', async ({ page, context }) => {
  await fakeWeather(page);
  await openToday(page);
  await page.route('**/api/outfits/figure', (route) => route.fulfill({ status: 503, json: { detail: 'Please try again.' } }));
  const view = page.getByRole('group', { name: 'Outfit view' });
  await view.getByRole('button', { name: 'As worn', exact: true }).click();
  await expect(current(page).getByRole('alert')).toContainText('Please try again.');
  await page.unroute('**/api/outfits/figure');
  await current(page).getByRole('button', { name: 'Try drawing again' }).click();
  await expect(current(page).getByRole('img', { name: 'Outfit as worn', exact: true })).toBeVisible();
  await context.setOffline(true);
  await view.getByRole('button', { name: 'Pieces', exact: true }).click();
  await view.getByRole('button', { name: 'As worn', exact: true }).click();
  await expect(current(page).getByRole('status')).toContainText('Switch to Pieces');
  await expect(current(page).getByRole('img', { name: 'Outfit as worn', exact: true })).toHaveCount(0);
  await view.getByRole('button', { name: 'Pieces', exact: true }).click();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
});

test('today: leaving a loading figure cannot show it in another closet', async ({ page }) => {
  await fakeWeather(page);
  await openToday(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let requested = false;
  await page.route('**/api/outfits/figure', async (route) => {
    requested = true;
    await held;
    await route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="200"/>' });
  });
  await page.getByRole('button', { name: 'As worn', exact: true }).click();
  await expect.poll(() => requested).toBe(true);
  await expect(current(page).getByRole('status')).toHaveText('Drawing the outfit…');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  const switched = page.waitForResponse('**/api/profile');
  await page.getByText('Show the demo closet').click();
  await switched;
  release();
  await page.locator('nav.sidebar').getByRole('link', { name: 'Today' }).click();
  await expect(page.getByRole('list', { name: 'Why not' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Outfit as worn', exact: true })).toHaveCount(0);
});

test('today: correcting a piece replaces its figure with loading, never the old drawing', async ({ page }) => {
  await fakeWeather(page);
  await openToday(page);
  const link = current(page).getByTestId('piece').first();
  await expect(link).toBeVisible();
  const id = (await link.getAttribute('href'))!.split('/').pop()!;
  const original = await (await page.request.get(`/api/items/${id}`)).json();
  await link.click();
  const panel = page.getByRole('complementary', { name: 'Item details' });
  await expect(panel.getByRole('group', { name: 'Colour', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'As worn', exact: true }).click();
  const image = current(page).getByRole('img', { name: 'Outfit as worn', exact: true });
  await expect(image).toBeVisible();
  const oldUrl = await image.getAttribute('src');
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/outfits/figure', async (route) => {
    const response = await route.fetch();
    await held;
    await route.fulfill({ response });
  });
  const saved = page.waitForResponse((response) => response.request().method() === 'PATCH' && response.url().endsWith(`/api/items/${id}`));
  await panel.getByRole('group', { name: 'Colour', exact: true }).getByRole('button', { name: original.color === 'red' ? 'Blue' : 'Red', exact: true }).click();
  const corrected = await (await saved).json();
  await expect(current(page).getByRole('status')).toHaveText('Drawing the outfit…');
  await expect(image).toHaveCount(0);
  release();
  await expect(image).toBeVisible();
  expect(await image.getAttribute('src')).not.toBe(oldUrl);
  expect(await image.evaluate(async (img: HTMLImageElement) => (await fetch(img.src)).text())).toContain(corrected.color_hex);
  await page.getByRole('link', { name: 'Back to the outfit' }).click();
  await expect(image).toBeVisible();
  expect(await image.getAttribute('src')).not.toBe(oldUrl);
  await page.request.patch(`/api/items/${id}`, { data: { color: original.color, color_hex: original.color_hex } });
});

test('figure pixels: an open shirt reveals the tee, a closed sweater covers it', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const { items } = await (await page.request.get('/api/items?status=active')).json() as {
    items: { id: string; name: string; color_hex: string }[];
  };
  const tee = items.find((item) => item.name === 'White tee')!;
  const shirt = items.find((item) => item.name === 'Chambray shirt')!;
  const sweater = items.find((item) => item.name === 'Cream v-neck sweater')!;
  expect(tee).toBeDefined();
  expect(shirt).toBeDefined();
  expect(sweater).toBeDefined();
  const drawings: string[] = [];
  for (const mid of [shirt, sweater]) {
    const response = await page.request.post('/api/outfits/figure', {
      data: { base: tee.id, mid: mid.id, outer: null, bottom: null, shoes: null },
    });
    expect(response.ok()).toBe(true);
    expect(response.headers()['content-type']).toContain('image/svg+xml');
    drawings.push(await response.text());
  }
  const pixels = await page.evaluate(async (svgs) => Promise.all(svgs.map(async (svg) => {
    const document = new DOMParser().parseFromString(svg, 'image/svg+xml');
    const [x, y, width, height] = document.documentElement.getAttribute('viewBox')!.split(/\s+/).map(Number);
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = window.document.createElement('canvas');
      canvas.width = Math.ceil(width);
      canvas.height = Math.ceil(height);
      const context = canvas.getContext('2d')!;
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      // Templates share their original frame; the SVG viewBox crops that frame.
      return [...context.getImageData(Math.floor((200 - x) * canvas.width / width), Math.floor((180 - y) * canvas.height / height), 1, 1).data];
    } finally {
      URL.revokeObjectURL(url);
    }
  })), drawings);
  const rgb = (hex: string) => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
  const difference = (pixel: number[], hex: string) => Math.max(...rgb(hex).map((channel, i) => Math.abs(pixel[i] - channel)));
  const [open, closed] = pixels;
  expect(open[3]).toBe(255);
  expect(closed[3]).toBe(255);
  // Cloth texture can shift a channel slightly; the exposed garment must still be the nearer colour.
  expect(difference(open, tee.color_hex)).toBeLessThanOrEqual(24);
  expect(difference(open, tee.color_hex)).toBeLessThan(difference(open, shirt.color_hex));
  expect(difference(closed, sweater.color_hex)).toBeLessThanOrEqual(24);
  expect(difference(closed, sweater.color_hex)).toBeLessThan(difference(closed, tee.color_hex));
});

test('today: the day, an outfit with its reasons, and the occasion changes the outfits', async ({ page }) => {
  const asked = await fakeWeather(page);
  await openToday(page);

  const day = page.getByTestId('day-line');
  await expect(day).toContainText('Brooklyn');
  await expect(day).toContainText('3°C to 10°C');
  await expect(day).toContainText('Rain likely (70%)');

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

test('today with no saved place: says so, links to Settings, and dresses for typed temperatures', async ({ page }) => {
  await openToday(page);
  const dayForm = page.getByRole('region', { name: 'The day' });
  await expect(dayForm.getByText(/Choose where you are in Settings/)).toBeVisible();
  await expect(dayForm.getByRole('link', { name: 'choose where you are in Settings' })).toHaveAttribute('href', '/settings');

  await dayForm.getByLabel('Low °C').fill('18');
  await dayForm.getByLabel('High °C').fill('26');
  await dayForm.getByRole('button', { name: 'Dress me for this' }).click();
  const day = page.getByTestId('day-line');
  await expect(day).toContainText('Your temperatures');
  await expect(day).toContainText('18°C to 26°C');
  await expect(day).toContainText('No rain expected');
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
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

test("today in a closet that can't dress the owner yet: the server's reasons, what to add first, and a link to add", async ({ page }) => {
  await fakeWeather(page);
  await login(page);
  await page.goto('/today');
  const why = page.getByRole('list', { name: 'Why not' });
  await expect(why.getByRole('listitem').first()).toBeVisible();
  await expect(page.getByTestId('add-first')).toContainText('Add first: a top');
  await expect(page.getByRole('link', { name: 'Add clothes' })).toHaveAttribute('href', '/add');
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
    const path = testInfo.outputPath(`today-${label}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`Today on a ${label}`, { path, contentType: 'image/png' });
  });
}
