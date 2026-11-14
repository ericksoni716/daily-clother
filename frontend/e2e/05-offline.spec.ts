import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('offline: the saved closet still opens, read-only, with a banner', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  // load once while the service worker is in charge so the data and pictures are saved
  await page.reload();
  await expect(page.getByTestId('tile')).toHaveCount(49);
  // open one item while online, so its full details are saved too
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  await expect(page.locator('.detail-panel').getByRole('button', { name: /^What is it\?:/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByTestId('tile')).toHaveCount(49);
  // pictures came from the saved copy
  const loaded = await page.locator('.tile img').first().evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0);
  expect(loaded).toBe(true);

  // adding is disabled with an explanation
  const add = page.locator('nav.sidebar').getByText('Add');
  await expect(add).toHaveAttribute('aria-disabled', 'true');
  await expect(page.locator('nav.sidebar [aria-disabled="true"]')).toHaveAttribute('title', /needs Closet on your computer/);

  // editing is disabled too (the page reloaded on the saved item)
  const panel = page.locator('.detail-panel');
  await expect(panel.getByText("You're offline, so this item can't be changed right now.")).toBeVisible();
  await expect(panel.getByRole('button', { name: /^What is it\?:/ })).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Archive' })).toBeDisabled();

  // an item never opened before still shows what the closet knows about it
  await page.getByTestId('tile').filter({ hasText: 'Grey hoodie' }).click();
  await expect(panel.getByText(/You're offline, so this item can't be changed right now/)).toBeVisible();
  await expect(panel.getByRole('heading', { name: 'Grey hoodie' })).toBeVisible();

  // back online: the banner goes away by itself
  await context.setOffline(false);
  await expect(page.getByText('Offline: showing your saved closet')).toBeHidden({ timeout: 15_000 });
});

test('logging out clears the saved closet', async ({ page }) => {
  await login(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.reload();
  await expect(page.locator('#closet-title')).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await page.evaluate(async () => (await caches.keys()).includes('closet-data'))).toBe(true);
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  const names = await page.evaluate(() => caches.keys());
  expect(names.filter((n) => n === 'closet-data' || n === 'closet-media')).toEqual([]);
});
