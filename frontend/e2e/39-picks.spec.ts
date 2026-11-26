import { axeViolations } from './a11y';
import type { Page } from '@playwright/test';
import { expect, hitArea, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend: a look for things you might like is a stand-in (tests/e2e_backend.py, FakeShop.picks), so nothing
// here reaches Claude or the web. The owner's closet starts as a copy of the demo closet, so there is enough to go on
// and each find is checked against a closet with something in it.
test.describe('you might like', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a read that fails with nothing kept says so in the card, with Try again', async ({ page }) => {
    // it showed nothing at all (the review of 23 November): the card was simply missing
    await page.setViewportSize({ width: 393, height: 852 });
    let fail = true;
    await page.route('**/api/picks', (route) => (fail && route.request().method() === 'GET'
      ? route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' })
      : route.fallback()));
    await page.goto(backend.url + '/wardrobe');
    const card = page.locator('section.picks');
    await expect(card.getByTestId('picks-failed')).toContainText("Couldn't load what you might like.", { timeout: 30_000 });
    await expect(card).not.toContainText('Internal Server Error');
    fail = false;
    await card.getByRole('button', { name: 'Try again' }).click();
    await expect(card.getByTestId('picks-failed')).toHaveCount(0);
    await expect(card.getByTestId('picks-look')).toBeVisible();
    await page.unroute('**/api/picks');
  });

  for (const theme of ['light', 'dark'] as const) {
    test(`a saved pick offers More like this again, at 320 wide (${theme}): one tap, nothing too wide, nothing below moves`, async ({ page }) => {
      // the owner's choice of 26 November: More like this comes back on a pick you saved. The card's answers are stood in
      // for (a made-up shop and products), so no look is needed
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width: 320, height: 700 });
      const more = await standInPicks(page);
      await page.goto(backend.url + '/wardrobe');
      const picks = page.locator('section.picks').getByTestId('pick');
      await expect(picks).toHaveCount(3, { timeout: 30_000 });
      const first = picks.first();
      const below = async () => picks.nth(1).evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
      const before = await below();
      await first.getByRole('button', { name: 'Save' }).click();
      await expect(first.getByRole('link', { name: 'On your wishlist' })).toBeVisible();
      await expect(first.getByRole('button', { name: /^Undo/ })).toBeVisible();
      const again = first.getByRole('button', { name: 'More like this' });
      await expect(again).toBeVisible();
      expect(await below()).toBe(before);   // saving moved nothing under it
      for (const target of [again, first.getByRole('link', { name: 'On your wishlist' }), first.getByRole('button', { name: /^Undo/ })]) {
        expect((await hitArea(target)).height).toBeGreaterThanOrEqual(44);
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      for (const el of await first.locator('.pick-actions .btn').all()) {
        expect(await el.evaluate((b) => b.scrollWidth <= b.clientWidth + 1)).toBe(true);   // no word cut inside a button
      }
      await first.scrollIntoViewIfNeeded();
      await page.screenshot({ path: test.info().outputPath(`saved-pick-320-${theme}.png`) });
      await again.click();
      await expect.poll(() => more.length).toBe(1);
      expect(more[0]).toBe('p1');
    });
  }

  test('look now, save one onto the wishlist, and turn one down with Undo', async ({ page }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: 393, height: 852 });
    await page.goto(backend.url + '/wardrobe');
    const card = page.locator('section.picks');
    // never looked: one sentence and Look now; nothing is searched before you ask
    await expect(card.getByRole('heading', { name: 'You might like' })).toBeVisible({ timeout: 30_000 });
    await expect(card).toContainText('Nines can look for three things you might like, from what you wear and love.');
    await card.getByText('How Nines looks').click();
    await expect(card.getByTestId('picks-sends')).toHaveText(/^A look sends Claude your style, what you tend to wear/);
    await expect(card.getByRole('switch')).toHaveCount(0);   // no weekly look to turn on before the first

    await card.getByText('How Nines looks').click();   // closed again, as the card usually is
    await card.getByTestId('picks-look').click();
    await expect(card.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toBeVisible();
    // while it looks, the card keeps the room of three picks: what is below it does not move when they come (it moved
    // down with each: the review of 24 November, 45)
    const below = page.getByRole('heading', { name: 'Thinking of buying something?' });
    const belowAt = async () => below.evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
    const whileLooking = await belowAt();
    const picks = card.getByTestId('pick');
    // the five finds are each checked against the closet on 40 kinds of day, about 30 seconds of computing in all on
    // a developer machine; in CI two such looks run at once, and a slow runner took just over a minute, so the wait is
    // three minutes
    await expect(picks).toHaveCount(3, { timeout: 180_000 });
    await expect(card.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toHaveCount(0);
    // within about two lines either way (the picks' own words and the font decide their height), not the whole card
    expect(Math.abs((await belowAt()) - whileLooking)).toBeLessThanOrEqual(48);
    // beside a hanger (no picture from the shop) a name has three lines, so the kind of piece is there (44)
    await expect(picks.first().locator('.pick-name')).toContainText('trench coat');
    await expect(picks.nth(1).locator('.pick-name')).toContainText('chore jacket');
    await expect(card).not.toContainText('Not a real link');
    await expect(card).not.toContainText('Striped oxford');   // it repeats a shirt the closet has
    const coat = picks.first();
    await expect(coat).toContainText('Example Shop · $320.00');
    await expect(coat).toContainText('Fills a gap in your closet.');
    await expect(picks.nth(1)).toContainText(/Goes with \d+ of your pieces\./);
    await expect(coat.getByRole('link', { name: /^Water-repellent/ })).toHaveAttribute('target', '_blank');
    await card.getByText('How Nines looks').click();
    await expect(card.getByRole('switch', { name: 'Look for me each week' })).toBeChecked();   // on once you have looked
    expect(await axeViolations(page)).toEqual([]);

    // Save: onto the wishlist, with the product as its first find
    const actions = coat.locator('.pick-actions');
    const unsavedHeight = await actions.evaluate((el) => el.getBoundingClientRect().height);
    await coat.getByRole('button', { name: 'Save' }).click();
    await expect(coat.getByRole('link', { name: 'On your wishlist' })).toBeVisible();
    const wishes = (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes;
    const made = wishes.find((w: { name: string }) => w.name.startsWith('Water-repellent cotton gabardine'));
    expect(made).toBeTruthy();
    const finds = (await (await page.request.get(`${backend.url}/api/wishlist/${made.id}/finds`)).json()).finds;
    expect(finds.map((f: { price: number }) => f.price)).toEqual([320]);
    // saved: "On your wishlist" and Undo on one line, as a gap's card (the buttons stacked, with no Undo: 43), and
    // More like this as before (26 November): on a phone on a line of its own in both states, so the row is as tall
    const wished = (await actions.getByRole('link', { name: 'On your wishlist' }).boundingBox())!;
    expect((await actions.getByRole('button', { name: /^Undo/ }).boundingBox())!.y).toBe(wished.y);
    await expect(actions.getByRole('button', { name: 'More like this' })).toBeVisible();
    expect(await actions.evaluate((el) => el.getBoundingClientRect().height)).toBe(unsavedHeight);
    await actions.getByRole('button', { name: /^Undo/ }).click();
    await expect(coat.getByRole('button', { name: 'Save' })).toBeVisible();
    expect((await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes.map((w: { id: string }) => w.id)).not.toContain(made.id);
    await coat.getByRole('button', { name: 'Save' }).click();
    await expect(coat.getByRole('link', { name: 'On your wishlist' })).toBeVisible();

    // Not for me: gone, with Undo in its place
    const jacket = picks.filter({ hasText: 'Garment-dyed' });
    await jacket.getByRole('button', { name: /^Not for me/ }).click();
    const gone = card.getByRole('status').filter({ hasText: "Not for me. You won't see it again." });
    await expect(gone).toBeVisible();
    await expect(picks).toHaveCount(2);
    await gone.getByRole('button', { name: 'Undo' }).click();
    await expect(picks).toHaveCount(3);
    await expect(picks.nth(1)).toContainText('Garment-dyed');
  });
});

