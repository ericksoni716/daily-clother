import { resolve } from 'node:path';
import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

/** Light and dark: the device's own setting, and the owner's choice in Settings (Look) winning over it. */

const LIGHT_BG = 'rgb(246, 242, 234)';
const DARK_BG = 'rgb(27, 25, 22)';
const SHOTS = resolve(import.meta.dirname, '../../docs/screenshots');
const LAYOUTS = [['phone', { width: 390, height: 844 }], ['computer', { width: 1440, height: 900 }]] as const;

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** Today's weather is faked (Open-Meteo is never called from a test): a cold, rainy day. */
async function fakeWeather(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: { ...body, low_c: 3.2, high_c: 9.8, rain: true } }) });
  });
}

const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

/** Closet, Today and Settings of the demo closet, checked for the expected canvas and saved as pictures. */
async function shoot(page: Page, name: string, layout: string, bg: string) {
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  await expect(page.getByTestId('item-count')).toBeVisible();
  expect(await background(page)).toBe(bg);
  await page.screenshot({ path: `${SHOTS}/theme-closet-${layout}-${name}.png` });

  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
  await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
  expect(await background(page)).toBe(bg);
  await page.screenshot({ path: `${SHOTS}/theme-today-${layout}-${name}.png` });

  await page.goto('/settings');
  await expect(page.getByRole('group', { name: 'Look' })).toBeVisible();
  expect(await background(page)).toBe(bg);
  await page.screenshot({ path: `${SHOTS}/theme-settings-${layout}-${name}.png` });
}

for (const [layout, viewport] of LAYOUTS) {
  test(`dark device, ${layout}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ colorScheme: 'dark' });
    await fakeWeather(page);
    await login(page);
    await useProfile(page, 'demo');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBeUndefined();
    await shoot(page, 'dark', layout, DARK_BG);
  });

  test(`light chosen on a dark device, ${layout}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.addInitScript(() => localStorage.setItem('closet.theme', 'light'));
    await fakeWeather(page);
    await login(page);
    await useProfile(page, 'demo');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light');
    await shoot(page, 'forced-light', layout, LIGHT_BG);
  });

  test(`dark chosen on a light device, ${layout}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ colorScheme: 'light' });
    await page.addInitScript(() => localStorage.setItem('closet.theme', 'dark'));
    await fakeWeather(page);
    await login(page);
    await useProfile(page, 'demo');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
    await shoot(page, 'forced-dark', layout, DARK_BG);
  });
}

test('the Look choice in Settings wins over the device and is remembered', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await login(page);
  await page.goto('/settings');
  const look = () => page.getByRole('group', { name: 'Look' });
  await expect(look().getByRole('button', { name: 'Same as this device' })).toHaveAttribute('aria-pressed', 'true');
  expect(await background(page)).toBe(LIGHT_BG);

  await look().getByRole('button', { name: 'Dark' }).click();
  await expect(look().getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(await background(page)).toBe(DARK_BG);
  expect(await page.evaluate(() => localStorage.getItem('closet.theme'))).toBe('dark');

  // remembered on this device after a reload
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(look().getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');

  // light chosen on a dark device stays light
  await page.emulateMedia({ colorScheme: 'dark' });
  await look().getByRole('button', { name: 'Light' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(await background(page)).toBe(LIGHT_BG);

  // back to following the device
  await look().getByRole('button', { name: 'Same as this device' }).click();
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', /./);
  expect(await page.evaluate(() => localStorage.getItem('closet.theme'))).toBeNull();
  expect(await background(page)).toBe(DARK_BG);
});
