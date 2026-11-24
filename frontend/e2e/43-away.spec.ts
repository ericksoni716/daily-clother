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

  // back, one tap, and Undo puts it away again (the closet comes back still showing what is away: its filters are kept)
  await page.goto('/');
  await expect(page.getByTestId('away')).toHaveText('1 away');
  await expect(page.getByRole('button', { name: 'Remove filter: Away' })).toBeVisible();
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

  // nothing is away now, so the closet, left showing what is away, opens on everything: once its list is drawn (the
  // count over it, and the tiles), no word about away, no Away filter, and no `away=1` left in the address
  await page.goto('/');
  const count = page.getByTestId('item-count');
  await expect(count).toHaveText(/^\d+ items?$/);
  const all = Number((await count.textContent())!.split(' ')[0]);
  await expect(page.getByTestId('tile')).toHaveCount(all);
  await expect(page.getByTestId('away')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Remove filter: Away' })).toHaveCount(0);
  await expect(page.getByText('Everything is in your closet.')).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);

  // the same when the address asks for what is away: the Away view goes, the search stays as it was
  await page.goto('/?q=shirt&away=1');
  await expect(page).toHaveURL(/\/\?q=shirt$/);
  await expect(page.getByRole('searchbox', { name: 'Search your clothes' })).toHaveValue('shirt');
  await expect(count).toBeVisible();
  await expect(page.getByTestId('away')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Remove filter: Away' })).toHaveCount(0);
  await expect(page.getByText('Everything is in your closet.')).toHaveCount(0);
});

/** Two pieces of the demo closet sent away, one with a long name; their ids, soonest first. The first is past its day,
 * so its row says when it was expected on two lines, and coming back makes its sentence shorter. */
async function twoAway(page: Page): Promise<string[]> {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const items = ((await (await page.request.get('/api/items')).json()).items as { id: string; name: string; away: unknown }[]);
  for (const it of items.filter((i) => i.away)) expect((await page.request.post(`/api/items/${it.id}/back`)).ok()).toBe(true);
  const a = items.find((i) => i.name === 'Navy bomber jacket')!;
  const b = items.find((i) => i.name === 'Black overcoat' || i.name === 'Heavyweight wool overcoat')!;   // named so by a test before
  expect((await page.request.put(`/api/items/${a.id}/away`, { data: { place: 'lent', since: '2020-01-01', until: '2020-01-04' } })).ok()).toBe(true);
  expect((await page.request.put(`/api/items/${b.id}/away`, { data: { place: 'cleaner', until: '2099-01-09' } })).ok()).toBe(true);
  expect((await page.request.patch(`/api/items/${b.id}`, { data: { name: 'Heavyweight wool overcoat' } })).ok()).toBe(true);
  return [a.id, b.id];
}

test('"It\'s back" changes its row in place: no row moves, so a second tap lands on the same piece', async ({ page }) => {
  const [first, second] = await twoAway(page);
  await page.goto('/');
  await page.getByTestId('away').click();
  const rows = page.getByTestId('away-row');
  await expect(rows).toHaveCount(2);
  const button = (n: number) => rows.nth(n).getByRole('button').first();
  const was = [(await rows.nth(0).boundingBox())!, (await rows.nth(1).boundingBox())!];
  const secondButton = (await button(1).boundingBox())!;
  await expect(rows.nth(0)).toContainText('Navy bomber jacket');

  await button(0).click();
  await expect(rows.nth(0)).toContainText('Back in your closet');
  await expect(rows.nth(0)).toContainText('Navy bomber jacket');
  await expect(rows.nth(1)).toContainText("At the cleaner's");
  const moved = (a: number, b: number) => Math.abs(a - b);
  expect(moved((await rows.nth(0).boundingBox())!.y, was[0].y)).toBeLessThan(1);
  expect(moved((await rows.nth(0).boundingBox())!.height, was[0].height)).toBeLessThan(1);
  expect(moved((await rows.nth(1).boundingBox())!.y, was[1].y)).toBeLessThan(1);
  expect(moved((await button(1).boundingBox())!.y, secondButton.y)).toBeLessThan(1);
  await page.screenshot({ path: test.info().outputPath('away-its-back-in-place.png') });
  // Undo, in the same place, puts it away again; the other piece was never touched
  await rows.nth(0).getByRole('button', { name: /^Undo/ }).click();
  await expect(rows.nth(0)).toContainText('Lent out');
  expect(((await (await page.request.get(`/api/items/${first}`)).json()).away)).not.toBeNull();
  expect(((await (await page.request.get(`/api/items/${second}`)).json()).away)).not.toBeNull();

  // brought back again and the view left: the order is made again when you come back to it
  await button(0).click();
  await expect(rows.nth(0)).toContainText('Back in your closet');
  await page.getByRole('button', { name: 'Remove filter: Away' }).click();
  await page.getByTestId('away').click();
  await expect(rows).toHaveCount(1);
  await expect(rows.nth(0)).toContainText("At the cleaner's");
});

test('in the Away view a long name takes two lines, and the whole row opens the piece', async ({ page }) => {
  const [, long] = await twoAway(page);
  await page.goto('/');
  await page.getByTestId('away').click();
  const row = page.getByTestId('away-row').filter({ hasText: 'Heavyweight' });
  const name = row.locator('.away-name');
  await expect(name).toBeVisible();
  // the name is whole on two lines, not cut on one
  const lines = await name.evaluate((el) => ({ cut: el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1,
    lines: Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)) }));
  expect(lines.cut).toBe(false);
  expect(lines.lines).toBe(2);
  // a tap anywhere on the row but its button opens the piece: on the line saying where it is, say
  const where = (await row.locator('.away-where').boundingBox())!;
  const href = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('a')?.getAttribute('href') ?? null,
    [where.x + 4, where.y + where.height / 2]);
  expect(href).toBe(`/item/${long}`);
  // the button keeps its own tap, over the row's, edge to edge
  const back = (await row.getByRole('button', { name: /^It's back/ }).boundingBox())!;
  for (const y of [back.y + 1, back.y + back.height / 2, back.y + back.height - 1]) {
    const hit = await page.evaluate(([px, py]) => document.elementFromPoint(px, py)?.closest('button')?.textContent ?? null, [back.x + back.width / 2, y]);
    expect(hit).toBe("It's back");
  }
  expect(await sideways(page)).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('away-long-name.png') });
});

test('a piece that is away: where it is leads, the laundry gives way, and Wore it today stays', async ({ page }) => {
  const [, coat] = await twoAway(page);
  await page.goto(`/item/${coat}`);
  const card = page.getByRole('region', { name: 'Wearing and washing' });
  const where = card.getByTestId('where-line');
  await expect(where).toHaveText("At the cleaner's until Friday 9 Jan 2099");
  await expect(card.getByTestId('laundry-state')).toHaveCount(0);
  await expect(card.getByRole('button', { name: 'Put in the laundry' })).toHaveCount(0);
  await expect(card.getByRole('button', { name: "It's clean" })).toHaveCount(0);
  const wore = card.getByRole('button', { name: 'Wore it today' });
  await expect(wore).toBeVisible();
  // where it is comes first in the card
  expect((await where.boundingBox())!.y).toBeLessThan((await card.getByTestId('wear-summary').boundingBox())!.y);
  expect(await sideways(page)).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('item-away.png') });

  // back home, the laundry's line and button are there again
  await card.getByRole('button', { name: "It's back" }).click();
  await expect(card.getByTestId('laundry-state')).toBeVisible();
  await expect(card.getByRole('button', { name: 'Put in the laundry' })).toBeVisible();
});
