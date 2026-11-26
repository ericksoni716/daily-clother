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
    test.setTimeout(300_000);
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
    // the form opens in a sheet over the list (it was put in above the list, and Escape did nothing: the review of 24
    // November, 42); the list under it does not move
    const listTop = async () => wishlist.locator('.wish-list, [data-testid="wishlist-empty"]').first().evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
    const listAt = await listTop();
    await wishlist.getByRole('button', { name: 'Add by hand' }).click({ timeout: 30_000 });
    const hand = page.getByTestId('hand-sheet');
    await expect(hand.getByRole('heading', { name: 'Add by hand' })).toBeVisible();
    expect(await listTop()).toBe(listAt);
    await page.keyboard.press('Escape');
    await expect(hand).toHaveCount(0);
    await wishlist.getByRole('button', { name: 'Add by hand' }).click();
    await wishlist.getByLabel('What are you looking for?').fill('A tan rain coat');
    await wishlist.getByRole('button', { name: 'Add to the list' }).click();
    // shopping is one level down, on the wish's own page
    await wishlist.getByTestId('wish-row').filter({ hasText: 'A tan rain coat' }).click();
    const wish = page.getByTestId('wish');
    await expect(page.getByRole('heading', { name: 'A tan rain coat', level: 1 })).toBeVisible();
    await expect(wish).toBeVisible();

    // nothing watched yet: the most you'd pay is one small button, above looking for more
    const price = wish.getByTestId('wish-price');
    await expect(price).toHaveText("Set the most you'd pay");
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
    await expect(price).toHaveText("The most you'd pay is $200.00. Change");
    const saved = (await (await page.request.get(backend.url + '/api/wishlist')).json()).wishes
      .find((w: { name: string }) => w.name === 'A tan rain coat');
    expect([saved.price_min, saved.price_max, saved.price_currency]).toEqual([null, 200, 'USD']);

    await wish.getByTestId('find-some').click();
    await expect(wish.getByRole('status').filter({ hasText: 'Claude is searching shops' })).toBeVisible();
    const finds = wish.getByTestId('find');
    // the two finds kept are judged against the closet before they show, over a minute on a slow runner
    await expect(finds).toHaveCount(2, { timeout: 120_000 });   // the one without a web address is not kept
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

    // what is watched comes first, then when it was checked and the most you'd pay, then looking for more (Google
    // Shopping a button beside Find more), the note, and what to do with the wish. What is true every day (the daily
    // check, what a search sends) is behind one closed "How this works", not on the page (the owner, 26 November)
    await expect(wish.getByTestId('wish-price')).toHaveText("The most you'd pay is $200.00. Change");
    const text = await wish.innerText();
    const order = ['Tan gabardine rain coat', 'Last checked today', "The most you'd pay", 'Find more', 'Search Google Shopping',
      'How this works', 'Note', 'Check one I found', 'I bought it', 'Remove from the list'].map((words) => text.indexOf(words));
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(text).not.toContain('Nines checks the price once a day');
    expect(text).not.toContain('A search sends Claude');
    const how = wish.getByTestId('shop-how');
    await expect(how).not.toHaveAttribute('open');
    await expect(how).toContainText("Nines checks the price once a day while it's running and tells you when it goes down to $200.00 or less.");
    await expect(how.getByTestId('search-sends')).toHaveText(/^A search sends Claude the wish/);
    await expect(wish.getByTestId('google-shopping')).toHaveClass(/\bbtn\b/);
    await expect(wish).not.toContainText('Nothing is ever bought for you');
    // on a wish added by hand, the third button checks one you found in a shop
    await expect(wish.getByRole('button', { name: 'Would it go with my clothes?' })).toHaveCount(0);
    await expect(wish.getByRole('button', { name: 'Check one I found' })).toHaveAttribute('title', /photo or a description.*against your closet/);
    // a find's card: the answer and two buttons on it, everything else in one closed fold
    await expect(coat.getByRole('button', { name: 'See it with your clothes' })).toBeVisible();
    await expect(coat.getByRole('button', { name: 'Stop watching' })).toBeHidden();
    await expect(coat.getByRole('button', { name: 'Add a code' })).toBeHidden();
    await expect(coat).toContainText('Claude saw:');
    await expect(coat.getByText(/^Claude saw:/)).toBeHidden();

    // Check now sees every price lower: the drop is shown. While it checks, "Checking the price…" takes the place of
    // "Last checked …" and nothing under it moves (a line put in under it moved Find more 48px, and named Claude: the
    // review of 24 November, 40)
    const findMore = wish.getByTestId('find-some');
    const top = async () => findMore.evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
    const before = await top();
    await wish.getByRole('button', { name: 'Check now' }).click();
    await expect(wish.getByTestId('prices-checked')).toContainText('Checking the price…');
    expect(await top()).toBe(before);
    await expect(wish).not.toContainText('is checking the prices');
    await expect(coat.getByTestId('find-drop')).toHaveText('Was $180.00, now $144.00 (20% less)', { timeout: 30_000 });
    await expect(coat).toContainText('Example Shop · $144.00');
    await expect(wish.getByTestId('prices-checked')).toContainText('Last checked today at');

    // the price can be changed in the same sheet, and cleared
    await wish.getByTestId('wish-price').getByRole('button', { name: 'Change' }).click();
    await expect(sheet.getByLabel('Amount')).toHaveValue('200');
    await sheet.getByRole('button', { name: 'Clear' }).click();
    await expect(wish.getByTestId('wish-price')).toHaveText("Set the most you'd pay");
    await expect(how).toContainText('tells you when it goes down.');

    // watching a find can be stopped: it stays in its place, saying so with Undo, until you leave the page (A8: it
    // went at once), and then it is gone
    await polo.getByTestId('find-more').locator('summary').click();   // in its fold, with the rest of the small print
    await polo.getByRole('button', { name: 'Stop watching' }).click();
    await expect(polo.getByTestId('find-stopped')).toContainText('You stopped watching it');
    await expect(finds).toHaveCount(2);
    const wishPath = new URL(page.url()).pathname;
    await page.goto(backend.url + '/wardrobe');
    await page.goto(backend.url + wishPath);
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

    // Stop watching can be undone (the review of 23 November, A8): the find stays in its place saying so, Undo has the
    // focus, and Undo puts it back as it was, its price history and its drop with it
    await find.getByTestId('find-more').locator('summary').click();   // in its fold, with the rest of the small print
    const top = (await find.boundingBox())!.y;
    await find.getByRole('button', { name: 'Stop watching' }).click();
    await expect(find.getByTestId('find-stopped')).toContainText('You stopped watching it');
    await expect(find.getByRole('button', { name: 'Undo' })).toBeFocused();
    expect((await find.boundingBox())!.y).toBe(top);
    const wishId = page.url().split('/wardrobe/wish/')[1];
    await expect.poll(async () => (await (await page.request.get(`${backend.url}/api/wishlist/${wishId}/finds`)).json()).finds.length).toBe(0);
    // the wishlist read again while it is stopped (here by a note saved as its box is left; a price check ending or
    // coming back to the window does the same) moves nothing above it: the wish came from a link, and still says so
    const readAgain = page.waitForResponse((r) => r.request().method() === 'GET' && r.url().endsWith('/api/wishlist') && r.ok());
    await wish.getByLabel('Note').fill('Size M');
    await wish.getByLabel('Note').blur();
    await readAgain;
    await expect(wish.getByTestId('wish-note-status')).toHaveText('Saved');
    await expect(page.getByText('Added by hand')).toHaveCount(0);
    expect((await find.boundingBox())!.y).toBe(top);
    await find.getByRole('button', { name: 'Undo' }).click();
    await expect(find.getByTestId('find-stopped')).toHaveCount(0);
    await expect(find.getByRole('button', { name: 'Stop watching' })).toBeVisible();
    await expect(find.getByTestId('find-drop')).toHaveText('Was $68.00, now $54.40 (20% less)');
    // (the note goes again, so the wish's row shows the page it was sent as)
    const cleared = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().endsWith(`/api/wishlist/${wishId}`) && r.ok());
    await wish.getByLabel('Note').fill('');
    await wish.getByLabel('Note').blur();
    await cleared;

    // the card already says whether it goes with your clothes, so the wish made from it does not offer to check one
    // (the owner, 26 November); Would this work? opened for it still starts from the product's name on the page
    await expect(wish.getByRole('button', { name: 'Check one I found' })).toHaveCount(0);
    await expect(wish.getByRole('button', { name: 'Would it go with my clothes?' })).toHaveCount(0);
    await page.goto(`${backend.url}/wardrobe/check/wish/${wishId}`);
    // (the name is among the rest, in "More about it")
    await page.getByTestId('would-work').getByRole('button', { name: 'More about it' }).click();
    await expect(page.getByRole('dialog', { name: 'More about it' }).getByLabel('Name (optional)')).toHaveValue('Linen camp-collar shirt');
    await page.getByRole('dialog', { name: 'More about it' }).getByRole('button', { name: 'Done' }).click();
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

  // A link nobody could read (tests/e2e_backend.py: the shop turns Nines away and Claude cannot read the page either):
  // it asks for a name in the verdict's place, cannot be searched for until it has one, and once named is described and
  // judged as any link is. The page holds still throughout.
  test('a link nobody could read asks for a name, then is described and judged, and the page holds still', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    const made = await page.request.post(backend.url + '/api/wishlist/link', { data: { url: 'https://shop.example/turned-away' } });
    const { id } = await made.json();
    await expect.poll(async () => (await (await page.request.get(`${backend.url}/api/wishlist/${id}/finds`)).json()).run?.state,
      { timeout: 30_000 }).toBe('done');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    const wish = page.getByTestId('wish');
    const find = wish.getByTestId('find');
    const naming = find.getByTestId('find-naming');
    await expect(naming).toContainText("Nines and Claude couldn't read what this is from its page.", { timeout: 30_000 });
    // the address once, as its shop; no verdict, and no second sentence about the page
    await expect(find.getByText('shop.example', { exact: true })).toHaveCount(1);
    await expect(find.getByTestId('find-not-judged')).toHaveCount(0);
    await expect(find.getByTestId('find-unread')).toHaveCount(0);
    const field = naming.getByLabel('What it is called');
    await expect(field).toHaveAttribute('placeholder', /Grey wool chore coat/);
    // not searched for until it has a name: no Google Shopping, Find some off with the server's own reason
    const refused = await page.request.post(`${backend.url}/api/wishlist/${id}/find`);
    expect(refused.status()).toBe(409);
    const reason = (await refused.json()).detail as string;
    await expect(wish.getByTestId('google-shopping')).toHaveCount(0);
    await expect(wish.getByTestId('find-some')).toBeDisabled();
    await expect(wish.getByTestId('find-off')).toHaveText(reason);
    expect(await axeViolations(page)).toEqual([]);

    // named: the name comes at once, then the waiting sentence where the field was, then the verdict; the buttons under
    // the card do not move
    const at = async () => Promise.all([wish.getByTestId('check-prices'), wish.getByTestId('find-some')].map(
      (b) => b.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY))));
    const before = await at();
    await field.fill('Grey wool overshirt');
    await naming.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('heading', { name: 'Grey wool overshirt', level: 1 })).toBeVisible({ timeout: 10_000 });
    await expect(find.getByTestId('find-naming')).toHaveCount(0);
    await expect(find.getByTestId('find-not-judged')).toHaveText('Nines checks it against your closet once Claude can describe it.');
    expect(await at()).toEqual(before);
    await expect(find.getByTestId('find-verdict')).not.toBeEmpty({ timeout: 30_000 });
    expect(await at()).toEqual(before);
    await expect(find.getByRole('heading')).toHaveCount(0);   // its name is the page's heading, said once
    await expect(wish.getByTestId('find-off')).toHaveCount(0);
    await expect(wish.getByTestId('find-some')).toBeEnabled();
    await expect(wish.getByTestId('google-shopping')).toBeVisible();
  });

  test('a name that is refused is said under the field, and what was typed stays', async ({ page }) => {
    test.setTimeout(90_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    const made = await page.request.post(backend.url + '/api/wishlist/link', { data: { url: 'https://shop.example/turned-away?colour=grey' } });
    const { id } = await made.json();
    await expect.poll(async () => (await (await page.request.get(`${backend.url}/api/wishlist/${id}/finds`)).json()).run?.state,
      { timeout: 30_000 }).toBe('done');
    await page.setViewportSize({ width: 375, height: 760 });
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    const naming = page.getByTestId('wish').getByTestId('find-naming');
    const long = 'x'.repeat(201);
    await naming.getByLabel('What it is called').fill(long);
    await naming.getByRole('button', { name: 'Save' }).click();
    await expect(naming.getByRole('alert')).not.toBeEmpty();
    await expect(naming.getByLabel('What it is called')).toHaveValue(long);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });

  // A page that let Nines in once and then turned it away (and Claude cannot read it): it keeps its last price, says so
  // quietly under the price, and the check says it in its own line; nothing moves while it checks.
  test('a page that could not be read keeps its last price, saying so once on its card', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    const made = await page.request.post(backend.url + '/api/wishlist/link', { data: { url: 'https://shop.example/once-shirt' } });
    const { id } = await made.json();
    const state = async () => (await (await page.request.get(`${backend.url}/api/wishlist/${id}/finds`)).json()).run?.state;
    await expect.poll(state, { timeout: 30_000 }).toBe('done');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    const wish = page.getByTestId('wish');
    const find = wish.getByTestId('find');
    await expect(find).toContainText('Example Shop · $68.00', { timeout: 30_000 });
    await expect(find.getByTestId('find-unread')).toHaveCount(0);
    await wish.getByTestId('check-prices').click();
    await expect(wish.getByTestId('prices-checked')).toContainText('Last checked today at', { timeout: 30_000 });
    await expect(find.getByTestId('find-unread')).toHaveText("Nines couldn't read the page today. This is the last price it read.");
    await expect(find).toContainText('Example Shop · $68.00');
    await expect(find).not.toContainText('Sold out');
    // the check said so as it ended; the page says it once, on the card, not again under Check now
    await expect(page.getByText('Nines could not read 1 of the pages today. Its last price is shown.')).toBeVisible();   // the toast
    await expect(wish.getByText(/could not read/)).toHaveCount(0);
    // checked again, still turned away: nothing under the finger moves, while it checks or after
    const findMore = wish.getByTestId('find-some');
    const top = async () => Promise.all([wish.getByTestId('check-prices'), findMore].map(
      (b) => b.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY))));
    const before = await top();
    await wish.getByTestId('check-prices').click();
    await expect(wish.getByTestId('prices-checked')).toHaveText('Checking the price…');
    expect(await top()).toEqual(before);
    await expect(wish.getByTestId('prices-checked')).toContainText('Last checked today at', { timeout: 30_000 });
    await expect(find.getByTestId('find-unread')).toBeVisible();
    expect(await top()).toEqual(before);
    // the card says it plainly, not as a fault
    expect(await find.getByTestId('find-unread').evaluate((el) => el.closest('[role="alert"], .notice, .form-error'))).toBeNull();
    // read again after a reload: the card still says it
    await page.reload();
    await expect(find.getByTestId('find-unread')).toBeVisible({ timeout: 30_000 });
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

  // The review of 24 November on a wish, on a phone: its name said once and whole (38), everything on it 44px to tap
  // (46), and "Remove from the list" with Undo on the wishlist it goes back to, putting it back whole (5).
  test('on a phone, a wish names its find once, is 44px to tap, and Remove from the list offers Undo', async ({ page }) => {
    test.setTimeout(120_000);
    expect((await page.request.post(backend.url + '/api/profile', { data: { profile: 'main' } })).ok()).toBe(true);
    const made = await page.request.post(backend.url + '/api/wishlist/link', { data: { url: 'https://shop.example/long-name' } });
    expect(made.ok()).toBe(true);
    const { id } = await made.json();
    expect((await page.request.patch(`${backend.url}/api/wishlist/${id}`, { data: { note: 'Size 40', price_max: 300, price_currency: 'USD' } })).ok()).toBe(true);
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    const wish = page.getByTestId('wish');
    const find = wish.getByTestId('find');
    await expect(find.getByTestId('find-verdict')).not.toBeEmpty({ timeout: 60_000 });

    // its name once: the heading whole (the wish's own name is cut at 60 letters), the find by its shop and price
    const name = (await find.getAttribute('aria-label'))!;
    expect(name.length).toBeGreaterThan(60);
    const heading = page.getByRole('heading', { level: 1 });
    await expect(heading).toHaveText(name);
    // a whole name of over a hundred letters is set smaller than a page title (it took six lines of the largest type
    // at 375): at most four lines at 375; at 320 it takes no more height than that (CI's wider font needs a fifth line
    // of the body's size there); never wider than the screen
    let tallest = 0;
    for (const width of [375, 320]) {
      await page.setViewportSize({ width, height: 667 });
      await expect(page.locator('.page-header.title-longer')).toHaveCount(1);
      const shape = await heading.evaluate((el) => ({
        height: el.getBoundingClientRect().height,
        lines: Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)),
        right: el.getBoundingClientRect().right,
        wide: document.documentElement.scrollWidth,
      }));
      if (width === 375) {
        expect(shape.lines, 'lines at 375').toBeLessThanOrEqual(4);
        tallest = shape.height;
      } else {
        expect(shape.height, `the heading's height at ${width}`).toBeLessThanOrEqual(tallest);
      }
      expect(shape.right, `the heading's right edge at ${width}`).toBeLessThanOrEqual(width);
      expect(shape.wide, `the page's width at ${width}`).toBeLessThanOrEqual(width);
      await page.screenshot({ path: test.info().outputPath(`wish-long-title-${width}.png`) });
    }
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(find.getByRole('heading')).toHaveCount(0);
    await expect(find).toContainText(/^Example Shop · /);

    // a wish made from a link: its card answers whether it goes with your clothes, so no third button
    await expect(wish.getByRole('button', { name: 'Check one I found' })).toHaveCount(0);

    // 44px to tap: a find's buttons, its fold and what is in it, and the wish's buttons (they were 20 to 37px high)
    await find.getByTestId('find-more').locator('summary').click();
    for (const button of [find.getByRole('button', { name: 'See it with your clothes' }), find.getByRole('link', { name: 'Open in shop' }),
      find.getByTestId('find-more').locator('summary'), find.getByRole('button', { name: /^(Add a code|Change the code)$/ }),
      find.getByRole('button', { name: 'Stop watching' }), wish.getByTestId('check-prices'), wish.getByTestId('wish-price').getByRole('button'),
      wish.getByTestId('find-some'), wish.getByTestId('add-link'), wish.getByTestId('google-shopping'), wish.getByTestId('shop-how').locator('summary'),
      wish.getByRole('button', { name: 'I bought it' }), wish.getByRole('button', { name: 'Remove from the list' })]) {
      const box = await button.evaluate((el) => el.getBoundingClientRect().toJSON() as DOMRect);
      expect(box.height, await button.innerText()).toBeGreaterThanOrEqual(44);
    }

    // Remove from the list: the wishlist, with the wish's place saying so and offering Undo (no question, no loss)
    const rows = page.getByTestId('wishlist').getByTestId('wish-row');
    const order = async () => (await page.request.get(backend.url + '/api/wishlist')).json().then((r) => r.wishes.map((w: { id: string }) => w.id));
    const before: string[] = await order();
    await wish.getByRole('button', { name: 'Remove from the list' }).click();
    await expect(page).toHaveURL(/\/wardrobe\/wishlist$/);
    const gone = page.getByTestId('wish-removed');
    await expect(gone).toContainText('You removed “');
    await expect(rows).toHaveCount(before.length - 1);
    // in the place it had
    const items = page.getByTestId('wishlist').locator('.wish-list > li');
    expect(await items.nth(before.indexOf(id)).getByTestId('wish-removed').count()).toBe(1);
    await gone.getByRole('button', { name: /^Undo/ }).click();
    await expect(gone).toHaveCount(0);
    await expect(rows).toHaveCount(before.length);
    expect(await order()).toEqual(before);
    // back whole: its find, its note and the most you'd pay
    await page.goto(backend.url + `/wardrobe/wish/${encodeURIComponent(id)}`);
    await expect(find).toHaveCount(1, { timeout: 30_000 });
    await expect(wish.getByLabel('Note')).toHaveValue('Size 40');
    await expect(wish.getByTestId('wish-price')).toContainText('$300.00');
  });
});
