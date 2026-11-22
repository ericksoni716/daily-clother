import { expect, goToCloset, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings show which routes to Claude can be used, in order', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  // Settings says it in one line, and Manage opens the details on the Advanced screen
  await expect(page.getByTestId('claude-line')).not.toHaveText(/Checking/, { timeout: 20_000 });
  await page.getByRole('region', { name: 'Claude' }).getByRole('link', { name: 'Manage how Nines reaches Claude' }).click();
  await expect(page).toHaveURL(/\/settings\/advanced$/);

  const section = page.getByRole('region', { name: 'Claude' });
  await expect(section.getByText('tries these in this order')).toBeVisible({ timeout: 20_000 });
  const routes = section.getByRole('listitem');
  await expect(routes).toHaveCount(2);
  await expect(routes.nth(0)).toContainText('Your Claude plan, through Claude Code');
  await expect(routes.nth(1)).toContainText('An API key');
  await expect(section.getByRole('button', { name: 'Check again' })).toBeVisible();
});
