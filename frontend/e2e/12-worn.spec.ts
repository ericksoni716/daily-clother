import type { Page, Route } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page, context }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await context.setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
  await page.request.put('/api/settings', { data: { laundry: { auto: true, day: 6 } } });
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
  // these tests are about the Worn screen: the laundry stays as the owner puts it (automatic laundry has its own tests)
  await page.request.put('/api/settings', { data: { laundry: { auto: false } } });
  await useProfile(page, 'demo');
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
}

const current = (page: Page) => page.getByTestId('current-outfit');
const question = (page: Page) => page.getByTestId('worn-question');
const cards = (page: Page) => page.getByTestId('worn-outfit');
/** Worn is reached from Recent outfits on Today: its "See all". */
const seeAll = (page: Page) => page.getByTestId('recent-outfits').getByRole('link', { name: 'See all' });

test('worn: wear an outfit, rate it, Today learns from it, wear one again, remove it', async ({ page }) => {
  await fakeWeather(page);
  await openToday(page);

  // yesterday's demo outfit has no rating, so Today asks about it, under today's outfits, first in Recent outfits
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  await expect(question(page).getByRole('heading', { name: "How was yesterday's outfit?" })).toBeVisible();
  expect((await question(page).boundingBox())!.y).toBeGreaterThan((await current(page).boundingBox())!.y);
  await expect(page.getByTestId('recent-outfits').getByTestId('worn-question')).toBeVisible();
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
  // it shows at once in Recent outfits, where it can be rated in place
  const recentToday = page.getByTestId('recent-outfit').filter({ has: page.getByRole('heading', { name: 'Today' }) });
  await expect(recentToday.getByRole('group', { name: 'How it went' }).getByRole('button', { name: 'Loved it' })).toBeVisible();

  await seeAll(page).click();
  await expect(page).toHaveURL(/\/today\/worn$/);
  const todays = cards(page).first();
  await expect(todays.getByRole('heading', { name: 'Today' })).toBeVisible();
  await expect(todays.getByTestId('worn-rating')).toHaveText('Not rated yet');
  await expect(todays.getByRole('list', { name: 'Pieces' }).getByRole('listitem')).toHaveCount(worn);
  await expect(cards(page).nth(1).getByTestId('worn-rating')).toHaveText('Loved it · got compliments');

  // rate it on the Worn screen, with a reason: unrated, the three answers are on the card
  await todays.getByRole('button', { name: 'Not again' }).click();
  await todays.getByRole('button', { name: 'Too cold' }).click();
  await expect(todays.getByTestId('worn-rating')).toHaveText('Not again · too cold');

  // rated, the rating is a chip that opens the answers again
  const loved = cards(page).nth(1);
  const chip = loved.getByTestId('worn-rating');
  await expect(chip).toHaveAttribute('aria-expanded', 'false');
  await expect(loved.getByRole('button', { name: 'Fine' })).toHaveCount(0);
  await chip.click();
  await expect(chip).toHaveAttribute('aria-expanded', 'true');
  await expect(loved.getByRole('button', { name: 'Loved it', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await chip.click();
  await expect(loved.getByRole('button', { name: 'Fine' })).toHaveCount(0);

  // the other actions wait behind ⋯: Escape closes the menu and puts focus back on its button
  const more = loved.getByRole('button', { name: 'More for this outfit' });
  await expect(more).toHaveAttribute('aria-haspopup', 'menu');
  await expect(loved.getByRole('button', { name: 'Wear this again' })).toHaveCount(0);
  await more.click();
  await expect(more).toHaveAttribute('aria-expanded', 'true');
  await expect(loved.getByRole('menuitem', { name: 'Wear this again' })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(loved.getByRole('menuitem', { name: 'Put these in the laundry' })).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(loved.getByRole('menuitem', { name: 'Remove' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(loved.getByRole('menu')).toHaveCount(0);
  await expect(more).toBeFocused();
  await expect(more).toHaveAttribute('aria-expanded', 'false');

  // the outfit's clothes go in the laundry in one tap (its shoes do not), and the closet can mark them all clean
  const before = ((await (await page.request.get('/api/items')).json()).items as { id: string; laundry: string | null }[])
    .filter((i) => i.laundry === 'laundry').map((i) => i.id);
  await more.click();
  await loved.getByRole('menuitem', { name: 'Put these in the laundry' }).click();
  await expect(page.getByText(/in the laundry$/).first()).toBeVisible();
  const washing = async () => ((await (await page.request.get('/api/items')).json()).items as { laundry: string | null; category: string }[])
    .filter((i) => i.laundry === 'laundry');
  await expect.poll(async () => (await washing()).length).toBeGreaterThan(0);
  expect((await washing()).every((i) => ['tee', 'shirt', 'polo', 'sweater', 'hoodie', 'jeans', 'trousers', 'shorts'].includes(i.category))).toBe(true);
  await page.goto('/');
  await page.getByTestId('in-laundry').click();
  const notice = page.getByTestId('laundry-notice');
  await notice.getByRole('button', { name: 'All clean' }).click();
  await expect.poll(async () => (await washing()).length).toBe(0);
  await expect(notice).toHaveCount(0);
  for (const id of before) await page.request.post(`/api/items/${id}/laundry`, { data: { state: 'laundry' } });   // as the rest of this test left them

  // Today changes because of the rating: on a day like this one, it dresses the owner a little warmer
  await page.goto('/today');
  await expect(current(page).getByRole('list', { name: 'Why this works' }))
    .toContainText('Dressed a little warmer than usual: you were cold on a day like this on');

  // wear one again: the loved outfit of six days ago comes back where its pieces are clean
  await seeAll(page).click();
  const older = cards(page).filter({ has: page.getByTestId('worn-rating').getByText('Loved it · got compliments') }).last();
  await expect(older.getByRole('heading')).not.toHaveText('Yesterday');
  await older.getByRole('button', { name: 'More for this outfit' }).click();
  await older.getByRole('menuitem', { name: 'Wear this again' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByText(/Not clean or not available today: White tee/)).toBeVisible();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();

  // remove today's outfit: the list and the wears go with it
  await page.goto('/today/worn');
  const first = cards(page).first();
  await expect(first.getByRole('heading', { name: 'Today' })).toBeVisible();
  await first.getByRole('button', { name: 'More for this outfit' }).click();
  await first.getByRole('menuitem', { name: 'Remove' }).click();
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
  await cards(page).first().getByRole('button', { name: 'More for this outfit' }).click();
  await expect(cards(page).first().getByRole('menuitem', { name: 'Wear this again' })).toBeDisabled();
});

test('worn: the list saved offline belongs to its closet', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.goto('/today/worn');
  await expect(cards(page).first()).toBeVisible();
  await page.waitForLoadState('networkidle');

  // switch to the owner's closet without opening Worn there, then lose the connection
  await useProfile(page, 'main');
  await context.setOffline(true);
  await page.goto('/today/worn');
  await expect(page.getByRole('heading', { name: 'Worn', exact: true })).toBeVisible();
  await expect(cards(page)).toHaveCount(0);
  await expect(page.getByText("You're offline, and the worn outfits were not saved on this device yet.")).toBeVisible();
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
  await expect(question(page)).toHaveCount(0);

  // the demo closet's own copy is still there for it
  await context.setOffline(false);
  await useProfile(page, 'demo');
  await context.setOffline(true);
  await page.goto('/today/worn');
  await expect(cards(page).first()).toBeVisible();
});

test('worn: the list fits a phone', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeWeather(page);
  await openToday(page);
  await seeAll(page).click();
  await expect(cards(page).first()).toBeVisible();
  await expect(cards(page).first().getByRole('button', { name: 'More for this outfit' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  await expect.poll(() => page.locator('.worn-list img').evaluateAll((imgs) => imgs.every((i) => (i as HTMLImageElement).complete))).toBe(true);
  const path = testInfo.outputPath('worn-phone.png');
  await page.screenshot({ path });
  await testInfo.attach('Worn on a phone', { path, contentType: 'image/png' });
});
