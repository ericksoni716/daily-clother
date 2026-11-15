import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const SCREENSHOTS = resolve(import.meta.dirname, '../../docs/screenshots');
const PHONE = { width: 390, height: 844 };

/** A made-up photo of a shoe seen from the front (a tall dark shape, as narrow as it is high), made in the page:
 * the side-on outline cannot be traced from it. */
async function frontOnPhoto(page: Page): Promise<Buffer> {
  const base64 = await page.evaluate(() => {
    const c = document.createElement('canvas');
    c.width = 900;
    c.height = 900;
    const g = c.getContext('2d')!;
    g.fillStyle = '#d6d0c4';
    g.fillRect(0, 0, 900, 900);
    g.fillStyle = '#2b2f3a';
    g.beginPath();
    g.ellipse(450, 470, 150, 300, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = '#f2f0ea';
    g.fillRect(300, 720, 300, 70);
    return c.toDataURL('image/png').split(',')[1];
  });
  return Buffer.from(base64, 'base64');
}

/** Made-up photos of a shoe from other sides (a plain shape in each colour), made in the page. */
async function otherPhotos(page: Page, colours: string[]): Promise<Buffer[]> {
  const shots = await page.evaluate((cs) => cs.map((colour, i) => {
    const c = document.createElement('canvas');
    c.width = 640;
    c.height = 480;
    const g = c.getContext('2d')!;
    g.fillStyle = '#d6d0c4';
    g.fillRect(0, 0, 640, 480);
    g.fillStyle = colour;
    g.beginPath();
    g.ellipse(320, 250, 220 - i * 40, 110 + i * 30, 0, 0, Math.PI * 2);
    g.fill();
    return c.toDataURL('image/png').split(',')[1];
  }), colours);
  return shots.map((b) => Buffer.from(b, 'base64'));
}

/** The demo closet's id for an item (tools/make_demo.py keeps them in items.json). */
function demoId(name: string): string {
  const data = JSON.parse(readFileSync(resolve(import.meta.dirname, '../../backend/closet/demo_data/items.json'), 'utf8'));
  return data.items.find((i: { name: string }) => i.name === name).id;
}

// Its own backend, with stand-ins for the model and for Claude; shoes are traced with GrabCut, as without the model.
test.describe('a shoe drawn from its photo', () => {
  let backend: Backend;
  test.use({ viewport: PHONE, hasTouch: true, isMobile: true });

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('Add guides the photo, says at once why it will not trace, takes more photos, and the item page sorts them, falls back and draws the shoe', async ({ page }) => {
    test.setTimeout(180_000);
    mkdirSync(SCREENSHOTS, { recursive: true });
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/add');
    await page.getByRole('button', { name: 'A shoe' }).click();
    const add = page.getByTestId('shoe-add');
    await expect(add).toContainText('One shoe on its own');
    await expect(add).toContainText('toe to the left');
    await expect(page.getByTestId('shoe-guide')).toBeVisible();
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-add-guide.png') });

    // a photo from the front: the instant check says it will not trace well, and why, with a chance to retake
    const photo = await frontOnPhoto(page);
    await page.getByTestId('shoe-library-input').setInputFiles({ name: 'front.png', mimeType: 'image/png', buffer: photo });
    const check = page.getByTestId('shoe-check');
    await expect(check).toContainText('This photo may not trace well.', { timeout: 30_000 });
    await expect(check.locator('li').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retake' })).toBeVisible();
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-add-check.png') });

    // retake goes back to the guide; the same photo again, added anyway
    await page.getByRole('button', { name: 'Retake' }).click();
    await expect(page.getByTestId('shoe-guide')).toBeVisible();
    await page.getByTestId('shoe-library-input').setInputFiles({ name: 'front.png', mimeType: 'image/png', buffer: photo });
    const created = page.waitForResponse((res) => new URL(res.url()).pathname === '/api/items' && res.request().method() === 'POST');
    await page.getByRole('button', { name: 'Add it anyway' }).click({ timeout: 30_000 });
    const id: string = (await (await created).json()).id;

    // the stand-in Claude would say it is a polo; the owner says it is a sneaker (and names it), so it is traced, and
    // its photos are sorted into views
    const r = await page.request.patch(`${backend.url}/api/items/${encodeURIComponent(id)}`, { data: { category: 'sneakers', name: 'Navy sneaker' } });
    expect(r.ok()).toBe(true);

    // more photos of the shoe, in any order: two chosen at once, one removed again, one more
    await expect(add).toContainText('Add more photos of this shoe');
    expect(await axeViolations(page)).toEqual([]);
    const others = await otherPhotos(page, ['#2b6f9e', '#9e2b52', '#7a5230']);
    const file = (name: string, buffer: Buffer) => ({ name, mimeType: 'image/png', buffer });
    await page.getByTestId('shoe-more-input').setInputFiles([file('top.png', others[0]), file('wrong.png', others[1])]);
    const added = add.getByRole('list', { name: 'Photos added' }).getByRole('listitem');
    await expect(added).toHaveCount(2);
    await add.getByRole('button', { name: 'Remove photo 3' }).click();
    await expect(added).toHaveCount(1);
    await page.getByTestId('shoe-more-input').setInputFiles([file('side.png', others[2])]);
    await expect(added).toHaveCount(2);
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-add-more.png') });
    await page.getByRole('button', { name: 'Done' }).click();
    await expect(add).toContainText('The shoe and 2 more photos are added.');
    await page.getByRole('link', { name: 'See the shoe' }).click();
    await expect(page).toHaveURL(/\/item\//);

    // the item page sorts the photos by itself: the stand-in says outer side (unsure), from above, inner side (unsure),
    // with a mark on one side only, so it asks which photo shows the outside
    const row = page.getByTestId('shoe-photos');
    await expect(row.getByRole('listitem')).toHaveCount(3);
    const ask = page.getByTestId('shoe-ask');
    await expect(ask).toContainText('Which photo shows the outside of the shoe?', { timeout: 45_000 });
    await expect(ask).toContainText('the outside faces away from the other shoe');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await ask.scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-ask-outside.png') });
    await ask.getByRole('button', { name: 'Photo 3 shows the outside' }).click();
    await expect(ask).toHaveCount(0);
    await expect(row.getByRole('img', { name: 'Photo 3: outer side' })).toBeVisible();
    await expect(row.getByRole('img', { name: 'Photo 1: inner side' })).toBeVisible();   // the other side follows
    await expect(row.getByRole('img', { name: 'Photo 2: from above' })).toBeVisible();
    await expect(row.getByRole('button', { name: 'Remove photo 1' })).toHaveCount(0);   // never the main photo
    await expect(row.getByRole('button', { name: 'Add photos' })).toBeEnabled();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });
    await row.screenshot({ path: resolve(SCREENSHOTS, 'shoe-photos-sorted.png') });

    // the trace: the photo from the front is turned down
    const fallback = page.getByTestId('shoe-fallback');
    await expect(fallback).toContainText("so it's drawn from its details instead", { timeout: 60_000 });
    await expect(fallback.getByRole('button', { name: 'Retake' })).toBeVisible();
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await fallback.scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-item-fallback.png') });

    // drawn for the outfit figure: once the photos are sorted, Claude (a stand-in answering with the dress shoe the
    // owner liked) draws the shoe and checks it once against the photos
    const drawnSection = page.getByTestId('shoe-drawn');
    await expect(drawnSection.getByTestId('shoe-drawn-line')).toContainText('checked once against the photos', { timeout: 60_000 });
    await expect(drawnSection).toContainText('on your Claude plan');
    await expect(drawnSection).toContainText('if drawn on the API key');
    const picture = drawnSection.getByRole('img', { name: /as Claude drew it from its photos/ });
    await expect.poll(() => picture.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    await expect(drawnSection).not.toContainText('The photos changed');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await drawnSection.scrollIntoViewIfNeeded();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });
    await drawnSection.screenshot({ path: resolve(SCREENSHOTS, 'shoe-drawn.png') });

    // "Draw again" asks first, saying what it does, how long it takes and roughly what it costs
    await drawnSection.getByRole('button', { name: 'Draw again' }).click();
    const question = drawnSection.getByRole('alertdialog');
    await expect(question).toContainText('replaces this one when it is done');
    await expect(question).toContainText('about two minutes');
    await expect(question).toContainText('on the API key');
    expect(await axeViolations(page)).toEqual([]);
    await question.getByRole('button', { name: 'Keep this drawing' }).click();
    await expect(question).toHaveCount(0);
    await drawnSection.getByRole('button', { name: 'Draw again' }).click();
    await question.getByRole('button', { name: 'Draw it again' }).click();
    // the old drawing stays shown until the new one is done
    await expect(drawnSection.getByRole('status')).toBeVisible();
    await expect(picture).toBeVisible();
    await expect(drawnSection.getByRole('status')).toHaveCount(0, { timeout: 30_000 });
    await expect(drawnSection.getByRole('button', { name: 'Draw again' })).toBeVisible();

    // the owner's one-line note: the stand-in Claude changes only the laces, and its check says the photos show them
    // brown, so the page says so in one line; the drawing before is kept, one tap away
    const box = drawnSection.getByLabel("What's wrong with the drawing?");
    const sendNote = drawnSection.getByRole('button', { name: 'Send' });
    await expect(box).toHaveAttribute('placeholder', /the elastic sides should be wider/);
    await expect(sendNote).toBeDisabled();
    const before = (await picture.getAttribute('src'))!;
    await box.fill('the laces should be black');
    await sendNote.click();
    await expect(drawnSection.getByRole('status')).toHaveText('Changing the drawing: “the laces should be black”');
    await expect(box).toHaveCount(0);
    await expect(picture).toHaveAttribute('src', before);   // the drawing stays shown until the change is done
    const changedLine = drawnSection.getByTestId('shoe-drawn-changed');
    await expect(changedLine).toHaveText('Changed as you asked: “the laces should be black”. The laces are black now.',
      { timeout: 30_000 });
    await expect(drawnSection.getByTestId('shoe-drawn-against')).toHaveText(
      'The photos show brown laces, not black; drawn as you asked.');
    await expect(drawnSection.getByTestId('shoe-drawn-line')).toContainText('Changed in');
    await expect(drawnSection.getByTestId('shoe-drawn-line')).toContainText('checked once against the photos');
    await expect(picture).not.toHaveAttribute('src', before);
    await expect.poll(() => picture.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    await expect(box).toBeVisible();
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await drawnSection.scrollIntoViewIfNeeded();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });
    await drawnSection.screenshot({ path: resolve(SCREENSHOTS, 'shoe-drawn-corrected.png') });

    // back to the drawing before in one tap, and the same button offers the newer one again
    const changedSrc = (await picture.getAttribute('src'))!;
    await drawnSection.getByRole('button', { name: 'Go back to the drawing before' }).click();
    await expect(picture).toHaveAttribute('src', before);
    await expect(changedLine).toHaveCount(0);
    await expect(drawnSection.getByTestId('shoe-drawn-against')).toHaveCount(0);
    await drawnSection.getByRole('button', { name: 'Go to the newer drawing' }).click();
    await expect(picture).toHaveAttribute('src', changedSrc);
    await expect(changedLine).toBeVisible();
    await expect(drawnSection.getByRole('button', { name: 'Go back to the drawing before' })).toBeVisible();

    // a photo removed: the shoe is not drawn again, and the page says the photos changed since the drawing
    await row.getByRole('button', { name: 'Remove photo 2' }).click();
    await expect(drawnSection).toContainText('The photos changed since this drawing.');
    await expect(drawnSection.getByRole('status')).toHaveCount(0);
  });

  test("a traced shoe's drawing, fixed in Fix the details", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase').fill(PASS);
    await page.getByRole('button', { name: 'Open my closet' }).click();
    await expect(page.getByLabel('Passphrase')).toHaveCount(0);
    expect((await page.request.post(`${backend.url}/api/profile`, { data: { profile: 'demo' } })).ok()).toBe(true);
    const id = demoId('Grey runners');
    await page.goto(`${backend.url}/item/${id}`);
    const drawing = page.locator('.detail img').first();
    await expect(drawing).toBeVisible();
    await expect(page.getByTestId('shoe-fallback')).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-item-traced.png') });

    await page.getByRole('button', { name: 'Fix the details' }).click();
    const fix = page.getByTestId('shoe-fix');
    await expect(fix).toBeVisible();
    await expect(fix.getByLabel('Colour of the laces')).toBeAttached();
    await expect(fix.getByLabel('Main colour')).toBeAttached();
    await expect(fix.getByRole('button', { name: 'Remove' }).first()).toBeVisible();
    await expect(fix.getByRole('button', { name: 'Use the plain drawing' })).toBeVisible();
    await expect(fix.getByRole('button', { name: 'Re-trace' })).toHaveCount(0);   // no photo kept to trace again
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page, '[data-testid="shoe-fix"]')).toEqual([]);

    // nudge then remove the stripes; undo the fixes
    await fix.getByRole('button', { name: /Move the .* towards the toe/ }).first().click();
    await expect(fix.getByRole('button', { name: 'Undo my fixes' })).toBeVisible();
    await fix.getByRole('button', { name: 'Remove' }).first().click();
    await expect(fix.getByText('(removed)')).toBeVisible();
    await fix.scrollIntoViewIfNeeded();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });   // the messages have gone
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-fix.png') });
    await fix.getByRole('button', { name: 'Undo my fixes' }).click();
    await expect(fix.getByText('(removed)')).toHaveCount(0);

    // its front view on the outfit figure: the two drawings side by side, the shape one drawn until a front photo
    const front = fix.getByTestId('shoe-front');
    const shape = front.getByRole('button', { name: /From the shoe's shape/ });
    const fromPhoto = front.getByRole('button', { name: /From your photo/ });
    await expect(shape).toHaveAttribute('aria-pressed', 'true');
    await expect(fromPhoto).toHaveAttribute('aria-pressed', 'false');
    for (const img of await front.locator('img').all()) {
      await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    }
    await expect(front.getByRole('button', { name: 'Add a front photo' })).toBeVisible();
    await fromPhoto.click();
    await expect(fromPhoto).toHaveAttribute('aria-pressed', 'true');
    await expect(shape).toHaveAttribute('aria-pressed', 'false');
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page, '[data-testid="shoe-front"]')).toEqual([]);
    await front.scrollIntoViewIfNeeded();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });
    await front.screenshot({ path: resolve(SCREENSHOTS, 'shoe-front-choice.png') });
    await shape.click();
    await expect(shape).toHaveAttribute('aria-pressed', 'true');

    // the plain drawing, and back
    await fix.getByRole('button', { name: 'Use the plain drawing' }).click();
    await expect(fix.getByRole('button', { name: 'Use the traced drawing' })).toBeVisible();
    await fix.getByRole('button', { name: 'Use the traced drawing' }).click();
    await expect(fix.getByRole('button', { name: 'Use the plain drawing' })).toBeVisible();
  });
});
