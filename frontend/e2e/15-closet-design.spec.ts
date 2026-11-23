import { expect, goToCloset, openFold, test, useProfile } from './fixtures';

/** Design 3: the Closet grid and the item page, on a phone and a computer, saved as pictures. */


test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('the first row of clothes is above the fold; filters open as a sheet; the item page reads first', async ({ page }) => {
    await goToCloset(page);
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
    await page.screenshot({ path: test.info().outputPath(`closet-phone.png`) });

    // the toolbar stays at the top while the clothes scroll under it
    await page.mouse.wheel(0, 900);
    await expect.poll(async () => (await toolbar.boundingBox())!.y).toBeLessThan(60);

    await toolbar.getByRole('button', { name: /^Filter/ }).click();
    const sheet = page.getByRole('dialog', { name: 'Filter' });
    await expect(sheet).toBeVisible();
    // it rises from the bottom edge of the screen
    await expect.poll(async () => { const b = (await sheet.boundingBox())!; return Math.round(b.y + b.height); }).toBe(844);
    await page.screenshot({ path: test.info().outputPath(`closet-filter-phone.png`) });
    // what a piece is is asked once: the groups, opening to what is in the one chosen
    await expect(sheet.getByRole('group', { name: 'Filter by category' })).toHaveCount(0);
    await expect(sheet.getByRole('group', { name: 'Filter by kind' })).toHaveCount(0);
    const what = sheet.getByRole('group', { name: 'What it is' });
    await what.getByRole('button', { name: 'Trousers & shorts' }).click();
    await sheet.getByRole('group', { name: 'Which Trousers & shorts' }).getByRole('button', { name: 'Jeans', exact: true }).click();
    await expect(toolbar.getByRole('button', { name: /^Filter\W+1 on$/ })).toBeVisible();
    // another group starts again rather than stacking on the first, so the two never leave nothing to show
    await what.getByRole('button', { name: 'Knitwear & mid layers' }).click();
    await expect(sheet.getByRole('group', { name: 'Which Trousers & shorts' })).toHaveCount(0);
    await sheet.getByRole('group', { name: 'Which Knitwear & mid layers' }).getByRole('button', { name: 'Sweaters', exact: true }).click();
    await expect(toolbar.getByRole('button', { name: /^Filter\W+1 on$/ })).toBeVisible();
    await sheet.getByRole('button', { name: 'Done' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^Remove filter/ })).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Remove filter: Sweaters' })).toBeVisible();
    expect(await page.getByTestId('tile').count()).toBeGreaterThan(0);

    // earlier tests may have changed the demo closet, so open whichever sweater comes first
    const first = page.getByTestId('tile').first();
    const name = (await first.locator('.tile-name').textContent())!;
    await first.click();
    await expect(page.getByRole('heading', { level: 2 }).getByRole('textbox', { name: 'Name' })).toHaveValue(name);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: test.info().outputPath(`item-phone.png`) });

    // a field, in the Details fold, opens as a sheet; one tap there changes it
    await openFold(page, 'Details');
    await page.getByRole('button', { name: /^Season/ }).click();
    const season = page.getByRole('dialog', { name: 'Season' });
    await expect(season).toBeVisible();
    await expect.poll(async () => { const b = (await season.boundingBox())!; return Math.round(b.y + b.height); }).toBe(844);
    await page.screenshot({ path: test.info().outputPath(`item-field-phone.png`) });
    await page.keyboard.press('Escape');
    await expect(season).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });

  test('an item opens at its top, and the closet keeps its search when you come back', async ({ page }) => {
    await goToCloset(page);
    await useProfile(page, 'demo');
    await expect(page.getByTestId('tile').first()).toBeVisible();
    // far down the grid, the item page opens at its picture, not at the grid's scroll position
    await page.getByTestId('tile').last().scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
    await page.getByTestId('tile').last().click();
    await expect(page).toHaveURL(/\/item\//);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
    await page.goBack();

    // a search survives opening one of its results and coming back
    await page.getByRole('searchbox').fill('jeans');
    const found = await page.getByTestId('tile').count();
    expect(found).toBeGreaterThan(0);
    await page.getByTestId('tile').first().click();
    await expect(page).toHaveURL(/\/item\//);
    await page.goBack();
    await expect(page.getByRole('searchbox')).toHaveValue('jeans');
    await expect(page.getByTestId('tile')).toHaveCount(found);
    await page.getByRole('searchbox').fill('');
  });
});

