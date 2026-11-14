import { mkdirSync } from 'node:fs';
import type { Page, Route } from '@playwright/test';
import { axeViolations, sideways, smallTargets } from './a11y';
import { expect, login, test, useProfile } from './fixtures';

/**
 * Accessibility over the main screens of the demo closet, on a phone and a computer, in light and dark: axe-core
 * (WCAG 2.2 A and AA, contrast included), nothing past the right edge of a 390px phone, and 44px touch targets there.
 * Set A11Y_SHOTS to a folder to save a picture of each screen.
 */

const LAYOUTS = [
  ['phone', { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }],
  ['computer', { viewport: { width: 1440, height: 900 } }],
] as const;
const THEMES = ['light', 'dark'] as const;
const SHOTS = process.env.A11Y_SHOTS;

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** Today's weather is faked (Open-Meteo is never called from a test). */
async function fakeWeather(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: { ...body, low_c: 3.2, high_c: 9.8, rain: true } }) });
  });
}

async function check(page: Page, name: string, phone: boolean, shot: string) {
  await page.waitForLoadState('networkidle');
  expect.soft(await axeViolations(page), `${name}: axe`).toEqual([]);
  if (phone) {
    expect.soft(await sideways(page), `${name}: past the right edge`).toEqual([]);
    expect.soft(await smallTargets(page), `${name}: touch targets`).toEqual([]);
  }
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: `${SHOTS}/${shot}-${name.replace(/\W+/g, '-')}.png`, fullPage: true });
  }
}

async function visit(page: Page, path: string, ready: string) {
  await page.goto(path);
  await expect(page.locator(ready).first()).toBeVisible();
}

for (const [layout, use] of LAYOUTS) {
  for (const theme of THEMES) {
    test.describe(`${layout}, ${theme}`, () => {
      test.use(use);

      test('the main screens pass the accessibility checks', async ({ page }) => {
        test.setTimeout(240_000);
        const phone = layout === 'phone';
        const shot = `${layout}-${theme}`;
        await page.addInitScript((t) => localStorage.setItem('closet.theme', t), theme);
        await fakeWeather(page);
        await login(page);
        await useProfile(page, 'demo');
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);

        await expect(page.getByTestId('tile').first()).toBeVisible();
        await check(page, 'closet', phone, shot);

        await page.getByRole('button', { name: /^Filter/ }).click();
        await expect(page.getByRole('dialog', { name: 'Filter' })).toBeVisible();
        await check(page, 'filter', phone, shot);
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog', { name: 'Filter' })).toHaveCount(0);

        await page.getByTestId('tile').first().click();
        await expect(page.getByRole('textbox', { name: 'Name' })).toBeVisible();
        await check(page, 'item', phone, shot);
        await page.getByRole('button', { name: /^Season/ }).click();
        await expect(page.getByRole('group', { name: 'Season' })).toBeVisible();
        await check(page, 'item field', phone, shot);

        await visit(page, '/today', '#today-title');
        await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
        await check(page, 'today', phone, shot);

        await visit(page, '/today/worn', 'h1');
        await check(page, 'worn', phone, shot);

        await visit(page, '/missing', 'h1');
        await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
        await check(page, 'missing', phone, shot);

        await visit(page, '/missing/check', 'h1');
        await check(page, 'would this work', phone, shot);

        await visit(page, '/trips', 'h1');
        await check(page, 'trips', phone, shot);

        await visit(page, '/insights', 'h1');
        await check(page, 'insights', phone, shot);

        await visit(page, '/review', 'h1');
        await check(page, 'review', phone, shot);

        await visit(page, '/add', 'h1');
        await check(page, 'add', phone, shot);

        await visit(page, '/settings', 'h1');
        await page.getByText('Advanced', { exact: true }).click();
        await check(page, 'settings', phone, shot);
      });
    });
  }
}
