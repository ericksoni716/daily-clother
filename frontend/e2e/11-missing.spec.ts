import type { Page } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

/** Takes back whatever a test decided, so the demo closet's suggestions start the same in every test. */
async function undoDecisions(page: Page) {
  const r = await page.request.post('/api/profile', { data: { profile: 'demo' } });
  if (!r.ok()) return;
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  for (const w of wishes) await page.request.delete(`/api/wishlist/${w.id}`);
  const answer = await (await page.request.get('/api/gaps')).json();
  for (const g of answer.gaps ?? []) if (g.state === 'hidden') await page.request.delete(`/api/gaps/${g.id}/hide`);
}

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await undoDecisions(page);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

async function openMissing(page: Page) {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: /missing/i }).first().click();
  await expect(page.locator('#missing-title')).toBeVisible();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
}

const gap = (page: Page, name: string) => page.getByTestId('gap').filter({ has: page.getByRole('heading', { name, exact: true }) });

async function gapNames(page: Page): Promise<string[]> {
  return page.getByTestId('gap').getByRole('heading', { level: 3 }).allInnerTexts();
}

test("what's missing shows the gaps, best first, with the reasons and what to look for", async ({ page }) => {
  await openMissing(page);
  const first = page.getByTestId('gap').first();
  // one sentence for why; the rest, day by day, behind a disclosure
  await expect(first.getByTestId('gap-summary')).toBeVisible();
  await expect(first.getByRole('list', { name: 'Why' })).toBeHidden();
  await first.getByText(/^Why, day by day \(\d+\)$/).click();
  await expect(first.getByRole('list', { name: 'Why' }).getByRole('listitem').first()).toBeVisible();
  await expect(first.getByTestId('look-for')).toContainText(/Look for/i);
  // the first one helps at least as much as the last
  const levels = await page.getByTestId('help').evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.level)));
  expect(levels.length).toBeGreaterThan(2);
  expect(levels[0]).toBeGreaterThanOrEqual(levels[levels.length - 1]);
  await expect(first.getByTestId('help')).toHaveText(/^Helps (a little|some|a fair bit|a lot)$/);
  // no field names or numbers out of 100
  await expect(first).not.toContainText(/smart_casual|dress_shoes|score/);
  // the quieter findings
  await expect(page.getByRole('heading', { name: 'Also worth knowing' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Not worn yet' })).toBeVisible();

  // one of the owner's own pieces opens the item, and comes back
  const piece = page.getByTestId('gap-piece').first();
  await piece.click();
  await expect(page).toHaveURL(/\/missing\/item\//);
  await expect(page.getByRole('link', { name: 'Back to the wishlist' })).toBeVisible();
  await page.getByRole('link', { name: 'Back to the wishlist' }).click();
  await expect(page.getByTestId('wishlist')).toBeVisible();
});

test('a reason given for several kinds of day is said once, with the days listed under it', async ({ page }) => {
  await openMissing(page);
  const belt = gap(page, 'A leather belt');
  const sentence = 'A leather belt finishes trousers and jeans; the engine adds one to every outfit that has them. You have none.';
  await expect(belt.getByTestId('gap-summary')).toHaveText(sentence);
  // the card is no longer a wall of the same sentence
  expect(await belt.evaluate((el) => el.getBoundingClientRect().height)).toBeLessThan(600);
  await belt.getByText('Why, day by day (4)').click();
  const why = belt.getByRole('list', { name: 'Why' });
  await expect(why.getByText(sentence, { exact: true })).toHaveCount(1);
  await expect(why.getByRole('list', { name: 'For' }).getByRole('listitem').locator('strong')).toHaveText(['Work', 'Everyday', 'Going out', 'Vacation']);
});

test("\"I'll look for this\" puts a gap on the wishlist; the note is kept; it can be removed", async ({ page }) => {
  await openMissing(page);
  const [name] = await gapNames(page);
  await gap(page, name).getByRole('button', { name: "I'll look for this" }).click();
  const wishlist = page.getByTestId('wishlist');
  const wish = wishlist.getByTestId('wish').filter({ hasText: name });
  await expect(wish).toBeVisible();
  // the gap stays in its place, marked, instead of being offered again
  await expect(gap(page, name)).toContainText('On your wishlist');
  await expect(gap(page, name).getByRole('button', { name: "I'll look for this" })).toHaveCount(0);

  await wish.getByLabel('Note').fill('Size 42, under 150');
  await wish.getByRole('button', { name: 'Save note' }).click();
  await expect(page.getByText('Note saved')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('wish').filter({ hasText: name }).getByLabel('Note')).toHaveValue('Size 42, under 150');

  await page.getByTestId('wish').filter({ hasText: name }).getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByTestId('wish')).toHaveCount(0);
  await expect(gap(page, name).getByRole('button', { name: "I'll look for this" })).toBeVisible();
});

test('"Not for me" hides a gap with a reason, and it can be brought back', async ({ page }) => {
  await openMissing(page);
  const names = await gapNames(page);
  const name = names[1];
  await gap(page, name).getByRole('button', { name: 'Not for me' }).click();
  await gap(page, name).getByText('Too expensive').click();
  await gap(page, name).getByRole('button', { name: `Hide ${name}` }).click();
  await expect(gap(page, name)).toHaveCount(0);

  const hidden = page.getByTestId('hidden-gaps');
  await expect(hidden).toContainText('Hidden (1)');
  await hidden.getByText('Hidden (1)').click();
  await expect(hidden).toContainText(name);
  await expect(hidden).toContainText('Too expensive');

  // it stays hidden when the page asks again
  await page.reload();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  await expect(gap(page, name)).toHaveCount(0);

  await page.getByTestId('hidden-gaps').getByText('Hidden (1)').click();
  await page.getByRole('button', { name: `Bring back ${name}` }).click();
  await expect(gap(page, name)).toBeVisible();
  await expect(page.getByTestId('hidden-gaps')).toHaveCount(0);
  expect(await gapNames(page)).toEqual(names);
});

test('a wish added by hand; "I bought it" takes it off the list and opens Add', async ({ page }) => {
  await openMissing(page);
  const wishlist = page.getByTestId('wishlist');
  await wishlist.getByRole('button', { name: 'Add by hand' }).click();
  await wishlist.getByLabel('What are you looking for?').fill('Brown suede loafers');
  await wishlist.getByLabel(/^Note/).fill('Like the ones in the shop window');
  await wishlist.getByRole('button', { name: 'Add to the list' }).click();
  const wish = wishlist.getByTestId('wish').filter({ hasText: 'Brown suede loafers' });
  await expect(wish).toBeVisible();
  await expect(wish).toContainText('Added by hand');
  await expect(wish.getByLabel('Note')).toHaveValue('Like the ones in the shop window');

  await wish.getByRole('button', { name: 'I bought it' }).click();
  await expect(page).toHaveURL(/\/add$/);
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  expect(wishes).toEqual([]);
});

test("on a phone: what's missing is in the tab bar, and the wishlist is beside the suggestions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await useProfile(page, 'demo');
  await page.locator('nav.tabbar').getByRole('link', { name: 'Missing' }).click();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  const [name] = await gapNames(page);
  await gap(page, name).getByRole('button', { name: "I'll look for this" }).click();
  await expect(page.getByRole('button', { name: 'Wishlist · 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Wishlist · 1' }).click();
  await expect(page.getByTestId('wish').filter({ hasText: name })).toBeVisible();
  // nothing is wider than the screen
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);
});

