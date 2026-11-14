import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('open the demo closet: 30 items, ribbon, filter by category', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await page.getByText('Show the demo closet').click();

  await expect(page.getByText('Demo closet', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Back to my closet' })).toBeVisible();
  await page.getByRole('link', { name: 'Closet', exact: true }).click();
  await expect(page.getByTestId('tile')).toHaveCount(30);
  await expect(page.getByTestId('item-count')).toHaveText('30 items');

  await page.getByRole('group', { name: 'Filter by category' }).getByRole('button', { name: 'Sweaters' }).click();
  await expect(page.getByTestId('tile')).toHaveCount(4);
  await expect(page.getByTestId('item-count')).toHaveText('4 of 30');
  for (const caption of await page.locator('.tile-caption').allTextContents()) expect(caption).toMatch(/^Sweater/);

  await page.getByRole('button', { name: 'All', exact: true }).click();
  await page.getByRole('searchbox').fill('jeans');
  await expect(page.getByTestId('tile')).toHaveCount(3);

  await page.getByRole('button', { name: 'Back to my closet' }).click();
  await expect(page.getByRole('button', { name: 'Back to my closet' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Your closet' })).toBeVisible();
});

test('item detail: switch pictures, change a chip, it persists', async ({ page }) => {
  await login(page);
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

  // tops show sleeve and neck questions, not leg or shoe height
  await expect(panel.getByRole('group', { name: 'Sleeves' })).toBeVisible();
  await expect(panel.getByRole('group', { name: 'Leg' })).toHaveCount(0);

  // Each change is its own save. Wait for the server's answer to each one: the "Saved" message
  // from an earlier change stays on screen for a while, so seeing it does not mean the latest
  // change has been stored, and reloading too soon would cancel a save still on its way.
  const stored = () => page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/items/') && r.ok());

  const formality = panel.getByRole('group', { name: 'Formality' });
  const target = (await formality.getByRole('button', { name: 'Smart casual' }).getAttribute('aria-pressed')) === 'true' ? 'Business' : 'Smart casual';
  let answer = stored();
  await formality.getByRole('button', { name: target }).click();
  await answer;
  await expect(formality.getByRole('button', { name: target })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();

  answer = stored();
  await page.getByRole('group', { name: 'How you feel about it' }).getByRole('button', { name: 'Love' }).click();
  await answer;
  answer = stored();
  await page.getByLabel('Why? (optional)').fill('Warmest shirt I own');
  await page.getByLabel('Why? (optional)').press('Enter');
  await answer;
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();

  // shown as words, never raw values
  await expect(panel.getByText('smart_casual')).toHaveCount(0);

  await page.reload();
  const again = page.locator('.detail-panel').getByRole('group', { name: 'Formality' });
  await expect(again.getByRole('button', { name: target })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.detail-panel').getByRole('group', { name: 'How you feel about it' }).getByRole('button', { name: 'Love' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Why? (optional)')).toHaveValue('Warmest shirt I own');
});

test('a rejected change is undone and the server message shown', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
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
  await login(page);
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
  const pattern = page.locator('.detail-panel').getByRole('group', { name: 'Pattern' });
  await expect(pattern.getByRole('button', { name: 'Stripe' })).toHaveAttribute('aria-pressed', 'true');
  const colours = pattern.getByTestId('pattern-colours');
  await expect(colours).toHaveAttribute('aria-label', 'Colours measured from the photo: Navy 60%, white 40%');
  await expect(colours.locator('.swatch')).toHaveCount(2);
  await page.context().unrouteAll({ behavior: 'ignoreErrors' });
});

test('archive and unarchive, delete with confirmation', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Olive shorts' }).click();
  const panel = page.locator('.detail-panel');
  await panel.getByRole('button', { name: 'Archive' }).click();
  await expect(panel.getByRole('button', { name: 'Unarchive' })).toBeVisible();
  await expect(page.getByTestId('tile').filter({ hasText: 'Olive shorts' })).toHaveCount(0);

  await page.getByRole('link', { name: 'Archived' }).first().click();
  await page.getByTestId('tile').filter({ hasText: 'Olive shorts' }).click();
  await page.locator('.detail-panel').getByRole('button', { name: 'Unarchive' }).click();
  await expect(page.locator('.detail-panel').getByRole('button', { name: 'Archive', exact: true })).toBeVisible();

  await page.goto('/');
  await page.getByTestId('tile').filter({ hasText: 'White tee' }).click();
  await page.locator('.detail-panel').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Delete this item for good?')).toBeVisible();
  await page.getByRole('button', { name: 'Keep it' }).click();
  await expect(page.getByTestId('tile').filter({ hasText: 'White tee' })).toHaveCount(1);
});
