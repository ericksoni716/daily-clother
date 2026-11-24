import type { Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test, useProfile } from './fixtures';

// From a piece to an outfit, on a phone: a piece's page opens Today built around it (and Back comes back to the piece),
// says in one line when it cannot, and lists the outfits the piece was worn in, the same outfit once, the first three
// on the page and the rest in a sheet, each with "Wear this again" and a way to remove a wear.

const PHONE = { width: 375, height: 740 };

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

interface Summary { id: string; name: string; category: string }

async function openDemo(page: Page): Promise<Map<string, Summary>> {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  // the demo's weather is never looked up in the browser tests: a mild, dry day
  await page.route('**/api/outfits/today', async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: { low_c: 9, high_c: 16, rain: false, ...body } }) });
  });
  const items = (await (await page.request.get('/api/items?status=active')).json()) as Summary[] | { items: Summary[] };
  const list = Array.isArray(items) ? items : items.items;
  return new Map(list.map((i) => [i.name, i]));
}

const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

test('a piece opens Today built around it, in place of the piece built around before, and Back comes back to it', async ({ page }) => {
  const byName = await openDemo(page);
  const flannel = byName.get('Plaid flannel shirt')!;
  const oxford = byName.get('Blue oxford shirt')!;

  await page.goto(`/item/${flannel.id}`);
  const around = page.getByTestId('build-around');
  await expect(around.getByRole('button', { name: 'Build an outfit around it' })).toBeVisible();
  await around.getByRole('button', { name: 'Build an outfit around it' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('button', { name: 'Stop building around Plaid flannel shirt' })).toBeVisible();
  await expect(page.getByTestId('current-outfit')).toBeVisible();

  // a piece left out on Today stays left out when another piece is built around from its page
  const piece = page.getByTestId('current-outfit').getByRole('button', { name: /^Choices for (?!Plaid flannel shirt)/ }).last();
  await piece.click();
  await page.getByTestId('piece-sheet').getByRole('button', { name: 'Not this piece' }).click();
  const without = page.getByRole('button', { name: /^Without .*, put it back$/ });
  await expect(without).toHaveCount(1);
  const leftOut = await without.getAttribute('aria-label');

  await page.goto(`/item/${oxford.id}`);
  await page.getByTestId('build-around').getByRole('button', { name: 'Build an outfit around it' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('button', { name: 'Stop building around Blue oxford shirt' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop building around Plaid flannel shirt' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: leftOut! })).toBeVisible();

  // the browser's Back returns to the piece
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/item/${oxford.id}$`));
  await expect(page.getByTestId('build-around')).toBeVisible();

  // from a piece opened on Today itself (Today stays open under it), and Back again
  await page.goto('/today');
  // its shoes, which never go in the laundry
  const links = page.getByTestId('recent-outfit').first().locator('a.worn-pic');
  await expect(links.first()).toBeVisible();
  const titles = await links.evaluateAll((all) => all.map((a) => a.getAttribute('title') ?? ''));
  const name = titles.find((t) => ['sneakers', 'boots', 'dress_shoes'].includes(byName.get(t)?.category ?? ''))!;
  const link = links.and(page.locator(`[title="${name}"]`));
  await link.click();
  await expect(page).toHaveURL(/\/today\/item\//);
  const at = page.url();
  await page.getByTestId('build-around').getByRole('button', { name: 'Build an outfit around it' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('button', { name: `Stop building around ${name}` })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(at);
});

test('a piece Today cannot build around says so in one line, and a tie has no button at all', async ({ page }) => {
  const byName = await openDemo(page);
  const tee = byName.get('White tee')!;
  expect((await page.request.post(`/api/items/${tee.id}/laundry`, { data: { state: 'laundry' } })).ok()).toBe(true);
  await page.goto(`/item/${tee.id}`);
  await expect(page.getByTestId('build-around')).toHaveText("Once it's clean, Today can build an outfit around it.");
  await expect(page.getByRole('button', { name: 'Build an outfit around it' })).toHaveCount(0);
  await page.getByRole('button', { name: "It's clean" }).click();
  await expect(page.getByRole('button', { name: 'Build an outfit around it' })).toBeVisible();

  await page.goto(`/item/${byName.get('Burgundy striped tie')!.id}`);
  await expect(page.getByTestId('wear-summary')).toBeVisible();
  await expect(page.getByTestId('build-around')).toHaveCount(0);
});

test('the outfits a piece was worn in: the same outfit once, three on the page, the rest in a sheet, Wear this again', async ({ page }) => {
  const byName = await openDemo(page);
  // a top the demo never wore, so the rows are the ones made here
  let piece: Summary | undefined;
  for (const name of ['Striped sweater', 'Marl turtleneck', 'Oatmeal henley', 'Floral camp shirt', 'Madras plaid shirt', 'Paper plane tee']) {
    const got = (await (await page.request.get(`/api/items/${byName.get(name)!.id}`)).json()) as { worn_in: unknown[] };
    if (!got.worn_in.length) {
      piece = byName.get(name);
      break;
    }
  }
  if (!piece) throw new Error('every top in the demo closet has been worn');
  const outfit = [piece.id, byName.get('Stone pleated chinos')!.id, byName.get('Brown boots')!.id];
  for (const n of [9, 4]) {   // the same outfit on two days
    expect((await page.request.post('/api/outfits/worn', { data: { item_ids: outfit, worn_on: daysAgo(n) } })).ok()).toBe(true);
  }
  const other = [piece.id, byName.get('Dark indigo jeans')!.id, byName.get('White leather sneakers')!.id];
  expect((await page.request.post('/api/outfits/worn', { data: { item_ids: other, worn_on: daysAgo(6) } })).ok()).toBe(true);
  for (const n of [2, 11]) {   // and twice on its own
    expect((await page.request.post(`/api/items/${piece.id}/wears`, { data: { worn_on: daysAgo(n) } })).ok()).toBe(true);
  }
  const rows = ((await (await page.request.get(`/api/items/${piece.id}`)).json()) as { worn_in: unknown[] }).worn_in;
  expect(rows.length).toBeGreaterThan(3);

  await page.goto(`/item/${piece.id}`);
  const list = page.getByTestId('worn-in');
  await expect(list.getByTestId('worn-in-row')).toHaveCount(3);
  await expect(list.getByTestId('worn-in-row').filter({ hasText: /^2 times, last on / })).toHaveCount(1);
  await expect(list.getByTestId('worn-in-row').nth(1).getByRole('listitem')).toHaveCount(3);   // the outfit's pieces
  expect(await axeViolations(page)).toEqual([]);

  // the rest open in a sheet; the page under it holds still
  const all = list.getByRole('button', { name: `All ${rows.length} outfits and wears` });
  await all.scrollIntoViewIfNeeded();
  const top = (await list.boundingBox())!.y;
  await all.click();
  const sheet = page.getByTestId('worn-in-all');
  await expect(sheet.getByTestId('worn-in-row')).toHaveCount(rows.length);
  expect((await list.boundingBox())!.y).toBe(top);
  await sheet.getByRole('button', { name: 'Done' }).click();

  // a wear is removed from a row's choices
  const plain = list.getByTestId('worn-in-row').first();
  const words = (await plain.locator('.worn-in-when').textContent())!;
  await plain.getByRole('button', { name: `More for the wear: ${words}` }).click();
  await page.getByTestId('worn-in-menu').getByRole('button', { name: `Remove the wear: ${words}` }).click();
  await expect(page.locator('.toast', { hasText: 'Wear removed' })).toBeVisible();
  await expect(list.getByRole('button', { name: `More for the wear: ${words}` })).toHaveCount(0);

  // an outfit's sheet: Wear this again, then its days as plain rows, newest first, each with a quiet Remove
  await list.getByTestId('worn-in-row').filter({ hasText: /^2 times/ }).getByRole('button', { name: /^More for the outfit/ }).click();
  const menu = page.getByTestId('worn-in-menu');
  await expect(menu.getByRole('heading', { name: 'The days you wore it' })).toBeVisible();
  await expect(menu.getByTestId('worn-in-day')).toHaveCount(2);
  await expect(menu.getByRole('button', { name: /^Remove the wear: / })).toHaveCount(2);
  await expect(menu.locator('.btn-danger-quiet')).toHaveCount(0);
  for (const remove of await menu.getByRole('button', { name: /^Remove the wear: / }).all()) {
    expect((await remove.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await menu.getByRole('button', { name: 'Wear this again' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole('group', { name: 'Wearing again' })).toContainText('Starting from an outfit you wore');
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/item/${piece.id}$`));
});

test('a row of "When you wore it" opens the outfit wherever it is tapped, its pictures included, with 44px to tap', async ({ page }) => {
  const byName = await openDemo(page);
  const piece = byName.get('Navy polo')!;
  const outfit = [piece.id, byName.get('Stone pleated chinos')!.id, byName.get('Brown boots')!.id];
  expect((await page.request.post('/api/outfits/worn', { data: { item_ids: outfit, worn_on: daysAgo(3) } })).ok()).toBe(true);
  await page.goto(`/item/${piece.id}`);
  const row = page.getByTestId('worn-in').getByTestId('worn-in-row').filter({ has: page.locator('.worn-pics') }).first();
  await expect(row).toBeVisible();
  await row.scrollIntoViewIfNeeded();
  // what takes a tap on each picture, and on the row's empty part beside them, is the button that opens the outfit
  const takes = (x: number, y: number) => page.evaluate(([px, py]) => {
    const el = document.elementFromPoint(px, py);
    return { link: !!el?.closest('a'), button: el?.closest('button')?.getAttribute('aria-label') ?? null };
  }, [x, y]);
  for (const pic of await row.locator('.worn-pic').all()) {
    const box = (await pic.boundingBox())!;
    expect(await takes(box.x + box.width / 2, box.y + box.height / 2)).toEqual({ link: false, button: expect.stringMatching(/^More for the outfit/) });
  }
  const rowBox = (await row.boundingBox())!;
  const pics = (await row.locator('.worn-pics').boundingBox())!;
  expect(await takes(rowBox.x + rowBox.width - 8, pics.y + pics.height / 2)).toEqual({ link: false, button: expect.stringMatching(/^More for the outfit/) });
  expect(rowBox.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({ path: test.info().outputPath('when-you-wore-it.png') });
  // a tap on a picture opens the outfit's sheet
  const pic = (await row.locator('.worn-pic').first().boundingBox())!;
  await page.mouse.click(pic.x + pic.width / 2, pic.y + pic.height / 2);
  await expect(page.getByTestId('worn-in-menu')).toBeVisible();
  await page.getByTestId('worn-in-menu').getByRole('button', { name: 'Done' }).click();
});
