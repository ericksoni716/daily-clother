import { expect, goToCloset, serviceWorkerInCharge, test, useProfile } from './fixtures';

let archived: string | null = null;

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  // Put the archived piece back so later runs (and specs) find the demo closet as it was.
  if (archived) await page.request.patch(`/api/items/${archived}`, { data: { status: 'active' } });
  archived = null;
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** Opens "More numbers" on the Wardrobe page, where cost per wear and the other figures are kept. */
async function moreNumbers(page: import('@playwright/test').Page) {
  await page.getByTestId('more-numbers').getByText('More numbers').click();
  await expect(page.getByTestId('cost-per-wear')).toBeVisible();
}

test('how the closet is used, in the demo closet: a cost per wear, and archiving a piece never worn', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');

  // Insights is part of the Wardrobe now: its old address leads there
  await page.goto('/insights');
  await expect(page).toHaveURL(/\/wardrobe$/);
  await expect(page.locator('#wardrobe-title')).toBeVisible();

  // cost per wear is kept, but is not what the page leads with (the owner, 16 November): behind "More numbers", the
  // last card there, its figure inside its sentence, and its pieces folded away until asked for
  await expect(page.getByTestId('cost-per-wear')).toBeHidden();
  await moreNumbers(page);
  const cards = page.getByTestId('more-numbers').locator('.insights-grid > .insights-card');
  await expect(cards.last()).toHaveAttribute('data-testid', 'cost-per-wear');
  const cost = page.getByTestId('cost-per-wear');
  await expect(cost).not.toHaveClass(/is-wide/);
  await expect(cost.getByRole('heading', { level: 3 })).toHaveText('What your clothes cost you');
  await expect(cost.getByTestId('insight-hero')).toHaveCount(0);
  await expect(cost.locator('.insights-sentence')).toHaveText(/^You paid \$[\d,]+ for the \d+ pieces with a price and have worn them \d+ times: \$[\d,]+\.\d\d a wear\.$/);
  await expect(page.getByTestId('cost-best')).toBeHidden();
  await cost.getByText('Which pieces have earned their price').click();
  await expect(page.getByTestId('cost-best')).toHaveText(/^Your .+ cost \$[\d,]+\.\d\d a wear over \d+ wears?\.$/);
  // pieces not worn yet are listed once, in their own card, not again under cost per wear
  await expect(cost.getByRole('heading', { name: 'Not worn yet' })).toHaveCount(0);

  // under the one heading "Not worn", said once: no second label, and the count only in its sentence
  const never = page.getByTestId('never-worn');
  await expect(page.getByRole('heading', { name: 'Not worn', level: 2 })).toBeVisible();
  await expect(never.getByRole('heading')).toHaveCount(0);
  await expect(never.getByTestId('insight-hero')).toHaveCount(0);
  const pieces = never.getByTestId('insight-piece');
  await expect(pieces.first()).toBeVisible();
  const before = await pieces.count();
  await expect(never.locator('.insights-sentence')).toHaveText(new RegExp(`^${before} pieces? ha(s|ve) not been worn`));
  // the Archive buttons line up, whatever the length of the names above them
  const tops = await never.getByRole('button', { name: /^Archive / }).evaluateAll((bs) => bs.map((b) => Math.round(b.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  const href = await pieces.first().getByRole('link').getAttribute('href');
  archived = href!.split('/').pop()!;

  await pieces.first().getByRole('button', { name: /^Archive / }).click();
  await expect(page.getByText(/^Archived\./)).toBeVisible();
  await expect(pieces).toHaveCount(before - 1);
  await expect(never.locator(`a[href$="${archived}"]`)).toHaveCount(0);

  const item = await (await page.request.get(`/api/items/${archived}`)).json();
  expect(item.status).toBe('archived');

  // "Keep" hides a piece on this device, and it can be shown again.
  await pieces.first().getByRole('button', { name: /^Keep / }).click();
  await expect(pieces).toHaveCount(before - 2);
  await never.getByRole('button', { name: 'Show again' }).click();
  await expect(pieces).toHaveCount(before - 1);
});

test("insights offline: one closet's saved answer is never shown as the other's", async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  await page.goto('/wardrobe');
  await moreNumbers(page);
  const demoSentence = await page.getByTestId('cost-per-wear').locator('.insights-sentence').innerText();
  expect(demoSentence).toMatch(/^You paid \$2,859 /);
  await page.waitForLoadState('networkidle');

  // the demo closet's answer is shown offline, marked as saved
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  await moreNumbers(page);
  await expect(page.getByTestId('cost-per-wear').getByText(demoSentence)).toBeVisible();
  await expect(page.getByTestId('never-worn').getByRole('button', { name: /^Archive / }).first()).toBeDisabled();
  await context.setOffline(false);

  // switch to the real closet, then go offline before its Insights were ever fetched
  await page.request.post('/api/profile', { data: { profile: 'main' } });
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.goto('/wardrobe');
  await expect(page.locator('#wardrobe-title')).toBeVisible();
  await expect(page.getByText('Your wardrobe was not saved on this device yet.', { exact: true })).toBeVisible();
  await expect(page.locator('main')).not.toContainText("You're offline");   // the banner says it (the review of 24 November, 30)
  await expect(page.getByText(demoSentence)).toHaveCount(0);
  await expect(page.getByText('$1,527')).toHaveCount(0);
});

test('how the closet is used shows drawings or photos as Settings says', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  // (turned on in Settings in 34-show-drawings.spec.ts; here straight through the settings)
  expect((await page.request.put('/api/settings', { data: { show_drawings: true } })).ok()).toBe(true);
  await page.goto('/wardrobe');
  await moreNumbers(page);
  await page.getByTestId('cost-per-wear').getByText('Which pieces have earned their price').click();
  const pics = page.getByTestId('cost-per-wear').locator('.insights-piece-pic img');
  await expect(pics.first()).toBeVisible();
  expect(await pics.evaluateAll((imgs) => imgs.every((i) => i.classList.contains('pic-illustration')))).toBe(true);
  expect((await page.request.put('/api/settings', { data: { show_drawings: false } })).ok()).toBe(true);
  await page.goto('/wardrobe');
  const all = page.locator('.insights img');
  await expect(all.first()).toBeVisible();
  // the demo's photographed pieces show their photo (cut out), as in the grid
  expect(await all.evaluateAll((imgs) => imgs.some((i) => !i.classList.contains('pic-illustration')))).toBe(true);
});

