import { expect, PASS, PHOTOS, test } from './fixtures';
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
    await expect(page.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();

    // the grid picks up the name once the description arrives, without a reload
    const tile = page.getByTestId('tile').first();
    await expect(tile).toContainText('Navy polo', { timeout: 60_000 });

    await tile.click();
    const detail = page.locator('.detail-panel');
    await expect(detail.getByText("Suggested by Claude; change anything that's wrong.")).toBeVisible();
    await expect(detail.getByRole('textbox', { name: 'Name' })).toHaveValue('Navy polo');
    const seen = detail.locator('details', { hasText: 'What Claude saw' });
    await expect(seen.getByText('embroidered chest logo')).toBeHidden();   // folded away until opened
    await seen.getByText('What Claude saw').click();
    await expect(seen.getByText('Seen but not drawn yet')).toBeVisible();
    await expect(seen.getByText('embroidered chest logo')).toBeVisible();
    await expect(seen.getByText('Flat knit')).toBeVisible();

    await detail.getByRole('button', { name: 'Describe it again' }).click();
    await expect(page.getByText('Asking Claude to describe it again')).toBeVisible();
    await expect(detail.getByText("Suggested by Claude; change anything that's wrong.")).toBeVisible({ timeout: 30_000 });

    await page.goto(backend.url + '/settings');
    const section = page.getByRole('region', { name: 'Tagging' });
    await expect(section.getByTestId('tags-waiting')).toHaveText('No items are waiting to be described.');
    const allow = section.getByRole('switch', { name: /Allow the API key/ });
    await expect(allow).not.toBeChecked();
  });
});
