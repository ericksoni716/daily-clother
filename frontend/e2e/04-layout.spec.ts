import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('bottom tab bar, two-column grid, detail as its own screen', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    const tabbar = page.locator('nav.tabbar');
    await expect(tabbar).toBeVisible();
    await expect(page.locator('nav.sidebar')).toBeHidden();
    for (const name of ['Closet', 'Add', 'Settings']) await expect(tabbar.getByRole('link', { name })).toBeVisible();
    const bar = (await tabbar.boundingBox())!;
    expect(bar.y + bar.height).toBeCloseTo(844, 0);

    const tiles = page.getByTestId('tile');
    const a = (await tiles.nth(0).boundingBox())!;
    const b = (await tiles.nth(1).boundingBox())!;
    const c = (await tiles.nth(2).boundingBox())!;
    expect(b.y).toBeCloseTo(a.y, 0);
    expect(c.y).toBeGreaterThan(a.y + a.height - 1);
    expect(a.height).toBeCloseTo(b.height, 0);

    // no horizontal page scroll
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    await tiles.filter({ hasText: 'Navy polo' }).click();
    await expect(page.getByRole('link', { name: 'Closet' }).first()).toBeVisible();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await expect(page.getByTestId('tile')).toHaveCount(0);
    // a detail opens its choices in a sheet from the bottom of the screen
    await page.getByRole('button', { name: /^Category:/ }).click();
    await expect(page.getByRole('dialog', { name: 'Category' }).getByRole('group', { name: 'Category' })).toBeVisible();
    await page.getByRole('dialog', { name: 'Category' }).getByRole('button', { name: 'Done' }).click();

    await tabbar.getByRole('link', { name: 'Add' }).click();
    await expect(page.getByRole('button', { name: 'Take photo' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Choose from library' })).toBeVisible();
    await expect(page.getByTestId('camera-input')).toHaveAttribute('capture', 'environment');
  });
});

test.describe('desktop', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('sidebar, grid and detail panel side by side', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    await expect(page.locator('nav.tabbar')).toBeHidden();
    const sidebar = page.locator('nav.sidebar');
    await expect(sidebar).toBeVisible();
    await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
    await expect(page).toHaveURL(/\/item\//);
    const panel = page.locator('aside.detail-panel');
    await panel.getByRole('button', { name: /^Category:/ }).click();
    await expect(panel.getByRole('group', { name: 'Category' })).toBeVisible();

    const s = (await sidebar.boundingBox())!;
    const g = (await page.locator('section.closet-main').boundingBox())!;
    const p = (await panel.boundingBox())!;
    expect(s.x + s.width).toBeLessThanOrEqual(g.x);
    expect(g.x + g.width).toBeLessThanOrEqual(p.x);
    expect(p.x + p.width).toBeLessThanOrEqual(1440);
    // all three share the top of the screen
    expect(Math.abs(g.y - p.y)).toBeLessThan(40);
    expect(s.y).toBeLessThan(10);

    // keyboard: the selected tile and the panel's chips are reachable
    await expect(page.getByTestId('tile').filter({ hasText: 'Navy polo' })).toHaveAttribute('aria-current', 'true');
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeVisible();

    await sidebar.getByRole('link', { name: 'Add' }).click();
    await expect(page.getByTestId('dropzone')).toBeVisible();
  });
});
