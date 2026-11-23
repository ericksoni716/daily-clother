import { readFileSync } from 'node:fs';
import type { BrowserContext, Page } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, goToCloset, PHOTOS, serviceWorkerInCharge, test, useProfile } from './fixtures';
import { startBackend, type Backend } from './server';

const PHONE = { width: 390, height: 844 };

type Garment = { colour: string; kind: 'tee' | 'sweater' | 'trousers' };

/** Made-up photos of clothes, drawn in the page: a plain garment shape in one colour on a pale floor. */
async function garmentPhotos(page: Page, garments: Garment[]): Promise<Buffer[]> {
  const shots = await page.evaluate((list) => list.map(({ colour, kind }) => {
    const c = document.createElement('canvas');
    c.width = 900;
    c.height = 900;
    const g = c.getContext('2d')!;
    g.fillStyle = '#e9e4da';
    g.fillRect(0, 0, 900, 900);
    const outline: Record<string, number[][]> = {
      tee: [[390, 200], [300, 230], [180, 330], [240, 400], [320, 360], [320, 720], [580, 720], [580, 360], [660, 400],
        [720, 330], [600, 230], [510, 200]],
      sweater: [[390, 190], [300, 220], [220, 420], [210, 660], [280, 670], [320, 430], [320, 730], [580, 730], [580, 430],
        [620, 670], [690, 660], [680, 420], [600, 220], [510, 190]],
      trousers: [[330, 160], [300, 780], [430, 780], [450, 330], [470, 780], [600, 780], [570, 160]],
    };
    g.fillStyle = colour;
    g.beginPath();
    outline[kind].forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
    if (kind !== 'trousers') g.quadraticCurveTo(450, 260, 390, outline[kind][0][1]);   // the neckline
    g.closePath();
    g.fill();
    g.strokeStyle = 'rgba(0, 0, 0, 0.25)';
    g.lineWidth = 4;
    g.stroke();
    return c.toDataURL('image/png').split(',')[1];
  }), garments);
  return shots.map((b) => Buffer.from(b, 'base64'));
}

const png = (name: string, buffer: Buffer) => ({ name, mimeType: 'image/png', buffer });

async function itemCount(page: import('@playwright/test').Page): Promise<number> {
  const [active, archived] = await Promise.all(['active', 'archived'].map(async (s) =>
    (await (await page.request.get(`/api/items?status=${s}`)).json()).items.length));
  return active + archived;
}

test('importing several photos: each goes in once, and a photo already in the closet is said so', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'main');
  const before = await itemCount(page);
  await page.goto('/add');

  const three = ['plaid-flannel.jpg', 'plaid-madras.jpg', 'sneakers-pair.jpg'];
  await page.getByTestId('library-input').setInputFiles(three.map((f) => `${PHOTOS}${f}`));
  await expect(page.getByTestId('import-note')).toHaveText('3 photos are going into your closet.');
  const rows = page.getByTestId('queue-row');
  await expect(rows).toHaveCount(3);
  for (const f of three) {
    await expect(rows.filter({ hasText: f }).getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByTestId('queue-summary')).toHaveText('3 added');
  expect(await itemCount(page)).toBe(before + 3);

  // the same file again, later
  await page.getByRole('button', { name: 'Clear list' }).click();
  await page.getByTestId('library-input').setInputFiles(`${PHOTOS}plaid-flannel.jpg`);
  await expect(rows.filter({ hasText: 'plaid-flannel' }).getByTestId('queue-status'))
    .toHaveText('Already in your closet', { timeout: 30_000 });
  await expect(page.getByTestId('queue-summary')).toHaveText('1 already in your closet');

  // a copy under another name is the same photo; a file that is not a photo is skipped and said so
  await page.getByTestId('library-input').setInputFiles([
    { name: 'flannel-copy.jpg', mimeType: 'image/jpeg', buffer: readFileSync(`${PHOTOS}plaid-flannel.jpg`) },
    { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('shopping list') },
  ]);
  await expect(page.getByTestId('import-note')).toContainText('Skipped 1 file that is not a photo: notes.txt.');
  await expect(rows.filter({ hasText: 'flannel-copy' }).getByTestId('queue-status'))
    .toHaveText('Already in your closet', { timeout: 30_000 });
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId('queue-summary')).toHaveText('2 already in your closet');
  expect(await itemCount(page)).toBe(before + 3);
});

