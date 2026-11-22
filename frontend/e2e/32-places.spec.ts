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

test('on a phone: Worn, Trips and the review are one level down in their place, and their back links go Back', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
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
  await page.getByRole('link', { name: 'Trips', exact: true }).click();
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
  await expect(page).toHaveURL(/\/$/);
  // the filter is kept while the app is open, so the closet comes back as it was left
  await expect(page.getByRole('button', { name: 'Remove filter: Needs a check' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove filter: Needs a check' }).click();

  // the Wardrobe: Would this work? and a wish are on the page, each with "‹ Wardrobe"
  await tabbar.getByRole('link', { name: 'Wardrobe' }).click();
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Would this work?' }).click();
  await expect(page).toHaveURL(/\/wardrobe\/check$/);
  await expect(lit).toHaveText('Wardrobe');
  await page.locator('.page-back').click();
  await expect(page).toHaveURL(/\/wardrobe$/);
});
