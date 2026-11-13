import type { Page } from '@playwright/test';
import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

/** A cold, dry day, so the outfit has layers; Open-Meteo is never called from a test. */
async function coldDay(page: Page) {
  await page.route('**/api/outfits/today', async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ response: await route.fetch({ postData: { ...body, low_c: 2, high_c: 7, rain: false } }) });
  });
}

test('today: switching to the outfit as worn shows it drawn, and the choice is remembered', async ({ page }) => {
  await coldDay(page);
  await login(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  const outfit = page.getByTestId('current-outfit');
  await expect(outfit.getByTestId('piece').first()).toBeVisible();
  const ids = (await outfit.getByTestId('piece').evaluateAll((links) => links.map((a) => a.getAttribute('href')))).map((h) => h!.split('/').pop()!);

  const asked: Record<string, unknown>[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/outfits/figure')) asked.push(r.postDataJSON()); });
  const show = outfit.getByRole('group', { name: 'Show the outfit' });
  await show.getByRole('button', { name: 'As worn' }).click();
  await expect(show.getByRole('button', { name: 'As worn' })).toHaveAttribute('aria-pressed', 'true');

  // the figure replaces the pieces, drawn by the server from this outfit's items
  const figure = outfit.getByTestId('outfit-figure').getByRole('img', { name: /^The outfit as worn: / });
  await expect(figure).toBeVisible();
  await expect(outfit.getByTestId('piece').first()).toBeHidden();
  await expect.poll(() => figure.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(100);
  const drawn = Object.values(asked[0] ?? {}).flat().filter(Boolean);
  expect(drawn.length).toBeGreaterThanOrEqual(3);
  expect(ids).toEqual(expect.arrayContaining(drawn as string[]));
  // tall enough to read, and "I'm wearing this" still on the first screen
  expect((await figure.boundingBox())!.height).toBeGreaterThan(300);
  await expect(outfit.getByRole('button', { name: "I'm wearing this" })).toBeInViewport();

  // on a phone, as wide as the card allows and still readable
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => (await figure.boundingBox())?.height ?? 0).toBeGreaterThan(400);
  await page.setViewportSize({ width: 1440, height: 900 });

  // remembered on this device
  await page.reload();
  await expect(page.getByTestId('current-outfit').getByTestId('outfit-figure').getByRole('img', { name: /^The outfit as worn: / })).toBeVisible();
  await page.getByTestId('current-outfit').getByRole('group', { name: 'Show the outfit' }).getByRole('button', { name: 'Pieces' }).click();
  await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
  await expect(page.getByTestId('current-outfit').getByTestId('outfit-figure')).toHaveCount(0);
});
