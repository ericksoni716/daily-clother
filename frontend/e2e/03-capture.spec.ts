import { expect, login, PHOTOS, test, useProfile } from './fixtures';

test('upload a photo: it shows up with its waiting badge', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  const before = (await (await page.request.get('/api/items')).json()).items.length;

  await page.getByRole('link', { name: 'Add' }).first().click();
  await expect(page.getByTestId('dropzone')).toBeVisible();
  // one column, at most 720px wide, beside the sidebar
  const sidebar = (await page.locator('nav.sidebar').boundingBox())!;
  const add = (await page.locator('section.add').boundingBox())!;
  expect(add.width).toBeLessThanOrEqual(720);
  expect(add.x - (sidebar.x + sidebar.width)).toBeLessThan(40);
  await page.getByTestId('library-input').setInputFiles(`${PHOTOS}marl-sweater.jpg`);

  const row = page.getByTestId('queue-row').filter({ hasText: 'marl-sweater' });
  await expect(row.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });

  // the browser resized it: what arrived is at most 2400px on the long edge, re-encoded as JPEG
  const items = (await (await page.request.get('/api/items')).json()).items;
  expect(items.length).toBe(before + 1);
  const item = await (await page.request.get(`/api/items/${items[0].id}`)).json();
  expect(Math.max(item.photos[0].width, item.photos[0].height)).toBeLessThanOrEqual(2400);

  await page.getByRole('link', { name: 'See them in your closet' }).click();
  const tile = page.getByTestId('tile').first();
  await expect(tile).toBeVisible();
  await expect(tile).toContainText('Waiting for the model');
  await expect(page.getByTestId('model-banner')).toContainText('not set up yet');

  await tile.click();
  await expect(page.locator('.detail-panel')).toContainText('Waiting for the model');
});

test('a file that is not a photo shows the server message in the queue', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  await page.goto('/add');
  await page.getByTestId('library-input').setInputFiles({ name: 'notes.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('this is not a picture') });
  const row = page.getByTestId('queue-row').filter({ hasText: 'notes.jpg' });
  await expect(row.getByTestId('queue-status')).toHaveText('Failed', { timeout: 30_000 });
  await expect(row.getByTestId('queue-error')).toContainText('not a photo this app can read');
  await expect(row.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('a dropped connection is retried with the same key and never duplicates', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  const before = (await (await page.request.get('/api/items')).json()).items.length;
  const keys: string[] = [];
  let drops = 1;
  await page.route('**/api/items', async (route) => {
    const req = route.request();
    if (req.method() !== 'POST') return route.fallback();
    const key = /name="client_key"\r\n\r\n([^\r]+)/.exec(req.postDataBuffer()?.toString('latin1') ?? '')?.[1] ?? '';
    keys.push(key);
    if (drops-- > 0) {
      // let the server make the item, then lose the answer
      await route.fetch();
      return route.abort('connectionreset');
    }
    return route.fallback();
  });
  await page.goto('/add');
  await page.getByTestId('library-input').setInputFiles(`${PHOTOS}jeans.jpg`);
  const row = page.getByTestId('queue-row').filter({ hasText: 'jeans' });
  await expect(row.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
  expect(keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  const after = (await (await page.request.get('/api/items')).json()).items.length;
  expect(after).toBe(before + 1);
});
