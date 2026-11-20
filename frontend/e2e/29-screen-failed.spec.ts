import { expect, login, test } from './fixtures';

// One screen that fails to draw no longer blanks the app (docs/assessment/ux-pages.md, finding H).

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

test('a screen that fails to draw says so, keeps the tab bar, and leaving it clears the message', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await login(page);
  // an answer of a shape the screen cannot draw
  await page.route('**/api/insights', (route) => route.fulfill({ json: { nothing: 'expected' } }));
  await page.goto('/wardrobe');

  const alert = page.getByRole('alert').filter({ hasText: 'Something went wrong on this screen.' });
  await expect(alert).toBeVisible();
  await expect(alert.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(alert.getByRole('button', { name: 'Reload Closet' })).toBeVisible();
  expect(errors.some((e) => e.includes('Closet could not show this screen'))).toBe(true);

  await page.screenshot({ path: testInfo.outputPath('screen-failed-phone.png') });
  const tabbar = page.locator('nav.tabbar');
  await expect(tabbar).toBeVisible();
  await tabbar.getByRole('link', { name: 'Closet' }).click();
  await expect(page.locator('#closet-title')).toBeVisible();
  await expect(alert).toHaveCount(0);
});
