import type { Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, serviceWorkerInCharge, test, useProfile } from './fixtures';

/** Takes every wish off the demo closet's list, its own two examples too, so each test starts from an empty list. */
async function undoWishes(page: Page) {
  const r = await page.request.post('/api/profile', { data: { profile: 'demo' } });
  if (!r.ok()) return;
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  for (const w of wishes) await page.request.delete(`/api/wishlist/${w.id}`);
}

test.beforeEach(async ({ page }) => {
  await undoWishes(page);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await undoWishes(page);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

async function openMissing(page: Page) {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/wardrobe');
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
}

/** Describes a tan rain-proof coat by hand and waits for the answer. Heavy: the demo's check is weighed by its example
 * answers, whose rainy days are mostly work and everyday ones, cold days among them, which a medium coat is not warm
 * enough for. */
async function checkCoat(page: Page) {
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  // the kind and the colour first: the answer comes as soon as both are chosen, with no button to press
  const coat = form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true });
  if ((await coat.getAttribute('aria-pressed')) !== 'true') await coat.click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  const answer = panel.getByTestId('would-work-answer');
  await expect(answer).toBeVisible({ timeout: 30_000 });
  // the rest is in "More about it", and the answer is worked out again once it is closed
  await panel.getByRole('button', { name: 'More about it' }).click();
  const more = page.getByRole('dialog', { name: 'More about it' });
  await more.getByRole('group', { name: 'Formality' }).getByRole('button', { name: 'Smart casual', exact: true }).click();
  await more.getByRole('group', { name: 'How heavy the cloth is' }).getByRole('button', { name: 'Heavy', exact: true }).click();
  await more.getByRole('switch', { name: /keeps the rain off/ }).check({ force: true });
  await more.getByRole('button', { name: 'Done' }).click();
  await expect(more).toHaveCount(0);
  await expect(answer).toHaveAttribute('data-piece', /keeps the rain off/, { timeout: 30_000 });
  await expect(panel.locator('.wouldwork-shown.is-stale')).toHaveCount(0, { timeout: 30_000 });
  return answer;
}

