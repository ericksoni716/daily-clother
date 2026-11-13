import { readFileSync } from 'node:fs';
import { expect, login, PHOTOS, test, useProfile } from './fixtures';

async function itemCount(page: import('@playwright/test').Page): Promise<number> {
  const [active, archived] = await Promise.all(['active', 'archived'].map(async (s) =>
    (await (await page.request.get(`/api/items?status=${s}`)).json()).items.length));
  return active + archived;
}

test('importing several photos: each goes in once, and a photo already in the closet is said so', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  const before = await itemCount(page);
  await page.goto('/add');

  const three = ['plaid-flannel.jpg', 'plaid-madras.jpg', 'sneakers-pair.jpg'];
  await page.getByTestId('library-input').setInputFiles(three.map((f) => `${PHOTOS}${f}`));
  await expect(page.getByTestId('import-note')).toHaveText('3 photos added to the import.');
  const rows = page.getByTestId('queue-row');
  await expect(rows).toHaveCount(3);
  for (const f of three) {
    await expect(rows.filter({ hasText: f }).getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
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
  await login(page);
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
  await expect(rows.filter({ hasText: 'graphic-tee' }).getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
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
    await expect(rows.filter({ hasText: name }).getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
  }
  await expect(resume).toHaveCount(0);
  await expect(page.getByTestId('queue-summary')).toHaveText('2 added');
  expect(await itemCount(page)).toBe(before + 2);
});