test('an import cut short by closing the page is carried on without adding anything twice', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'main');
  const before = await itemCount(page);
  // the upload of one photo never gets an answer, as if the tab were closed during it
  await page.route('**/api/items', async (route) => {
    const req = route.request();
    if (req.method() === 'POST' && (req.postDataBuffer()?.toString('latin1') ?? '').includes('filename="sneaker-held')) return;
    return route.fallback();
  });
  await page.goto('/add');
  const pair = [`${PHOTOS}graphic-tee.jpg`, `${PHOTOS}sneaker-held.jpg`];
  await page.getByTestId('library-input').setInputFiles(pair);
  const rows = page.getByTestId('queue-row');
  await expect(rows.filter({ hasText: 'graphic-tee' }).getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
  await expect(rows.filter({ hasText: 'sneaker-held' }).getByTestId('queue-status')).toHaveText('Uploading');

  // Reload while the upload is still held, as closing the tab would end it. Removing the route first
  // would let the held request through to the server, and the photo would go in before the reload.
  await page.reload();
  await page.unroute('**/api/items');
  const resume = page.getByTestId('resume');
  await expect(resume).toContainText('1 photo was not added yet');
  await expect(rows.filter({ hasText: 'sneaker-held' }).getByTestId('queue-status')).toHaveText('Not added yet');

  // choosing both again: each row keeps its first upload key, so the one that went in is not added twice
  await page.getByTestId('library-input').setInputFiles(pair);
  for (const name of ['graphic-tee', 'sneaker-held']) {
    await expect(rows.filter({ hasText: name }).getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
  }
  await expect(resume).toHaveCount(0);
  await expect(page.getByTestId('queue-summary')).toHaveText('2 added');
  expect(await itemCount(page)).toBe(before + 2);
});

/** Answers the closet's list with some of its items changed, for a picture of states that pass too quickly to catch. It
 * is routed on the browser, so the service worker's requests are answered the same way. */
// two rows as the server says them while Claude works through a batch (backend/closet/progress.py)
const DESCRIBING = { stage: 'describing', step: 2, of: 3, state: 'working', title: 'Describing and drawing', words: 'Claude is describing it',
  about: 'By Claude, usually within a minute.', waiting_for: null, why: null, error: null, can_retry: false, retry: null };
const NEXT = { ...DESCRIBING, state: 'queued', words: 'Waiting its turn with Claude' };

async function answerTheList(context: BrowserContext, changes: Record<string, Record<string, unknown>>) {
  await context.route((url) => url.pathname === '/api/items' && url.searchParams.get('status') === 'active', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    for (const it of body.items) if (changes[it.id]) Object.assign(it, changes[it.id]);
    await route.fulfill({ response: res, json: body });
  });
}

/** Opens a backend of its own, on the owner's own closet. */
async function openCloset(page: Page, url: string) {
  await page.goto(url + '/');
  await expect(page.locator('#closet-title')).toBeVisible();
}

