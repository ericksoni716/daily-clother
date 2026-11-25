import { expect, goToCloset, test, useProfile } from './fixtures';

// Four places and Add (docs/DECISIONS.md, "Four places and Add"): the old addresses of the places that were merged
// away still land somewhere sensible, after a reload too, and Back returns from them; each place's back link goes
// back in history to where you came from.

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

const MOVED: [from: string, to: RegExp, ready: string][] = [
  ['/missing', /\/wardrobe$/, '#wardrobe-title'],
  ['/insights', /\/wardrobe$/, '#wardrobe-title'],
  ['/missing/check', /\/wardrobe\/check$/, '[data-testid="would-work"]'],
  ['/would-work', /\/wardrobe\/check$/, '[data-testid="would-work"]'],
  ['/wishlist', /\/wardrobe\/wishlist$/, '#wishlist-title'],
  ['/worn', /\/today\/worn$/, '.worn h1'],
];

test('every old address lands on its new place, stays there after a reload, and Back returns', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  for (const [from, to, ready] of MOVED) {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
    await page.goto(from);
    await expect(page.locator(ready).first(), from).toBeVisible({ timeout: 30_000 });
    await expect(page, from).toHaveURL(to);
    await page.reload();
    await expect(page.locator(ready).first(), `${from} after a reload`).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(to);
    // the old address was replaced, not added: Back goes to the page before it
    await page.goBack();
    await expect(page, `Back from ${from}`).toHaveURL(/\/settings$/);
  }
  // an item opened from the old What's missing opens in the Wardrobe, with what it names
  const { items } = await (await page.request.get('/api/items')).json();
  await page.goto(`/missing/item/${items[0].id}`);
  await expect(page).toHaveURL(new RegExp(`/wardrobe/item/${items[0].id}$`));
  await expect(page.getByRole('textbox', { name: 'Name' })).toBeVisible();
});

test('on a phone: Worn, Trips, the review and the wishlist are one level down in their place, and their back links go Back', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  // the foot of Today leads to Trips only when no trip is coming (second review of the screens, finding 13): the demo's
  // trip twelve days away is left out of the list here
  await page.route('**/api/trips', (route) => (route.request().method() === 'GET' ? route.fulfill({ json: { trips: [] } }) : route.fallback()));
  await goToCloset(page);
  await useProfile(page, 'demo');
  const tabbar = page.locator('nav.tabbar');
  const lit = tabbar.locator('[aria-current="page"]');

  // Today: Recent outfits leads to Worn, and "‹ Today" comes back where Today was left
  await tabbar.getByRole('link', { name: 'Today' }).click();
  await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
  const recent = page.getByTestId('recent-outfits');
  await recent.scrollIntoViewIfNeeded();
  const scrolled = await page.evaluate(() => window.scrollY);
  expect(scrolled).toBeGreaterThan(200);
  const length = await page.evaluate(() => history.length);
  await recent.getByRole('link', { name: 'See all' }).click();
  await expect(page).toHaveURL(/\/today\/worn$/);
  await expect(lit).toHaveText('Today');
  await page.getByRole('link', { name: 'Today', exact: true }).first().click();
  await expect(page).toHaveURL(/\/today$/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(scrolled - 2);
  expect(await page.evaluate(() => history.length)).toBe(length + 1);

  // Trips: a plain link at the foot of Today, lit as Today, with "‹ Today"
  await page.getByRole('link', { name: 'Going away? Trips says what to pack.', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Trips', level: 1 })).toBeVisible();
  await expect(lit).toHaveText('Today');
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/today$/);

  // the review: from the closet's status line, lit as Closet, with "‹ Closet"
  await tabbar.getByRole('link', { name: /Closet/ }).click();
  await page.getByTestId('to-check').click();
  await page.getByRole('link', { name: 'Check them one at a time' }).click();
  await expect(page).toHaveURL(/\/review$/);
  await expect(lit).toHaveText(/^Closet/);
  await page.locator('.page-back').click();
  // the filter is kept in the closet's address, so the closet comes back as it was left
  await expect(page).toHaveURL(/\/\?check=1$/);
  await expect(page.getByRole('button', { name: 'Remove filter: Needs a check' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove filter: Needs a check' }).click();

  // the Wardrobe: Would this work? and the wishlist are one tap from the page, each with "‹ Wardrobe"
  await tabbar.getByRole('link', { name: 'Wardrobe' }).click();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Would this work?' }).click();
  await expect(page).toHaveURL(/\/wardrobe\/check$/);
  await expect(lit).toHaveText('Wardrobe');
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/wardrobe$/);

  // the wishlist, from its row under the things worth buying, and a wish from the list, with "‹ Wishlist"; each back
  // link goes Back, and the Wardrobe comes back where it was left
  const row = page.getByTestId('wishlist-open');
  await row.scrollIntoViewIfNeeded();
  const atRow = await page.evaluate(() => window.scrollY);
  expect(atRow).toBeGreaterThan(200);
  await row.click();
  await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
  await expect(page.getByRole('heading', { name: 'Wishlist', level: 1 })).toBeVisible();
  await expect(lit).toHaveText('Wardrobe');
  await page.getByTestId('wish-row').first().click();
  await expect(page).toHaveURL(/\/wardrobe\/wish\//);
  await expect(lit).toHaveText('Wardrobe');
  // going back adds nothing to history
  const deep = await page.evaluate(() => history.length);
  await expect(page.locator('.page-back')).toHaveText('Wishlist');
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
  await expect(page.locator('.page-back')).toHaveText('Wardrobe');
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/wardrobe$/);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(atRow - 2);
  expect(await page.evaluate(() => history.length)).toBe(deep);
});
