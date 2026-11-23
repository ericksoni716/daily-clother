import type { Page } from '@playwright/test';
import { expect, goToCloset, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.put('/api/settings', { data: { show_drawings: false } });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

const tilePics = (page: Page) => page.getByTestId('tile').locator('.tile-card img');
const allDrawings = (pics: ReturnType<Page['locator']>) =>
  pics.evaluateAll((imgs) => imgs.length > 0 && imgs.every((i) => i.classList.contains('pic-illustration')));
const someNot = (pics: ReturnType<Page['locator']>) =>
  pics.evaluateAll((imgs) => imgs.some((i) => !i.classList.contains('pic-illustration')));

/** The closet's choice of photos or drawings, in the Filter sheet (opened when it is not). */
async function showChoice(page: Page) {
  const filter = page.getByRole('button', { name: /^Filter/ });
  if ((await filter.getAttribute('aria-expanded')) !== 'true') await filter.click();
  return page.getByRole('dialog', { name: 'Filter' }).getByRole('group', { name: 'Show' });
}

async function setInSettings(page: Page, on: boolean) {
  await page.goto('/settings');
  const toggle = page.locator('section[aria-labelledby="s-everyday"]').getByRole('switch', { name: 'Show drawings instead of photos' });
  await expect(toggle).toBeChecked({ checked: !on });
  await toggle.click();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  await expect(toggle).toBeChecked({ checked: on });
}

test('Show drawings instead of photos: set in Settings, followed by the closet and an item page, and off again', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/');
  await expect(tilePics(page).first()).toBeVisible();
  expect(await someNot(tilePics(page))).toBe(true);   // off by default: the demo's photographed pieces show photos
  const photographed = (await page.getByTestId('tile').filter({ has: page.locator('img.pic-cutout') }).first().getAttribute('href'))!;

  await setInSettings(page, true);
  // the closet starts on drawings, its switch with it, and so does a fresh page (the setting is kept on the computer)
  await page.goto('/');
  await expect((await showChoice(page)).getByRole('button', { name: 'Drawings' })).toHaveAttribute('aria-pressed', 'true');
  await expect(tilePics(page).first()).toBeVisible();
  await expect.poll(() => allDrawings(tilePics(page))).toBe(true);
  // the switch over the grid shows photos for the moment; opened again, the closet starts from the setting
  await (await showChoice(page)).getByRole('button', { name: 'Photos' }).click();
  await expect.poll(() => someNot(tilePics(page))).toBe(true);
  await page.reload();
  await expect.poll(() => allDrawings(tilePics(page))).toBe(true);

  // a photographed piece's own page opens on its drawing
  await page.goto(photographed);
  const picture = page.getByRole('group', { name: 'Picture' });
  await expect(picture.getByRole('button', { name: 'Drawing' })).toHaveAttribute('aria-pressed', 'true');

  await setInSettings(page, false);
  await page.goto(photographed);
  await expect(picture.getByRole('button', { name: 'Cutout' })).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/');
  await expect((await showChoice(page)).getByRole('button', { name: 'Photos' })).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => someNot(tilePics(page))).toBe(true);
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true });

  test('photos or drawings is a choice said in words, under Filter, a whole tap high', async ({ page }) => {
    await goToCloset(page);
    await useProfile(page, 'demo');
    await page.goto('/');
    await expect(tilePics(page).first()).toBeVisible();
    // nothing over the grid has to be guessed from a picture: the toolbar is the search and Filter
    await expect(page.locator('.closet-toolbar').getByRole('group', { name: 'Show' })).toHaveCount(0);
    await page.getByRole('button', { name: /^Filter/ }).click();
    const show = page.getByRole('dialog', { name: 'Filter' }).getByRole('group', { name: 'Show' });
    for (const name of ['Photos', 'Drawings']) {
      const choice = show.getByRole('button', { name });
      await expect(choice).toHaveText(name);
      expect((await choice.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await show.getByRole('button', { name: 'Drawings' }).click();
    await expect.poll(() => allDrawings(tilePics(page))).toBe(true);
    await expect(show.getByRole('button', { name: 'Drawings' })).toHaveAttribute('aria-pressed', 'true');
    await page.screenshot({ path: test.info().outputPath('show-in-words-320.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    await page.getByRole('button', { name: 'Done' }).click();
    // kept while the app is open: coming back to the closet finds drawings
    await page.getByRole('link', { name: /^Today/ }).click();
    await page.getByRole('link', { name: /^Closet/ }).click();
    await expect.poll(() => allDrawings(tilePics(page))).toBe(true);
  });
});
