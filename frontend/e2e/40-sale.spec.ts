import { axeViolations } from './a11y';
import { expect, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend: a look for things on sale is a stand-in (tests/e2e_backend.py, FakeShop.sale) whose made-up pages
// are read by the real page reader (ShopPages, SALE_PAGES), so nothing here reaches Claude or the web. The owner's
// closet starts as a copy of the demo closet, so there is enough to go on.
test.describe('on sale now', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('the On sale view, Shops you like, a sale row and Save', async ({ page }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: 393, height: 852 });
    await page.goto(backend.url + '/wardrobe');
    const card = page.locator('section.picks');
    await expect(card.getByRole('heading', { name: 'You might like' })).toBeVisible({ timeout: 30_000 });
    // two views with one switch; On sale has never looked, and offers to name shops once
    await card.getByRole('button', { name: 'On sale' }).click();
    await expect(card.getByRole('button', { name: 'On sale' })).toHaveAttribute('aria-pressed', 'true');
    await expect(card).toContainText('Nines can look for things on sale that suit you, in shops you might never have found.');
    await card.getByTestId('picks-shops').click();

    // Shops you like: Settings, Everyday, its sheet opened by the card's link; saved as you go
    await expect(page).toHaveURL(/\/settings\?open=shops$/);
    const sheet = page.getByTestId('shops-sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText('Nines starts here when it looks for things on sale, and tells Claude these names.');
    const box = sheet.getByLabel("A shop's name or site");
    await box.fill('https://www.small-maker.example/collections/sale?page=2');
    await box.press('Enter');
    await expect(sheet.getByRole('listitem')).toHaveText(['small-maker.exampleRemove']);
    await box.fill('Example Shop');
    await sheet.getByRole('button', { name: 'Add' }).click();
    await expect(sheet.getByRole('status')).toHaveText('Saved');
    await box.fill('example shop');
    await box.press('Enter');
    await expect(sheet.getByRole('alert')).toHaveText('That shop is on your list already.');
    await sheet.getByRole('button', { name: 'Remove small-maker.example' }).click();
    await expect(sheet.getByRole('listitem')).toHaveCount(1);
    const everyday = page.locator('section[aria-labelledby="s-everyday"]');
    await sheet.getByRole('button', { name: 'Done' }).click();
    await expect(sheet).toBeHidden();
    await expect(everyday.getByTestId('shops-line')).toHaveText('Shops you like: Example Shop');

    // back on the Wardrobe the view is remembered; with a shop named, the offer is gone
    await page.goto(backend.url + '/wardrobe');
    await expect(card.getByRole('button', { name: 'On sale' })).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 });
    await expect(card.getByTestId('picks-shops')).toHaveCount(0);
    await card.getByText('How Nines looks').click();
    await expect(card.getByTestId('picks-sends')).toContainText('A look for things on sale also sends the shops you like');
    await card.getByTestId('picks-look').click();
    await expect(card.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toBeVisible();
    const picks = card.getByTestId('pick');
    // the finds are judged against the closet before they show: why the wait is three minutes is in 39-picks.spec.ts
    await expect(picks).toHaveCount(3, { timeout: 180_000 });
    await expect(card).not.toContainText('Cotton twill pleated trousers');   // 8% off: not a sale worth a pick
    await expect(card).not.toContainText('Brushed flannel work shirt');      // sold out on its page
    const coat = picks.filter({ hasText: 'Double-faced wool' });
    await expect(coat.getByTestId('pick-price')).toHaveText('Was $240.00, now $168.00 (30% less)');
    await expect(coat.getByTestId('pick-note')).toHaveText('Your size is in stock.');
    const knit = picks.filter({ hasText: 'Hand-framed lambswool' });
    await expect(knit.getByTestId('pick-price')).toHaveText('Was $150.00, now $105.00 (30% less)');
    await expect(knit.getByTestId('pick-note')).toHaveText('Claude read the earlier price from the page.');
    await expect(picks.filter({ hasText: 'Waxed suede' }).getByTestId('pick-price')).toHaveText('Was $260.00, now $195.00 (25% less)');
    expect(await axeViolations(page)).toEqual([]);

    // Save: onto the wishlist, its price before kept so the wish shows the drop
    await coat.getByRole('button', { name: 'Save' }).click();
    await expect(coat.getByRole('link', { name: 'On your wishlist' })).toBeVisible();
    const wishes = (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes;
    const made = wishes.find((w: { name: string }) => w.name.startsWith('Double-faced wool'));
    const finds = (await (await page.request.get(`${backend.url}/api/wishlist/${made.id}/finds`)).json()).finds;
    expect(finds[0].history.map((h: { price: number }) => h.price)).toEqual([240, 168]);

    // For you keeps its own state: never looked there
    await card.getByRole('button', { name: 'For you' }).click();
    await expect(card).toContainText('Nines can look for three things you might like, from what you wear and love.');
    await expect(picks).toHaveCount(0);
  });
});
