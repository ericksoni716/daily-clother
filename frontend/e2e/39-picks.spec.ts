import { axeViolations } from './a11y';
import { expect, test } from './fixtures';
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

    await card.getByTestId('picks-look').click();
    await expect(card.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toBeVisible();
    const picks = card.getByTestId('pick');
    // the five finds are each checked against the closet on 40 kinds of day, about 30 seconds of computing in all on
    // a developer machine; in CI two such looks run at once, and a slow runner took just over a minute, so the wait is
    // three minutes
    await expect(picks).toHaveCount(3, { timeout: 180_000 });
    await expect(card).not.toContainText('Not a real link');
    await expect(card).not.toContainText('Striped oxford');   // it repeats a shirt the closet has
    const coat = picks.first();
    await expect(coat).toContainText('Example Shop · $320.00');
    await expect(coat).toContainText('Fills a gap in your closet.');
    await expect(picks.nth(1)).toContainText(/Goes with \d+ of your pieces\./);
    await expect(coat.getByRole('link', { name: /^Water-repellent/ })).toHaveAttribute('target', '_blank');
    await expect(card.getByRole('switch', { name: 'Look for me each week' })).toBeChecked();   // on once you have looked
    expect(await axeViolations(page)).toEqual([]);

    // Save: onto the wishlist, with the product as its first find
    await coat.getByRole('button', { name: 'Save' }).click();
    await expect(coat.getByRole('link', { name: 'On your wishlist' })).toBeVisible();
    const wishes = (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes;
    const made = wishes.find((w: { name: string }) => w.name.startsWith('Water-repellent cotton gabardine'));
    expect(made).toBeTruthy();
    const finds = (await (await page.request.get(`${backend.url}/api/wishlist/${made.id}/finds`)).json()).finds;
    expect(finds.map((f: { price: number }) => f.price)).toEqual([320]);

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
