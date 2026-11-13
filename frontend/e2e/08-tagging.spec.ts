import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings show which routes to Claude can be used, in order', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();

  const section = page.getByRole('region', { name: 'Tagging' });
  await expect(section.getByText('tries these in this order')).toBeVisible({ timeout: 20_000 });
  const routes = section.getByRole('listitem');
  await expect(routes).toHaveCount(2);
  await expect(routes.nth(0)).toContainText('Your Claude plan, through Claude Code');
  await expect(routes.nth(1)).toContainText('An API key');
  await expect(section.getByRole('button', { name: 'Check again' })).toBeVisible();
});
