import type { Page, Route } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, goToCloset, test, useProfile } from './fixtures';

// Where a piece is (23 November): sent to the cleaner's from its page, said on the closet's line and in its away view,
// left out of Today's outfits, and back with one tap, with Undo. On a phone-sized page.

const PHONE = { width: 375, height: 740 };
const DAY = { low_c: 12, high_c: 18, rain: false };

test.use({ viewport: PHONE });

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** Today's outfits asked of the real server for a mild dry day, so no forecast is needed. */
async function mildDay(page: Page) {
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.continue({ postData: JSON.stringify({ ...body, ...DAY }) });
  });
}

const todaysIds = async (page: Page) =>
  (await page.getByTestId('current-outfit').getByTestId('piece').evaluateAll((links) => links.map((a) => a.getAttribute('href'))))
    .map((h) => h!.split('/').pop()!);

test('send a piece to the cleaner\'s, see it on the closet and not on Today, then bring it back and undo', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await mildDay(page);
  // the piece Today would put on your legs first today
  const offered = await (await page.request.post('/api/outfits/today', { data: { ...DAY, count: 3 } })).json();
  const pieceId: string = offered.outfits[0].pieces.bottom;
  const item = await (await page.request.get(`/api/items/${pieceId}`)).json();
  expect(item.away).toBeNull();

  // its page: one row says where it is; Change opens the choices in a sheet
  await page.goto(`/item/${pieceId}`);
  const row = page.getByTestId('where-it-is');
  await expect(row.getByTestId('where-line')).toHaveText('In your closet');
  await row.getByRole('button', { name: 'Change where it is' }).click();
  const sheet = page.getByTestId('where-sheet');
  await expect(sheet).toBeVisible();
  await sheet.getByRole('button', { name: "At the cleaner's" }).click();
  await sheet.getByLabel('When do you expect it back? (if you know)').fill('2099-01-09');
  await sheet.getByLabel('A note for you').fill('Ask about the stain');
  expect(await sideways(page)).toEqual([]);
  expect(await axeViolations(page)).toEqual([]);
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(row.getByTestId('where-line')).toHaveText("At the cleaner's until Friday 9 Jan 2099");
  await expect(row).toContainText('Ask about the stain');
  await expect(row.getByRole('button', { name: "It's back" })).toBeVisible();

  // the closet: its part of the line, which shows only those pieces, where each is and when
  await page.goto('/');
  const part = page.getByTestId('away');
  await expect(part).toHaveText('1 away');
  await expect(page.getByTestId('away-mark')).toHaveCount(1);
  await part.click();
  await expect(page.getByRole('button', { name: 'Remove filter: Away' })).toBeVisible();
  const away = page.getByTestId('away-row');
  await expect(away).toHaveCount(1);
  await expect(away).toContainText("At the cleaner's");
  await expect(away).toContainText('Until Friday 9 Jan 2099');
  expect(await sideways(page)).toEqual([]);

  // Today does not offer it
  await page.goto('/today');
  await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
  expect(await todaysIds(page)).not.toContain(pieceId);

  // back, one tap, and Undo puts it away again
  await page.goto('/');
  await expect(page.getByTestId('away')).toHaveText('1 away');
  await page.getByTestId('away').click();
  await away.getByRole('button', { name: /^It's back/ }).click();
  await expect(away).toContainText('Back in your closet');
  await away.getByRole('button', { name: /^Undo/ }).click();
  await expect(away).toContainText('Until Friday 9 Jan 2099');
  const again = await (await page.request.get(`/api/items/${pieceId}`)).json();
  expect(again.away).toMatchObject({ place: 'cleaner', until: '2099-01-09', note: 'Ask about the stain' });

  // and from its page, the return is said once with Undo
  await page.goto(`/item/${pieceId}`);
  await row.getByRole('button', { name: "It's back" }).click();
  await expect(row.getByTestId('where-line')).toHaveText("Back from the cleaner's, and marked clean");
  await expect(row.getByRole('button', { name: "Undo: it's back" })).toBeVisible();
  await page.goto('/');
  await expect(page.getByTestId('away')).toHaveCount(0);
});
