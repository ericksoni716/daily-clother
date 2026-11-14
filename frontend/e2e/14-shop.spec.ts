import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend: searching shops and checking prices are stand-ins (tests/e2e_backend.py, FakeShop), so nothing
// here reaches Claude or the web. The owner's closet starts as a copy of the demo closet, so what is found is
// checked against a closet with something in it.
test.describe('shopping for a wish', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('find some, see how each would work with the closet, check the prices and see a drop', async ({ page }) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/missing');
    const wishlist = page.getByTestId('wishlist');
    await wishlist.getByRole('button', { name: 'Add by hand' }).click({ timeout: 30_000 });
    await wishlist.getByLabel('What are you looking for?').fill('A tan rain coat');
    await wishlist.getByRole('button', { name: 'Add to the list' }).click();
    const wish = wishlist.getByTestId('wish').filter({ hasText: 'A tan rain coat' });
    await expect(wish).toBeVisible();

    // a price range, said to Claude when it searches
    await wish.getByRole('button', { name: 'Set one' }).click();
    const range = wish.getByRole('form', { name: 'Price range' });
    await range.getByLabel('To').fill('200');
    await range.getByRole('button', { name: 'Save price range' }).click();
    await expect(wish).toContainText('Price range: Up to $200.00');

    await wish.getByTestId('find-some').click();
    await expect(wish.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toBeVisible();
    const finds = wish.getByTestId('find');
    await expect(finds).toHaveCount(2, { timeout: 30_000 });   // the one without a web address is not kept
    await expect(wish).not.toContainText('Not a real link');

    const coat = finds.filter({ hasText: 'Tan gabardine rain coat' });
    await expect(coat).toContainText('Example Shop · $180.00');
    await expect(coat).toHaveAttribute('data-verdict', 'fills_gap');
    await expect(coat.getByTestId('find-verdict')).toHaveText('Fills a gap');
    await expect(coat.getByRole('list', { name: 'Why' }).getByRole('listitem').first()).toBeVisible();
    const polo = finds.filter({ hasText: 'Navy pique polo' });
    await expect(polo.getByTestId('find-verdict')).not.toBeEmpty();
    // links open in a new tab and nothing is opened by itself
    const open = coat.getByRole('link', { name: 'Open in shop' });
    await expect(open).toHaveAttribute('href', 'https://shop.example/tan-coat');
    await expect(open).toHaveAttribute('target', '_blank');
    await expect(open).toHaveAttribute('rel', 'noopener noreferrer');
    expect(page.context().pages()).toHaveLength(1);

    // a price check sees every price lower: the drop is shown
    await wish.getByTestId('check-prices').click();
    await expect(coat.getByTestId('find-drop')).toHaveText('Was $180.00, now $144.00 (20% less)', { timeout: 30_000 });
    await expect(coat).toContainText('Example Shop · $144.00');
    await expect(wish).toContainText('Prices last checked');

    // a find can be taken off
    await polo.getByRole('button', { name: 'Remove' }).click();
    await expect(finds).toHaveCount(1);

    // the demo closet never searches, and says why
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'demo' } })).ok()).toBe(true);
    expect((await page.request.post(backend.url + '/api/wishlist', { data: { name: 'Brown loafers' } })).ok()).toBe(true);
    await page.goto(backend.url + '/missing');
    const demoWish = page.getByTestId('wishlist').getByTestId('wish').filter({ hasText: 'Brown loafers' });
    await expect(demoWish).toContainText('The demo closet never searches shops', { timeout: 30_000 });
    await expect(demoWish.getByTestId('find-some')).toBeDisabled();
  });
});
