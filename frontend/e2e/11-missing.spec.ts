import type { Page } from '@playwright/test';
import { expect, login, PASS, test, useProfile } from './fixtures';

async function clearChoices(page: Page) {
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  for (const wish of wishes) await page.request.delete(`/api/wishlist/${wish.id}`);
  const { gaps } = await (await page.request.get('/api/gaps/hidden')).json();
  for (const gap of gaps) await page.request.delete(`/api/gaps/${gap.id}/hidden`);
}

test.beforeEach(async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await clearChoices(page);
  await page.goto('/missing');
});

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/login', { data: { passphrase: PASS } });
  await page.request.post('/api/profile', { data: { profile: 'demo' } });
  await clearChoices(page);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('gaps show the server reasons, what to look for, help levels and the owner’s pieces', async ({ page }) => {
  const answer = await (await page.request.get('/api/gaps')).json();
  await expect(page.getByTestId('gap')).toHaveCount(answer.gaps.length);
  const gap = page.getByTestId('gap').first();
  await expect(gap.getByRole('heading', { name: answer.gaps[0].name, exact: true })).toBeVisible();
  for (const why of answer.gaps[0].why) await expect(gap.getByText(why, { exact: true })).toBeVisible();
  await expect(gap.getByText('What to look for', { exact: true })).toBeVisible();
  await expect(gap.locator('.missing-help')).toHaveAttribute('aria-label', /How much it would help/);
  const piece = gap.getByRole('list', { name: 'Your own pieces' }).getByRole('link').first();
  await expect(piece.locator('img')).toBeVisible();
  await piece.click();
  await expect(page).toHaveURL(/\/missing\/item\//);
  await expect(page.locator('.detail')).toBeVisible();
  await page.locator('.missing-item').getByRole('link', { name: "What's missing" }).click();
  await expect(page.locator('#missing-title')).toBeVisible();
});

test('a suggested wish is marked, remembers its note, and can be removed', async ({ page }) => {
  const gap = page.getByTestId('gap').first();
  const name = await gap.getByRole('heading').innerText();
  await gap.getByRole('button', { name: "I'll look for this" }).click();
  const wish = page.getByTestId('wish');
  await expect(wish.getByRole('heading', { name })).toBeVisible();
  await expect(gap.getByRole('link', { name: 'On your wishlist' })).toBeVisible();
  await expect(gap.getByRole('button', { name: "I'll look for this" })).toHaveCount(0);
  await wish.getByLabel('Your note').fill('Try a light lining.');
  await wish.getByRole('button', { name: 'Save note' }).click();
  await expect(wish.getByRole('button', { name: 'Save note' })).toHaveCount(0);
  await page.reload();
  await expect(wish.getByLabel('Your note')).toHaveValue('Try a light lining.');
  await wish.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(wish).toHaveCount(0);
  await expect(gap.getByRole('button', { name: "I'll look for this" })).toBeVisible();
});

test('Not for me hides a suggestion with an optional reason; it can be brought back', async ({ page }) => {
  const first = page.getByTestId('gap').first();
  const name = await first.getByRole('heading').innerText();
  await first.getByRole('button', { name: 'Not for me' }).click();
  await first.getByLabel('Why not? (optional)').selectOption('already_owned');
  await first.getByRole('button', { name: 'Hide suggestion' }).click();
  await expect(page.getByTestId('gap').filter({ has: page.getByRole('heading', { name, exact: true }) })).toHaveCount(0);
  await page.reload();
  await page.getByText('Hidden suggestions', { exact: false }).click();
  const hidden = page.locator('.missing-hidden-card');
  await expect(hidden.getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(hidden.getByText('I have one that is not in the closet yet')).toBeVisible();
  await hidden.getByRole('button', { name: 'Bring back' }).click();
  await expect(page.getByTestId('gap').filter({ has: page.getByRole('heading', { name, exact: true }) })).toBeVisible();
  await expect(hidden).toHaveCount(0);
});

test('a wish added by hand can be marked bought and leads to Add', async ({ page }) => {
  await page.getByRole('button', { name: 'Add your own wish' }).click();
  const form = page.getByRole('form', { name: 'Add your own wish' });
  await form.getByLabel('What are you looking for?').fill('A wool scarf');
  await form.getByLabel('What to look for (optional)').fill('Soft, charcoal, no fringe.');
  await form.getByLabel('A note (optional)').fill('Try it with the navy coat.');
  await form.getByRole('button', { name: 'Add wish', exact: true }).click();
  const wish = page.getByTestId('wish');
  await expect(wish.getByRole('heading', { name: 'A wool scarf' })).toBeVisible();
  await expect(wish.getByText('Soft, charcoal, no fringe.')).toBeVisible();
  await expect(wish.getByLabel('Your note')).toHaveValue('Try it with the navy coat.');
  await wish.getByRole('button', { name: 'I bought it' }).click();
  await expect(page).toHaveURL(/\/add$/);
  await page.goto('/missing');
  await expect(page.getByTestId('wish')).toHaveCount(0);
});

test('refresh picks up a changed note without discarding an unsaved draft', async ({ page }) => {
  await page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" }).click();
  const wish = page.getByTestId('wish');
  await expect(wish).toHaveCount(1);
  const { wishes } = await (await page.request.get('/api/wishlist')).json();
  const url = `/api/wishlist/${wishes[0].id}`;
  await page.request.patch(url, { data: { note: 'Changed on the phone.' } });
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(wish.getByLabel('Your note')).toHaveValue('Changed on the phone.');
  await expect(wish.getByRole('button', { name: 'Save note', exact: true })).toHaveCount(0);
  await wish.getByLabel('Your note').fill('My unsaved draft.');
  await page.request.patch(url, { data: { note: 'A newer saved note.' } });
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(wish.getByText('This note changed elsewhere. Your draft is kept below.')).toBeVisible();
  await expect(wish.getByLabel('Your note')).toHaveValue('My unsaved draft.');
  await wish.getByRole('button', { name: 'Use saved note' }).click();
  await expect(wish.getByLabel('Your note')).toHaveValue('A newer saved note.');
});

test('a save finishing after logout cannot restore saved closet data', async ({ page }) => {
  await page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" }).click();
  const wish = page.getByTestId('wish');
  await expect(wish).toHaveCount(1);
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let reachedServer!: () => void;
  const reached = new Promise<void>((resolve) => { reachedServer = resolve; });
  await page.route('**/api/wishlist/*', async (route) => {
    const response = await route.fetch();
    reachedServer();
    await held;
    await route.fulfill({ response });
  });
  await wish.getByLabel('Your note').fill('A delayed save.');
  await wish.getByRole('button', { name: 'Save note', exact: true }).click();
  await reached;
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByLabel('Passphrase')).toBeVisible();
  const response = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes('/api/wishlist/'));
  release();
  await response;
  await page.waitForLoadState('networkidle');
  expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('closet-shopping:')))).toEqual([]);
});

