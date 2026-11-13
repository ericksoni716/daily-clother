import type { Page } from '@playwright/test';
import { expect, login, PASS, test, useProfile } from './fixtures';
import { localDay } from '../src/wears';

const PLACE = { name: 'Brooklyn, New York, United States', latitude: 40.65, longitude: -73.95, timezone: 'America/New_York' };
const FORECAST = { date: localDay(), low_c: 10, high_c: 17, rain: true, rain_chance: 70, summary: 'rain', fetched_at: new Date().toISOString() };

async function fakeWeather(page: Page, options: { noPlace?: boolean; old?: boolean } = {}) {
  await page.route('**/api/weather', (route) => route.fulfill({ json: {
    place: options.noPlace ? null : PLACE, weather: options.noPlace ? null : FORECAST,
    is_today: !options.noPlace, old: !!options.old,
    message: options.noPlace ? 'Choose where you are in Settings to see the weather here.'
      : options.old ? "The weather service couldn't be reached. This is the last forecast we kept." : null,
  } }));
  // Use the real demo engine and wear log, but never ask Open-Meteo from a test.
  await page.route('**/api/outfits/today', async (route) => {
    const body = route.request().postDataJSON();
    const response = await route.fetch({ postData: {
      ...body, low_c: body.low_c ?? FORECAST.low_c, high_c: body.high_c ?? FORECAST.high_c, rain: body.rain ?? FORECAST.rain,
    } });
    const answer = await response.json();
    if (answer.context && !options.noPlace && body.low_c === undefined) {
      Object.assign(answer.context, { place: PLACE.name, source: 'forecast', old: !!options.old, summary: 'rain', rain_chance: 70 });
    }
    await route.fulfill({ response, json: answer });
  });
}

async function openToday(page: Page, options: { noPlace?: boolean; old?: boolean } = {}) {
  await fakeWeather(page, options);
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  await expect(page.getByRole('heading', { name: 'Today, put together.' })).toBeVisible();
}

async function pieceIds(page: Page) {
  return page.locator('.today-piece').evaluateAll((pieces) => pieces.map((piece) => piece.getAttribute('data-item-id')!));
}

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('real outfits show reasons, weather and warnings; occasion and mood are remembered', async ({ page }) => {
  await openToday(page, { old: true });
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await expect(page.getByText('Low 10°C · High 17°C · Rain expected')).toBeVisible();
  await expect(page.getByText("The weather service couldn't be reached. This is the last forecast we kept.")).toBeVisible();
  await expect(page.locator('.today-reasons li').first()).toBeVisible();
  await expect(page.locator('.today-warning').filter({ hasText: 'Before you head out' })).toBeVisible();
  const first = await pieceIds(page);
  await page.getByRole('button', { name: 'Business', exact: true }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  expect(await pieceIds(page)).not.toEqual(first);
  await page.getByRole('button', { name: 'Sharp', exact: true }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Business', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Sharp', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('wearing an outfit records every piece, survives reload, and undo preserves earlier wears', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  const ids = await pieceIds(page);
  const before = await Promise.all(ids.map(async (id) => (await page.request.get(`/api/items/${id}`)).json()));
  // This piece was recorded separately, so outfit Undo must leave it alone.
  const existing = await page.request.post(`/api/items/${ids[0]}/wears`);
  const preexisting = await existing.json();
  const response = page.waitForResponse((r) => r.url().endsWith('/api/wears') && r.request().method() === 'POST');
  await page.getByRole('button', { name: "I'm wearing this", exact: true }).click();
  const receipt = await (await response).json();
  expect(receipt.created_ids).not.toContain(ids[0]);
  await expect(page.getByText(`Today's wear is recorded for ${ids.length} pieces.`)).toBeVisible();
  for (const id of ids) {
    const item = await (await page.request.get(`/api/items/${id}`)).json();
    expect(item.recent_wears).toContain(receipt.worn_on);
  }
  await page.reload();
  await expect(page.getByRole('button', { name: 'Wearing this today', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: "I'm wearing this", exact: true })).toBeEnabled();
  for (let index = 0; index < ids.length; index++) {
    const item = await (await page.request.get(`/api/items/${ids[index]}`)).json();
    expect(item.wear_count).toBe(index === 0 ? preexisting.wear_count : before[index].wear_count);
  }
  if (existing.status() === 201) await page.request.delete(`/api/items/${ids[0]}/wears/${receipt.worn_on}`);
});

test('leave out and build around a piece, clear both, and return from item details to the same outfit', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  const excluded = (await pieceIds(page))[0];
  await page.locator('.today-piece-more').first().click();
  await page.getByRole('button', { name: 'Not this piece', exact: true }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  expect(await pieceIds(page)).not.toContain(excluded);
  await page.getByRole('button', { name: 'Clear left-out pieces' }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  const builtAround = (await pieceIds(page))[0];
  await page.locator('.today-piece-more').first().click();
  await page.getByRole('button', { name: 'Start from this piece', exact: true }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.getByRole('button', { name: 'Next outfit' }).click();
  expect(await pieceIds(page)).toContain(builtAround);
  const second = await pieceIds(page);
  await page.locator('.today-piece-link').first().click();
  await expect(page.getByRole('button', { name: 'Wore it today', exact: true })).toBeVisible();
  await page.getByRole('link', { name: "Back to today's outfit" }).click();
  expect(await pieceIds(page)).toEqual(second);
  await page.reload();
  expect(await pieceIds(page)).toEqual(second);
  await page.getByRole('button', { name: 'Clear starting piece' }).click();
  await expect(page.getByRole('button', { name: 'Clear starting piece' })).toHaveCount(0);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
});

test('navigating away while a wear is saving keeps its original undo receipt', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  const ids = await pieceIds(page);
  const before = await Promise.all(ids.map(async (id) => (await page.request.get(`/api/items/${id}`)).json()));
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let recorded!: () => void;
  const recordedOnServer = new Promise<void>((resolve) => { recorded = resolve; });
  await page.route('**/api/wears', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const response = await route.fetch();
    recorded();
    await held;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: "I'm wearing this", exact: true }).click();
  await recordedOnServer;
  await page.locator('nav.sidebar').getByRole('link', { name: 'Closet', exact: true }).click();
  await page.locator('nav.sidebar').getByRole('link', { name: 'Today', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: 'Undo', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByRole('button', { name: "I'm wearing this", exact: true })).toBeEnabled();
  for (let index = 0; index < ids.length; index++) {
    expect((await (await page.request.get(`/api/items/${ids[index]}`)).json()).wear_count).toBe(before[index].wear_count);
  }
});

test('no saved place: enter temperatures here and link to Settings', async ({ page }) => {
  await openToday(page, { noPlace: true });
  await expect(page.getByLabel('Low (°C)')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Where you are in Settings' })).toHaveAttribute('href', '/settings#s-place');
  await page.getByLabel('Low (°C)').fill('10');
  await page.getByLabel('High (°C)').fill('17');
  await page.getByLabel('Rain expected', { exact: true }).check();
  await page.getByRole('button', { name: 'Use these temperatures' }).click();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await expect(page.getByText('Low 10°C · High 17°C · Rain expected')).toBeVisible();
});

test('a late wear response after logout cannot recreate saved closet data', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let recorded!: () => void;
  const recordedOnServer = new Promise<void>((resolve) => { recorded = resolve; });
  let receipt!: { created_ids: string[]; worn_on: string };
  await page.route('**/api/wears', async (route) => {
    const response = await route.fetch();
    receipt = await response.json();
    recorded();
    await held;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: "I'm wearing this", exact: true }).click();
  await recordedOnServer;
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Log out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  const response = page.waitForResponse('**/api/wears');
  release();
  await response;
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 50)));
  expect(await page.evaluate(() => [localStorage.getItem('closet-today-demo'), localStorage.getItem('closet-today-demo-wear')])).toEqual([null, null]);
  await page.request.post('/api/login', { data: { passphrase: PASS } });
  await page.request.delete('/api/wears', { data: { item_ids: receipt.created_ids, worn_on: receipt.worn_on } });
});

test('saved outfits open offline, images included, with server actions disabled', async ({ page, context }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  await page.reload();
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const ids = await pieceIds(page);
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/Saved earlier today.*Offline/)).toBeVisible();
  expect(await pieceIds(page)).toEqual(ids);
  await expect(page.getByRole('button', { name: "I'm wearing this", exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Business', exact: true })).toBeDisabled();
  await expect(page.locator('.today-piece-more').first()).toBeDisabled();
  expect(await page.locator('.today-piece img').first().evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
});

test('empty answer, loading and retry use the server sentences', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.route('**/api/outfits/today', (route) => route.fulfill({ status: 500, json: { detail: 'Please try this outfit again.' } }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Please try this outfit again.');
  await page.route('**/api/outfits/today', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ json: { outfits: [], missing: ['There are no shoes in this closet yet.'], context: {
      ...FORECAST, source: 'forecast', old: false, place: PLACE.name,
    } } });
  });
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByText('Putting your outfit together…')).toBeVisible();
  await expect(page.getByText('There are no shoes in this closet yet.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Add clothes', exact: true })).toBeVisible();
});

