import { type Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test, useProfile } from './fixtures';

// A closet the tests start from has no price news (no price has come down in it), so the news is a stand-in, as the
// updates banner's is (14-updates.spec.ts); marking it seen is a stand-in too, which keeps what the page sent.

type News = { wish_id: string; name: string; shop: string; from: number; to: number; currency: string; percent: number; at: string; at_price: boolean };

const news = (wishId: string, over: Partial<News> = {}): News => ({
  wish_id: wishId, name: 'A tan rain coat', shop: 'Example Shop', from: 177, to: 150, currency: 'USD', percent: 15,
  at: '2026-11-22T09:00:00.000000Z', at_price: false, ...over,
});

/** Answers the news with `told`, and marking it seen by taking those wishes out; gives back what was marked seen. */
async function standIn(page: Page, told: News[]): Promise<string[][]> {
  const seen: string[][] = [];
  let left = told;
  await page.route('**/api/wishlist/news', (route) => route.fulfill({ json: { news: left } }));
  await page.route('**/api/wishlist/news/seen', (route) => {
    const ids: string[] = route.request().postDataJSON().wish_ids;
    seen.push(ids);
    left = left.filter((n) => !ids.includes(n.wish_id));
    return route.fulfill({ json: { news: left } });
  });
  return seen;
}

test('price news (stand-in): a banner tells you, and See it opens the wish, which marks it seen', async ({ page }) => {
  const wish = await (await page.request.post('/api/wishlist', { data: { name: 'A tan rain coat' } })).json();
  const seen = await standIn(page, [news(wish.id, { at_price: true })]);
  await goToCloset(page);
  const banner = page.getByTestId('price-news');
  await expect(banner).toContainText("A tan rain coat is down to $150.00 at Example Shop, from $177.00. That's within your price.");
  expect(await axeViolations(page, '[data-testid="price-news"]')).toEqual([]);
  expect(seen).toEqual([]);   // reading the news changes nothing

  await banner.getByRole('button', { name: 'See it' }).click();
  await expect(page).toHaveURL(new RegExp(`/wardrobe/wish/${wish.id}$`));
  await expect(page.getByRole('heading', { name: 'A tan rain coat', level: 1 })).toBeVisible();
  await expect(banner).toHaveCount(0);
  expect(seen[0]).toEqual([wish.id]);
  await page.request.delete(`/api/wishlist/${wish.id}`);
});

test('price news (stand-in) for several wishes: one sentence, See them opens the Wardrobe, Got it marks them all seen', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const seen = await standIn(page, [news('w1'), news('w2', { name: 'Brown suede loafers with a long name', to: 54.4, from: 68 })]);
  await goToCloset(page);
  const banner = page.getByTestId('price-news');
  await expect(banner).toContainText('Prices went down for 2 things on your wishlist.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);

  await banner.getByRole('button', { name: 'See them' }).click();
  await expect(page).toHaveURL(/\/wardrobe$/);
  await expect(banner).toBeVisible();   // the list is not each wish: the news stays until you look or say Got it
  expect(seen).toEqual([]);
  await banner.getByRole('button', { name: 'Got it' }).click();
  await expect(banner).toHaveCount(0);
  expect(seen).toEqual([['w1', 'w2']]);
});

test('price news is never asked for in the demo closet', async ({ page }) => {
  let asked = 0;
  await page.route('**/api/wishlist/news', (route) => {
    asked += 1;
    return route.fulfill({ json: { news: [news('w1')] } });
  });
  await useProfile(page, 'demo');
  await expect(page.getByRole('note').filter({ hasText: 'Demo closet' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('price-news')).toHaveCount(0);
  expect(asked).toBe(0);
  await useProfile(page, 'main');
});
