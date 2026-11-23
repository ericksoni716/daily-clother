import type { Page } from '@playwright/test';
import { expect, goToCloset, serviceWorkerInCharge, test, useProfile } from './fixtures';

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

/** Opens the Wardrobe (what was What's missing) from the sidebar, with every thing worth buying showing. */
async function openMissing(page: Page) {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Wardrobe' }).first().click();
  await expect(page.locator('#wardrobe-title')).toBeVisible();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  await seeAll(page);
}

/** The page shows the three most worth buying, then "See all N": open the rest. */
async function seeAll(page: Page) {
  const all = page.getByRole('button', { name: /^See all \d+$/ });
  if (await all.isVisible()) await all.click();
}

/** Opens the wishlist's own page from its row on the Wardrobe, under "Thinking of buying something?". */
async function openWishlist(page: Page) {
  await page.getByTestId('wishlist-open').click();
  await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
  await expect(page.getByRole('heading', { name: 'Wishlist', level: 1 })).toBeVisible();
}

/** Opens a wish's own page from its row in the wishlist. */
async function openWish(page: Page, name: string) {
  await page.getByTestId('wish-row').filter({ hasText: name }).click();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  return page.getByTestId('wish');
}

const gap = (page: Page, name: string) => page.getByTestId('gap').filter({ has: page.getByRole('heading', { name, exact: true }) });

async function gapNames(page: Page): Promise<string[]> {
  return page.getByTestId('gap').getByRole('heading', { level: 3 }).allInnerTexts();
}

