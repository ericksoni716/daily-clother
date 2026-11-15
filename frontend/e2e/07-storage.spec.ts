import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings show how much space the demo closet takes', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();

  // storage is part of "Your closet", with the demo switch and the backups
  const closet = page.getByRole('region', { name: 'Your closet' });
  await expect(closet.getByRole('switch', { name: /Show the demo closet/ })).toBeChecked();
  await expect(closet.getByRole('region', { name: 'Backups' })).toBeVisible();
  const section = closet.getByRole('region', { name: 'Storage' });
  await expect(section.getByTestId('storage-total')).toHaveText(/^[\d.]+ (KB|MB|GB)$/);
  await expect(section.getByTestId('storage-total')).not.toHaveText(/^0 /);
  await expect(section.getByText('used by 49 items')).toBeVisible();
  for (const row of ['Photos', 'Cutouts', 'Thumbnails', 'Backups on this computer', 'Background-removal model', 'Everything else']) {
    await expect(section.getByText(row, { exact: true })).toBeVisible();
  }
  await expect(section.getByText(/free on this disk/)).toBeVisible();
});

test('settings: one column beside the sidebar, the technical parts folded under Advanced, Log out and Quit at the end', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/settings');
  const groups = ['Your closet', 'Where you are', 'How you live', 'Look', 'Describing clothes', 'Phone access'];
  for (const name of groups) await expect(page.getByRole('region', { name, exact: true })).toBeVisible();
  const tops = await Promise.all(groups.map(async (name) => (await page.getByRole('region', { name, exact: true }).boundingBox())!.y));
  expect(tops).toEqual([...tops].sort((a, b) => a - b));

  const sidebar = (await page.locator('nav.sidebar').boundingBox())!;
  const column = (await page.locator('.settings').boundingBox())!;
  expect(column.width).toBeLessThanOrEqual(720);
  expect(column.x - (sidebar.x + sidebar.width)).toBeLessThan(40);   // left-aligned beside the sidebar, not centred

  // Advanced is closed until opened: the model's download address, the data folder and the version
  const advanced = page.locator('details#s-advanced');
  await expect(advanced).not.toHaveAttribute('open');
  await expect(page.getByLabel('Download address')).toBeHidden();
  await advanced.getByText('Advanced', { exact: true }).click();
  await expect(advanced.getByLabel('Download address')).toBeVisible();
  await expect(advanced.getByText('Your closet is stored in')).toBeVisible();
  await expect(advanced.getByText('Version', { exact: true })).toBeVisible();

  // Log out and Quit are a row after the last group, not a card
  const leave = page.getByRole('group', { name: 'Leave' });
  await expect(leave.getByRole('button', { name: 'Log out' })).toBeVisible();
  await expect(leave.getByRole('button', { name: 'Quit Closet' })).toBeVisible();
  expect(await leave.evaluate((el) => el.classList.contains('card'))).toBe(false);
  expect((await leave.boundingBox())!.y).toBeGreaterThan((await advanced.boundingBox())!.y);
});
