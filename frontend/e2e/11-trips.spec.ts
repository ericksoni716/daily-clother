import type { Page } from '@playwright/test';
import { resolve } from 'node:path';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

let backend: Backend;
test.beforeAll(async () => { backend = await startBackend({ weather: true }); });
test.afterAll(async () => { await backend?.stop(); });
test.afterEach(async ({ context }) => { await context.setOffline(false); });

async function open(page: Page) {
  const session = await (await page.request.get(backend.url + '/api/session')).json();
  await page.request.post(backend.url + (session.setup_required ? '/api/setup' : '/api/login'), { data: { passphrase: PASS } });
  await page.request.post(backend.url + '/api/profile', { data: { profile: 'demo' } });
  await page.goto(backend.url + '/trips');
}

function day(offset: number) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function plan(page: Page) {
  await page.getByRole('link', { name: 'Plan a trip', exact: true }).click();
  await page.getByLabel('Search for a place').fill('Lisbon');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.getByRole('button', { name: 'Lisbon, Portugal' }).click();
  await page.getByLabel('First day').fill(day(13));
  await page.getByLabel('Last day').fill(day(17));
  await page.getByRole('button', { name: 'Work out what to pack' }).click();
  await expect(page.getByRole('heading', { name: 'What to pack' })).toBeVisible();
  await expect(page.getByText('No suitable outfit', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Forecast', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Usually, on these dates', { exact: true }).first()).toBeAttached();
  await page.getByRole('button', { name: 'Save trip', exact: true }).click();
  await expect(page).toHaveURL(/\/trips\/[a-f0-9-]+$/);
  await expect(page.getByRole('button', { name: 'Plan again', exact: true })).toBeEnabled();
}

for (const [label, width, height] of [['computer', 1280, 800], ['phone', 390, 844]] as const) {
  test(`trip on ${label}: plan, pack, reload, swap, pin and read offline`, async ({ page, context }) => {
    await page.setViewportSize({ width, height });
    await open(page);
    await plan(page);
    const region = page.getByRole('region', { name: 'What to pack', exact: true });
    const first = region.getByRole('checkbox').first();
    const check = page.waitForResponse((r) => r.url().includes('/api/trips/') && r.request().method() === 'PATCH');
    await first.check();
    expect((await check).ok()).toBe(true);
    await expect(region.getByText(/1 of \d+ packed/)).toBeVisible();
    await page.reload();
    await expect(first).toBeChecked();
    await expect(page.getByRole('button', { name: 'Plan again', exact: true })).toBeEnabled();

    const swap = page.getByTestId('packing-piece').first().getByRole('button');
    const oldName = await swap.getAttribute('aria-label');
    const swapped = page.waitForResponse((r) => r.url().includes('/api/trips/') && r.request().method() === 'PATCH');
    await swap.click();
    expect((await swapped).ok()).toBe(true);
    await expect(page.getByRole('button', { name: oldName!, exact: true })).toHaveCount(0);
    await page.getByText('Take a particular piece, or undo a swap').click();
    const pinnedName = oldName!.replace('Not this piece: ', '');
    await page.getByLabel('I want to take this').selectOption({ label: pinnedName });
    await page.getByRole('button', { name: 'Pin to take', exact: true }).click();
    await expect(page.getByText('Pinned to take', { exact: false })).toBeVisible();
    await page.getByText('Take a particular piece, or undo a swap').click();

    if (label === 'phone') {
      await expect(page.locator('nav.tabbar').getByRole('link', { name: 'Trips' })).toHaveCount(0);
      expect(await page.locator('nav.tabbar').getByRole('link').count()).toBe(5);
    } else await expect(page.locator('nav.sidebar').getByRole('link', { name: 'Trips', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Lisbon', exact: true })).toBeVisible();
    await page.waitForLoadState('networkidle');
    if (process.env.CLOSET_TRIP_SCREENSHOTS === '1') {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: resolve(import.meta.dirname, `../../docs/screenshots/trips-${label}.png`) });
    }
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText('Offline: showing your saved closet.')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Lisbon', exact: true })).toBeVisible();
    await expect(first).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Plan again', exact: true })).toBeDisabled();
    const image = page.locator('.packing-line img').first();
    await expect(image).toBeVisible();
    expect(await image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  });
}

test('phone reaches Trips from Today, and deleting removes the saved trip', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await plan(page);
  await page.goto(backend.url + '/today');
  await page.getByRole('link', { name: 'Trips · plan what to pack' }).click();
  await expect(page.getByRole('heading', { name: 'Trips', exact: true })).toBeVisible();
  await page.locator('.trip-card').first().click();
  const url = page.url();
  page.once('dialog', (d) => d.accept());
  await page.getByRole('button', { name: 'Delete trip', exact: true }).click();
  await expect(page).toHaveURL(backend.url + '/trips');
  await expect(page.locator(`a[href="${new URL(url).pathname}"]`)).toHaveCount(0);
});

test('a failed tick is undone, and changed weather waits for permission', async ({ page }) => {
  await open(page);
  await plan(page);
  const url = page.url().replace('/trips/', '/api/trips/');
  await page.route(url, async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({ status: 409, json: { detail: 'This trip changed on another screen. Open it again before changing it.' } });
    } else await route.continue();
  });
  const first = page.getByRole('region', { name: 'What to pack', exact: true }).getByRole('checkbox').first();
  await first.click();
  await expect(page.getByRole('alert')).toContainText('changed on another screen');
  await expect(first).not.toBeChecked();
  await page.unroute(url);
  const before = await (await page.request.get(url)).json();
  await page.route(url, async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    await route.fulfill({ response, json: { ...json, weather_changed: route.request().method() === 'GET' } });
  });
  await page.reload();
  await expect(page.getByText('The forecast has changed, plan again', { exact: true })).toBeVisible();
  const after = await (await page.request.get(url)).json();
  expect(after.plan).toEqual(before.plan);
  expect(after.checked).toEqual(before.checked);
  await page.getByRole('button', { name: 'Use the new forecast' }).click();
  await expect(page.getByText('The forecast has changed, plan again', { exact: true })).toHaveCount(0);
});
