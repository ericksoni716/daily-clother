import { expect, PHOTOS, test } from './fixtures';
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
    await expect(page.locator('#closet-title')).toBeVisible();

    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
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
    await expect(recorded).toContainText('[a path outside Nines]');
    await expect(recorded).not.toContainText('sk-ant');
    await expect(recorded).not.toContainText('someone');

    await detail.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByText('Asking Claude to describe it again')).toBeVisible();
    const id = new URL(page.url()).pathname.split('/').at(-1)!;
    await expect.poll(async () => (await (await page.request.get(`${backend.url}/api/items/${id}`)).json()).tag_state,
      { timeout: 30_000 }).toBe('done');
    await expect(detail.getByTestId('look-line')).toHaveText(/ · Navy/);
    await expect(detail.getByTestId('failure-details')).toHaveCount(0);
  });
});
