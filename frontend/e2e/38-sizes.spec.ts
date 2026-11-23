import { expect, goToCloset, test } from './fixtures';

test.afterEach(async ({ page }) => {
  for (const kind of ['tops', 'trousers']) await page.request.put(`/api/sizes/${kind}`, { data: { size: '' } });
  await page.request.put('/api/sizes/tops/brand', { data: { brand: 'Example Brand', size: '' } });
});

test('Your sizes: a box saved as you leave it, a brand that fits differently, and the line in Settings', async ({ page }) => {
  await goToCloset(page);
  await page.goto('/settings');
  const everyday = page.locator('section[aria-labelledby="s-everyday"]');
  await expect(everyday.getByTestId('sizes-line')).toHaveText('Your sizes are not saved yet.');
  await everyday.getByRole('button', { name: 'Change your sizes' }).click();
  const sheet = page.getByTestId('sizes-sheet');

  await sheet.getByLabel('Tops').fill('M');
  await sheet.getByLabel('Trousers and jeans').click();   // leaving the box saves it
  await expect(sheet.getByTestId('size-tops').getByRole('status')).toHaveText('Saved');
  await sheet.getByLabel('Trousers and jeans').fill('32x32');
  await sheet.getByLabel('Trousers and jeans').press('Enter');
  await expect(sheet.getByTestId('size-trousers').getByRole('status')).toHaveText('Saved');

  await sheet.getByRole('button', { name: 'A brand that fits differently' }).click();
  const form = sheet.getByTestId('brand-size-form');
  await form.getByLabel('Brand').fill('Example Brand');
  await form.getByLabel('Your size in it').fill('L');
  await form.getByRole('button', { name: 'Save' }).click();
  await expect(sheet.getByTestId('size-tops')).toContainText('In Example Brand, L');

  // on a wide screen the sheet opens in place and the button that opened it closes it
  await everyday.getByRole('button', { name: 'Done' }).click();
  await expect(sheet).toBeHidden();
  await expect(everyday.getByTestId('sizes-line')).toHaveText('Your sizes: M tops · 32x32 trousers');
  await page.reload();
  await expect(everyday.getByTestId('sizes-line')).toHaveText('Your sizes: M tops · 32x32 trousers');
});
