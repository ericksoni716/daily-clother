import { expect, login, test, useProfile } from './fixtures';

let archived: string | null = null;

test.afterEach(async ({ page }) => {
  // Put the archived piece back so later runs (and specs) find the demo closet as it was.
  if (archived) await page.request.patch(`/api/items/${archived}`, { data: { status: 'active' } });
  archived = null;
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('insights in the demo closet: a cost per wear, and archiving a piece never worn', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');

  await page.getByRole('link', { name: 'Insights' }).click();
  await expect(page).toHaveURL(/\/insights$/);
  await expect(page.locator('#insights-title')).toBeVisible();

  const cost = page.getByTestId('cost-per-wear');
  await expect(cost.getByText(/\$[\d,]+\.\d\d a wear/).first()).toBeVisible();
  await expect(page.getByTestId('cost-best')).toHaveText(/^Your .+ cost \$[\d,]+\.\d\d a wear over \d+ wears?\.$/);

  const never = page.getByTestId('never-worn');
  const pieces = never.getByTestId('insight-piece');
  await expect(pieces.first()).toBeVisible();
  const before = await pieces.count();
  const href = await pieces.first().getByRole('link').getAttribute('href');
  archived = href!.split('/').pop()!;

  await pieces.first().getByRole('button', { name: /^Archive / }).click();
  await expect(page.getByText(/^Archived\./)).toBeVisible();
  await expect(pieces).toHaveCount(before - 1);
  await expect(never.locator(`a[href$="${archived}"]`)).toHaveCount(0);

  const item = await (await page.request.get(`/api/items/${archived}`)).json();
  expect(item.status).toBe('archived');

  // "Keep" hides a piece on this device, and it can be shown again.
  await pieces.first().getByRole('button', { name: /^Keep / }).click();
  await expect(pieces).toHaveCount(before - 2);
  await never.getByRole('button', { name: 'Show again' }).click();
  await expect(pieces).toHaveCount(before - 1);
});