// Its own backend, with stand-ins for the model and for Claude (which calls every item "Navy polo"): nothing here
// reaches the real Claude. The photos are made up, drawn in the page.
test.describe('the import list shows what each photo became', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test.describe('on a phone', () => {
    test.use({ viewport: PHONE, hasTouch: true, isMobile: true });

    test('each row shows its item and what Claude called it, opens it, and keeps it offline', async ({ page, context }) => {
      test.setTimeout(150_000);
      await openCloset(page, backend.url);

      await page.goto(backend.url + '/add');
      const [tee, sweater, trousers, shirt] = await garmentPhotos(page, [
        { colour: '#2c3e63', kind: 'tee' }, { colour: '#8a8d91', kind: 'sweater' }, { colour: '#5b6b3a', kind: 'trousers' },
        { colour: '#f4f1ea', kind: 'tee' },
      ]);
      const names = ['navy-tee.png', 'grey-sweater.png', 'olive-trousers.png', 'white-shirt.png'];
      await page.getByTestId('library-input').setInputFiles([tee, sweater, trousers, shirt].map((b, i) => png(names[i], b)));
      const rows = page.getByTestId('queue-row');
      await expect(rows).toHaveCount(4);

      // once added, each row shows the item instead of the upload (never both): its cut-out, and what Claude called it
      // once it is described; the file's name stays, small, below
      for (const name of names) {
        const row = rows.filter({ hasText: name });
        await expect(row.getByTestId('queue-title')).toHaveText('Navy polo', { timeout: 60_000 });
        await expect(row.getByTestId('queue-status')).toHaveCount(0);
        await expect(row.locator('.queue-file')).toHaveText(name);
        await expect(row.locator('.queue-thumb img')).toHaveAttribute('src', /\.cut\.t\.webp$/);
      }
      await expect(page.getByTestId('import-waiting')).toHaveCount(0);   // nothing waits, so no reason is given

      // a row opens its item, where it can be fixed
      const first = rows.filter({ hasText: 'navy-tee.png' }).getByTestId('queue-item');
      const href = await first.getAttribute('href');
      expect(href).toMatch(/^\/item\/[0-9a-f]+$/);
      await first.click();
      await expect(page).toHaveURL(new RegExp(`${href}$`));
      await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Navy polo');
      await page.goBack();

      // the same photo again under another name: already in the closet, and the row opens the item it is
      await page.getByTestId('library-input').setInputFiles(png('tee-again.png', tee));
      const again = rows.filter({ hasText: 'tee-again.png' });
      await expect(again.getByTestId('queue-status')).toHaveText('Already in your closet', { timeout: 30_000 });
      await expect(again.getByTestId('queue-title')).toHaveText('Navy polo');
      await expect(again.getByTestId('queue-item')).toHaveAttribute('href', href!);
      expect(await sideways(page)).toEqual([]);
      expect(await axeViolations(page, '.queue')).toEqual([]);
      for (const row of await rows.all()) {   // one tidy row each: its picture and two short lines
        expect((await row.boundingBox())!.height).toBeLessThanOrEqual(70);
      }

      // Nines out of reach: the page opened again shows the rows as it last saw them
      await serviceWorkerInCharge(page);
      await page.reload();   // once while the service worker is in charge, so the closet's list is saved
      await expect(rows.filter({ hasText: 'grey-sweater.png' }).getByTestId('queue-title')).toHaveText('Navy polo');
      await page.waitForLoadState('networkidle');
      await context.setOffline(true);
      await page.reload();
      await expect(page.getByTestId('import-offline')).toBeVisible();
      await expect(rows).toHaveCount(5);
      for (const name of names) await expect(rows.filter({ hasText: name }).getByTestId('queue-title')).toHaveText('Navy polo');
      await context.setOffline(false);
      await expect(page.getByTestId('import-offline')).toBeHidden({ timeout: 15_000 });

      // For the picture: the names Claude would give these made-up clothes (the stand-in calls everything "Navy polo"),
      // and two rows as they look while Claude works through a batch, one being described and one waiting its turn
      const idOf = async (name: string) =>
        (await rows.filter({ hasText: name }).getByTestId('queue-item').getAttribute('href'))!.split('/').pop()!;
      await answerTheList(context, {
        [await idOf('navy-tee.png')]: { name: 'Navy crew-neck tee', category: 'tee' },
        [await idOf('grey-sweater.png')]: { name: 'Grey wool sweater', category: 'sweater', color: 'grey' },
        [await idOf('olive-trousers.png')]: { name: null, category: null, color: null, tag_state: 'working', progress: DESCRIBING },
        [await idOf('white-shirt.png')]: { name: null, category: null, color: null, tag_state: 'waiting', progress: NEXT },
      });
      await page.reload();
      await expect(rows.filter({ hasText: 'navy-tee.png' }).getByTestId('queue-title')).toHaveText('Navy crew-neck tee');
      await expect(rows.filter({ hasText: 'olive-trousers.png' }).getByTestId('queue-title')).toHaveText('Claude is describing it');
      await expect(rows.filter({ hasText: 'white-shirt.png' }).getByTestId('queue-title')).toHaveText('Waiting its turn with Claude');
      await page.locator('.queue-done').evaluate((el) => el.scrollIntoView({ block: 'center' }));   // the list and its buttons, above the bar
      expect(await sideways(page)).toEqual([]);
      expect(await axeViolations(page, '.queue')).toEqual([]);
      for (const row of await rows.all()) expect((await row.boundingBox())!.height).toBeLessThanOrEqual(70);
      await page.screenshot({ path: test.info().outputPath('add-import-phone.png') });
    });
  });

  test.describe('on a computer', () => {
    test('the rows show the items the same way, one tidy row each', async ({ page, context }) => {
      test.setTimeout(120_000);
      await openCloset(page, backend.url);
      await page.goto(backend.url + '/add');
      const [jacket, chinos] = await garmentPhotos(page, [{ colour: '#7a4b2a', kind: 'sweater' }, { colour: '#c8b48a', kind: 'trousers' }]);
      await page.getByTestId('library-input').setInputFiles([png('brown-jacket.png', jacket), png('tan-chinos.png', chinos)]);
      const rows = page.getByTestId('queue-row');
      const ids: string[] = [];
      for (const name of ['brown-jacket.png', 'tan-chinos.png']) {
        const row = rows.filter({ hasText: name });
        await expect(row.getByTestId('queue-title')).toHaveText('Navy polo', { timeout: 60_000 });
        await expect(row.locator('.queue-thumb img')).toHaveAttribute('src', /\.cut\.t\.webp$/);
        expect((await row.boundingBox())!.height).toBeLessThanOrEqual(70);
        ids.push((await row.getByTestId('queue-item').getAttribute('href'))!.split('/').pop()!);
      }
      expect(await axeViolations(page, '.queue')).toEqual([]);

      // for the picture, the names Claude would give them, and the second still being described
      await answerTheList(context, {
        [ids[0]]: { name: 'Brown wool sweater', category: 'sweater', color: 'brown' },
        [ids[1]]: { name: null, category: null, color: null, tag_state: 'working', progress: DESCRIBING },
      });
      await page.reload();
      await expect(rows.filter({ hasText: 'tan-chinos.png' }).getByTestId('queue-title')).toHaveText('Claude is describing it');
      for (const row of await rows.all()) expect((await row.boundingBox())!.height).toBeLessThanOrEqual(70);
      await page.locator('.queue').scrollIntoViewIfNeeded();
      await page.screenshot({ path: test.info().outputPath('add-import-computer.png') });
    });
  });
});