test('would this work?, described by hand in the demo closet on a computer, on a page of its own, and put on the wishlist', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openMissing(page);
  await page.getByRole('link', { name: 'Would this work?' }).click();
  await expect(page).toHaveURL(/\/wardrobe\/check$/);
  const panel = page.getByTestId('would-work');
  // a full-width page of its own: what it is on the left, the answer on the right; no suggestions, no side panel
  await expect(page.getByRole('heading', { level: 1, name: 'Would this work?' })).toBeVisible();
  await expect(page.getByTestId('gap')).toHaveCount(0);
  await expect(page.getByRole('complementary')).toHaveCount(0);
  const left = await panel.getByRole('region', { name: 'The piece' }).boundingBox();
  const right = await panel.getByRole('region', { name: 'The answer' }).boundingBox();
  expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
  expect(left!.width + right!.width).toBeGreaterThan(800);
  await expect(panel.getByRole('region', { name: 'The answer' })).toContainText('The answer shows here');
  // the demo closet sends nothing to Claude: the photo way is off, and says why
  await expect(panel.getByRole('button', { name: 'Take a photo' })).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Choose a photo' })).toBeDisabled();
  await expect(panel).toContainText('The demo closet never sends anything to Claude');
  // nothing to check until the kind and the colour are chosen, and no long form before the answer: the rest waits
  // behind "More about it"
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await expect(form.getByRole('group', { name: 'Formality' })).toHaveCount(0);
  await expect(form.getByRole('button', { name: 'Would it work?' })).toHaveCount(0);
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true }).click();
  await expect(form).toContainText('Choose its main colour.');
  await expect(panel.getByRole('region', { name: 'The answer' })).toContainText('The answer shows here');

  const answer = await checkCoat(page);
  // the piece is one line, saying what it is; what it was not told is no longer said as taken for granted
  await expect(panel.getByTestId('would-work-piece')).toContainText('Tan coat');
  await expect(panel.getByTestId('would-work-untold')).toHaveText('Until you say more, it is checked as a plain piece for any time of year.');
  // the piece is said once: its line names it, and the verdict does not repeat it
  await expect(answer.locator('.wouldwork-piece')).toHaveCount(0);
  // the description stays on the left beside the answer
  await expect(panel.getByRole('form', { name: 'Describe it by hand' })).toBeVisible();
  await expect(panel.getByRole('region', { name: 'The answer' }).getByTestId('would-work-answer')).toBeVisible();
  await expect(answer).toHaveAttribute('data-verdict', 'fills_gap');
  await expect(answer.getByTestId('verdict')).toHaveText('Fills a gap');
  await expect(answer).toContainText('A rain-proof outer layer');
  // the demo's list is weighed by its example answers, and so is the check: it says when the coat would be worn
  await expect(answer.getByTestId('would-work-situations')).toContainText('It suits work');
  await expect(answer.getByRole('list', { name: 'Your pieces it pairs with best' }).getByRole('link').first()).toBeVisible();
  await expect(answer.getByTestId('would-work-outfit').first()).toContainText('This piece');
  await expect(answer).not.toContainText(/smart_casual|fills_gap|~candidate/);

  await panel.getByRole('button', { name: 'Put it on my wishlist' }).click();
  await expect(panel.getByRole('button', { name: 'On your wishlist' })).toBeDisabled();
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  expect(wishes).toHaveLength(1);
  expect(wishes[0].name).toBe('Tan coat');
  expect(wishes[0].note).toContain('keeps the rain off');
  expect(wishes[0].note).toContain('fills a gap');

  // a piece of the closet opens from the answer; coming back shows the answer again
  await answer.getByRole('list', { name: 'Your pieces it pairs with best' }).getByRole('link').first().click();
  await expect(page).toHaveURL(/\/wardrobe\/item\//);
  await page.goBack();
  await expect(page.getByTestId('would-work-answer')).toBeVisible();
  // ...and it is still on the wishlist once: the button does not add it again
  await expect(panel.getByRole('button', { name: 'On your wishlist' })).toBeDisabled();
  expect((await (await page.request.get('/api/wishlist')).json()).wishes).toHaveLength(1);
  // back to the Wardrobe: the row to the wishlist is in the side panel, counting the new wish, and opens the list
  await panel.locator('.wouldwork-back').click();
  await expect(page).toHaveURL(/\/wardrobe$/);
  const row = page.getByRole('complementary', { name: 'Thinking of buying something?' }).getByTestId('wishlist-open');
  await expect(row).toContainText('1 thing');
  await row.click();
  await expect(page.getByTestId('wishlist').getByTestId('wish-row')).toHaveCount(1);
});

test('would this work?: leaving while the check is being sent and coming back picks it up', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openMissing(page);
  let held: import('@playwright/test').Route | null = null;
  await page.route('**/api/would-this-work', (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    held = route;   // not answered until the test lets it go
  });
  await page.getByRole('link', { name: 'Would this work?' }).click();
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  await expect(panel.getByTestId('would-work-waiting')).toContainText('Sending');
  await expect.poll(() => held !== null).toBe(true);
  // away to the closet, then back while the request is still on its way
  await page.getByRole('link', { name: /^Closet/ }).first().click();
  await expect(page).not.toHaveURL(/\/wardrobe/);
  await page.goBack();
  await expect(page).toHaveURL(/\/wardrobe\/check$/);
  await expect(page.getByTestId('would-work-waiting')).toContainText('Sending');
  await held!.continue();
  await expect(page.getByTestId('would-work-answer')).toBeVisible({ timeout: 30_000 });
  await page.unroute('**/api/would-this-work');
});

