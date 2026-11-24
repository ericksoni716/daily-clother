import { expect, goToCloset, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('settings say how Nines reaches Claude, then the plan and the API key, each with its line', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  // Settings says it in one line, and Manage opens the details on the Advanced screen
  await expect(page.getByTestId('claude-line')).not.toHaveText(/Checking/, { timeout: 20_000 });
  await page.getByRole('region', { name: 'Claude' }).getByRole('link', { name: 'Manage how Nines reaches Claude' }).click();
  await expect(page).toHaveURL(/\/settings\/advanced$/);

  const section = page.getByRole('region', { name: 'Claude' });
  // one first line saying how Nines reaches Claude, with Check again beside it
  await expect(section.getByTestId('claude-lead')).not.toHaveText(/Checking/, { timeout: 20_000 });
  await expect(section.getByRole('button', { name: 'Check again' })).toBeVisible();
  await expect(section.getByTestId('route-plan').getByRole('heading', { name: 'Your Claude plan', level: 3 })).toBeVisible();
  await expect(section.getByTestId('route-api').getByRole('heading', { name: 'An API key', level: 3 })).toBeVisible();
  const tops = await Promise.all(['claude-lead', 'route-plan', 'route-api'].map(async (id) => (await section.getByTestId(id).boundingBox())!.y));
  expect(tops).toEqual([...tops].sort((a, b) => a - b));
});
