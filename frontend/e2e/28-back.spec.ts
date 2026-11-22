import { expect, goToCloset, test, useProfile } from './fixtures';

// "‹ Closet" goes Back: the closet comes back where you left it and history does not grow
// (docs/assessment/ux-items.md, "5. Page transitions").

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('the back link returns to the closet where you left it, without adding to history', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const tiles = page.getByTestId('tile');
  await expect(tiles.first()).toBeVisible();
  const count = await tiles.count();
  expect(count).toBeGreaterThan(8);
  const tile = tiles.nth(count - 2);
  await tile.scrollIntoViewIfNeeded();
  const scrolled = await page.evaluate(() => window.scrollY);
  expect(scrolled).toBeGreaterThan(400);
  const before = await page.evaluate(() => history.length);

  await tile.click();
  const back = page.locator('.detail-top').getByRole('link', { name: 'Closet' });
  await expect(back).toBeVisible();
  // the item page opens at its top
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  expect(await page.evaluate(() => history.length)).toBe(before + 1);

  await back.click();
  await expect(page.locator('#closet-title')).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(scrolled - 2);
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - scrolled)).toBeLessThanOrEqual(2);
  expect(await page.evaluate(() => history.length)).toBe(before + 1);

  // the browser's Forward goes to the item again, and Back to the closet where it was
  await page.goForward();
  await expect(back).toBeVisible();
  await page.goBack();
  await expect(page.locator('#closet-title')).toBeVisible();
  await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(Math.round(scrolled));
});

test('an item opened straight from its address goes back to the closet', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const href = await page.getByTestId('tile').first().getAttribute('href');
  expect(href).toMatch(/^\/item\//);

  await page.goto(href!);
  const back = page.locator('.detail-top').getByRole('link', { name: 'Closet' });
  await expect(back).toBeVisible();
  const length = await page.evaluate(() => history.length);
  await back.click();
  await expect(page.locator('#closet-title')).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/');
  // the closet took the item page's place
  expect(await page.evaluate(() => history.length)).toBe(length);
});
