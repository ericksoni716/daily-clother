import { axeViolations } from './a11y';
import { expect, test } from './fixtures';
import { startBackend, type Backend } from './server';

/** A synthetic photo of three pieces laid out (coloured shapes, as conftest.pile_bytes draws them), made in the page. */
async function pilePhoto(page: import('@playwright/test').Page, ground = '#ebe8e1'): Promise<Buffer> {
  const base64 = await page.evaluate((ground) => {
    const c = document.createElement('canvas');
    c.width = 1200;
    c.height = 900;
    const g = c.getContext('2d')!;
    g.fillStyle = ground;
    g.fillRect(0, 0, 1200, 900);
    const pieces: [number, number, number, number, string][] = [
      [0.05, 0.10, 0.30, 0.60, '#be2828'], [0.40, 0.10, 0.65, 0.90, '#1e46aa'], [0.72, 0.30, 0.95, 0.70, '#28963c'],
    ];
    for (const [x0, y0, x1, y1, color] of pieces) {
      g.fillStyle = color;
      g.fillRect(x0 * 1200, y0 * 900, (x1 - x0) * 1200, (y1 - y0) * 900);
    }
    return c.toDataURL('image/png').split(',')[1];
  }, ground);
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
    await expect(page.locator('#closet-title')).toBeVisible();

    await page.goto(backend.url + '/add');
    // one Add for everything: the photo is sorted as several pieces (a stand-in for Claude reads the file name) and
    // waits for the owner to check it
    await page.getByTestId('library-input').setInputFiles({ name: 'pile.png', mimeType: 'image/png', buffer: await pilePhoto(page) });
    await expect(page.getByTestId('tray-row').getByRole('combobox')).toHaveValue('pieces');
    await expect(page.getByTestId('tray-state')).toHaveText('1 photo of several pieces');
    await page.getByTestId('add-tray').getByRole('button', { name: 'Add it' }).click();

    // the one photo is in: its pieces are checked straight away, once Claude has found them
    await expect(page).toHaveURL(/\/add\/several\//, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'Check the pieces' })).toBeVisible();
    const boxes = page.getByTestId('several-box');
    await expect(boxes).toHaveCount(3, { timeout: 30_000 });
    const pieces = page.getByTestId('several-piece');
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/]);
    await expect(page.getByTestId('several-add')).toHaveText('Add these 3 items');
    expect(await axeViolations(page)).toEqual([]);

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
    await page.reload();   // kept by Nines, not just moved on the screen
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
  test('a removed box and a reshaped one go back to what Claude found, by Undo or by putting them back', async ({ page }) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles({ name: 'pile.png', mimeType: 'image/png', buffer: await pilePhoto(page, '#e4e1d8') });
    await expect(page.getByTestId('tray-state')).toHaveText('1 photo of several pieces');
    await page.getByTestId('add-tray').getByRole('button', { name: 'Add it' }).click();
    await expect(page).toHaveURL(/\/add\/several\//, { timeout: 30_000 });
    const pieces = page.getByTestId('several-piece');
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/], { timeout: 30_000 });
    const back = page.getByRole('button', { name: 'Back to what Claude found' });
    await expect(back).toHaveCount(0);   // nothing differs yet
    await expect(page.getByTestId('several-undo')).toHaveCount(0);

    // a box removed by a slip comes back with Undo, in its place
    await page.getByRole('button', { name: 'Remove box 2' }).click();
    await expect(pieces).toHaveText([/red shirt/, /green scarf/]);
    const undo = page.getByTestId('several-undo');
    await expect(undo).toContainText('Removed box 2 (blue trousers).');
    await undo.getByRole('button', { name: 'Undo' }).click();
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/]);
    await expect(undo).toHaveCount(0);

    // removed again, it is listed as one Claude found, and Put back brings it back in its turn
    await page.getByRole('button', { name: 'Remove box 2' }).click();
    await expect(page.getByTestId('several-removed')).toContainText('blue trousers');
    await page.reload();   // kept by Nines: what Claude found is still there after the page is opened again
    await page.getByRole('button', { name: 'Put back blue trousers as Claude found it' }).click();
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/]);
    await expect(page.getByTestId('several-removed')).toHaveCount(0);

    // a box reshaped with the keyboard goes back to its own shape, the others untouched
    const red = page.getByTestId('several-box').first();
    const was = (await red.boundingBox())!;
    await red.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Shift+ArrowRight');   // a hundredth of the photo wider
    await expect.poll(async () => (await red.boundingBox())!.width).toBeGreaterThan(was.width + 2);
    await expect(page.getByTestId('several-undo')).toContainText('Changed the shape of box 1 (red shirt).');
    await page.getByRole('button', { name: 'Put box 1 back as Claude found it' }).click();
    await expect.poll(async () => Math.round((await red.boundingBox())!.width)).toBe(Math.round(was.width));
    await expect(page.getByRole('button', { name: 'Put box 1 back as Claude found it' })).toHaveCount(0);
    await expect(back).toHaveCount(0);

    // several changes, then the whole photo back as Claude found it
    await page.getByRole('button', { name: 'Remove box 3' }).click();
    await expect(pieces).toHaveCount(2);
    await page.getByRole('button', { name: 'Add a box' }).click();
    await expect(pieces).toHaveCount(3);
    await back.click();
    await expect(pieces).toHaveText([/red shirt/, /blue trousers/, /green scarf/]);
    await expect(back).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    expect(await axeViolations(page)).toEqual([]);

    // confirmed: the three pieces are added
    await page.getByTestId('several-add').click();
    await expect(page).toHaveURL(backend.url + '/');
    await expect(page.getByText('3 items were added.', { exact: false })).toBeVisible();
  });
});
