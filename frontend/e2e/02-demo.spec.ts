import { expect, goToCloset, openFold, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('open the demo closet: 49 items, the demo strip, filter by category', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'main');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await page.getByRole('link', { name: 'Advanced settings' }).click();
  await page.getByText('Show the demo closet').click();

  await expect(page.getByText('Demo closet', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Leave the demo closet' })).toBeVisible();
  await page.getByRole('link', { name: /^Closet/ }).click();
  await expect(page.getByTestId('tile')).toHaveCount(49);
  await expect(page.getByTestId('item-count')).toHaveText('49 items');

  // what a piece is: a group, then what is in it (the sweaters of Knitwear, not its hoodies)
  const sweaters = ((await (await page.request.get('/api/items')).json()).items as { category: string; group: string }[])
    .filter((i) => i.category === 'sweater' && i.group === 'knitwear').length;
  expect(sweaters).toBeGreaterThan(1);
  await page.getByRole('button', { name: 'Filter' }).click();
  await page.getByRole('group', { name: 'What it is' }).getByRole('button', { name: 'Knitwear & mid layers' }).click();
  await page.getByRole('group', { name: 'Which Knitwear & mid layers' }).getByRole('button', { name: 'Sweaters' }).click();
  await expect(page.getByTestId('tile')).toHaveCount(sweaters);
  await expect(page.getByTestId('item-count')).toHaveText(`${sweaters} of 49`);
  for (const caption of await page.locator('.tile-caption').allTextContents()) expect(caption).toMatch(/^Sweater/);

  await page.getByRole('group', { name: 'What it is' }).getByRole('button', { name: 'All', exact: true }).click();
  await expect(page.getByTestId('tile')).toHaveCount(49);
  await page.getByRole('searchbox').fill('jeans');
  await expect(page.getByTestId('tile')).toHaveCount(3);

  await page.getByRole('button', { name: 'Leave the demo closet' }).click();
  await expect(page.getByRole('button', { name: 'Leave the demo closet' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Your closet' })).toBeVisible();
});

test('item detail: switch pictures, change a chip, it persists', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Plaid flannel shirt' }).click();

  const panel = page.locator('.detail-panel');
  const picture = panel.getByRole('group', { name: 'Picture' });
  // cutout is the default when there is one
  await expect(picture.getByRole('button', { name: 'Cutout' })).toHaveAttribute('aria-pressed', 'true');
  await expect(panel.getByRole('img', { name: /background removed/ })).toBeVisible();
  await picture.getByRole('button', { name: 'Drawing' }).click();
  await expect(panel.getByRole('img', { name: /drawing/ })).toBeVisible();
  await picture.getByRole('button', { name: 'Photo' }).click();
  await expect(panel.getByRole('img', { name: /original photo/ })).toBeVisible();

  // one line under the name says what it is and how it sits, read from the description the drawing was made from;
  // the shape is not asked again among the details
  await expect(panel.getByTestId('look-line')).toHaveText(/ · .*sleeves/i);
  await openFold(panel, 'Details');
  await expect(panel.getByRole('button', { name: /^Sleeves:/ })).toHaveCount(0);
  await expect(panel.getByRole('button', { name: /^Leg:/ })).toHaveCount(0);

  // Each change is its own save. Wait for the server's answer to each one: the "Saved" message
  // from an earlier change stays on screen for a while, so seeing it does not mean the latest
  // change has been stored, and reloading too soon would cancel a save still on its way.
  const stored = () => page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/items/') && r.ok());

  // each detail is a row in the Details fold; it opens its choices in place
  await panel.getByRole('button', { name: /^Formality:/ }).click();
  const formality = panel.getByRole('group', { name: 'Formality' });
  const target = (await formality.getByRole('button', { name: 'Smart casual' }).getAttribute('aria-pressed')) === 'true' ? 'Business' : 'Smart casual';
  let answer = stored();
  await formality.getByRole('button', { name: target }).click();
  await answer;
  await expect(formality.getByRole('button', { name: target })).toHaveAttribute('aria-pressed', 'true');
  // said beside the row that changed, not in a toast (23 November)
  await expect(panel.getByTestId('kept-formality')).toHaveText('Saved');

  // About it: how you feel about it, and one box for your notes
  answer = stored();
  await panel.getByRole('group', { name: 'How you feel about it' }).getByRole('button', { name: 'Love' }).click();
  await answer;
  answer = stored();
  const notes = panel.getByRole('textbox', { name: 'Notes for you and Claude' });
  await notes.fill('Warmest shirt I own');
  await notes.blur();
  await answer;
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();

  // shown as words, never raw values
  await expect(panel.getByText('smart_casual')).toHaveCount(0);

  await page.reload();
  await openFold(page.locator('.detail-panel'), 'Details');
  await expect(page.locator('.detail-panel').getByRole('button', { name: `Formality: ${target}` })).toBeVisible();
  await page.locator('.detail-panel').getByRole('button', { name: /^Formality:/ }).click();
  const again = page.locator('.detail-panel').getByRole('group', { name: 'Formality' });
  await expect(again.getByRole('button', { name: target })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.detail-panel').getByRole('group', { name: 'How you feel about it' }).getByRole('button', { name: 'Love' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.detail-panel').getByRole('textbox', { name: 'Notes for you and Claude' })).toHaveValue('Warmest shirt I own');
});

test('formality: a piece can be either of two levels next to each other', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Burgundy penny loafers' }).click();
  const panel = page.locator('.detail-panel');
  await openFold(panel, 'Details');
  const stored = () => page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/items/') && r.ok());

  // smart casual, and business too: the row says both, the lower first
  await panel.getByRole('button', { name: 'Formality: Smart casual' }).click();
  const also = panel.getByRole('group', { name: 'It can also be' });
  await expect(also.getByRole('button')).toHaveText(['Casual', 'Business']);
  let answer = stored();
  await also.getByRole('button', { name: 'Business' }).click();
  await answer;
  await expect(panel.getByRole('button', { name: 'Formality: Smart casual to business' })).toBeVisible();

  await page.reload();
  const again = page.locator('.detail-panel');
  await openFold(again, 'Details');
  await again.getByRole('button', { name: 'Formality: Smart casual to business' }).click();
  await expect(again.getByRole('group', { name: 'It can also be' }).getByRole('button', { name: 'Business' }))
    .toHaveAttribute('aria-pressed', 'true');

  // on a phone the two choices open in a sheet over the page; choosing a level makes it one level again
  const items = (await (await page.request.get('/api/items?q=penny')).json()).items as { id: string }[];
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/item/${items[0].id}`);
  await openFold(page, 'Details');
  const row = page.getByRole('button', { name: 'Formality: Smart casual to business' });
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: test.info().outputPath('formality-row-phone.png') });
  await row.click();
  const sheet = page.getByRole('dialog', { name: 'Formality' });
  await expect(sheet.getByRole('group', { name: 'It can also be' }).getByRole('button', { name: 'Business' }))
    .toHaveAttribute('aria-pressed', 'true');
  await sheet.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)));
  await page.screenshot({ path: test.info().outputPath('formality-phone.png') });
  answer = stored();
  await sheet.getByRole('group', { name: 'Formality' }).getByRole('button', { name: 'Business', exact: true }).click();
  await answer;
  await expect(page.getByRole('button', { name: 'Formality: Business' })).toBeVisible();
});

test('trousers: the drawing comes with a small one from the back', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Black jeans' }).click();
  const panel = page.locator('.detail-panel');
  await expect(panel.getByRole('img', { name: 'Black jeans, drawing', exact: true })).toBeVisible();   // no photo: the drawing
  const back = panel.getByRole('img', { name: 'Black jeans, drawing from the back' });
  await expect(back).toBeVisible();
  await expect(panel.getByText('From the back')).toBeVisible();
  const svg = await page.request.get((await back.getAttribute('src'))!);
  expect(svg.ok() && (await svg.text()).startsWith('<svg')).toBe(true);

  // a top has none
  await page.getByTestId('tile').filter({ hasText: 'Plaid flannel shirt' }).click();
  await panel.getByRole('group', { name: 'Picture' }).getByRole('button', { name: 'Drawing' }).click();
  await expect(panel.getByRole('img', { name: 'Plaid flannel shirt, drawing', exact: true })).toBeVisible();
  await expect(panel.getByText('From the back')).toHaveCount(0);
});

test('a rejected change is undone and the server message shown', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
  await openFold(panel, 'Details');
  await panel.getByRole('button', { name: /^Pattern:/ }).click();
  await expect(panel.getByRole('group', { name: 'Pattern' })).toBeVisible();
  await page.route('**/api/items/*', async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: "'zigzag' is not a known pattern." }) });
    } else await route.fallback();
  });
  const stripe = panel.getByRole('group', { name: 'Pattern' }).getByRole('button', { name: 'Stripe' });
  await stripe.click();
  await expect(page.getByText("'zigzag' is not a known pattern.")).toBeVisible();
  await expect(stripe).toHaveAttribute('aria-pressed', 'false');
});

test('the colours measured from a pattern show as swatches beside the pattern word', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  // the demo closet is never measured: the item page is given the colours a measured navy and white stripe has
  // (on the context, so the answer is changed whether the page or its service worker asks)
  await page.context().route('**/api/items/*', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const res = await route.fetch();
    const item = await res.json();
    item.pattern = 'stripe';
    item.pattern_colors = [{ color: 'navy', hex: '#1b2a49', share: 0.6 }, { color: 'white', hex: '#f4f1ea', share: 0.4 }];
    await route.fulfill({ response: res, json: item });
  });
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
  await openFold(panel, 'Details');
  // read first: the Details row shows the swatches beside the pattern word, and says them
  const row = panel.getByRole('button', { name: 'Pattern: Stripe. Colours measured from the photo: Navy 60%, white 40%' });
  await expect(row.getByTestId('pattern-colours').locator('.swatch')).toHaveCount(2);
  await row.click();
  const pattern = panel.getByRole('group', { name: 'Pattern' });
  await expect(pattern.getByRole('button', { name: 'Stripe' })).toHaveAttribute('aria-pressed', 'true');
  const colours = pattern.getByTestId('pattern-colours');
  await expect(colours).toHaveAttribute('aria-label', 'Colours measured from the photo: Navy 60%, white 40%');
  await expect(colours.locator('.swatch')).toHaveCount(2);
  await page.context().unrouteAll({ behavior: 'ignoreErrors' });
});

test('archive and unarchive, delete with confirmation', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Olive shorts' }).click();
  const panel = page.locator('.detail-panel');
  await openFold(panel, 'Archive or delete');
  await panel.getByRole('button', { name: 'Archive' }).click();
  await expect(panel.getByRole('button', { name: 'Unarchive' })).toBeVisible();
  await expect(page.getByTestId('tile').filter({ hasText: 'Olive shorts' })).toHaveCount(0);

  // Archived is reached from the closet's In use / Archived switch only, which is under Filter
  await expect(page.locator('nav.sidebar').getByRole('link', { name: 'Archived' })).toHaveCount(0);
  await page.getByRole('button', { name: /^Filter/ }).click();
  await page.getByRole('dialog', { name: 'Filter' }).getByRole('group', { name: 'Which clothes' }).getByRole('link', { name: 'Archived' }).click();
  await page.getByTestId('tile').filter({ hasText: 'Olive shorts' }).click();
  await openFold(page.locator('.detail-panel'), 'Put it back or delete it');
  await page.locator('.detail-panel').getByRole('button', { name: 'Unarchive' }).click();
  await expect(page.locator('.detail-panel').getByRole('button', { name: 'Archive', exact: true })).toBeVisible();

  await page.goto('/');
  await page.getByTestId('tile').filter({ hasText: 'White tee' }).click();
  await openFold(page.locator('.detail-panel'), 'Archive or delete');
  await page.locator('.detail-panel').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Delete this item for good?')).toBeVisible();
  await page.getByRole('button', { name: 'Keep it' }).click();
  await expect(page.getByTestId('tile').filter({ hasText: 'White tee' })).toHaveCount(1);
});

test('in the demo closet, Add names the strip\'s own button, and Leave is 44px to tap (the review of 24 November, 10 and 56)', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await useProfile(page, 'demo');
  await page.goto('/add');
  // it said 'Use "Back to my closet" above', a button that is not there: the strip says Leave
  await expect(page.getByText("You're in the demo closet, so new photos are added to the demo. Use Leave, above, to add to your own.")).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Back to my closet');
  const leave = page.locator('.ribbon').getByRole('button', { name: 'Leave the demo closet' });
  await expect(leave).toHaveText('Leave');
  // the button was 32px high against the screen's top edge, so its hit area could not reach 44px there
  const box = await leave.evaluate((el) => el.getBoundingClientRect().toJSON() as DOMRect);
  expect(box.top).toBeGreaterThanOrEqual(0);
  expect(box.height).toBeGreaterThanOrEqual(44);
  expect(box.width).toBeGreaterThanOrEqual(44);
});
