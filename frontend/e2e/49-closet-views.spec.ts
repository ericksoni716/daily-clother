import type { Page } from '@playwright/test';
import { expect, goToCloset, test, useProfile } from './fixtures';

// The closet's line and the views it opens (the second review of the screens, 24 November): a kept view with nothing
// in it is not where the closet opens; a tap on a part of the line shows those pieces; the Filter sheet keeps its
// head while its body scrolls. On a phone-sized page, in the demo closet.

test.use({ viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true });

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

type Summary = { id: string; laundry: string | null; away: unknown };
const pieces = async (page: Page) => ((await (await page.request.get('/api/items')).json()).items as Summary[]);

/** The closet drawn with its whole list: "49 items" over it (no "0 of 49"), and every tile. */
async function allShown(page: Page) {
  const count = page.getByTestId('item-count');
  const all = (await pieces(page)).length;
  await expect(count).toHaveText(`${all} items`);
  await expect(page.getByTestId('tile')).toHaveCount(all);
}

test('the laundry view left empty by All clean holds while you are in it, and the closet opens on all your clothes after', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const before = (await pieces(page)).filter((p) => p.laundry === 'laundry');
  expect(before.length).toBeGreaterThan(1);

  await page.getByTestId('in-laundry').click();
  const notice = page.getByTestId('laundry-notice');
  await notice.getByRole('button', { name: 'All clean' }).click();
  await expect(notice).toContainText(`You marked ${before.length} pieces clean.`);
  // in the view nothing changes under you: the line with Undo stays once the closet has read its list again
  await page.waitForLoadState('networkidle');
  await expect(notice.getByRole('button', { name: 'Undo' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Remove filter: In the laundry' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('laundry-after-all-clean.png') });

  // another place, then the Closet tab: all your clothes, no laundry chip, no "Nothing in the laundry"
  await page.locator('nav.tabbar').getByRole('link', { name: 'Today' }).click();
  await expect(page.locator('#today-title')).toBeVisible();
  await page.locator('nav.tabbar').getByRole('link', { name: 'Closet' }).click();
  await allShown(page);
  await expect(page.getByRole('button', { name: 'Remove filter: In the laundry' })).toHaveCount(0);
  await expect(page.getByTestId('closet-status')).not.toContainText('Nothing in the laundry');
  await expect(page.getByText('Your laundry is empty.')).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);

  // the same from an address that asks for the laundry, keeping the search
  await page.goto('/?q=shirt&laundry=laundry');
  await expect(page).toHaveURL(/\/\?q=shirt$/);
  await expect(page.getByRole('searchbox', { name: 'Search your clothes' })).toHaveValue('shirt');
  await expect(page.getByTestId('item-count')).toHaveText(/^\d+ of \d+$/);
  await expect(page.getByRole('button', { name: 'Remove filter: In the laundry' })).toHaveCount(0);
  await expect(page.getByText('Your laundry is empty.')).toHaveCount(0);

  // the laundry as it was, for the tests after this one
  for (const p of before) {
    expect((await page.request.post(`/api/items/${p.id}/laundry`, { data: { state: 'laundry' } })).ok()).toBe(true);
  }
});

test('the "Needs a check" view with nothing left to check is not where the closet opens, and the line never says "0 to check"', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const queued = (await (await page.request.get('/api/review')).json()).items as { id: string; fields: { field: string }[] }[];
  expect(queued.length).toBeGreaterThan(0);

  await page.getByTestId('to-check').click();
  await expect(page.getByRole('button', { name: 'Remove filter: Needs a check' })).toBeVisible();
  await expect(page.getByTestId('tile')).toHaveCount(queued.length);

  // every check answered (as the review's "That's right" does), then the closet opened again
  for (const q of queued) {
    expect((await page.request.post(`/api/items/${q.id}/confirm`, { data: { fields: q.fields.map((f) => f.field) } })).ok()).toBe(true);
  }
  expect((await (await page.request.get('/api/review')).json()).count).toBe(0);
  // opened again from its plain address: the view kept for the tab, and the count to check read after the list
  await page.goto('/');
  await allShown(page);
  await expect(page.getByRole('button', { name: 'Remove filter: Needs a check' })).toHaveCount(0);
  await expect(page.getByTestId('closet-status')).not.toContainText('0 to check');
  await expect(page.getByText('Nothing needs a check now.')).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);
  await page.screenshot({ path: test.info().outputPath('closet-after-the-last-check.png') });

  // and a reload of the view's own address
  await page.goto('/?check=1');
  await allShown(page);
  await expect(page).toHaveURL(/\/$/);
});