test("the wardrobe shows the three most worth buying first, then the rest, with the reasons and what to look for", async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/wardrobe');
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  // the few that help most lead; the rest are one tap away
  await expect(page.getByTestId('gap')).toHaveCount(3);
  await page.getByRole('button', { name: /^See all \d+$/ }).click();
  expect(await page.getByTestId('gap').count()).toBeGreaterThan(3);
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
  // what is not worn and what is worn most are said once, in their own sections, not again under the suggestions
  await expect(page.getByRole('heading', { name: 'Also worth knowing' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Not worn yet' })).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'Worn most', level: 2 })).toBeVisible();

  // one of the owner's own pieces opens the item beside the page, and comes back to "Thinking of buying something?"
  const piece = page.getByTestId('gap-piece').first();
  await piece.click();
  await expect(page).toHaveURL(/\/wardrobe\/item\//);
  const back = page.getByRole('complementary', { name: 'Item details' }).getByRole('link', { name: 'Wardrobe' });
  await expect(back).toBeVisible();
  await back.click();
  await expect(page).toHaveURL(/\/wardrobe$/);
  await expect(page.getByRole('complementary', { name: 'Thinking of buying something?' }).getByTestId('wishlist-open')).toBeVisible();
});

test('a reason given for several kinds of day is said once, with the days listed under it', async ({ page }) => {
  await openMissing(page);
  const rain = gap(page, 'A rain-proof outer layer');
  const sentence = 'A mac, trench or waxed jacket keeps the rain off without an umbrella. You have none.';
  await expect(rain.getByTestId('gap-summary')).toHaveText(sentence);
  // the card is no longer a wall of the same sentence
  expect(await rain.evaluate((el) => el.getBoundingClientRect().height)).toBeLessThan(600);
  await rain.getByText('Why, day by day (4)').click();
  const why = rain.getByRole('list', { name: 'Why' });
  await expect(why.getByText(sentence, { exact: true })).toHaveCount(1);
  await expect(why.getByRole('list', { name: 'For' }).getByRole('listitem').locator('strong')).toHaveText(['Work', 'Everyday', 'Going out', 'Vacation']);
});

test("\"I'll look for this\" puts a gap on the wishlist; the note is kept; it can be removed", async ({ page }) => {
  await openMissing(page);
  await expect(page.getByTestId('wishlist-open')).toContainText('Nothing on it yet');
  const [name] = await gapNames(page);
  await gap(page, name).getByRole('button', { name: "I'll look for this" }).click();
  // the Wardrobe's row to the wishlist counts it
  await expect(page.getByTestId('wishlist-open')).toContainText('1 thing');
  // the gap stays in its place, marked, instead of being offered again
  await expect(gap(page, name)).toContainText('On your wishlist');
  await expect(gap(page, name).getByRole('button', { name: "I'll look for this" })).toHaveCount(0);

  // the wishlist is a page of its own, one tap from the Wardrobe
  await openWishlist(page);
  await expect(page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: name })).toBeVisible();

  // the wish has a page of its own, where its note is kept and it says it saved
  const wish = await openWish(page, name);
  await wish.getByLabel('Note').fill('Size 42, under 150');
  await wish.getByRole('button', { name: 'Save note' }).click();
  await expect(wish.getByTestId('wish-note-status')).toHaveText('Saved');
  await page.reload();
  await expect(page.getByTestId('wish').getByLabel('Note')).toHaveValue('Size 42, under 150');

  // removed from its page, it goes back to the wishlist, now empty, and on the Wardrobe the gap is offered again
  await page.getByTestId('wish').getByRole('button', { name: 'Remove' }).click();
  await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
  await expect(page.getByTestId('wish-row')).toHaveCount(0);
  const empty = page.getByTestId('wishlist-empty');
  await expect(empty).toContainText('Your wishlist is empty');
  await expect(empty.getByRole('link', { name: "See what's worth buying" })).toHaveAttribute('href', '/wardrobe');
  await page.locator('.page-back').click();   // "‹ Wardrobe"
  await expect(page).toHaveURL(/\/wardrobe$/);
  await seeAll(page);
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
  await seeAll(page);
  await expect(gap(page, name)).toHaveCount(0);

  await page.getByTestId('hidden-gaps').getByText('Hidden (1)').click();
  await page.getByRole('button', { name: `Bring back ${name}` }).click();
  await expect(gap(page, name)).toBeVisible();
  await expect(page.getByTestId('hidden-gaps')).toHaveCount(0);
  expect(await gapNames(page)).toEqual(names);
});

test('a wish added by hand; "I bought it" takes it off the list and opens Add', async ({ page }) => {
  await openMissing(page);
  await openWishlist(page);
  const wishlist = page.getByTestId('wishlist');
  await wishlist.getByRole('button', { name: 'Add by hand' }).click();
  await wishlist.getByLabel('What are you looking for?').fill('Brown suede loafers');
  await wishlist.getByLabel(/^Note/).fill('Like the ones in the shop window');
  await wishlist.getByRole('button', { name: 'Add to the list' }).click();
  const row = wishlist.getByTestId('wish-row').filter({ hasText: 'Brown suede loafers' });
  await expect(row).toBeVisible();
  await expect(row).toContainText('Like the ones in the shop window');
  const wish = await openWish(page, 'Brown suede loafers');
  await expect(wish).toContainText('Added by hand');
  await expect(wish.getByLabel('Note')).toHaveValue('Like the ones in the shop window');

  await wish.getByRole('button', { name: 'I bought it' }).click();
  await expect(page).toHaveURL(/\/add$/);
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  expect(wishes).toEqual([]);
});

test('on a phone: the Wardrobe is in the tab bar, and its row to the wishlist, after the things worth buying, opens the list', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.locator('nav.tabbar').getByRole('link', { name: 'Wardrobe' }).click();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('gap')).toHaveCount(3);
  const [name] = await gapNames(page);
  await gap(page, name).getByRole('button', { name: "I'll look for this" }).click();
  const row = page.getByTestId('wishlist-open');
  await expect(row).toHaveText(/^Wishlist\s*1 thing$/);
  // below the things worth buying, on the same page
  const lastGap = await page.getByTestId('gap').last().boundingBox();
  expect((await row.boundingBox())!.y).toBeGreaterThan(lastGap!.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  // the list itself is on its own page; nothing is wider than the screen there either
  await openWishlist(page);
  await expect(page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: name })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("what's missing offline: the answer fetched earlier is shown as saved, and the buttons say why they are off", async ({ page, context }) => {
  await openMissing(page);
  await serviceWorkerInCharge(page);   // which reloads the page: show every gap again
  await expect(page.getByTestId('gap').first()).toBeVisible();
  await seeAll(page);
  const names = await gapNames(page);
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  await seeAll(page);
  expect(await gapNames(page)).toEqual(names);
  const wish = page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" });
  await expect(wish).toBeDisabled();
  await expect(wish).toHaveAttribute('title', /needs Nines on your computer/i);
  // the wishlist opens offline too, from the copy saved on this device, and its buttons say why they are off
  await openWishlist(page);
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add by hand' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Add a link' })).toHaveAttribute('title', /needs Nines on your computer/i);
});
