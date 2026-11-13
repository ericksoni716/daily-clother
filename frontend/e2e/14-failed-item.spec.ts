import { expect, PASS, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend, whose stand-in for Claude fails the first three descriptions with a reason Closet does not know.
test.describe('an item whose description failed', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, tagFails: 3 });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('says why, with the details cleaned, and can be tried again', async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();
    await page.getByTestId('tile').first().click();

    const detail = page.locator('.detail-panel');
    await expect(detail.getByText("Claude couldn't describe this item.")).toBeVisible({ timeout: 60_000 });
    const more = detail.getByTestId('failure-details');
    const recorded = more.locator('pre');
    await expect(recorded).toBeHidden();   // folded away until opened
    await more.getByText('Details').click();
    await expect(recorded).toContainText('the stand-in was told to fail');
    await expect(recorded).toContainText('[hidden]');
    await expect(recorded).toContainText('[a path outside Closet]');
    await expect(recorded).not.toContainText('sk-ant');
    await expect(recorded).not.toContainText('someone');

    await detail.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByText('Asking Claude to describe it again')).toBeVisible();
    await expect(detail.getByText("Suggested by Claude; change anything that's wrong.")).toBeVisible({ timeout: 30_000 });
    await expect(detail.getByTestId('failure-details')).toHaveCount(0);
  });
});
