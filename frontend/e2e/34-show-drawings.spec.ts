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
  await expect(page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Drawings' })).toHaveAttribute('aria-pressed', 'true');
  await expect(tilePics(page).first()).toBeVisible();
  await expect.poll(() => allDrawings(tilePics(page))).toBe(true);
  // the switch over the grid shows photos for the moment; opened again, the closet starts from the setting
  await page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Photos' }).click();
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
  await expect(page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Photos' })).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => someNot(tilePics(page))).toBe(true);
});
