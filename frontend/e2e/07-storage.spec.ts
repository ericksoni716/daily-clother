import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings show how much space the demo closet takes, on the Advanced screen', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/settings/advanced');

  // the demo switch is with the closet; backups and storage are groups of their own
  const closet = page.getByRole('region', { name: 'Your closet' });
  await expect(closet.getByRole('switch', { name: /Show the demo closet/ })).toBeChecked();
  await expect(page.getByRole('region', { name: 'Backups' })).toBeVisible();
  const section = page.getByRole('region', { name: 'Storage' });
  await expect(section.getByTestId('storage-line')).toHaveText(/^Closet uses [\d.]+ (KB|MB|GB) for 49 items · .+ free on this disk\.$/);
  await expect(section.getByTestId('storage-line')).not.toHaveText(/^Closet uses 0 /);
  // the breakdown is folded under the one line
  await expect(section.getByText('Photos', { exact: true })).toBeHidden();
  await section.getByText('What takes the space').click();
  for (const row of ['Photos', 'Cutouts', 'Thumbnails', 'Backups on this computer', 'Background-removal model', 'Everything else']) {
    await expect(section.getByText(row, { exact: true })).toBeVisible();
  }
});

test('settings: short groups in one column beside the sidebar, the technical parts on Advanced, Log out and Quit at the end', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/settings');
  const groups = ['Your style', 'Everyday', 'Claude', 'Updates', 'Phone', 'This device', 'Your data'];
  for (const name of groups) await expect(page.getByRole('region', { name, exact: true })).toBeVisible();
  const tops = await Promise.all(groups.map(async (name) => (await page.getByRole('region', { name, exact: true }).boundingBox())!.y));
  expect(tops).toEqual([...tops].sort((a, b) => a - b));

  const sidebar = (await page.locator('nav.sidebar').boundingBox())!;
  const column = (await page.locator('.settings').boundingBox())!;
  expect(column.width).toBeLessThanOrEqual(720);
  expect(column.x - (sidebar.x + sidebar.width)).toBeLessThan(40);   // left-aligned beside the sidebar, not centred

  // the technical parts are not on the page: they are on Advanced, a screen of its own
  await expect(page.getByLabel('Download address')).toHaveCount(0);
  await expect(page.getByText('Your closet is stored in')).toHaveCount(0);

  // Log out and Quit are a row after the last group, not a card
  const leave = page.getByRole('group', { name: 'Leave' });
  await expect(leave.getByRole('button', { name: 'Log out' })).toBeVisible();
  await expect(leave.getByRole('button', { name: 'Quit Closet' })).toBeVisible();
  expect(await leave.evaluate((el) => el.classList.contains('card'))).toBe(false);
  expect((await leave.boundingBox())!.y).toBeGreaterThan((await page.getByRole('region', { name: 'Your data' }).boundingBox())!.y);

  await page.getByRole('link', { name: 'Advanced settings' }).click();
  await expect(page).toHaveURL(/\/settings\/advanced$/);
  await expect(page.getByLabel('Download address')).toBeVisible();
  await expect(page.getByText('Your closet is stored in')).toBeVisible();
  await expect(page.getByText('Version', { exact: true })).toBeVisible();
});

test('the Advanced screen: opened from Settings, kept through a reload, and Back and "‹ Settings" return to Settings', async ({ page }) => {
  await login(page);
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: 'Advanced settings' }).click();
  await expect(page).toHaveURL(/\/settings\/advanced$/);
  await expect(page.getByRole('heading', { name: 'Advanced', level: 1 })).toBeVisible();
  // the sidebar still lights Settings
  await expect(page.locator('nav.sidebar [aria-current="page"]')).toHaveText(/Settings/);

  // a reload opens the same screen, not Settings or the closet
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Advanced', level: 1 })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Claude' })).toBeVisible();

  // Back goes to Settings, Forward to Advanced again
  await page.goBack();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'Advanced', level: 1 })).toBeVisible();

  // "‹ Settings" goes back in history rather than adding a page to it
  await expect(page.locator('.page-back')).toHaveText(/Settings/);
  const before = await page.evaluate(() => history.length);
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/settings$/);
  expect(await page.evaluate(() => history.length)).toBe(before);
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'Advanced', level: 1 })).toBeVisible();

  // opened straight from its address, "‹ Settings" takes its place
  await page.goto('/settings/advanced');
  await page.locator('.page-back').click();
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
});
