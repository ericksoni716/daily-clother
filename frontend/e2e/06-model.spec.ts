import { expect, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const model = process.env.CLOSET_E2E_MODEL;

test.describe('with the background-removal model', () => {
  test.skip(!model, 'Set CLOSET_E2E_MODEL to the model file to run this.');
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ model });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a real photo gets its cutout', async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto(backend.url + '/');
    await expect(page.locator('#closet-title')).toBeVisible();
    await expect(page.getByTestId('model-banner')).toHaveCount(0);

    await page.goto(backend.url + '/add');
    await expect(page.getByTestId('model-banner')).toHaveCount(0);
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();
    const tile = page.getByTestId('tile').first();
    await expect(tile.locator('img.pic-cutout')).toBeVisible({ timeout: 150_000 });
    await expect(tile.getByTestId('step-mark')).toHaveCount(0);

    await tile.click();
    const picture = page.locator('.detail-panel').getByRole('group', { name: 'Picture' });
    await expect(picture.getByRole('button', { name: 'Cutout' })).toHaveAttribute('aria-pressed', 'true');
  });
});