test('would this work? on a phone: a full page, a fourth pair of jeans you have already, and checking a find from a wish', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openMissing(page);
  await page.getByRole('link', { name: 'Would this work?' }).click();
  const panel = page.getByTestId('would-work');
  await expect(panel).toBeVisible();
  await expect(page.getByTestId('gap')).toHaveCount(0);   // a page of its own
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Jeans', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Navy', exact: true }).click();
  const answer = panel.getByTestId('would-work-answer');
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).toHaveAttribute('data-verdict', 'have_it');
  await expect(answer).toContainText('You have three like it');
  await expect(answer.getByRole('list', { name: 'Pieces you have like it' }).getByRole('link')).toHaveCount(3);
  // every piece in the answer is a small picture, never one stretched to the width of the page
  const thumbs = await answer.locator('.gap-thumb').evaluateAll((els) => els.map((el) => el.getBoundingClientRect()));
  expect(thumbs.length).toBeGreaterThan(3);
  for (const box of thumbs) {
    expect(box.width).toBeLessThanOrEqual(64);
    expect(box.height).toBeLessThanOrEqual(72);
  }
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);

  // from a wish: the form starts with what the wish asks for
  const gaps = await (await page.request.get('/api/gaps')).json();
  const rain = gaps.gaps.find((g: { id: string }) => g.id === 'outer-rain');
  await page.request.post('/api/wishlist', { data: { gap_id: rain.id } });
  // back from the check, the lists are asked for again: the wish shows without reloading the page
  await page.locator('.wouldwork-back').click();
  await page.getByTestId('wishlist-open').click();
  await page.getByTestId('wish-row').first().click();
  await page.getByTestId('wish').getByRole('button', { name: 'Would it go with my clothes?' }).click();
  await expect(page).toHaveURL(/\/wardrobe\/check\/wish\//);
  const fromWish = page.getByTestId('would-work');
  await expect(fromWish).toContainText(`Checking a find for ${rain.name}`);
  const kind = fromWish.getByRole('form', { name: 'Describe it by hand' });
  if (await kind.getByRole('group', { name: 'Main colour' }).count()) {   // the wish names no one colour: choose it
    await expect(kind.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await kind.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  }
  await expect(fromWish.getByTestId('would-work-answer')).toBeVisible({ timeout: 30_000 });
  await expect(fromWish.getByTestId('would-work-piece')).toContainText('coat');
  await fromWish.getByRole('button', { name: 'More about it' }).click();
  await expect(page.getByRole('dialog', { name: 'More about it' }).getByRole('switch', { name: /keeps the rain off/ })).toBeChecked();
  await page.getByRole('dialog', { name: 'More about it' }).getByRole('button', { name: 'Done' }).click();

  // the answer goes into that wish's note, not into a second wish
  await fromWish.getByRole('button', { name: "Add it to the wish's note" }).click();
  await expect(fromWish.getByRole('button', { name: "In the wish's note" })).toBeDisabled();
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  expect(wishes).toHaveLength(1);
  expect(wishes[0].note).toContain('keeps the rain off');
  // back goes to the wish it was opened from, not to the Wardrobe (BACKLOG, "The wishlist's own page"), where the
  // note shows what was added
  const back = page.locator('.wouldwork-back');
  await expect(back).toHaveText(/Wish$/);
  await back.click();
  await expect(page).toHaveURL(new RegExp(`/wardrobe/wish/${encodeURIComponent(wishes[0].id)}$`));
  await expect(page.getByTestId('wish').getByRole('textbox', { name: 'Note' })).toHaveValue(/keeps the rain off/);
});

test('would this work? by hand on a small phone: the answer as soon as the kind and colour are chosen, in view, the rest in a sheet', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/wardrobe/check');
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Shirt', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Light blue', exact: true }).click();
  // no button to press: the verdict comes, and it is on the screen without scrolling to it
  const verdict = panel.getByTestId('verdict');
  await expect(verdict).toBeVisible({ timeout: 30_000 });
  await expect(verdict).toBeInViewport();
  await expect(panel.getByTestId('would-work-piece')).toBeInViewport();
  // led by the answer: the piece's name, then the verdict, then what was assumed and the two buttons, and the first
  // reason still on the first screen (23 November)
  const top = async (l: import('@playwright/test').Locator) => (await l.boundingBox())!.y;
  const untold = panel.getByTestId('would-work-untold');
  const firstReason = panel.getByRole('list', { name: 'Why' }).getByRole('listitem').first();
  expect(await top(panel.getByTestId('would-work-piece'))).toBeLessThan(await top(verdict));
  expect(await top(verdict)).toBeLessThan(await top(untold));
  expect(await top(untold)).toBeLessThan(await top(panel.getByRole('button', { name: 'More about it' })));
  await expect(firstReason).toBeInViewport();
  await expect(panel.getByTestId('would-work-answer').locator('.wouldwork-piece')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('by-hand-answer.png') });
  // "More about it" opens over the page; the answer stays where it was
  const before = (await verdict.boundingBox())!.y;
  await panel.getByRole('button', { name: 'More about it' }).click();
  const more = page.getByRole('dialog', { name: 'More about it' });
  await more.getByRole('group', { name: 'Pattern' }).getByRole('button', { name: 'Stripe', exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath('by-hand-more.png') });
  await more.getByRole('button', { name: 'Done' }).click();
  await expect(panel.getByTestId('would-work-answer')).toHaveAttribute('data-piece', /stripe/, { timeout: 30_000 });
  await expect(panel.locator('.wouldwork-shown.is-stale')).toHaveCount(0, { timeout: 30_000 });
  expect(Math.abs((await verdict.boundingBox())!.y - before)).toBeLessThan(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  expect(await axeViolations(page)).toEqual([]);
});

