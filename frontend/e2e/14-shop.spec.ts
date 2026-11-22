import { axeViolations } from './a11y';
import { expect, test } from './fixtures';
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
    await expect(page.locator('#closet-title')).toBeVisible();

    await page.goto(backend.url + '/wardrobe');
    const wishlist = page.getByTestId('wishlist');
    await wishlist.getByRole('button', { name: 'Add by hand' }).click({ timeout: 30_000 });
    await wishlist.getByLabel('What are you looking for?').fill('A tan rain coat');
    await wishlist.getByRole('button', { name: 'Add to the list' }).click();
    // shopping is one level down, on the wish's own page
    await wishlist.getByTestId('wish-row').filter({ hasText: 'A tan rain coat' }).click();
    const wish = page.getByTestId('wish');
    await expect(page.getByRole('heading', { name: 'A tan rain coat', level: 1 })).toBeVisible();
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
    expect(await axeViolations(page)).toEqual([]);

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
    await page.goto(backend.url + '/wardrobe');
    await page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: 'Brown loafers' }).click({ timeout: 30_000 });
    const demoWish = page.getByTestId('wish');
    await expect(demoWish).toContainText('The demo closet never searches shops', { timeout: 30_000 });
    await expect(demoWish.getByTestId('find-some')).toBeDisabled();
  });

  // A product's page sent as a link: its page is read by Nines itself (tests/e2e_backend.py, ShopPages, made-up pages
  // that never reach the web), and Claude's stand-in only for a page that gives no price.
  test('paste a link, see the wish with its price, check it again and see the drop on its row', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(backend.url + '/wardrobe');
    const wishlist = page.getByTestId('wishlist');
    await wishlist.getByRole('button', { name: 'Add a link' }).click({ timeout: 30_000 });
    const box = wishlist.getByRole('form', { name: 'Add a link' });
    const field = box.getByLabel("The address of a product's page");
    // not a link: said in the box, nothing sent
    await field.fill('a linen shirt');
    await box.getByRole('button', { name: 'Add to the list' }).click();
    await expect(box.getByRole('alert')).toHaveText('Paste the whole address of the page, starting with https://.');
    // a link the server will not open: its reason, in the box
    await field.fill('http://shop.example/linen-shirt');
    await box.getByRole('button', { name: 'Add to the list' }).click();
    await expect(box.getByRole('alert')).toHaveText('Nines only opens pages whose address starts with https://.');

    await field.fill('Have a look: https://shop.example/linen-shirt');
    await box.getByRole('button', { name: 'Add to the list' }).click();
    // the new wish's own page: named after the product once its page is read, with its price
    await expect(page).toHaveURL(/\/wardrobe\/wish\//);
    const wish = page.getByTestId('wish');
    const find = wish.getByTestId('find');
    await expect(find).toHaveCount(1);
    await expect(find).toContainText('Example Shop · $68.00', { timeout: 30_000 });
    await expect(find.getByTestId('find-link')).toHaveText('You sent this link.');
    await expect(page.getByRole('heading', { name: 'Linen camp-collar shirt', level: 1 })).toBeVisible();
    await expect(find.getByRole('link', { name: 'Open in shop' })).toHaveAttribute('href', 'https://shop.example/linen-shirt');
    expect(await axeViolations(page)).toEqual([]);

    // read again a little cheaper: the drop on the wish, then on its row in the wishlist
    await wish.getByTestId('check-prices').click();
    await expect(find.getByTestId('find-drop')).toHaveText('Was $68.00, now $54.40 (20% less)', { timeout: 30_000 });
    await page.goto(backend.url + '/wardrobe');
    const row = page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: 'Linen camp-collar shirt' });
    await expect(row.getByTestId('wish-drop')).toHaveText('Down from $68.00 to $54.40', { timeout: 30_000 });
    await expect(row).toContainText('$54.40 at Example Shop');
  });

  test('a link shared from another app opens the box filled in, and nothing is added without a tap', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    await page.setViewportSize({ width: 390, height: 844 });
    const count = async () => (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes.length;
    const before = await count();
    // as Android's share sheet sends it: the link in the text, with words around it
    await page.goto(backend.url + '/wardrobe/link?title=A%20shirt&text=' + encodeURIComponent('Look at this https://shop.example/plain-shirt'));
    await expect(page.getByRole('heading', { name: 'Add a link', level: 1 })).toBeVisible({ timeout: 30_000 });
    const box = page.getByRole('form', { name: 'Add a link' });
    await expect(box.getByLabel("The address of a product's page")).toHaveValue('https://shop.example/plain-shirt');
    expect(await count()).toBe(before);
    expect(await axeViolations(page)).toEqual([]);

    await box.getByRole('button', { name: 'Add to the list' }).click();
    // the page gives no price, so Claude's stand-in reads it
    const find = page.getByTestId('wish').getByTestId('find');
    await expect(find).toContainText('$80.00', { timeout: 30_000 });
    await expect(find.getByTestId('find-link')).toHaveText('You sent this link. Claude read its price from the page.');
    await expect(page.getByRole('heading', { name: 'A plain shirt', level: 1 })).toBeVisible();
    expect(await count()).toBe(before + 1);
    // nothing wider than the phone
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
