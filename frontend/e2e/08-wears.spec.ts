import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('wear log and laundry in the demo closet: wear, undo, laundry and back', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const tile = page.getByTestId('tile').filter({ hasText: 'Chambray shirt' });
  await tile.click();
  const panel = page.locator('.detail-panel');
  const summary = panel.getByTestId('wear-summary');
  // the demo closet's history: worn once, a week ago
  await expect(summary).toHaveText(/^Worn once, on /);

  await panel.getByRole('button', { name: 'Wore it today' }).click();
  await expect(summary).toHaveText('Worn 2 times, last today');
  await expect(panel.getByText('Worn today', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Remove the wear: Today' })).toBeVisible();

  await panel.getByRole('button', { name: 'Undo' }).click();
  await expect(summary).toHaveText(/^Worn once, on /);
  await expect(panel.getByRole('button', { name: 'Wore it today' })).toBeVisible();

  // into the laundry: the tile gets a mark and the laundry filter finds it
  await expect(tile.getByTestId('laundry-mark')).toHaveCount(0);
  await panel.getByRole('button', { name: 'Put in the laundry' }).click();
  await expect(panel.getByTestId('laundry-state')).toHaveText(/^In the laundry/);
  await expect(tile.getByTestId('laundry-mark')).toBeVisible();
  // the laundry filter is in the Filter popover, which closes when something else is clicked
  const filterButton = page.getByRole('button', { name: /^Filter/ });
  const filter = page.getByRole('group', { name: 'Filter by laundry' });
  const chooseLaundry = async (name: string) => {
    if ((await filterButton.getAttribute('aria-expanded')) !== 'true') await filterButton.click();
    await filter.getByRole('button', { name }).click();
  };
  await chooseLaundry('In the laundry');
  await expect(tile).toHaveCount(1);
  const inLaundry = await page.getByTestId('tile').count();
  expect(inLaundry).toBeLessThan(49);
  await expect(page.getByTestId('laundry-mark')).toHaveCount(inLaundry);

  // and back
  await panel.getByRole('button', { name: "It's clean" }).click();
  await expect(panel.getByTestId('laundry-state')).toHaveText(/^Clean/);
  await expect(tile).toHaveCount(0);
  await chooseLaundry('Clean');
  await expect(tile).toHaveCount(1);
  await expect(page.getByTestId('laundry-mark')).toHaveCount(0);
  await chooseLaundry('Clean');
  await expect(page.getByTestId('tile')).toHaveCount(49);
});

test('offline: the wear and laundry buttons are disabled and say why', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.reload();
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
  await expect(panel.getByRole('button', { name: 'Wore it today' })).toBeEnabled();
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  for (const name of ['Wore it today', 'Put in the laundry']) {
    const button = panel.getByRole('button', { name });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute('title', /needs Closet on your computer/i);
  }
});
