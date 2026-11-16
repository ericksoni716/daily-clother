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
  const show = page.getByRole('region', { name: "Today's outfits" }).getByRole('group', { name: 'Show the outfit' });
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
  await page.getByRole('group', { name: 'Show the outfit' }).getByRole('button', { name: 'Pieces' }).click();
  await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
  await expect(page.getByTestId('current-outfit').getByTestId('outfit-figure')).toHaveCount(0);
});

test('today: a layered outfit is dressed a layer at a time once in sight, and at once when the device asks for less motion', async ({ page }) => {
  await coldDay(page);
  await login(page);
  await useProfile(page, 'demo');
  const asked: Record<string, unknown>[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/outfits/figure')) asked.push(r.postDataJSON()); });
  const items = (pieces: Record<string, unknown>) => Object.values(pieces).flat().filter(Boolean) as string[];

  await page.goto('/today');
  const outfit = page.getByTestId('current-outfit');
  await expect(outfit.getByTestId('piece').first()).toBeVisible();
  const ids = (await outfit.getByTestId('piece').evaluateAll((links) => links.map((a) => a.getAttribute('href')))).map((h) => h!.split('/').pop()!);
  await page.getByRole('group', { name: 'Show the outfit' }).getByRole('button', { name: 'As worn' }).click();
  const figure = outfit.getByTestId('outfit-figure');
  await expect(figure.getByRole('img', { name: /^The outfit as worn: / })).toBeVisible();

  // one drawing per layer, the outfit's own last and on top; only that one is described
  const layers = figure.locator('.figure-stack > img');
  expect(await layers.count()).toBeGreaterThanOrEqual(2);   // a cold day: more than one top
  await expect(figure.getByRole('img')).toHaveCount(1);
  await expect(layers.last()).toHaveAccessibleName(/^The outfit as worn: /);
  // each layer was asked for as the outfit up to it: never anything that is not in the outfit
  const mine = asked.filter((a) => items(a).every((id) => ids.includes(id)));
  expect(mine.some((a) => items(a).length === ids.length)).toBe(true);
  expect(mine.length).toBeGreaterThanOrEqual(await layers.count());
  // every layer placed inside the outfit's frame, and the outfit's own fills it. Where each is placed, not where it
  // is seen: the first layer rises 8px as it arrives, so its box on the screen can be below the frame for a moment
  const stack = await figure.locator('.figure-stack').evaluate((s) => ({ w: s.clientWidth, h: s.clientHeight }));
  const placed = await layers.evaluateAll((all) => all.map((img) => {
    const el = img as HTMLElement;
    return { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight };
  }));
  for (const box of placed) {
    expect(box.x).toBeGreaterThanOrEqual(-1);
    expect(box.y).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.w).toBeLessThanOrEqual(stack.w + 1);
    expect(box.y + box.h).toBeLessThanOrEqual(stack.h + 1);
  }
  expect(placed[placed.length - 1].h).toBeGreaterThan(stack.h - 1);
  // dressed within a moment: the outfit's own drawing ends fully shown
  await expect.poll(() => layers.last().evaluate((img) => getComputedStyle(img).opacity)).toBe('1');

  // the next outfit waits undressed beside it, and is dressed once swiped to
  const next = page.getByRole('button', { name: 'Next outfit' });
  if (await next.isVisible()) {
    const second = page.locator('.today-slide').nth(1).getByTestId('outfit-figure').locator('.figure-stack > img').last();
    await expect(second).toBeAttached();
    expect(await second.evaluate((img) => getComputedStyle(img).opacity)).toBe('0');
    await next.click();
    await expect.poll(() => second.evaluate((img) => getComputedStyle(img).opacity)).toBe('1');
  }

  // less motion: each outfit asked for once, and shown as it is
  await page.emulateMedia({ reducedMotion: 'reduce' });
  asked.length = 0;
  await page.reload();
  await expect(page.getByTestId('current-outfit').getByTestId('outfit-figure').getByRole('img', { name: /^The outfit as worn: / })).toBeVisible();
  await expect.poll(() => asked.length).toBe(await page.locator('.today-slide').count());
  await expect(page.getByTestId('current-outfit').getByTestId('outfit-figure').locator('img')).toHaveCount(1);
});
