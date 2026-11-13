import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

// A change made a moment before the page is reloaded or closed is kept: the save is sent so that it
// outlives the page, and an edit still being typed is saved as the page goes away.
test('edit, reload at once: the edit is there', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
  const panel = page.locator('.detail-panel');
  const notes = () => page.locator('.detail-panel').getByRole('textbox', { name: 'Notes', exact: true });

  // a chip: reload straight after the tap, without waiting for the answer
  const formality = panel.getByRole('group', { name: 'Formality' });
  await expect(formality).toBeVisible();
  const target = (await formality.getByRole('button', { name: 'Casual', exact: true }).getAttribute('aria-pressed')) === 'true'
    ? 'Smart casual' : 'Casual';
  await formality.getByRole('button', { name: target, exact: true }).click();
  await page.reload();
  await expect(page.locator('.detail-panel').getByRole('group', { name: 'Formality' }).getByRole('button', { name: target, exact: true }))
    .toHaveAttribute('aria-pressed', 'true');

  // notes still being typed (the field never left): reload at once
  const note = `Kept through a reload ${Date.now()}`;
  await page.locator('.detail-panel').getByText('More details').click();
  await notes().fill(note);
  await page.reload();
  await page.locator('.detail-panel').getByText('More details').click();
  await expect(notes()).toHaveValue(note);

  // and the same when the page is closed instead
  const closing = `Kept through closing ${Date.now()}`;
  await notes().fill(closing);
  const items = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  const id = items.find((x) => x.name === 'Oatmeal henley')!.id;
  const request = page.context().request;
  await page.close();
  await expect.poll(async () => (await (await request.get(`/api/items/${id}`)).json()).notes).toBe(closing);
});
