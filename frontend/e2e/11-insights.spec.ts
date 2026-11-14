import { expect, login, test, useProfile } from './fixtures';

let archived: string | null = null;

test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  // Put the archived piece back so later runs (and specs) find the demo closet as it was.
  if (archived) await page.request.patch(`/api/items/${archived}`, { data: { status: 'active' } });
  archived = null;
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('insights in the demo closet: a cost per wear, and archiving a piece never worn', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');

  await page.getByRole('link', { name: 'Insights' }).click();
  await expect(page).toHaveURL(/\/insights$/);
  await expect(page.locator('#insights-title')).toBeVisible();

  // each card: a short label, the figure first, then one sentence that does not repeat it
  const cost = page.getByTestId('cost-per-wear');
  await expect(cost.getByRole('heading', { level: 2 })).toHaveText('Cost per wear');
  await expect(cost.getByTestId('insight-hero')).toHaveText(/^\$[\d,]+\.\d\d a wear$/);
  await expect(cost.locator('.insights-sentence')).toHaveText(/^You paid \$[\d,]+ for the \d+ pieces with a price and have worn them \d+ times\.$/);
  await expect(page.getByTestId('cost-best')).toHaveText(/^Your .+ cost \$[\d,]+\.\d\d a wear over \d+ wears?\.$/);
  // pieces not worn yet are listed once, in their own card, not again under cost per wear
  await expect(cost.getByRole('heading', { name: 'Not worn yet' })).toHaveCount(0);

  const never = page.getByTestId('never-worn');
  await expect(never.getByRole('heading', { level: 2 })).toHaveText('Not worn yet');
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
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.goto('/insights');
  const demoSentence = await page.getByTestId('cost-per-wear').locator('.insights-sentence').innerText();
  expect(demoSentence).toMatch(/^You paid \$2,859 /);
  await page.waitForLoadState('networkidle');

  // the demo closet's answer is shown offline, marked as saved
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText(/^Saved earlier today/)).toBeVisible();
  await expect(page.getByTestId('cost-per-wear').getByText(demoSentence)).toBeVisible();
  await expect(page.getByTestId('never-worn').getByRole('button', { name: /^Archive / }).first()).toBeDisabled();
  await context.setOffline(false);

  // switch to the real closet, then go offline before its Insights were ever fetched
  await page.request.post('/api/profile', { data: { profile: 'main' } });
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.goto('/insights');
  await expect(page.locator('#insights-title')).toBeVisible();
  await expect(page.getByText(/nothing was saved on this device yet/)).toBeVisible();
  await expect(page.getByText(demoSentence)).toHaveCount(0);
  await expect(page.getByText('$1,527')).toHaveCount(0);
});

test('insights shows the same pictures as the closet grid: photos or drawings, as chosen there', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Drawings' }).click();
  await page.goto('/insights');
  const pics = page.getByTestId('cost-per-wear').locator('.insights-piece-pic img');
  await expect(pics.first()).toBeVisible();
  expect(await pics.evaluateAll((imgs) => imgs.every((i) => i.classList.contains('pic-illustration')))).toBe(true);
  await page.goto('/');
  await page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Photos' }).click();
  await page.goto('/insights');
  const all = page.locator('.insights img');
  await expect(all.first()).toBeVisible();
  // the demo's photographed pieces show their photo (cut out), as in the grid
  expect(await all.evaluateAll((imgs) => imgs.some((i) => !i.classList.contains('pic-illustration')))).toBe(true);
});
