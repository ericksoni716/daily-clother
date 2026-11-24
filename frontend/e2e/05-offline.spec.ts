import { expect, goToCloset, openFold, serviceWorkerInCharge, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('offline: the saved closet still opens, read-only, with a banner', async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  // load once while the service worker is in charge so the data and pictures are saved
  await page.reload();
  await expect(page.getByTestId('tile')).toHaveCount(49);
  // open one item while online, so its full details are saved too
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  await expect(page.locator('.detail-panel').getByRole('textbox', { name: 'Notes for you and Claude' })).toBeVisible();
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
  await expect(page.locator('nav.sidebar [aria-disabled="true"]')).toHaveAttribute('title', /needs Nines on your computer/);

  // editing is disabled too (the page reloaded on the saved item)
  const panel = page.locator('.detail-panel');
  // offline is said once, by the banner: the piece adds no sentence of its own saying it again (the review of 24
  // November, 30)
  await expect(panel.getByRole('heading').first()).toBeVisible();
  await expect(panel.getByText("You're offline, so this item can't be changed")).toHaveCount(0);
  await openFold(panel, 'Details');
  await expect(panel.getByRole('button', { name: /^What is it\?:/ })).toBeDisabled();
  await openFold(panel, 'Archive or delete');
  await expect(panel.getByRole('button', { name: 'Archive' })).toBeDisabled();

  // an item never opened before still shows what the closet knows about it
  await page.getByTestId('tile').filter({ hasText: 'Grey hoodie' }).click();
  await expect(panel.getByText('Its full details were not saved on this device.')).toBeVisible();
  await expect(panel.getByText("You're offline, so this item can't be changed")).toHaveCount(0);
  await expect(panel.getByRole('heading', { name: 'Grey hoodie' })).toBeVisible();

  // back online: the banner goes away by itself
  await context.setOffline(false);
  await expect(page.getByText('Offline: showing your saved closet')).toBeHidden({ timeout: 15_000 });
  await expect(panel.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Grey hoodie');
  await openFold(panel, 'Archive or delete');
  await expect(panel.getByRole('button', { name: 'Archive', exact: true })).toBeEnabled();
});

test('settings opened offline recover when the computer is reachable again', async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings', exact: true }).click();
  // what is Settings' own, in a few words: the banner says it is offline (the review of 24 November, 30)
  await expect(page.getByText('Your settings were not saved on this device.')).toBeVisible();
  await expect(page.locator('main')).not.toContainText("You're offline");
  // offline the saved copy is all this device has to show, so it cannot be forgotten then
  await page.getByTestId('saved-copies').locator('summary').click();
  await expect(page.getByRole('button', { name: 'Forget saved copies' })).toBeDisabled();
  await context.setOffline(false);
  await expect(page.getByText('Offline: showing your saved closet')).toBeHidden({ timeout: 15_000 });
  await expect(page.getByRole('switch', { name: 'Let Claude choose my outfits' })).toBeEnabled();
  await page.getByTestId('saved-copies').locator('summary').click();
  await expect(page.getByRole('button', { name: 'Forget saved copies' })).toBeEnabled();
});

test("forgetting this device's saved copies clears the saved closet, and the closet stays as it is", async ({ page }) => {
  await goToCloset(page);
  await serviceWorkerInCharge(page);
  await page.reload();
  await expect(page.locator('#closet-title')).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await page.evaluate(async () => (await caches.keys()).includes('closet-data'))).toBe(true);
  await page.evaluate(() => localStorage.setItem('closet-today-saved:outfits:main', '{}'));   // something Today kept
  await page.goto('/settings');
  const fold = page.getByTestId('saved-copies');
  await fold.locator('summary').click();
  await expect(fold).toContainText('Forgetting it leaves your closet on the computer as it is.');
  await fold.getByRole('button', { name: 'Forget saved copies' }).click();
  await expect(page.getByText('This device has forgotten its saved copies.')).toBeVisible();
  const names = await page.evaluate(() => caches.keys());
  expect(names.filter((n) => n === 'closet-data' || n === 'closet-media')).toEqual([]);
  expect(await page.evaluate(() => localStorage.getItem('closet-today-saved:outfits:main'))).toBeNull();
  expect(names.some((n) => n.startsWith('closet-shell-'))).toBe(true);   // the app itself still opens offline
  await expect(page.getByRole('region', { name: 'This device', exact: true })).toBeVisible();   // nothing to sign in to
  expect((await page.request.get('/api/items')).ok()).toBe(true);
});
