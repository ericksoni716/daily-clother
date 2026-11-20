import { expect, openFold, PASS, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend, with stand-ins for the model and for Claude: nothing here reaches the real Claude.
test.describe('with a stand-in for Claude', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a new item is described by itself, and can be described again', async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();

    // the grid picks up the name once the description arrives, without a reload
    const tile = page.getByTestId('tile').first();
    await expect(tile).toContainText('Navy polo', { timeout: 60_000 });

    await tile.click();
    const detail = page.locator('.detail-panel');
    await expect(detail.getByRole('textbox', { name: 'Name' })).toHaveValue('Navy polo');
    // one line under the name, from the description the drawing was made from ("What Claude saw" is gone: the
    // details one by one show the same values, and what was seen but not drawn is a mark on the drawing)
    await expect(detail.getByTestId('look-line')).toHaveText(/ · Navy.* · Short sleeves$/);
    await detail.getByRole('group', { name: 'Picture' }).getByRole('button', { name: 'Drawing' }).click();
    await detail.getByRole('button', { name: 'Not in the drawing' }).click();
    await expect(page.getByRole('dialog', { name: 'Not in the drawing' }).getByText(/embroidered chest logo/i)).toBeVisible();
    await page.keyboard.press('Escape');
    await detail.getByRole('button', { name: 'Something wrong? Tell Claude' }).click();
    const sheet = page.getByRole('dialog', { name: 'Fix the details' });
    await sheet.getByRole('button', { name: 'Change the details one by one' }).click();
    await expect(sheet.getByTestId('described-by')).toHaveText(/^Described with your Claude plan on .*\.$/);
    await expect(sheet.getByRole('button', { name: /^Collar: flat knit/ })).toBeVisible();
    await page.keyboard.press('Escape');

    const id = new URL(page.url()).pathname.split('/').at(-1)!;
    const described = async () => (await (await page.request.get(`${backend.url}/api/items/${id}`)).json()).tag_state;
    await openFold(detail, 'Describe it again, archive or delete');
    await detail.getByRole('button', { name: 'Describe it again' }).click();
    await expect(page.getByText('Asking Claude to describe it again')).toBeVisible();
    await expect.poll(described, { timeout: 30_000 }).toBe('done');
    await expect(detail.getByTestId('look-line')).toHaveText(/ · Navy.* · Short sleeves$/);

    await page.goto(backend.url + '/settings/advanced');
    const section = page.getByRole('region', { name: 'Claude' });
    await expect(section.getByTestId('route-plan')).toBeVisible();
    // nothing is waiting, so nothing is said about it (step 6 removed "No items are waiting")
    await expect(section.getByTestId('tags-waiting')).toHaveCount(0);
    const allow = section.getByRole('switch', { name: /Allow the API key/ });
    await expect(allow).not.toBeChecked();
  });
});
