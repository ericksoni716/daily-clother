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

/** Describes a tan rain-proof coat by hand and waits for the answer. */
async function checkCoat(page: Page) {
  const panel = page.getByTestId('would-work');
  const form = panel.getByRole('form', { name: 'Describe it by hand' });
  await form.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true }).click();
  await form.getByRole('group', { name: 'Main colour' }).getByRole('button', { name: 'Tan', exact: true }).click();
  await form.getByRole('group', { name: 'Formality' }).getByRole('button', { name: 'Smart casual', exact: true }).click();
  await form.getByRole('group', { name: 'How heavy the cloth is' }).getByRole('button', { name: 'Medium', exact: true }).click();
  await form.getByRole('switch', { name: /keeps the rain off/ }).check({ force: true });
  await form.getByRole('button', { name: 'Would it work?' }).click();
  const answer = panel.getByTestId('would-work-answer');
  await expect(answer).toBeVisible({ timeout: 30_000 });
  return answer;
}

test('would this work?, described by hand in the demo closet on a computer, and put on the wishlist', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openMissing(page);
  await page.getByRole('link', { name: 'Would this work?' }).click();
  await expect(page).toHaveURL(/\/missing\/check$/);
  const panel = page.getByTestId('would-work');
  // beside the list, in place of the wishlist
  await expect(page.getByRole('complementary', { name: 'Would this work?' })).toContainText('Would this work?');
  await expect(page.getByTestId('gap').first()).toBeVisible();
  // the demo closet sends nothing to Claude: the photo way is off, and says why
  await expect(panel.getByRole('button', { name: 'Take a photo' })).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Choose a photo' })).toBeDisabled();
  await expect(panel).toContainText('The demo closet never sends anything to Claude');
  // nothing to check until the kind and colour are chosen
  await expect(panel.getByRole('button', { name: 'Would it work?' })).toBeDisabled();

  const answer = await checkCoat(page);
  await expect(answer).toHaveAttribute('data-verdict', 'fills_gap');
  await expect(answer.getByTestId('verdict')).toHaveText('Fills a gap');
  await expect(answer).toContainText('A rain-proof outer layer');
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
  await page.locator('.detail-top').getByRole('link', { name: "What's missing" }).click();
  await page.reload();   // the wish was added behind the screen's back
  await page.getByRole('button', { name: /^Wishlist · 1/ }).click();
  await page.getByTestId('wish').first().getByRole('button', { name: 'I found one: would it work?' }).click();
  await expect(page).toHaveURL(/\/missing\/check\/wish\//);
  const fromWish = page.getByTestId('would-work');
  await expect(fromWish).toContainText(`Checking a find for ${rain.name}`);
  await expect(fromWish.getByRole('group', { name: 'What kind of piece' }).getByRole('button', { name: 'Coat', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(fromWish.getByRole('switch', { name: /keeps the rain off/ })).toBeChecked();
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
    if (label === 'computer') await page.getByTestId('would-work').evaluate((el) => el.closest('aside')?.scrollTo(0, 0));
    else await page.getByTestId('would-work-answer').scrollIntoViewIfNeeded();
    const path = testInfo.outputPath(`would-this-work-${label}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`Would this work? on a ${label}`, { path, contentType: 'image/png' });
  });
}
