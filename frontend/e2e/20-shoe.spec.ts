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

  test('Add guides the photo, says at once why it will not trace, and the item page falls back', async ({ page }) => {
    test.setTimeout(150_000);
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
    await page.getByRole('button', { name: 'Add it anyway' }).click({ timeout: 30_000 });

    // the optional second photo, from the front or from above
    await expect(add).toContainText('A second photo, from the front or from above');
    expect(await axeViolations(page)).toEqual([]);
    await page.getByRole('button', { name: 'Skip' }).click();
    await page.getByRole('link', { name: 'See the shoe' }).click();
    await expect(page).toHaveURL(/\/item\//);
    const id = decodeURIComponent(page.url().split('/item/')[1]);

    // the stand-in Claude says it is a polo; the owner says it is a sneaker (and names it), so it is traced, and turned down
    const r = await page.request.patch(`${backend.url}/api/items/${encodeURIComponent(id)}`, { data: { category: 'sneakers', name: 'Navy sneaker' } });
    expect(r.ok()).toBe(true);
    await page.reload();
    const fallback = page.getByTestId('shoe-fallback');
    await expect(fallback).toContainText("so it's drawn from its details instead", { timeout: 60_000 });
    await expect(fallback.getByRole('button', { name: 'Retake' })).toBeVisible();
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await fallback.scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(SCREENSHOTS, 'shoe-item-fallback.png') });
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