/** Three made-up picks, the first saved on Save, and the ids More like this was asked for. */
async function standInPicks(page: Page): Promise<string[]> {
  const pick = (id: string, name: string) => ({
    id, kind: 'taste', source: 'look', name, shop: 'Example Shop', url: `https://shop.example/${id}`, image_url: null,
    price: 120, price_before: null, currency: 'USD', piece: { category: 'jacket' }, verdict: 'gap',
    verdict_words: 'Fills a gap in your closet.', pairs: 4, found_at: '2026-11-26T09:00:00Z', state: 'shown', wish_id: null,
  });
  const answer = (saved: boolean) => ({
    picks: [{ ...pick('p1', 'Example field jacket in waxed cotton'), ...(saved ? { state: 'saved', wish_id: 'w1' } : {}) },
      pick('p2', 'Example chore jacket in heavy canvas'), pick('p3', 'Example quilted liner jacket')],
    run: null, last: { source: 'look', at: '2026-11-26T09:00:00Z', found: 3 }, looked: true, weekly: true, enough: true,
    demo: false, estimate: { api: false, look_usd: 0 }, offer: null, shops: 1,
  });
  let saved = false;
  const asked: string[] = [];
  await page.route('**/api/picks', (route) => (route.request().method() === 'GET' ? route.fulfill({ json: answer(saved) }) : route.fallback()));
  await page.route('**/api/picks/*/save', (route) => {
    saved = route.request().method() === 'POST';
    return route.fulfill({ json: { ...answer(saved), ...(saved ? { wish_id: 'w1' } : {}) } });
  });
  await page.route('**/api/picks/*/more', (route) => {
    asked.push(decodeURIComponent(route.request().url().split('/').slice(-2)[0]));
    return route.fulfill({ json: answer(saved) });
  });
  return asked;
}
