import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings show how much space the demo closet takes', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();

  const section = page.getByRole('region', { name: 'Storage' });
  await expect(section.getByTestId('storage-total')).toHaveText(/^[\d.]+ (KB|MB|GB)$/);
  await expect(section.getByTestId('storage-total')).not.toHaveText(/^0 /);
  await expect(section.getByText('used by 30 items')).toBeVisible();
  for (const row of ['Photos', 'Cutouts', 'Thumbnails', 'Backups on this computer', 'Background-removal model', 'Everything else']) {
    await expect(section.getByText(row, { exact: true })).toBeVisible();
  }
  await expect(section.getByText(/free on this disk/)).toBeVisible();
});
