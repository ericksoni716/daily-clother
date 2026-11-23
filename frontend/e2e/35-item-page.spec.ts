import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, goToCloset, openFold, PHOTOS, test, useProfile } from './fixtures';
import { startBackend, type Backend } from './server';

// The item page in the owner's order (22 November): the picture and the name, then what it is, its brand and its
// price, then its state, then how it looks, the photos last. And the review, which now offers every new piece once
// for those same essentials.

const PHONE = { width: 375, height: 667 };

/** The demo closet's id for an item (tools/make_demo.py keeps them in items.json). */
function demoId(name: string): string {
  const data = JSON.parse(readFileSync(resolve(import.meta.dirname, '../../backend/closet/demo_data/items.json'), 'utf8'));
  return data.items.find((i: { name: string }) => i.name === name).id;
}

/** How far down the page each part starts, in the order given; fails on a part that is missing. */
async function tops(parts: Locator[]): Promise<number[]> {
  const out: number[] = [];
  for (const part of parts) {
    await expect(part).toBeAttached();
    const box = await part.boundingBox();
    expect(box).not.toBeNull();
    out.push(box!.y);
  }
  return out;
}

const increasing = (ys: number[]) => ys.every((y, i) => i === 0 || y > ys[i - 1]);

/** The parts of the item page, top to bottom, as the owner asked for them. */
function parts(page: Page, shoe: boolean): Locator[] {
  const detail = page.locator('article.detail');
  const fold = (title: string | RegExp) => detail.locator('details.more').filter({ has: page.locator('summary', { hasText: title }) });
  return [
    detail.locator('.detail-picture').first(),
    detail.getByRole('textbox', { name: 'Name' }),
    detail.getByTestId('essentials').getByTestId('what-is-it'),
    detail.getByTestId('essentials').getByRole('textbox', { name: 'Brand' }),
    detail.getByRole('region', { name: 'Wearing and washing' }),
    detail.getByRole('region', { name: 'About it' }),
    detail.getByTestId('how-it-looks').getByTestId('look-line'),
    ...(shoe ? [detail.getByTestId('how-it-looks').getByTestId('shoe-drawn')] : []),
    fold('Details'),
    fold('Size, material and more'),
    ...(shoe ? [detail.getByTestId('shoe-photos')] : []),
    fold('History'),
    fold(/delete/),
  ];
}

