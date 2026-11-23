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
    // a closet that can dress you opens on Today (src/landing.ts), depending on whether its clothes or its title come
    // first: either means the page is up (fixtures.ts's goToCloset waits the same way)
    await expect(page.locator('#closet-title').or(page.locator('#today-title'))).toBeVisible();

    await page.goto(backend.url + '/wardrobe');
    // each thing worth buying can be looked for on Google Shopping, in your browser, with only what to look for
    // (inside the card, once it is opened)
    await page.getByTestId('gap').first().getByRole('heading', { level: 3 }).getByRole('button').click({ timeout: 30_000 });
    const search = page.getByTestId('gap').first().getByRole('link', { name: 'Search Google Shopping' });
    await expect(search).toHaveAttribute('href', /^https:\/\/www\.google\.com\/search\?tbm=shop&q=men's%20/, { timeout: 30_000 });
    await expect(search).toHaveAttribute('target', '_blank');
    await page.goto(backend.url + '/wardrobe/wishlist');
    const wishlist = page.getByTestId('wishlist');
    await wishlist.getByRole('button', { name: 'Add by hand' }).click({ timeout: 30_000 });
    await wishlist.getByLabel('What are you looking for?').fill('A tan rain coat');
    await wishlist.getByRole('button', { name: 'Add to the list' }).click();
    // shopping is one level down, on the wish's own page
    await wishlist.getByTestId('wish-row').filter({ hasText: 'A tan rain coat' }).click();
    const wish = page.getByTestId('wish');
    await expect(page.getByRole('heading', { name: 'A tan rain coat', level: 1 })).toBeVisible();
    await expect(wish).toBeVisible();

    // nothing watched yet: the price is offered where Claude is asked to look
    const price = wish.getByTestId('wish-price');
    await expect(price).toContainText('Claude looks at any price.');
    await expect(wish.getByRole('link', { name: 'Search Google Shopping' }))
      .toHaveAttribute('href', "https://www.google.com/search?tbm=shop&q=men's%20tan%20rain%20coat");
    // the most you'd pay, in a sheet over the page: one amount and its currency, and no lower limit
    await price.getByRole('button', { name: "Set the most you'd pay" }).click();
    const sheet = page.getByTestId('price-sheet');
    await expect(sheet.getByRole('heading', { name: "The most you'd pay" })).toBeVisible();
    await expect(sheet.getByLabel('From')).toHaveCount(0);
    await expect(sheet.getByRole('button', { name: 'Clear' })).toHaveCount(0);   // nothing to clear yet
    await expect(sheet.getByLabel('Currency')).toHaveValue('USD');
    await sheet.getByLabel('Amount').fill('cheap');
    await sheet.getByRole('button', { name: 'Save' }).click();
    await expect(sheet.getByRole('alert')).toHaveText('Type the price as a number, like 45 or 45.50.');
    // a decimal comma is the same price (it was read a hundred times too high: 20,000.00)
    await sheet.getByLabel('Amount').fill('200,00');
    await sheet.getByRole('button', { name: 'Save' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(price).toContainText('Claude looks for ones up to $200.00.');
    const saved = (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes
      .find((w: { name: string }) => w.name === 'A tan rain coat');
    expect([saved.price_min, saved.price_max, saved.price_currency]).toEqual([null, 200, 'USD']);

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

    // what is watched comes first, then one sentence about watching with the price, then looking for more, the note,
    // and what to do with the wish
    await expect(wish.getByTestId('wish-price')).toHaveText(
      "Nines checks the price once a day while it's running and tells you when it goes down to $200.00 or less. Change");
    const text = await wish.innerText();
    const order = ['Tan gabardine rain coat', 'Nines checks the price once a day', 'Last checked today', 'Find more', 'Note',
      'Would it go with my clothes?', 'I bought it', 'Remove from the list'].map((words) => text.indexOf(words));
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    await expect(wish).not.toContainText('Nothing is ever bought for you');
    await expect(wish.getByRole('button', { name: 'Would it go with my clothes?' })).toHaveAttribute('title', /against your closet/);

    // Check now sees every price lower: the drop is shown
    await wish.getByRole('button', { name: 'Check now' }).click();
    await expect(coat.getByTestId('find-drop')).toHaveText('Was $180.00, now $144.00 (20% less)', { timeout: 30_000 });
    await expect(coat).toContainText('Example Shop · $144.00');
    await expect(wish.getByTestId('prices-checked')).toContainText('Last checked today at');

    // the price can be changed in the same sheet, and cleared
    await wish.getByTestId('wish-price').getByRole('button', { name: 'Change' }).click();
    await expect(sheet.getByLabel('Amount')).toHaveValue('200');
    await sheet.getByRole('button', { name: 'Clear' }).click();
    await expect(wish.getByTestId('wish-price')).toContainText('tells you when it goes down. ');

    // watching a find can be stopped
    await polo.getByRole('button', { name: 'Stop watching' }).click();
    await expect(finds).toHaveCount(1);

    // the demo closet never searches, and says why
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'demo' } })).ok()).toBe(true);
    expect((await page.request.post(backend.url + '/api/wishlist', { data: { name: 'Brown loafers' } })).ok()).toBe(true);
    await page.goto(backend.url + '/wardrobe/wishlist');
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
    await page.goto(backend.url + '/wardrobe/wishlist');
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
    // Claude's stand-in describes it from the page's words, and it is checked against the closet as a search's finds are
    await expect(find.getByTestId('find-verdict')).not.toBeEmpty({ timeout: 30_000 });
    await expect(find.getByRole('list', { name: 'Why' }).getByRole('listitem').first()).toBeVisible();
    await expect(find).toContainText('Claude saw: Linen camp-collar shirt, white shirt');
    await expect(find.getByTestId('find-not-judged')).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);

    // read again a little cheaper: the drop on the wish, then on its row in the wishlist
    await wish.getByRole('button', { name: 'Check now' }).click();
    await expect(find.getByTestId('find-drop')).toHaveText('Was $68.00, now $54.40 (20% less)', { timeout: 30_000 });

    // Would it go with my clothes? starts from the product's name on the page that was sent
    await wish.getByRole('button', { name: 'Would it go with my clothes?' }).click();
    await expect(page).toHaveURL(/\/wardrobe\/check\/wish\//);
    await expect(page.getByTestId('would-work').getByLabel('Name (optional)')).toHaveValue('Linen camp-collar shirt');
    // on the Wardrobe, the row to the wishlist counts the things on it and the prices that went down, as the list does
    const { wishes } = await (await page.request.get(backend.url + '/api/wishlist')).json();
    const down = wishes.filter((w: { drop: unknown }) => w.drop).length;
    expect(down).toBeGreaterThan(0);
    await page.goto(backend.url + '/wardrobe');
    const open = page.getByTestId('wishlist-open');
    await expect(open).toContainText(`${wishes.length} ${wishes.length === 1 ? 'thing' : 'things'}`, { timeout: 30_000 });
    await expect(open.getByTestId('wishlist-down')).toHaveText(`${down} ${down === 1 ? 'price' : 'prices'} went down`);
    await open.click();
    await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
    const row = page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: 'Linen camp-collar shirt' });
    await expect(row.getByTestId('wish-drop')).toHaveText('Down from $68.00 to $54.40', { timeout: 30_000 });
    await expect(row).toContainText('$54.40 at Example Shop');
    await expect(page.getByTestId('wishlist').getByTestId('wish-drop')).toHaveCount(down);
  });

  // The wish is named after the product as soon as its page is read, not when Claude has finished describing it: the
  // page takes three seconds to read (ShopPages' slow shirt), so the wishlist was asked for before, and the run is
  // held in its describing step here for as long as the test looks.
  test("a wish made from a link carries the product's name while Claude is still describing it", async ({ page }) => {
    test.setTimeout(90_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    await page.setViewportSize({ width: 1280, height: 900 });
    const finds = /\/api\/wishlist\/[^/]+\/finds$/;   // only the finds themselves, not a find's outfits or its code
    await page.route(finds, async (route) => {
      if (route.request().method() !== 'GET') return route.continue();
      const answer = await route.fetch();
      const body = await answer.json();
      if (body.run && body.run.state !== 'running') {
        // the run ended: answered as still describing, with what the page gave
        body.run = { ...body.run, state: 'running', step: 'describe', message: null, added: null, finished_at: null };
      }
      await route.fulfill({ response: answer, json: body });
    });
    await page.goto(backend.url + '/wardrobe/wishlist');
    const wishlist = page.getByTestId('wishlist');
    await wishlist.getByRole('button', { name: 'Add a link' }).click({ timeout: 30_000 });
    const box = wishlist.getByRole('form', { name: 'Add a link' });
    await box.getByLabel("The address of a product's page").fill('https://shop.example/slow-shirt');
    await box.getByRole('button', { name: 'Add to the list' }).click();
    await expect(page).toHaveURL(/\/wardrobe\/wish\//);
    const wish = page.getByTestId('wish');
    const describing = wish.getByRole('status').filter({ hasText: 'Claude is describing it…' });
    await expect(wish.getByTestId('find')).toContainText('Example Shop · $68.00', { timeout: 30_000 });
    await expect(describing).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'Slowly read linen shirt', level: 1 })).toBeVisible({ timeout: 10_000 });
    // still describing: the name came with the page's reading, not with the run's end
    await expect(describing).toBeVisible();
    await page.unroute(finds);
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
    await expect(page.getByRole('link', { name: 'Wishlist', exact: true })).toHaveAttribute('href', '/wardrobe/wishlist');

    await box.getByRole('button', { name: 'Add to the list' }).click();
    // the page gives no price, so Claude's stand-in reads it
    const find = page.getByTestId('wish').getByTestId('find');
    await expect(find).toContainText('$80.00', { timeout: 30_000 });
    await expect(find.getByTestId('find-link')).toHaveText('You sent this link. Claude read its price from the page.');
    await expect(page.getByRole('heading', { name: 'A plain shirt', level: 1 })).toBeVisible();
    expect(await count()).toBe(before + 1);
    // nothing wider than the phone
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    // "‹ Wishlist" leads to the list, with the new wish on it (the shared link's page is not offered again)
    await page.getByRole('link', { name: 'Wishlist', exact: true }).click();
    await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
    await expect(page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: 'A plain shirt' })).toBeVisible();
  });

  // A judged find worn with your own clothes: the outfits Would this work? makes with it, drawn as worn on this computer
  // (nothing asks Claude), in a sheet over the wish's page, with the shop's picture beside the drawing.
  test('see a judged find with your clothes, step through its outfits and close the sheet', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    const made = await page.request.post(backend.url + '/api/wishlist/link', { data: { url: 'https://shop.example/long-name' } });
    expect(made.ok()).toBe(true);
    const { id } = await made.json();
    await page.setViewportSize({ width: 393, height: 760 });
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    const find = page.getByTestId('wish').getByTestId('find');
    // Claude's stand-in describes the page, then it is judged against the closet: only then is the action offered
    await expect(find.getByTestId('find-verdict')).not.toBeEmpty({ timeout: 60_000 });
    await find.getByRole('button', { name: 'See it with your clothes' }).click();

    const sheet = page.getByTestId('worn-sheet');
    await expect(sheet.getByRole('heading', { name: 'With your clothes' })).toBeVisible();
    await expect(sheet).toContainText("This piece is drawn from the shop's description, so it shows roughly its shape and colour");
    const outfit = sheet.getByTestId('worn-outfit');
    await expect(outfit.getByTestId('outfit-figure').locator('img')).toBeVisible({ timeout: 30_000 });
    await expect(outfit.getByRole('list')).toContainText('This piece');
    // the owner's own pieces in it open as elsewhere
    await expect(outfit.getByRole('list').getByRole('link').first()).toHaveAttribute('href', /^\/wardrobe\/item\//);
    await expect(sheet.getByText(/^Outfit 1 of [23], for an? /)).toBeVisible();
    await sheet.getByRole('button', { name: 'The next outfit' }).click();
    await expect(sheet.getByText(/^Outfit 2 of [23], for an? /)).toBeVisible();
    await expect(outfit.getByTestId('outfit-figure').locator('img')).toBeVisible({ timeout: 30_000 });
    expect(await axeViolations(page)).toEqual([]);
    await sheet.getByRole('button', { name: 'Done' }).click();
    await expect(sheet).toHaveCount(0);
  });
});