test('would this work?: a reload keeps what was typed and the answer; checking another piece forgets them', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/wardrobe/check');
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Jeans', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Navy', exact: true }).click();
  await expect(panel.getByTestId('would-work-answer')).toBeVisible({ timeout: 30_000 });
  await panel.getByRole('button', { name: 'More about it' }).click();
  await page.getByRole('dialog', { name: 'More about it' }).getByLabel('Name (optional)').fill('Made-up selvedge jeans');
  await page.getByRole('dialog', { name: 'More about it' }).getByRole('button', { name: 'Done' }).click();
  await expect(panel.getByTestId('would-work-answer')).toHaveAttribute('data-piece', /Made-up selvedge jeans/, { timeout: 30_000 });
  await expect(panel.locator('.wouldwork-shown.is-stale')).toHaveCount(0, { timeout: 30_000 });
  const verdict = await panel.getByTestId('verdict').textContent();

  // a reload (or iOS closing the app) used to forget all of it (the review of 23 November, P12)
  let asked = 0;
  page.on('request', (r) => { if (r.method() === 'POST' && r.url().endsWith('/api/would-this-work')) asked++; });
  await page.reload();
  await expect(panel.getByTestId('would-work-piece')).toContainText('Made-up selvedge jeans, navy jeans');
  await expect(panel.getByTestId('verdict')).toHaveText(verdict!);
  expect(asked).toBe(0);   // shown as it was, not worked out again

  // a new one starts empty, and stays empty after a reload
  await panel.getByRole('button', { name: 'Check another piece' }).click();
  await expect(form.getByRole('group', { name: 'Main colour' }).getByRole('button', { pressed: true })).toHaveCount(0);
  await page.reload();
  await expect(form.getByRole('group', { name: 'What kind of piece' })).toBeVisible();
  await expect(form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { pressed: true })).toHaveCount(0);
  await expect(panel.getByTestId('would-work-answer')).toHaveCount(0);
});

test('would this work? is off while offline, with the same words as the other buttons', async ({ page, context }) => {
  await openMissing(page);
  await serviceWorkerInCharge(page);
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  const off = page.locator('.thinking-check').getByText('Would this work?');
  await expect(off).toHaveAttribute('aria-disabled', 'true');
  await expect(off).toHaveAttribute('title', /needs Nines on your computer/i);
});

for (const [label, viewport] of [['computer', { width: 1280, height: 800 }], ['phone', { width: 390, height: 844 }]] as const) {
  test(`screenshot of an answer to would this work? on a ${label} (${viewport.width}×${viewport.height})`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await goToCloset(page);
    await useProfile(page, 'demo');
    await page.goto('/wardrobe/check');
    await checkCoat(page);
    await expect.poll(() => page.locator('main img').evaluateAll((imgs) => imgs.every((i) => (i as HTMLImageElement).complete))).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    const answer = page.getByTestId('would-work-answer');
    expect(await answer.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    const path = testInfo.outputPath(`would-this-work-${label}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`Would this work? on a ${label}`, { path, contentType: 'image/png' });
  });
}