test.describe('computer', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('the grid takes the width until an item is chosen, then a 420px panel opens beside it', async ({ page }) => {
    await goToCloset(page);
    await useProfile(page, 'demo');
    await expect(page.getByTestId('tile').first()).toBeVisible();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: test.info().outputPath(`closet-computer.png`) });

    await page.getByRole('button', { name: /^Filter/ }).click();
    const popover = page.getByRole('dialog', { name: 'Filter' });
    await expect(popover).toBeVisible();
    await page.screenshot({ path: test.info().outputPath(`closet-filter-computer.png`) });
    await page.keyboard.press('Escape');
    await expect(popover).toHaveCount(0);

    const first = page.getByTestId('tile').first();
    const name = (await first.locator('.tile-name').textContent())!;
    await first.click();
    const panel = page.locator('aside.detail-panel');
    await expect(panel.getByRole('textbox', { name: 'Name' })).toHaveValue(name);
    expect((await panel.boundingBox())!.width).toBeCloseTo(420, 0);
    // no scrollbar of its own: it scrolls with the page
    expect(await panel.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);

    // a field opens in place
    await openFold(panel, 'Details');
    await panel.getByRole('button', { name: /^Formality/ }).click();
    await expect(panel.getByRole('group', { name: 'Formality' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: test.info().outputPath(`item-computer.png`) });
  });

  test('opening a piece far down the grid keeps the grid still; the panel closes with Close, Escape and Back', async ({ page }) => {
    await goToCloset(page);
    await useProfile(page, 'demo');
    await page.goto('/');
    const tiles = page.getByTestId('tile');
    await expect(tiles.first()).toBeVisible();
    const columns = () => page.locator('ul.grid').evaluate((g) => getComputedStyle(g).gridTemplateColumns.split(' ').length);
    const before = await columns();
    expect(before).toBeGreaterThanOrEqual(4);
    // a few rows down, the last tile of its row
    const tile = tiles.nth(before * 3 - 1);
    await tile.scrollIntoViewIfNeeded();
    await page.mouse.wheel(0, 120);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(300);
    const at = (await tile.boundingBox())!;
    const href = (await tile.getAttribute('href'))!;

    await tile.click();
    const panel = page.getByRole('complementary', { name: 'Item details' });
    await expect(panel.getByRole('textbox', { name: 'Name' })).toBeVisible();
    // the grid keeps its columns, and the piece chosen stays where it was on the screen
    expect(await columns()).toBe(before);
    const now = (await tile.boundingBox())!;
    expect(Math.abs(now.y - at.y)).toBeLessThan(3);
    // the panel opens level with the top of the screen, and focus goes into it
    const box = (await panel.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeLessThan(40);
    await expect.poll(() => panel.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    await page.screenshot({ path: test.info().outputPath('computer-panel-holds-still.png') });

    // Close closes it, the address is the closet's again, and focus is back on the piece
    await panel.getByRole('button', { name: 'Close' }).click();
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);
    await expect(tile).toBeFocused();
    expect(await columns()).toBe(before);

    // Escape closes it too
    await tile.click();
    await expect(panel).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${href}$`));
    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);

    // and so does the browser's Back
    await tile.click();
    await expect(panel).toBeVisible();
    await page.goBack();
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/$/);
    // Close and Escape went Back rather than adding a page, so the closet is still the first page of this visit
    expect(await page.evaluate(() => (history.state as { idx: number }).idx)).toBe(0);
  });
});
