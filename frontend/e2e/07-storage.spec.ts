import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('Settings shows demo storage on desktop and phone, then refreshes for the real closet', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'Storage', exact: true });
  const total = section.getByTestId('storage-total');
  await expect(total).toHaveText(/[1-9]\d*(?:\.\d+)? (?:KB|MB|GB)/);
  await expect(section).toContainText('30 items');
  for (const label of ['Photos', 'Cutouts', 'Thumbnails', 'Backups', 'Background-removal model', 'Everything else']) {
    await expect(section.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(section).toContainText('free on the disk');
  const demoTotal = await total.textContent();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(total).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.getByRole('switch', { name: /Show the demo closet/ }).click();
  await expect(page.locator('#closet-title')).toBeVisible();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(section).not.toContainText('30 items');
  await expect(total).not.toHaveText(demoTotal!);
});

test('Storage has loading, error, retry and offline states without breaking Settings', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/storage', async (route) => {
    await pending;
    await route.fulfill({ status: 503, json: { detail: 'Please try again.' } });
  });
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'Storage', exact: true });
  await expect(section.getByRole('status')).toHaveText('Measuring storage…');
  release();
  await expect(section.getByRole('alert')).toContainText('Storage is unavailable.');
  await expect(page.getByRole('heading', { name: 'About', exact: true })).toBeVisible();
  await page.unroute('**/api/storage');
  await section.getByRole('button', { name: 'Try again' }).click();
  await expect(section.getByTestId('storage-total')).toBeVisible();
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null);
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.reload();
  await expect(section).toContainText("Storage is unavailable while you're offline.");
  await expect(section.getByTestId('storage-total')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await context.setOffline(false);
  await expect(section.getByTestId('storage-total')).toBeVisible();
});