test("what's missing offline: the answer fetched earlier is shown as saved, and the buttons say why they are off", async ({ page, context }) => {
  await openMissing(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  const names = await gapNames(page);
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  expect(await gapNames(page)).toEqual(names);
  const wish = page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" });
  await expect(wish).toBeDisabled();
  await expect(wish).toHaveAttribute('title', /needs Closet on your computer/i);
  await expect(page.getByRole('button', { name: 'Add by hand' })).toBeDisabled();
});

for (const [label, viewport] of [['phone', { width: 390, height: 844 }], ['computer', { width: 1280, height: 800 }]] as const) {
  test(`screenshot of What's missing on a ${label} (${viewport.width}×${viewport.height})`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await login(page);
    await useProfile(page, 'demo');
    // something on the wishlist, as there would be after a while
    const answer = await (await page.request.get('/api/gaps')).json();
    await page.request.post('/api/wishlist', { data: { gap_id: answer.gaps[1].id } });
    await page.request.post('/api/wishlist', { data: { name: 'Brown suede loafers', note: 'Size 43' } });
    await page.goto('/missing');
    await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => page.locator('main img').evaluateAll((imgs) => imgs.every((i) => (i as HTMLImageElement).complete))).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    const path = testInfo.outputPath(`missing-${label}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`What's missing on a ${label}`, { path, contentType: 'image/png' });
  });
}
