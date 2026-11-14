import { resolve } from 'node:path';
import { expect, login, test, useProfile } from './fixtures';

/** Design 3: the Closet grid and the item page, on a phone and a computer, saved as pictures. */

const SHOTS = resolve(import.meta.dirname, '../../docs/screenshots');

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('the first row of clothes is above the fold; filters open as a sheet; the item page reads first', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    await expect(page.getByTestId('tile').first()).toBeVisible();
    await page.waitForLoadState('networkidle');

    // the first two tiles, names included, sit above the tab bar without scrolling
    const bar = (await page.locator('nav.tabbar').boundingBox())!;
    for (const i of [0, 1]) {
      const tile = (await page.getByTestId('tile').nth(i).boundingBox())!;
      expect(tile.y + tile.height).toBeLessThanOrEqual(bar.y);
    }
    // one toolbar: search, Filter and the Photos / Drawings switch on one row
    const toolbar = page.locator('.closet-toolbar');
    const search = (await toolbar.getByRole('searchbox').boundingBox())!;
    const filter = (await toolbar.getByRole('button', { name: /^Filter/ }).boundingBox())!;
    const show = (await toolbar.getByRole('group', { name: 'Show' }).boundingBox())!;
    expect(Math.abs(search.y + search.height / 2 - (filter.y + filter.height / 2))).toBeLessThan(4);
    expect(Math.abs(show.y + show.height / 2 - (filter.y + filter.height / 2))).toBeLessThan(4);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: `${SHOTS}/closet-phone.png` });

    // the toolbar stays at the top while the clothes scroll under it
    await page.mouse.wheel(0, 900);
    await expect.poll(async () => (await toolbar.boundingBox())!.y).toBeLessThan(60);

    await toolbar.getByRole('button', { name: /^Filter/ }).click();
    const sheet = page.getByRole('dialog', { name: 'Filter' });
    await expect(sheet).toBeVisible();
    // it rises from the bottom edge of the screen
    await expect.poll(async () => { const b = (await sheet.boundingBox())!; return Math.round(b.y + b.height); }).toBe(844);
    await page.screenshot({ path: `${SHOTS}/closet-filter-phone.png` });
    await sheet.getByRole('group', { name: 'Filter by category' }).getByRole('button', { name: 'Polos', exact: true }).click();
    await sheet.getByRole('button', { name: 'Done' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Remove filter: Polos' })).toBeVisible();

    await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
    await expect(page.getByRole('heading', { level: 2 }).getByRole('textbox', { name: 'Name' })).toHaveValue('Navy polo');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `${SHOTS}/item-phone.png` });

    // a field opens as a sheet; one tap there changes it
    await page.getByRole('button', { name: /^Season/ }).click();
    const season = page.getByRole('dialog', { name: 'Season' });
    await expect(season).toBeVisible();
    await expect.poll(async () => { const b = (await season.boundingBox())!; return Math.round(b.y + b.height); }).toBe(844);
    await page.screenshot({ path: `${SHOTS}/item-field-phone.png` });
    await page.keyboard.press('Escape');
    await expect(season).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});

test.describe('computer', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('the grid takes the width until an item is chosen, then a 420px panel opens beside it', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    await expect(page.getByTestId('tile').first()).toBeVisible();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `${SHOTS}/closet-computer.png` });

    await page.getByRole('button', { name: /^Filter/ }).click();
    const popover = page.getByRole('dialog', { name: 'Filter' });
    await expect(popover).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/closet-filter-computer.png` });
    await page.keyboard.press('Escape');
    await expect(popover).toHaveCount(0);

    await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
    const panel = page.locator('aside.detail-panel');
    await expect(panel.getByRole('textbox', { name: 'Name' })).toHaveValue('Navy polo');
    expect((await panel.boundingBox())!.width).toBeCloseTo(420, 0);
    // no scrollbar of its own: it scrolls with the page
    expect(await panel.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);

    // a field opens in place
    await panel.getByRole('button', { name: /^Formality/ }).click();
    await expect(panel.getByRole('group', { name: 'Formality' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `${SHOTS}/item-computer.png` });
  });
});