test.describe('the item page in the demo closet', () => {
  test.afterEach(async ({ page }) => {
    await page.request.post('/api/profile', { data: { profile: 'main' } });
  });

  for (const [what, name, shoe] of [['a garment', 'Navy polo', false], ['a shoe', 'White leather sneakers', true]] as const) {
    for (const [where, viewport] of [['a phone', PHONE], ['a computer', { width: 1440, height: 900 }]] as const) {
      test(`${what} reads in the owner's order on ${where}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await goToCloset(page);
        await useProfile(page, 'demo');
        await page.goto(`/item/${demoId(name)}`);
        await expect(page.getByRole('textbox', { name: 'Name' })).toHaveValue(name);
        expect(increasing(await tops(parts(page, shoe)))).toBe(true);
        expect(await sideways(page)).toEqual([]);
        // the brand and the price are no longer behind a fold: no other fold holds them
        await expect(page.locator('details.more').getByRole('textbox', { name: 'Brand' })).toHaveCount(0);
        await expect(page.locator('details.more').getByRole('textbox', { name: 'Price' })).toHaveCount(0);
      });
    }
  }

  test('the essentials are changed in place, with the keyboard, and kept', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await goToCloset(page);
    await useProfile(page, 'demo');
    const id = demoId('Black tee');
    await page.goto(`/item/${id}`);
    const essentials = page.getByTestId('essentials');
    const name = page.getByRole('textbox', { name: 'Name' });
    await expect(name).toHaveValue('Black tee');

    // the name, then Tab to what it is, Tab to the brand, Tab to the price, Enter: each saves as you leave it
    await name.fill('Everyday black tee');
    await page.keyboard.press('Tab');
    await expect(essentials.getByTestId('what-is-it')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(essentials.getByRole('textbox', { name: 'Brand' })).toBeFocused();
    await page.keyboard.type('Made-up Mills');
    await page.keyboard.press('Tab');
    await expect(essentials.getByRole('textbox', { name: 'Price' })).toBeFocused();
    await page.keyboard.type('24.5');
    await page.keyboard.press('Enter');
    const item = async () => (await page.request.get(`/api/items/${id}`)).json();
    await expect.poll(async () => {
      const got = await item();
      return [got.name, got.brand, got.price_cents];
    }).toEqual(['Everyday black tee', 'Made-up Mills', 2450]);
    expect((await item()).checked_at).toBeTruthy();   // it counts as checked, so the review does not offer it

    // a price that is not a price is said plainly under the box, which keeps what you typed, and nothing is saved
    const price = essentials.getByRole('textbox', { name: 'Price' });
    await price.fill('about twenty');
    await price.press('Enter');
    await expect(essentials.getByTestId('price-wrong')).toHaveText('Type the price as a number, like 45 or 45.50.');
    await expect(price).toHaveValue('about twenty');
    expect((await item()).price_cents).toBe(2450);
    // a decimal comma, as a phone set to such a region types it, is the same price (it was saved a hundred times
    // too high, as 2,450.00)
    await price.fill('24,95');
    await price.press('Enter');
    await expect(essentials.getByTestId('price-wrong')).toHaveCount(0);
    await expect.poll(async () => (await item()).price_cents).toBe(2495);
    await price.fill('24.50');
    await price.press('Enter');
    await expect.poll(async () => (await item()).price_cents).toBe(2450);

    // what it is: the row opens the kinds in a sheet; choosing one saves it at once as your word
    await essentials.getByTestId('what-is-it').click();
    const picker = page.getByTestId('kind-picker');
    await picker.getByRole('searchbox').fill('henley');
    await picker.getByRole('button', { name: 'Henley' }).first().click();
    await expect(picker).toHaveCount(0);
    await expect(essentials.getByTestId('what-is-it')).toContainText('Henley');
    await expect(essentials.getByTestId('what-is-it')).toContainText('Set by you');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);

    // all of it is still there after a reload
    await page.reload();
    await expect(name).toHaveValue('Everyday black tee');
    await expect(essentials.getByRole('textbox', { name: 'Brand' })).toHaveValue('Made-up Mills');
    await expect(essentials.getByRole('textbox', { name: 'Price' })).toHaveValue('24.50');
    await expect(essentials.getByTestId('what-is-it')).toContainText('Henley');
  });

  test('a change is said to be kept beside it, quietly, and no toast covers what you tap next', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await goToCloset(page);
    await useProfile(page, 'demo');
    const id = demoId('Grey hoodie');
    await page.goto(`/item/${id}`);
    const essentials = page.getByTestId('essentials');
    const brand = essentials.getByRole('textbox', { name: 'Brand' });
    await expect(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Grey hoodie');

    // the brand: "Saved" beside its box, and no toast (the review of 23 November: every change raised its own)
    await brand.fill('Made-up Knits');
    await brand.press('Enter');
    await expect(page.getByTestId('kept-brand')).toHaveText('Saved');
    await expect(page.locator('.toast')).toHaveCount(0);
    // a row of Details: the word sits in the row that changed
    const fold = await openFold(page, 'Details');
    await fold.getByRole('button', { name: /^Season:/ }).click();
    await page.getByRole('dialog', { name: 'Season' }).getByRole('button', { name: 'All year' }).click();
    await expect(page.getByTestId('kept-season')).toHaveText('Saved');
    await expect(page.locator('.toast')).toHaveCount(0);
    // it goes quiet again by itself, keeping its place
    await expect(page.getByTestId('kept-brand')).toHaveText('', { timeout: 6000 });
    expect(await sideways(page)).toEqual([]);

    // what went wrong is still a toast: offline the page says it cannot change, and a refused save says why
    await page.route(`**/api/items/${id}`, (route) => route.request().method() === 'PATCH'
      ? route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'That brand cannot be kept.' }) })
      : route.fallback());
    await brand.fill('Another made-up brand');
    await brand.press('Enter');
    await expect(page.locator('.toast', { hasText: 'That brand cannot be kept.' })).toBeVisible();
    await expect(page.getByTestId('kept-brand')).toHaveText("Didn't save");
    await page.unroute(`**/api/items/${id}`);
  });

  test("Fix the details says a failed read of its details in the app's words, with Try again", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await goToCloset(page);
    await useProfile(page, 'demo');
    const id = demoId('Grey hoodie');
    let fail = true;
    await page.route(`**/api/items/${id}/details**`, (route) => (fail && route.request().method() === 'GET'
      ? route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal Server Error"}' })
      : route.fallback()));
    await page.goto(`/item/${id}`);
    await page.getByRole('button', { name: 'Something wrong? Change the details' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByTestId('details-failed')).toContainText("Couldn't load the details.", { timeout: 30_000 });
    await expect(sheet).not.toContainText('Internal Server Error');
    fail = false;
    await sheet.getByRole('button', { name: 'Try again' }).click();
    await expect(sheet.getByTestId('details-failed')).toHaveCount(0);
    // a detail's own choices: the same, under the detail, not a toast
    fail = true;
    await sheet.locator('.fix-detail').first().click();
    await expect(sheet.getByTestId('choices-failed')).toContainText("Couldn't load the choices", { timeout: 30_000 });
    await expect(page.locator('.toast')).toHaveCount(0);
    fail = false;
    await sheet.getByTestId('choices-failed').getByRole('button', { name: 'Try again' }).click();
    await expect(sheet.getByTestId('choices-failed')).toHaveCount(0);
    await expect(sheet.locator('.fix-choices')).toBeVisible();
    await page.unroute(`**/api/items/${id}/details**`);
  });

  test("a colour's shades are offered under it, and the shade chosen is kept with its colour", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await goToCloset(page);
    await useProfile(page, 'demo');
    const id = demoId('Burgundy cable sweater');
    await page.goto(`/item/${id}`);
    await expect(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Burgundy cable sweater');
    const fold = await openFold(page, 'Details');
    const row = fold.getByRole('button', { name: /^Colour:/ });
    await expect(row).toHaveAttribute('aria-label', 'Colour: Burgundy');
    await row.click();
    const sheet = page.getByRole('dialog', { name: 'Colour' });

    // under the colours, the shades of the item's colour, the one it is in chosen
    const burgundies = sheet.getByRole('group', { name: 'Shades of burgundy' });
    await expect(burgundies.getByRole('button')).toHaveText(['Oxblood', 'Burgundy']);
    await expect(burgundies.getByRole('button', { name: 'Burgundy' })).toHaveAttribute('aria-pressed', 'true');

    // choosing another colour keeps the sheet open, on that colour's shades
    await sheet.getByRole('group', { name: 'Colour' }).getByRole('button', { name: 'Green', exact: true }).click();
    const greens = sheet.getByRole('group', { name: 'Shades of green' });
    await expect(greens.getByRole('button', { name: 'Sage' })).toBeVisible();
    await expect(burgundies).toHaveCount(0);
    // the colour alone claims no shade: none of green's is lit, and the row says the colour only (P15)
    await expect(greens.getByRole('button', { pressed: true })).toHaveCount(0);
    await expect(row).toHaveAttribute('aria-label', 'Colour: Green');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);

    // choosing a shade saves it with its colour and closes the sheet
    await greens.getByRole('button', { name: 'Sage' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(row).toHaveAttribute('aria-label', 'Colour: Green (sage)');
    const item = async () => (await page.request.get(`/api/items/${id}`)).json();
    await expect.poll(async () => {
      const got = await item();
      return [got.color, got.shade, got.color_hex, got.source.color];
    }).toEqual(['green', 'sage', '#a3ad8f', 'user']);

    // the line under the name says it too, after a reload as well
    await page.reload();
    await expect(page.getByTestId('look-line')).toContainText('Green (sage)');
  });
});

// Its own backend, with stand-ins for the model and for Claude: a photo added is described as a navy polo.
test.describe('with a stand-in for Claude', () => {
  let backend: Backend;
  test.use({ viewport: PHONE, hasTouch: true, isMobile: true });

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a piece just added is checked straight after Add, one at a time', async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto(backend.url + '/');
    await expect(page.locator('#closet-title')).toBeVisible();
    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);

    // once Claude has described it, Add offers to check it
    const check = page.getByTestId('check-added');
    await expect(check).toBeVisible({ timeout: 60_000 });
    await expect(check).toHaveText('Check them one at a time');
    await check.click();
    await expect(page).toHaveURL(/\/review$/);

    // the card: the picture, the name Claude gave, what Claude thinks it is, and the brand and price boxes
    const card = page.getByTestId('review-card');
    await expect(card.getByRole('heading', { name: 'Navy polo' })).toBeVisible();
    const name = card.getByRole('textbox', { name: 'Name' });
    await expect(name).toHaveValue('Navy polo');
    await expect(card.getByTestId('what-is-it')).toBeVisible();
    await expect(card.getByRole('textbox', { name: 'Brand' })).toHaveValue('');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('quick-pass.png'), fullPage: true });

    const id = (await (await page.request.get(`${backend.url}/api/review`)).json()).items[0].id as string;
    const item = async () => (await page.request.get(`${backend.url}/api/items/${id}`)).json();

    // a price that is not a price: said plainly, nothing sent, the card stays
    await name.fill('Weekend polo');
    await card.getByRole('textbox', { name: 'Brand' }).fill('Made-up Mills');
    await card.getByRole('textbox', { name: 'Price' }).fill('lots');
    await card.getByRole('textbox', { name: 'Price' }).press('Enter');
    await expect(page.locator('.toast').filter({ hasText: 'Type the price as a number, like 45 or 45.50.' })).toBeVisible();
    await expect(card).toBeVisible();
    expect((await item()).name).toBe('Navy polo');

    // put right, Enter in the box is "That's right": everything is saved at once and the piece leaves the review
    await card.getByRole('textbox', { name: 'Price' }).fill('42.50');
    await card.getByRole('textbox', { name: 'Price' }).press('Enter');
    await expect(page.locator('.toast').filter({ hasText: 'Saved your changes' })).toBeVisible();
    await expect(page.getByTestId('review-empty').or(page.getByTestId('review-end'))).toBeVisible();
    const saved = await item();
    expect([saved.name, saved.brand, saved.price_cents]).toEqual(['Weekend polo', 'Made-up Mills', 4250]);
    expect(saved.source.name).toBe('user');
    expect(saved.checked_at).toBeTruthy();
    expect((await (await page.request.get(`${backend.url}/api/review`)).json()).count).toBe(0);

    // the closet has nothing to check any more
    await page.goto(backend.url + '/');
    await expect(page.getByTestId('tile')).toHaveCount(1);
    await expect(page.getByTestId('to-check')).toHaveCount(0);
  });

  test("a shoe's outside can be put right at any time, not only when Claude was unsure", async ({ page }) => {
    test.setTimeout(150_000);
    const send = (path: string, file: string, extra: Record<string, string> = {}) => page.request.post(`${backend.url}${path}`, {
      multipart: { photo: { name: file, mimeType: 'image/jpeg', buffer: readFileSync(`${PHOTOS}${file}`) }, ...extra },
    });
    const made = await (await send('/api/items', 'sneaker-held.jpg', { shoe: 'true', client_key: 'outside-1' })).json();
    expect((await send(`/api/items/${made.id}/photos`, 'sneakers-pair.jpg')).ok()).toBe(true);
    // the stand-in Claude says a polo; the owner says it is a sneaker, so its photos are sorted (the stand-in: the
    // outer side, unsure, then from above; with one side photo nothing needs asking)
    expect((await page.request.patch(`${backend.url}/api/items/${made.id}`, { data: { category: 'sneakers' } })).ok()).toBe(true);
    await page.goto(`${backend.url}/item/${made.id}`);
    const photos = page.getByTestId('shoe-photos');
    await expect(photos.getByRole('img', { name: 'Photo 1: outer side?' })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('shoe-ask')).toHaveCount(0);

    // Claude was wrong: the second photo shows the outside
    await photos.getByTestId('say-outside').click();
    const sheet = page.getByTestId('say-outside-sheet');
    await expect(sheet).toContainText('Which photo shows the outside of the shoe?');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await sheet.getByRole('button', { name: 'Photo 2 shows the outside' }).click();
    await expect(sheet).toHaveCount(0);
    // it becomes the main photo (the closet picture), and the other side follows
    await expect(photos.getByRole('img', { name: 'Photo 1: outer side' })).toBeVisible();
    await expect(photos.getByRole('img', { name: 'Photo 2: inner side' })).toBeVisible();
    const got = await (await page.request.get(`${backend.url}/api/items/${made.id}`)).json();
    expect(got.photos.map((p: { kind: string; view: string; view_by: string }) => [p.kind, p.view, p.view_by]))
      .toEqual([['front', 'outer', 'owner'], ['detail', 'inner', 'owner']]);
  });
});
