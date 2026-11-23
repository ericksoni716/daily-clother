import type { Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test, useProfile } from './fixtures';

// Outfits you keep, on a phone: kept from Today and from an outfit worn (said when kept twice), found under Worn's
// other half, named in place, removed with Undo, and worn again, today or on another day.

const PHONE = { width: 375, height: 740 };

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

const current = (page: Page) => page.getByTestId('current-outfit');
const kept = (page: Page) => page.getByTestId('kept-outfit');
const toast = (page: Page, text: string) => page.locator('.toast', { hasText: text });

async function openDemo(page: Page, path = '/today') {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  // the demo's weather is never looked up in the browser tests: a mild, dry day
  await page.route('**/api/outfits/today', async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: { low_c: 9, high_c: 16, rain: false, ...body } }) });
  });
  await page.goto(path);
}

test('the outfits you keep are empty until one is kept, with one sentence saying how', async ({ page }) => {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await page.goto('/today/worn/kept');
  await expect(page.getByRole('group', { name: 'Show' }).getByRole('link', { name: 'Outfits you keep' })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByTestId('kept-empty')).toContainText('No outfits kept yet');
  await expect(page.getByTestId('kept-empty')).toContainText('Keep this outfit');
  expect(await axeViolations(page)).toEqual([]);
});

test('keep an outfit from Today and from one worn, find it under Worn, name it, remove it with Undo', async ({ page }) => {
  await openDemo(page);
  await current(page).getByRole('button', { name: 'Keep this outfit' }).click();
  await expect(toast(page, 'Kept. You will find it under Worn.')).toBeVisible();
  await expect(current(page).getByTestId('kept-mark')).toHaveText('Kept under Worn');
  // "I'm wearing this" is still on the first phone screen
  const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
  const wear = (await current(page).getByRole('button', { name: "I'm wearing this" }).boundingBox())!;
  expect(wear.y + wear.height).toBeLessThanOrEqual(tabbar.y);

  // from an outfit worn, in its choices: kept once, then said, not kept twice
  await page.goto('/today/worn');
  const first = page.getByTestId('worn-outfit').first();
  for (const said of ['Kept. You will find it under Worn.', 'You keep this outfit already. It is under Worn.']) {
    await first.getByRole('button', { name: 'More for this outfit' }).click();
    await page.getByRole('dialog', { name: 'This outfit' }).getByRole('button', { name: 'Keep this outfit' }).click();
    await expect(toast(page, said)).toBeVisible();
  }

  await page.getByRole('group', { name: 'Show' }).getByRole('link', { name: 'Outfits you keep' }).click();
  await expect(page).toHaveURL(/\/today\/worn\/kept$/);
  await expect(kept(page)).toHaveCount(4);   // the demo's two and the two kept here
  const card = kept(page).first();
  const listTop = (await kept(page).nth(1).boundingBox())!.y;
  await card.getByLabel('Name of this outfit').fill('Market morning');
  await card.getByLabel('Name of this outfit').press('Enter');
  await expect(card.getByText('Saved')).toBeVisible();
  expect((await kept(page).nth(1).boundingBox())!.y).toBe(listTop);   // the page holds still as it saves

  // removed, it leaves a line with Undo in its place
  await card.getByRole('button', { name: 'More for this outfit' }).click();
  await page.getByRole('dialog', { name: 'This outfit' }).getByRole('button', { name: 'Remove' }).click();
  await expect(page.getByTestId('kept-removed')).toContainText('You removed “Market morning”.');
  await page.getByTestId('kept-removed').getByRole('button', { name: 'Undo' }).click();
  await expect(kept(page)).toHaveCount(4);
  await expect(kept(page).first().getByLabel('Name of this outfit')).toHaveValue('Market morning');
  expect(await axeViolations(page)).toEqual([]);
});

test('wear a kept outfit today, or on another day', async ({ page }) => {
  await openDemo(page, '/today/worn/kept');
  const named = page.getByRole('article', { name: 'Lunch in the sun' });   // one of the demo's
  await expect(named).toHaveCount(1);
  await named.getByRole('button', { name: 'Wear this' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('group', { name: 'Wearing again' })).toContainText('Starting from an outfit you kept');
  await expect(current(page).getByTestId('piece').filter({ hasText: 'Madras plaid shirt' })).toBeVisible();

  await page.goto('/today/worn/kept');
  await named.getByRole('button', { name: 'More for this outfit' }).click();
  await page.getByRole('dialog', { name: 'This outfit' }).getByRole('button', { name: 'Wear this on another day' }).click();
  const sheet = page.getByRole('dialog', { name: 'Wear it on another day' });
  await sheet.getByRole('list', { name: 'The next days' }).getByRole('button').first().click();
  await expect(page).toHaveURL(/\/today\/day\/\d{4}-\d{2}-\d{2}$/);
  await expect(page.getByRole('group', { name: 'Wearing again' })).toContainText('Starting from an outfit you kept');
  await expect(current(page).getByTestId('piece').filter({ hasText: 'Madras plaid shirt' })).toBeVisible();
  await expect(current(page).getByRole('button', { name: 'Wear this tomorrow' })).toBeVisible();
});
