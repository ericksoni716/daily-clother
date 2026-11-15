import { expect, login, test, useProfile } from './fixtures';

test.use({ serviceWorkers: 'block' });

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('a list requested before an edit cannot replace the saved item', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const tile = page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' });
  await expect(tile).toBeVisible();
  const original = (await (await page.request.get('/api/items')).json()).items.find(
    (item: { name: string }) => item.name === 'Oatmeal henley',
  ) as { id: string; name: string };
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/items?status=active', async (route) => {
    const response = await route.fetch();
    await waiting;
    await route.fulfill({ response });
  }, { times: 1 });

  try {
    await page.getByRole('link', { name: 'Settings', exact: true }).filter({ visible: true }).click();
    const requested = page.waitForRequest('**/api/items?status=active', { timeout: 10_000 });
    await page.getByRole('link', { name: /^Closet/ }).filter({ visible: true }).click();
    await requested;
    await tile.click();
    const name = page.getByRole('textbox', { name: 'Name', exact: true });
    await name.fill('Review race updated');
    const saved = page.waitForResponse((response) => response.request().method() === 'PATCH' && response.ok());
    await name.press('Enter');
    await saved;
    await expect(page.getByTestId('tile').filter({ hasText: 'Review race updated' })).toBeVisible();

    const answered = page.waitForResponse('**/api/items?status=active');
    release();
    await answered;
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('tile').filter({ hasText: 'Review race updated' })).toBeVisible();
    await expect(page.getByTestId('tile').filter({ hasText: original.name })).toHaveCount(0);
  } finally {
    release();
    await page.request.patch(`/api/items/${original.id}`, { data: { name: original.name } });
  }
});

test('browser Back saves a text field without waiting for blur', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
  const id = new URL(page.url()).pathname.split('/').at(-1)!;
  const original = await (await page.request.get(`/api/items/${id}`)).json();
  try {
    await page.locator('.detail-panel').getByText('More details').click();
    const notes = page.getByRole('textbox', { name: 'Notes', exact: true });
    await notes.fill('Saved by browser Back');
    await expect(notes).toBeFocused();
    await page.goBack();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await expect.poll(async () => (await (await page.request.get(`/api/items/${id}`)).json()).notes)
      .toBe('Saved by browser Back');
  } finally {
    await page.request.patch(`/api/items/${id}`, { data: { notes: original.notes } });
  }
});
