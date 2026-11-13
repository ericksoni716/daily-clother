import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** Open-Meteo is never called from a test: Today's outfits are asked of the real server with a mild, dry day filled in. */
async function fakeWeather(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { low_c: 9, high_c: 16, rain: false, ...body } });
    await route.fulfill({ response });
  });
}

async function openToday(page: Page) {
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
}

const current = (page: Page) => page.getByTestId('current-outfit');
const question = (page: Page) => page.getByTestId('worn-question');
const cards = (page: Page) => page.getByTestId('worn-outfit');

test('worn: wear an outfit, rate it, Today learns from it, wear one again, remove it', async ({ page }) => {
  await fakeWeather(page);
  await openToday(page);

  // yesterday's demo outfit has no rating, so Today asks about it, below today's outfits
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(question(page).getByRole('heading', { name: "How was yesterday's outfit?" })).toBeVisible();
  await question(page).getByRole('button', { name: 'Loved it' }).click();
  await expect(question(page).getByRole('group', { name: 'Why' })).toBeVisible();
  await question(page).getByRole('button', { name: 'Got compliments' }).click();
  await expect(question(page).getByRole('button', { name: 'Got compliments' })).toHaveAttribute('aria-pressed', 'true');
  await question(page).getByRole('button', { name: 'Done' }).click();
  await expect(question(page)).toHaveCount(0);

  // wear today's outfit: it is remembered as an outfit
  await current(page).getByRole('button', { name: "I'm wearing this" }).click();
  await expect(current(page).getByTestId('worn-today')).toHaveText("You're wearing this today");
  const worn = await current(page).getByTestId('piece').count();

  await page.getByRole('link', { name: 'Worn', exact: true }).click();
  await expect(page).toHaveURL(/\/today\/worn$/);
  const todays = cards(page).first();
  await expect(todays.getByRole('heading', { name: 'Today' })).toBeVisible();
  await expect(todays.getByTestId('worn-rating')).toHaveText('Not rated yet');
  await expect(todays.getByRole('list', { name: 'Pieces' }).getByRole('listitem')).toHaveCount(worn);
  await expect(cards(page).nth(1).getByTestId('worn-rating')).toHaveText('Loved it · got compliments');

  // rate it on the Worn screen, with a reason
  await todays.getByRole('button', { name: 'Not again' }).click();
  await todays.getByRole('button', { name: 'Too cold' }).click();
  await expect(todays.getByTestId('worn-rating')).toHaveText('Not again · too cold');

  // Today changes because of the rating: on a day like this one, it dresses the owner a little warmer
  await page.goto('/today');
  await expect(current(page).getByRole('list', { name: 'Why this works' }))
    .toContainText('Dressed a little warmer than usual: you were cold on a day like this on');

  // wear one again: the loved outfit of six days ago comes back where its pieces are clean
  await page.getByRole('link', { name: 'Worn', exact: true }).click();
  const older = cards(page).filter({ has: page.getByTestId('worn-rating').getByText('Loved it · got compliments') }).last();
  await expect(older.getByRole('heading')).not.toHaveText('Yesterday');
  await older.getByRole('button', { name: 'Wear this again' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByText(/Not clean or not available today: White tee/)).toBeVisible();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();

  // remove today's outfit: the list and the wears go with it
  await page.goto('/today/worn');
  const first = cards(page).first();
  await expect(first.getByRole('heading', { name: 'Today' })).toBeVisible();
  await first.getByRole('button', { name: 'Remove' }).click();
  await first.getByRole('group', { name: 'Remove this outfit?' }).getByRole('button', { name: 'Remove' }).click();
  await expect(cards(page).first().getByRole('heading', { name: 'Today' })).toHaveCount(0);
  const day = await page.evaluate(() => new Date().toLocaleDateString('en-CA'));
  const listed = await page.request.get('/api/outfits/worn').then((r) => r.json());
  expect(listed.outfits.filter((o: { worn_on: string }) => o.worn_on === day)).toEqual([]);
});

test('worn: offline the saved list is shown as last changed, and rating says why it waits', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.goto('/today/worn');
  const first = cards(page).first();
  await expect(first).toBeVisible();
  const count = await cards(page).count();

  // a change made online is what the saved copy shows offline
  const change = first.getByRole('button', { name: 'Change rating' });
  if (await change.count()) await change.click();
  await first.getByRole('button', { name: 'Not again' }).click();
  await expect(first.getByTestId('worn-rating')).toHaveText(/^Not again/);
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(cards(page)).toHaveCount(count);
  await expect(cards(page).first().getByTestId('worn-rating')).toHaveText(/^Not again/);
  await cards(page).first().getByRole('button', { name: 'Change rating' }).click();
  await expect(cards(page).first().getByRole('button', { name: 'Loved it' })).toBeDisabled();
  await expect(cards(page).first().getByText("You're offline, so rating has to wait")).toBeVisible();
  await expect(cards(page).first().getByRole('button', { name: 'Wear this again' })).toBeDisabled();
});

test('worn: the list fits a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeWeather(page);
  await openToday(page);
  await page.getByRole('link', { name: 'Worn', exact: true }).click();
  await expect(cards(page).first()).toBeVisible();
  await expect(cards(page).first().getByRole('button', { name: 'Wear this again' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
