import type { Page } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

/** Takes the wishes a test added off the list again, so the demo closet starts the same in every test. */
async function undoWishes(page: Page) {
  const r = await page.request.post('/api/profile', { data: { profile: 'demo' } });
  if (!r.ok()) return;
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  for (const w of wishes) await page.request.delete(`/api/wishlist/${w.id}`);
}

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await undoWishes(page);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

async function openMissing(page: Page) {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/missing');
  await expect(page.getByTestId('gap').first()).toBeVisible({ timeout: 30_000 });
}

/** Describes a tan rain-proof coat by hand and waits for the answer. Heavy: the demo's check is weighed by its example
 * answers, whose rainy days are mostly work and everyday ones, cold days among them, which a medium coat is not warm
 * enough for. */
async function checkCoat(page: Page) {
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  await form.getByRole('group', { name: 'Formality' }).getByRole('button', { name: 'Smart casual', exact: true }).click();
  await form.getByRole('group', { name: 'How heavy the cloth is' }).getByRole('button', { name: 'Heavy', exact: true }).click();
  await form.getByRole('switch', { name: /keeps the rain off/ }).check({ force: true });
  await form.getByRole('button', { name: 'Would it work?' }).click();
  const answer = panel.getByTestId('would-work-answer');
  await expect(answer).toBeVisible({ timeout: 30_000 });
  return answer;
}

test('would this work?, described by hand in the demo closet on a computer, on a page of its own, and put on the wishlist', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openMissing(page);
  await page.getByRole('link', { name: 'Would this work?' }).click();
  await expect(page).toHaveURL(/\/missing\/check$/);
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
  // nothing to check until the kind and colour are chosen
  await expect(panel.getByRole('button', { name: 'Would it work?' })).toBeDisabled();

  const answer = await checkCoat(page);
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
  await expect(page).toHaveURL(/\/missing\/item\//);
  await page.goBack();
  await expect(page.getByTestId('would-work-answer')).toBeVisible();
  // ...and it is still on the wishlist once: the button does not add it again
  await expect(panel.getByRole('button', { name: 'On your wishlist' })).toBeDisabled();
  expect((await (await page.request.get('/api/wishlist')).json()).wishes).toHaveLength(1);
  // back to What's missing: the wishlist is in the side panel, with the new wish in it
  await panel.locator('.wouldwork-back').click();
  await expect(page).toHaveURL(/\/missing$/);
  await expect(page.getByRole('complementary', { name: 'Your wishlist' }).getByTestId('wish')).toHaveCount(1);
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
  await form.getByRole('button', { name: 'Would it work?' }).click();
  await expect(panel.getByTestId('would-work-waiting')).toContainText('Sending');
  await expect.poll(() => held !== null).toBe(true);
  // away to the closet, then back while the request is still on its way
  await page.getByRole('link', { name: 'Closet', exact: true }).first().click();
  await expect(page).not.toHaveURL(/\/missing/);
  await page.goBack();
  await expect(page).toHaveURL(/\/missing\/check$/);
  await expect(page.getByTestId('would-work-waiting')).toContainText('Sending');
  await held!.continue();
  await expect(page.getByTestId('would-work-answer')).toBeVisible({ timeout: 30_000 });
  await page.unroute('**/api/would-this-work');
});

test('would this work? on a phone: a full page, a fourth pair of jeans you have already, and I found one from a wish', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openMissing(page);
  await page.getByRole('link', { name: 'Would this work?' }).click();
  const panel = page.getByTestId('would-work');
  await expect(panel).toBeVisible();
  await expect(page.getByTestId('gap')).toHaveCount(0);   // a page of its own
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Jeans', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Navy', exact: true }).click();
  await form.getByRole('button', { name: 'Would it work?' }).click();
  const answer = panel.getByTestId('would-work-answer');
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).toHaveAttribute('data-verdict', 'have_it');
  await expect(answer).toContainText('You have three like it');
  await expect(answer.getByRole('list', { name: 'Pieces you have like it' }).getByRole('link')).toHaveCount(3);
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);

  // from a wish: the form starts with what the wish asks for
  const gaps = await (await page.request.get('/api/gaps')).json();
  const rain = gaps.gaps.find((g: { id: string }) => g.id === 'outer-rain');
  await page.request.post('/api/wishlist', { data: { gap_id: rain.id } });
  // back from the check, the lists are asked for again: the wish shows without reloading the page
  await page.locator('.wouldwork-back').click();
  await page.getByRole('button', { name: /^Wishlist · 1/ }).click();
  await page.getByTestId('wish').first().getByRole('button', { name: 'I found one: would it work?' }).click();
  await expect(page).toHaveURL(/\/missing\/check\/wish\//);
  const fromWish = page.getByTestId('would-work');
  await expect(fromWish).toContainText(`Checking a find for ${rain.name}`);
  await expect(fromWish.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(fromWish.getByRole('switch', { name: /keeps the rain off/ })).toBeChecked();

  // the answer goes into that wish's note, not into a second wish
  const kind = fromWish.getByRole('form', { name: 'Describe it by hand' });
  if (await kind.getByRole('button', { name: 'Would it work?' }).isDisabled()) {
    await kind.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  }
  await kind.getByRole('button', { name: 'Would it work?' }).click();
  await expect(fromWish.getByTestId('would-work-answer')).toBeVisible({ timeout: 30_000 });
  await fromWish.getByRole('button', { name: "Add it to the wish's note" }).click();
  await expect(fromWish.getByRole('button', { name: "In the wish's note" })).toBeDisabled();
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  expect(wishes).toHaveLength(1);
  expect(wishes[0].note).toContain('keeps the rain off');
  await page.locator('.wouldwork-back').click();
  await page.getByRole('button', { name: /^Wishlist · 1/ }).click();
  await expect(page.getByTestId('wish').first().getByRole('textbox', { name: 'Note' })).toHaveValue(/keeps the rain off/);
});

test('would this work? is off while offline, with the same words as the other buttons', async ({ page, context }) => {
  await openMissing(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  const off = page.locator('.missing-header').getByText('Would this work?');
  await expect(off).toHaveAttribute('aria-disabled', 'true');
  await expect(off).toHaveAttribute('title', /needs Closet on your computer/i);
});

for (const [label, viewport] of [['computer', { width: 1280, height: 800 }], ['phone', { width: 390, height: 844 }]] as const) {
  test(`screenshot of an answer to would this work? on a ${label} (${viewport.width}×${viewport.height})`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await login(page);
    await useProfile(page, 'demo');
    await page.goto('/missing/check');
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
