import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { axeViolations, sideways } from './a11y';
import { expect, goToCloset, openFold, test, useProfile } from './fixtures';

// The shared parts every screen stands on: what a screen says when Nines does not answer, the toasts, and how sheets
// and in-place editors take Escape and hold the page behind them (the UI review of 23 November, A6, P5, P7, P10).

const PHONE = { width: 375, height: 812 };
// what is read comes from this backend, never the service worker's saved copy, so a fault stood in for is what the page gets
test.use({ serviceWorkers: 'block' });
const FAULT = { status: 500, json: { detail: 'Internal Server Error' } };

function demoId(name: string): string {
  const data = JSON.parse(readFileSync(resolve(import.meta.dirname, '../../backend/closet/demo_data/items.json'), 'utf8'));
  return data.items.find((i: { name: string }) => i.name === name).id;
}

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('a screen whose read fails says so in plain words, offers Try again, and keeps an earlier answer marked as earlier', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.route('**/api/items?*', (route) => route.fulfill(FAULT));
  await page.reload();
  const failed = page.getByTestId('failed');
  await expect(failed).toBeVisible();
  await expect(failed).toContainText("Couldn't load your closet.");
  await expect(failed).toContainText('Nines on your computer answered with a fault.');
  await expect(page.locator('main')).not.toContainText('Internal Server Error');
  expect(await sideways(page)).toEqual([]);
  expect(await axeViolations(page)).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('failed-closet.png') });

  // Try again, once Nines answers: the closet, and nothing about the fault
  await page.unroute('**/api/items?*');
  await failed.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByTestId('tile').first()).toBeVisible();
  await expect(failed).toHaveCount(0);

  // a read that fails again while the closet is on screen: the clothes stay, under one line saying they are from earlier
  await page.route('**/api/items?*', (route) => route.fulfill(FAULT));
  await page.locator('nav.tabbar').getByRole('link', { name: 'Settings' }).click();
  await page.locator('nav.tabbar').getByRole('link', { name: 'Closet' }).click();
  const earlier = page.getByTestId('failed-earlier');
  await expect(earlier).toContainText('This is your closet as it was earlier. Nines on your computer answered with a fault.');
  await expect(page.getByTestId('tile').first()).toBeVisible();
  await page.unroute('**/api/items?*');
  await earlier.getByRole('button', { name: 'Try again' }).click();
  await expect(earlier).toHaveCount(0);
});

test('every screen that reads says the same when it fails: Worn, a trip list, Review and Would this work?', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await page.route('**/api/outfits/worn*', (route) => route.fulfill(FAULT));
  await page.route('**/api/trips', (route) => route.fulfill(FAULT));
  await page.route('**/api/review', (route) => route.fulfill(FAULT));
  await page.route('**/api/vocab', (route) => route.fulfill(FAULT));
  for (const [path, what] of [['/today/worn', 'your worn outfits'], ['/trips', 'your trips'], ['/review', 'the pieces to check'],
    ['/wardrobe/check', 'the words to describe a piece']]) {
    await page.goto(path);
    const failed = page.getByTestId('failed');
    await expect(failed, path).toContainText(`Couldn't load ${what}.`);
    await expect(failed.getByRole('button', { name: 'Try again' })).toBeVisible();
    await expect(page.locator('main')).not.toContainText('Internal Server Error');
  }
});

test('one toast of each kind at a time, at the top of the screen, clear of what you tap next', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto(`/item/${demoId('Black tee')}`);
  const brand = page.getByTestId('essentials').getByRole('textbox', { name: 'Brand' });
  await expect(brand).toBeVisible();
  await page.route(`**/api/items/${demoId('Black tee')}`, (route) => (route.request().method() === 'PATCH' ? route.fulfill(FAULT) : route.continue()));
  for (const word of ['Made-up Mills', 'Other Mills', 'Third Mills']) {
    await brand.fill(word);
    await brand.press('Tab');
  }
  const errors = page.locator('.toast-error');
  await expect(errors).toHaveCount(1);
  await expect(errors).not.toContainText('Internal Server Error');
  expect((await errors.boundingBox())!.y).toBeLessThan(80);
});

test("Escape closes an in-place editor wherever focus is, and Your style's Escape drops only the line being changed", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto(`/item/${demoId('Burgundy cable sweater')}`);
  const fold = await openFold(page, 'Details');
  const row = fold.getByRole('button', { name: /^Colour:/ });
  await row.focus();
  await page.keyboard.press('Enter');
  const editor = page.getByTestId('detail-editor-color');
  await expect(editor).toBeVisible();
  await expect(row).toBeFocused();   // opened in place on a computer, focus stays on its row
  await page.keyboard.press('Escape');
  await expect(editor).toHaveCount(0);

  // Your style: Escape while a line is being changed drops that change only, and focus goes back to its Change
  await page.setViewportSize(PHONE);
  const profile = await (await page.request.post('/api/style/lines', { headers: { 'X-Closet-Client': '1' }, data: { text: 'Navy rather than black.' } })).json();
  const added = (profile.lines as { id: number; text: string }[]).find((l) => l.text.includes('Navy rather than black.'))!;
  await page.goto('/settings');
  await page.getByRole('button', { name: /^(See all lines|Change the lines)$/ }).click();
  const sheet = page.getByTestId('style-lines-sheet');
  await expect(sheet).toBeVisible();
  const change = sheet.getByRole('button', { name: 'Change “Navy rather than black.”' });
  await change.click();
  await sheet.getByRole('textbox', { name: 'Change this line' }).fill('Navy, never black.');
  await page.keyboard.press('Escape');
  await expect(sheet.getByRole('textbox', { name: 'Change this line' })).toHaveCount(0);
  await expect(sheet).toBeVisible();
  await expect(change).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await page.request.delete(`/api/style/lines/${added.id}`, { headers: { 'X-Closet-Client': '1' } });
});

test('the page behind a phone sheet holds still when you drag on the dimmed part', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.evaluate(() => window.scrollTo(0, 200));
  const before = await page.evaluate(() => window.scrollY);
  await page.getByRole('button', { name: 'Filter' }).click();
  await expect(page.getByRole('dialog', { name: 'Filter' })).toBeVisible();
  await page.mouse.move(180, 60);   // over the dim part, above the sheet
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(200);
  expect(await page.evaluate(() => window.scrollY)).toBe(before);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Filter' })).toHaveCount(0);
  await page.mouse.wheel(0, 300);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(before);
});
