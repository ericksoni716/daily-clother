import { expect, PASS, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend, with stand-ins for the model and for Claude: nothing here reaches the real Claude.
test.describe('the drawing, with a stand-in for Claude', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a new item gets its drawing, which follows a change of colour', async ({ page }) => {
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

    const tile = page.getByTestId('tile').first();
    await expect(tile).toContainText('Navy polo', { timeout: 60_000 });
    await tile.click();

    const detail = page.locator('.detail-panel');
    const picture = detail.getByRole('group', { name: 'Picture' });
    await expect(picture.getByRole('button', { name: 'Cutout' })).toHaveAttribute('aria-pressed', 'true');
    await picture.getByRole('button', { name: 'Drawing' }).click();
    const drawing = detail.getByRole('img', { name: 'Navy polo, drawing' });
    await expect(drawing).toBeVisible();
    const before = await drawing.getAttribute('src');
    const notes = detail.getByRole('region', { name: 'Not in the drawing' });
    await expect(notes.getByText('Embroidered chest logo')).toBeVisible();

    // the owner's colour wins over Claude's, and the drawing follows it
    const stored = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/items/') && r.ok());
    await detail.getByRole('group', { name: 'Colour' }).getByRole('button', { name: 'Red' }).click();
    await stored;
    await expect(drawing).not.toHaveAttribute('src', before!);
    const svg = await page.request.get(backend.url + (await drawing.getAttribute('src'))!);
    expect((await svg.text()).toLowerCase()).toContain('#b8322e');

    // the grid can show drawings instead of photos, remembered on this device
    const show = page.getByRole('group', { name: 'Show' });
    await expect(show.getByRole('button', { name: 'Photos' })).toHaveAttribute('aria-pressed', 'true');
    await show.getByRole('button', { name: 'Drawings' }).click();
    await expect(tile.getByRole('img', { name: 'Navy polo, drawing' })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Drawings' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('tile').first().getByRole('img', { name: 'Navy polo, drawing' })).toBeVisible();
  });
});
