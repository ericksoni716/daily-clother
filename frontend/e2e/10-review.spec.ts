import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

type Field = { field: string; value: string | Record<string, string>; allowed: string[] | Record<string, string[]> };
type Queued = { id: string; name: string; fields: Field[] };

test('review in the demo closet: confirm one, change one, skip one', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const queued = (await (await page.request.get('/api/review')).json()).items as Queued[];
  const before = queued.length;
  expect(before).toBeGreaterThanOrEqual(3);
  const sidebar = page.locator('nav.sidebar');
  const badge = sidebar.getByTestId('review-badge');
  await expect(badge).toHaveText(String(before));

  // the closet says so too, and Review sits under Closet in the sidebar
  await expect(page.getByTestId('review-notice')).toContainText(`${before} pieces need a quick check`);
  await sidebar.getByRole('link', { name: 'Review' }).click();
  await expect(sidebar.getByRole('link', { name: 'Review' })).toHaveAttribute('aria-current', 'page');
  const progress = page.getByTestId('review-progress');
  const card = page.getByTestId('review-card');
  const fields = card.getByTestId('review-field');

  // 1. the most doubtful item, with only its doubtful fields: confirm it as it is
  await expect(progress).toHaveText(`1 of ${before}`);
  await expect(card.getByRole('heading', { name: queued[0].name })).toBeVisible();
  const parts = (f: Field) => (typeof f.value === 'string' ? 1 : Object.keys(f.value).length);
  await expect(fields).toHaveCount(queued[0].fields.reduce((n, f) => n + parts(f), 0));
  await card.getByRole('button', { name: "That's right" }).click();
  await expect(progress).toHaveText(`2 of ${before}`);
  await expect(badge).toHaveText(String(before - 1));

  // 2. the next one: choose the second value of its first field with the keyboard, then Enter
  await expect(card.getByRole('heading', { name: queued[1].name })).toBeVisible();
  const choices = fields.first().getByRole('group').getByRole('button');
  await expect(choices.first()).toHaveAttribute('aria-pressed', 'true');   // Claude's guess comes first, chosen
  await page.locator('#review-title').click();   // nothing focused that takes keys itself
  await page.keyboard.press('ArrowRight');
  await expect(choices.nth(1)).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Enter');
  await expect(progress).toHaveText(`3 of ${before}`);

  // 3. skip the third: the count goes down by two in all
  await expect(card.getByRole('heading', { name: queued[2].name })).toBeVisible();
  await card.getByRole('button', { name: 'Skip for now' }).click();
  await expect(badge).toHaveText(String(before - 2));

  // what was saved
  const after = (await (await page.request.get('/api/review')).json()).items as Queued[];
  expect(after.map((i) => i.id)).toEqual(queued.slice(2).map((i) => i.id));   // the skipped one is still there
  const item = async (id: string) => (await page.request.get(`/api/items/${id}`)).json();
  const confirmed = await item(queued[0].id);
  for (const f of queued[0].fields) {
    expect(confirmed.source[f.field]).toBe('user');
    expect(confirmed[f.field]).toEqual(f.value);
  }
  const changed = await item(queued[1].id);
  const f = queued[1].fields[0];
  expect(changed.source[f.field]).toBe('user');
  if (typeof f.value === 'string') {
    expect(changed[f.field]).toBe((f.allowed as string[]).filter((v) => v !== f.value)[0]);
  } else {
    expect(changed[f.field]).not.toEqual(f.value);
  }
});

test('review is unavailable offline, and says what is not described yet when empty', async ({ page, context }) => {
  await login(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.route('/api/review', (route) => route.fulfill({
    json: { count: 0, items: [], waiting: 2, failed: 1, waiting_items: [{ id: 'a', name: 'Navy polo', category: 'polo' }, { id: 'b', name: null, category: 'jeans' }],
      failed_items: [{ id: 'c', name: 'Grey hoodie', category: 'hoodie' }] },
  }));
  // nothing to review: no notice on the closet and no Review link until the queue is opened by its address
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  await expect(page.getByTestId('review-notice')).toHaveCount(0);
  await expect(page.locator('nav.sidebar').getByRole('link', { name: 'Review' })).toHaveCount(0);
  await page.goto('/review');
  await expect(page.getByTestId('review-empty')).toContainText('Nothing to review');
  await expect(page.locator('nav.sidebar').getByRole('link', { name: 'Review' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('review-not-ready')).toHaveText("2 items are still waiting to be described. 1 item couldn't be described.");
  await expect(page.getByRole('link', { name: 'Grey hoodie' })).toHaveAttribute('href', '/item/c');
  await expect(page.getByRole('link', { name: 'Jeans' })).toHaveAttribute('href', '/item/b');
  await expect(page.locator('nav.sidebar').getByTestId('review-badge')).toHaveCount(0);

  await page.unroute('/api/review');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByText('Reviewing is unavailable offline')).toBeVisible();
  await context.setOffline(false);
});
