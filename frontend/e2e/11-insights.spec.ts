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
  await expect(cost.getByRole('heading', { level: 3 })).toHaveText('Cost per wear');
  await expect(cost.getByTestId('insight-hero')).toHaveCount(0);
  await expect(cost.locator('.insights-sentence')).toHaveText(/^You paid \$[\d,]+ for the \d+ pieces with a price and have worn them \d+ times: \$[\d,]+\.\d\d a wear\.$/);
  await expect(page.getByTestId('cost-best')).toBeHidden();
  await cost.getByText('Best value and most per wear').click();
  await expect(page.getByTestId('cost-best')).toHaveText(/^Your .+ cost \$[\d,]+\.\d\d a wear over \d+ wears?\.$/);
  // pieces not worn yet are listed once, in their own card, not again under cost per wear
  await expect(cost.getByRole('heading', { name: 'Not worn yet' })).toHaveCount(0);

  const never = page.getByTestId('never-worn');
  await expect(never.getByRole('heading', { level: 3 })).toHaveText('Not worn yet');
  const pieces = never.getByTestId('insight-piece');
  await expect(pieces.first()).toBeVisible();
  const before = await pieces.count();
  await expect(never.getByTestId('insight-hero')).toHaveText(before === 1 ? '1 piece' : `${before} pieces`);
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
  await expect(page.getByText(/nothing was saved on this device yet/)).toBeVisible();
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
  await page.getByTestId('cost-per-wear').getByText('Best value and most per wear').click();
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
