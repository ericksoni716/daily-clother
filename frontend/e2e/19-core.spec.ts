import { expect, login, test, useProfile } from './fixtures';

test.use({ serviceWorkers: 'block' });

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('a list requested before an edit cannot replace the saved item', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const tile = page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' });
  await expect(tile).toBeVisible();
  const original = (await (await page.request.get('/api/items')).json()).items.find(
    (item: { name: string }) => item.name === 'Oatmeal henley',
  ) as { id: string; name: string };
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/items?status=active', async (route) => {
    const response = await route.fetch();
    await waiting;
    await route.fulfill({ response });
  }, { times: 1 });

  try {
    await page.getByRole('link', { name: 'Settings', exact: true }).filter({ visible: true }).click();
    const requested = page.waitForRequest('**/api/items?status=active', { timeout: 10_000 });
    await page.getByRole('link', { name: /^Closet/ }).filter({ visible: true }).click();
    await requested;
    await tile.click();
    const name = page.getByRole('textbox', { name: 'Name', exact: true });
    await name.fill('Review race updated');
    const saved = page.waitForResponse((response) => response.request().method() === 'PATCH' && response.ok());
    await name.press('Enter');
    await saved;
    await expect(page.getByTestId('tile').filter({ hasText: 'Review race updated' })).toBeVisible();

    const answered = page.waitForResponse('**/api/items?status=active');
    release();
    await answered;
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('tile').filter({ hasText: 'Review race updated' })).toBeVisible();
    await expect(page.getByTestId('tile').filter({ hasText: original.name })).toHaveCount(0);
  } finally {
    release();
    await page.request.patch(`/api/items/${original.id}`, { data: { name: original.name } });
  }
});

test('browser Back saves a text field without waiting for blur', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
  const id = new URL(page.url()).pathname.split('/').at(-1)!;
  const original = await (await page.request.get(`/api/items/${id}`)).json();
  try {
    await page.locator('.detail-panel').getByText('More details').click();
    const notes = page.getByRole('textbox', { name: 'Notes', exact: true });
    await notes.fill('Saved by browser Back');
    await expect(notes).toBeFocused();
    await page.goBack();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await expect.poll(async () => (await (await page.request.get(`/api/items/${id}`)).json()).notes)
      .toBe('Saved by browser Back');
  } finally {
    await page.request.patch(`/api/items/${id}`, { data: { notes: original.notes } });
  }
});

test('a delayed save cannot roll back a newer edit of the same field', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
  const id = new URL(page.url()).pathname.split('/').at(-1)!;
  const original = await (await page.request.get(`/api/items/${id}`)).json();
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  let first = true;
  await page.route(`**/api/items/${id}`, async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue();
    const hold = first;
    first = false;
    const response = await route.fetch();
    if (hold) await waiting;
    await route.fulfill({ response });
  });

  const name = page.getByRole('textbox', { name: 'Name', exact: true });
  try {
    await name.fill('First edit');
    const requested = page.waitForRequest((request) => request.method() === 'PATCH');
    await name.press('Enter');
    await requested;
    await name.fill('Second edit');
    await name.press('Enter');
    // If saves overlap, deliver the second answer first. A queued save cannot answer yet.
    await page.waitForResponse((response) => response.request().method() === 'PATCH', { timeout: 1000 })
      .catch((error: Error) => { if (error.name !== 'TimeoutError') throw error; });
    release();
    await page.waitForLoadState('networkidle');
    await expect(name).toHaveValue('Second edit');
    await expect(page.getByTestId('tile').filter({ hasText: 'Second edit' })).toBeVisible();
    expect((await (await page.request.get(`/api/items/${id}`)).json()).name).toBe('Second edit');
  } finally {
    release();
    await page.request.patch(`/api/items/${id}`, { data: { name: original.name } });
  }
});

