import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

/** A synthetic photo of three pieces laid out (coloured shapes, as conftest.pile_bytes draws them), made in the page. */
async function pilePhoto(page: import('@playwright/test').Page): Promise<Buffer> {
  const base64 = await page.evaluate(() => {
    const c = document.createElement('canvas');
    c.width = 1200;
    c.height = 900;
    const g = c.getContext('2d')!;
    g.fillStyle = '#ebe8e1';
    g.fillRect(0, 0, 1200, 900);
    const pieces: [number, number, number, number, string][] = [
      [0.05, 0.10, 0.30, 0.60, '#be2828'], [0.40, 0.10, 0.65, 0.90, '#1e46aa'], [0.72, 0.30, 0.95, 0.70, '#28963c'],
    ];
    for (const [x0, y0, x1, y1, color] of pieces) {
      g.fillStyle = color;
      g.fillRect(x0 * 1200, y0 * 900, (x1 - x0) * 1200, (y1 - y0) * 900);
    }
    return c.toDataURL('image/png').split(',')[1];
  });
  return Buffer.from(base64, 'base64');
}

// Its own backend, with stand-ins for the model and for Claude: Claude "finds" a red piece, a blue one and a green one.
test.describe('several items from one photo', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('find the pieces, remove one, fit another, and add them', async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/add');
    await page.getByRole('button', { name: 'Several items per photo' }).click();
    await expect(page.getByTestId('several-intro')).toContainText('Claude finds each piece');
    await page.getByTestId('library-input').setInputFiles({ name: 'pile.png', mimeType: 'image/png', buffer: await pilePhoto(page) });

    // the one photo is in: its pieces are checked straight away, once Claude has found them
    await expect(page).toHaveURL(/\/add\/several\//, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'Check the pieces' })).toBeVisible();
    const boxes = page.getByTestId('several-box');
    await expect(boxes).toHaveCount(3, { timeout: 30_000 });
    const pieces = page.getByTestId('several-piece');
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/]);
    await expect(page.getByTestId('several-add')).toHaveText('Add these 3 items');

    // the green scarf is not wanted
    await page.getByRole('button', { name: 'Remove box 3' }).click();
    await expect(boxes).toHaveCount(2);
    await expect(page.getByTestId('several-add')).toHaveText('Add these 2 items');

    // the red box is made bigger by dragging its lower right corner
    const red = boxes.first();
    const before = (await red.boundingBox())!;
    await red.click();
    const handle = red.getByTestId('handle-se');
    await expect(handle).toBeVisible();
    const h = (await handle.boundingBox())!;
    await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 30, h.y + h.height / 2 + 20, { steps: 5 });
    const saved = page.waitForResponse((r) => r.request().method() === 'PUT' && r.url().includes('/boxes/'));
    await page.mouse.up();
    expect((await saved).status()).toBe(200);
    const after = (await red.boundingBox())!;
    expect(after.width).toBeGreaterThan(before.width + 20);
    expect(after.height).toBeGreaterThan(before.height + 10);
    await page.reload();   // kept by Closet, not just moved on the screen
    await expect(boxes).toHaveCount(2);
    expect((await boxes.first().boundingBox())!.width).toBeGreaterThan(before.width + 20);

    // the photo is listed on Add until its pieces are added
    await page.goto(backend.url + '/add');
    await expect(page.getByTestId('several-open')).toContainText('2 pieces to check');
    await page.getByTestId('several-open').click();

    await page.getByTestId('several-add').click();
    await expect(page).toHaveURL(backend.url + '/');
    const tiles = page.getByTestId('tile');
    await expect(tiles).toHaveCount(2);
    // each is cut out and described like any other photo
    await expect(tiles.nth(0)).toContainText('Navy polo', { timeout: 60_000 });
    await expect(tiles.nth(1)).toContainText('Navy polo', { timeout: 60_000 });

    await page.goto(backend.url + '/add');
    await expect(page.getByTestId('several-open')).toHaveCount(0);
  });
});