test('a part of the closet\'s line shows those pieces: the search and the kind are cleared for that tap', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const inLaundry = (await pieces(page)).filter((p) => p.laundry === 'laundry' && !p.away).length;
  expect(inLaundry).toBeGreaterThan(0);
  const count = page.getByTestId('item-count');
  await expect(count).toHaveText(/^\d+ items$/);

  // a search on, then the laundry's part
  await page.getByRole('searchbox', { name: 'Search your clothes' }).fill('tee');
  await expect(count).toHaveText(/^\d+ of \d+$/);
  await page.getByTestId('in-laundry').click();
  await expect(page.getByRole('searchbox', { name: 'Search your clothes' })).toHaveValue('');
  await expect(page.getByTestId('laundry-mark')).toHaveCount(inLaundry);
  await expect(page.getByText('Nothing matches')).toHaveCount(0);
  await page.getByRole('button', { name: 'Remove filter: In the laundry' }).click();

  // a kind chosen in the filter, then the laundry's part
  const filter = page.getByRole('button', { name: /^Filter/ });
  await filter.click();
  const sheet = page.getByTestId('filter-sheet');
  await sheet.getByRole('group', { name: 'What it is' }).getByRole('button', { name: 'Trousers & shorts' }).click();
  await sheet.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('button', { name: 'Remove filter: Trousers & shorts' })).toBeVisible();
  await page.getByTestId('in-laundry').click();
  await expect(page.getByRole('button', { name: 'Remove filter: Trousers & shorts' })).toHaveCount(0);
  await expect(page.getByTestId('laundry-mark')).toHaveCount(inLaundry);

  // tapping it again leaves the view, and nothing else
  await page.getByTestId('in-laundry').click();
  await expect(page.getByRole('button', { name: 'Remove filter: In the laundry' })).toHaveCount(0);
});

for (const width of [375, 320]) {
  test(`the Filter sheet keeps its title and Done at its top while its body scrolls, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 667 });
    await goToCloset(page);
    await useProfile(page, 'demo');
    await page.getByRole('button', { name: /^Filter/ }).click();
    const sheet = page.getByTestId('filter-sheet');
    await sheet.getByRole('group', { name: 'What it is' }).getByRole('button', { name: 'Trousers & shorts' }).click();
    await expect(sheet.getByRole('group', { name: 'Which Trousers & shorts' })).toBeVisible();
    // the sheet is longer than it can show
    expect(await sheet.evaluate((el) => el.scrollHeight > el.clientHeight + 40)).toBe(true);
    const head = sheet.locator('.sheet-head');
    const before = (await head.boundingBox())!;

    await sheet.evaluate((el) => { el.scrollTop = el.scrollHeight; });
    await expect(sheet.getByRole('group', { name: 'Filter by laundry' })).toBeInViewport();
    const box = (await sheet.boundingBox())!;
    const now = (await head.boundingBox())!;
    expect(Math.abs(now.y - before.y)).toBeLessThan(1);
    expect(now.y).toBeGreaterThanOrEqual(box.y);
    // Done is where it was and takes the tap: nothing of the body is drawn over it
    const done = sheet.getByRole('button', { name: 'Done' });
    const at = (await done.boundingBox())!;
    const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('button')?.textContent ?? null,
      [at.x + at.width / 2, at.y + at.height / 2]);
    expect(hit).toBe('Done');
    await page.screenshot({ path: test.info().outputPath(`filter-sheet-scrolled-${width}.png`) });
    await done.click();
    await expect(sheet).toHaveCount(0);
  });
}

// On a computer the Filter is a popover under its button. Where it fits, it opens exactly where its own styles put it
// (Sheet moves a popover only when part of it would be off the screen); at 1,024 × 700 it did not fit (it ran 80px past
// the right edge, its Done cut off) and now opens whole, beside the button (26 November).
test('on a computer the Filter opens under its button where it fits, and whole on the screen where it did not', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  const button = page.getByRole('button', { name: /^Filter/ });
  await button.click();
  const sheet = page.getByTestId('filter-sheet');
  await expect(sheet).toBeVisible();
  // not moved: no place of its own, its top just under the button, its left edge at the button's
  expect(await sheet.evaluate((el) => [el.style.top, el.style.left, el.style.maxHeight])).toEqual(['', '', '']);
  const b = (await button.boundingBox())!;
  const s = (await sheet.boundingBox())!;
  expect(Math.round(s.y - (b.y + b.height))).toBe(8);
  expect(Math.abs(s.x - b.x)).toBeLessThan(2);
  await expect(sheet).toBeInViewport({ ratio: 1 });
  await sheet.getByRole('button', { name: 'Done' }).click();

  await page.setViewportSize({ width: 1024, height: 700 });
  await button.click();
  await expect(sheet).toBeInViewport({ ratio: 1 });
  await expect(sheet.getByRole('button', { name: 'Done' })).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: test.info().outputPath('filter-1024.png') });
});