test('slow polling makes progress when a poll takes longer than the interval', async ({ page }) => {
  // The closet follows the work under way through GET /api/progress (src/work.ts): here one item is being described,
  // and the poll's second answer is slow. When it lands, saying the item is done, the closet's list is read again.
  await login(page);
  await useProfile(page, 'demo');
  await expect(page.getByTestId('tile').first()).toBeVisible();
  const list = await (await page.request.get('/api/items')).json();
  const item = list.items[0];
  const describing = { stage: 'describing', step: 2, of: 3, state: 'working', title: 'Describing and drawing',
    words: 'Claude is describing it', about: '', waiting_for: null, why: null, error: null, can_retry: false, retry: null };
  let released = false;
  let firstProgress = true;
  const pending: (() => void)[] = [];
  await page.route('**/api/items?status=active', async (route) => {
    const name = released ? 'Slow poll refreshed' : 'Slow poll initial';
    await route.fulfill({ json: { items: [{ ...item, name }, ...list.items.slice(1)] } });
  });
  await page.route('**/api/progress', async (route) => {
    if (firstProgress) {
      firstProgress = false;
      return route.fulfill({ json: { items: [{ id: item.id, name: item.name, category: item.category, color: item.color,
        status: 'active', thumb_url: item.thumb_url, progress: describing }], going: 1, waiting: 0, why: null } });
    }
    await new Promise<void>((resolve) => pending.push(resolve));
    await route.fulfill({ json: { items: [], going: 0, waiting: 0, why: null } });
  });
  await page.clock.install();
  try {
    await page.locator('nav.sidebar').getByRole('link', { name: 'Settings', exact: true }).click();
    await page.locator('nav.sidebar').getByRole('link', { name: /^Closet/ }).click();
    await expect(page.getByTestId('tile').filter({ hasText: 'Slow poll initial' })).toBeVisible();
    await expect(page.getByTestId('working-line')).toHaveText('Working on 1 item');
    await page.clock.fastForward(2000);
    await expect.poll(() => pending.length).toBe(1);
    // the next tick does not pile a second request on the one still on its way, nor call it off: it lands
    await page.clock.fastForward(2000);
    await page.clock.fastForward(2000);
    expect(pending.length).toBe(1);
    released = true;
    pending[0]();
    await expect(page.getByTestId('tile').filter({ hasText: 'Slow poll refreshed' })).toBeVisible();
    await expect(page.getByTestId('working-line')).toHaveCount(0);
  } finally {
    pending.forEach((release) => release());
  }
});

for (const saved of [false, true]) {
  test(`a late reconnect response preserves a newer ${saved ? 'saved edit' : 'unsaved draft'}`, async ({ page, context }) => {
    await login(page);
    await useProfile(page, 'demo');
    await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
    const id = new URL(page.url()).pathname.split('/').at(-1)!;
    const original = await (await page.request.get(`/api/items/${id}`)).json();
    const name = page.getByRole('textbox', { name: 'Name', exact: true });
    let release!: () => void;
    const waiting = new Promise<void>((resolve) => { release = resolve; });
    try {
      await context.setOffline(true);
      await name.fill('Unavailable edit');
      await name.press('Enter');
      await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
      await page.request.patch(`/api/items/${id}`, { data: { name: 'Background update' } });
      const snapshot = await (await page.request.get(`/api/items/${id}`)).json();
      await page.route(`**/api/items/${id}`, async (route) => {
        if (route.request().method() !== 'GET') return route.continue();
        await waiting;
        await route.fulfill({ json: snapshot });
      });
      const requested = page.waitForRequest((request) => request.method() === 'GET' && request.url().endsWith(`/api/items/${id}`));
      await context.setOffline(false);
      await requested;
      await expect(page.getByText('Offline: showing your saved closet')).toBeHidden();
      await name.fill('Newest edit');
      if (saved) {
        const answer = page.waitForResponse((response) => response.request().method() === 'PATCH' && response.ok());
        await name.press('Enter');
        await answer;
      }
      const answered = page.waitForResponse((response) => response.request().method() === 'GET' && response.url().endsWith(`/api/items/${id}`));
      release();
      await answered;
      await page.waitForLoadState('networkidle');
      await expect(name).toHaveValue('Newest edit');
    } finally {
      await context.setOffline(false);
      release();
      await page.request.patch(`/api/items/${id}`, { data: { name: original.name } });
    }
  });
}