test('offline shows the saved analysis and wishlist, locks changes and recovers', async ({ page, context }) => {
  await page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" }).click();
  await expect(page.getByTestId('wish')).toHaveCount(1);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null);
  await page.reload();
  await expect(page.getByTestId('gap').first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  const names = await page.getByTestId('gap').getByRole('heading').allTextContents();
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/Saved earlier ·/)).toBeVisible();
  await expect(page.getByTestId('gap').getByRole('heading')).toHaveText(names);
  const add = page.getByRole('button', { name: 'Add your own wish' });
  await expect(add).toBeDisabled();
  await expect(add).toHaveAttribute('title', /Needs Closet on your computer/);
  await expect(page.getByRole('button', { name: "I'll look for this" }).first()).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Not for me' }).first()).toBeDisabled();
  await expect(page.getByTestId('wish').getByLabel('Your note')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'I bought it' })).toBeDisabled();
  await context.setOffline(false);
  await expect(add).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByText(/Saved earlier ·/)).toHaveCount(0);
});

test('a small closet repeats the server sentence and links to adding clothes', async ({ page }) => {
  await useProfile(page, 'main');
  const answer = await (await page.request.get('/api/gaps')).json();
  expect(answer.enough).toBe(false);
  await page.goto('/missing');
  await expect(page.getByText(answer.message, { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Add clothes', exact: true })).toHaveAttribute('href', '/add');
  await expect(page.getByRole('button', { name: 'Add your own wish' })).toBeEnabled();
});

test('loading and a server error are explained; retry works', async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/gaps', async (route) => {
    await held;
    await route.fulfill({ status: 503, json: { detail: 'The closet is busy. Please try again.' } });
  });
  await page.reload();
  await expect(page.getByText('Looking at your closet…')).toBeVisible();
  release();
  await expect(page.getByRole('alert')).toContainText('The closet is busy. Please try again.');
  await page.unroute('**/api/gaps');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByTestId('gap').first()).toBeVisible();
});

for (const [device, viewport] of [['phone', { width: 390, height: 844 }], ['computer', { width: 1280, height: 800 }]] as const) {
  test(`What's missing screenshot on ${device} (${viewport.width}×${viewport.height})`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await expect(page.getByTestId('gap').first()).toBeVisible();
    await page.getByTestId('gap').nth(1).getByRole('button', { name: "I'll look for this" }).click();
    await expect(page.getByTestId('wish')).toHaveCount(1);
    await expect(page.getByText('Added to your wishlist.', { exact: true })).toHaveCount(0);
    const nav = page.locator(viewport.width < 1000 ? 'nav.tabbar' : 'nav.sidebar');
    await expect(nav.getByRole('link', { name: "What's missing", exact: true })).toHaveAttribute('aria-current', 'page');
    await expect.poll(() => page.locator('.missing img').evaluateAll((imgs) => imgs.every((i) => (i as HTMLImageElement).complete))).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    const path = testInfo.outputPath(`missing-${device}.png`);
    await page.screenshot({ path });
    await testInfo.attach(`What's missing — ${device}`, { path, contentType: 'image/png' });
    if (device === 'phone') {
      await page.getByRole('link', { name: 'Your wishlist 1', exact: true }).click();
      await expect(page.getByTestId('wish').getByRole('heading')).toBeInViewport();
    }
  });
}