test('Your nines: the nine pieces worn most, as a square, over the time you choose, each opening the piece', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  // drawings, as Settings says, like every other picture of a piece
  expect((await page.request.put('/api/settings', { data: { show_drawings: true } })).ok()).toBe(true);
  try {
    await page.goto('/wardrobe');
    const nines = page.getByTestId('nines');
    await expect(page.getByRole('heading', { name: 'Your nines', level: 2 })).toBeVisible({ timeout: 30_000 });
    const tiles = nines.getByTestId('nine');
    await expect(tiles).toHaveCount(9);
    await expect(nines.getByRole('button', { name: 'Last 30 days' })).toHaveAttribute('aria-pressed', 'true');
    // the periods are 44px to tap (they were 34: the review of 24 November, 46)
    for (const period of ['Last 30 days', 'Last 90 days', 'All time']) {
      const box = await nines.getByRole('button', { name: period }).evaluate((el) => el.getBoundingClientRect().toJSON() as DOMRect);
      expect(box.height, period).toBeGreaterThanOrEqual(44);
    }
    // each says its number of wears, the most first
    const counts = (await tiles.locator('.nines-count').allInnerTexts()).map(Number);
    expect(counts).toEqual([...counts].sort((a, b) => b - a));
    await expect(tiles.first()).toHaveAttribute('aria-label', new RegExp(`, ${counts[0]} wears?$`));
    expect(await nines.locator('img').evaluateAll((imgs) => imgs.length > 0 && imgs.every((i) => i.classList.contains('pic-illustration')))).toBe(true);
    // a square on a phone: three across, three down, about as tall as it is wide
    const grid = (await nines.locator('.nines-grid').boundingBox())!;
    expect(Math.abs(grid.width - grid.height)).toBeLessThan(12);
    expect(grid.width).toBeLessThanOrEqual(375);
    // all time
    await nines.getByRole('button', { name: 'All time' }).click();
    await expect(tiles).toHaveCount(9);
    // a piece opens in the Wardrobe
    const href = await tiles.first().getAttribute('href');
    expect(href).toMatch(/^\/wardrobe\/item\//);
    await tiles.first().click();
    await expect(page).toHaveURL(new RegExp(`${href}$`));
    // and on a computer it is not a wall: about a phone's width
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/wardrobe');
    expect((await page.getByTestId('nines').locator('.nines-grid').boundingBox())!.width).toBeLessThanOrEqual(420);
  } finally {
    await page.request.put('/api/settings', { data: { show_drawings: false } });
  }
});