test('a connection lost while changing the day restores the last successful outfits and choices', async ({ page }) => {
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  const first = await pieceIds(page);
  await page.route('**/api/outfits/today', (route) => route.abort('internetdisconnected'));
  await page.getByRole('button', { name: 'Business', exact: true }).click();
  await expect(page.getByText(/Saved earlier today.*Offline/)).toBeVisible();
  expect(await pieceIds(page)).toEqual(first);
  await expect(page.getByRole('button', { name: 'Casual', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: "I'm wearing this", exact: true })).toBeDisabled();
});

test('Today is the opening screen once the closet has the pieces to dress from', async ({ page }) => {
  await openToday(page);
  await page.goto('/');
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('heading', { name: 'Today, put together.' })).toBeVisible();
});

test('phone swipe, no sideways overflow, and phone and computer screenshots', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openToday(page);
  await expect(page.getByTestId('today-outfit')).toBeVisible();
  await page.waitForLoadState('networkidle');
  const first = await pieceIds(page);
  const gallery = page.getByTestId('today-outfit');
  await gallery.evaluate((target) => {
    target.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [new Touch({ identifier: 1, target, clientX: 330, clientY: 400 })] }));
    target.dispatchEvent(new TouchEvent('touchend', { bubbles: true, changedTouches: [new Touch({ identifier: 1, target, clientX: 100, clientY: 408 })] }));
  });
  expect(await pieceIds(page)).not.toEqual(first);
  await page.getByRole('button', { name: 'Previous outfit' }).click();
  for (const [name, width, height] of [['phone', 390, 844], ['computer', 1280, 800]] as const) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.locator('.today-piece img').first()).toBeVisible();
    const path = testInfo.outputPath(`today-${name}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`Today — ${name} (${width}×${height})`, { path, contentType: 'image/png' });
    const fullPath = testInfo.outputPath(`today-${name}-full.png`);
    await page.screenshot({ path: fullPath, fullPage: true });
    await testInfo.attach(`Today — ${name}, full page`, { path: fullPath, contentType: 'image/png' });
  }
});
