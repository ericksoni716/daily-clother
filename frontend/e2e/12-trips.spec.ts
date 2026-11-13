import { expect, login, test, useProfile } from './fixtures';

const PLACE = { name: 'Lisbon, Portugal', latitude: 38.7167, longitude: -9.1333, timezone: 'Europe/Lisbon' };

function futureDay(offset: number): string {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
}

function tripWeather(first: string, last: string) {
  const out = [];
  const day = new Date(`${first}T00:00:00Z`);
  const end = new Date(`${last}T00:00:00Z`);
  while (day <= end) {
    out.push({
      date: day.toISOString().slice(0, 10),
      low_c: 13,
      high_c: 21,
      rain: false,
    });
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return out;
}

async function stubTripWeather(page: import('@playwright/test').Page) {
  await page.route('**/api/places?*', (route) => route.fulfill({ json: { places: [PLACE] } }));
  await page.route('**/api/trips**', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = route.request().postDataJSON() as { first_day: string; last_day: string; weather?: unknown };
    const response = await route.fetch({
      postData: JSON.stringify({ ...body, weather: tripWeather(body.first_day, body.last_day) }),
    });
    await route.fulfill({ response });
  });
}

test.afterEach(async ({ page }) => {
  await page.context().setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

for (const viewport of [{ name: 'computer', width: 1280, height: 800 }, { name: 'phone', width: 390, height: 844 }]) {
  test(`plan, pack and swap a trip on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await login(page);
    await useProfile(page, 'demo');
    await stubTripWeather(page);
    let tripId: string | null = null;
    try {
      await page.goto('/trips');
      await page.getByRole('link', { name: 'Plan a trip' }).click();
      await page.getByLabel('Where are you going?').fill('Lisbon');
      await page.getByRole('button', { name: 'Search' }).click();
      await page.getByRole('button', { name: PLACE.name }).click();
      await page.getByRole('button', { name: 'Work out what to pack' }).click();
      await expect(page.getByRole('heading', { name: /What to pack/ })).toBeVisible();
      await page.getByRole('button', { name: 'Save this trip' }).click();
      await expect(page.getByRole('heading', { name: 'Lisbon' })).toBeVisible();
      tripId = page.url().split('/').pop() ?? null;

      const firstTick = page.getByRole('checkbox', { name: /^Packed:/ }).first();
      const patch = page.waitForResponse((response) =>
        response.request().method() === 'PATCH' && response.url().includes(`/api/trips/${tripId}`) && response.ok());
      await firstTick.check();
      await patch;
      await expect(page.getByTestId('trip-progress')).toContainText('1 of');
      await page.reload();
      await expect(page.getByRole('checkbox', { name: /^Packed:/ }).first()).toBeChecked();

      const firstPiece = page.getByTestId('pack-line').filter({ has: page.locator('.trip-more') }).first();
      const oldName = (await firstPiece.locator('.trip-line-name').textContent())?.trim();
      expect(oldName).toBeTruthy();
      await firstPiece.getByRole('button', { name: /^Choices for/ }).click();
      const swap = page.waitForResponse((response) =>
        response.request().method() === 'PATCH' && response.url().includes(`/api/trips/${tripId}`) && response.ok());
      await page.getByRole('button', { name: 'Not this one' }).click();
      await swap;
      // the piece is gone from the lines to pack; it is still among the choices under "Take something else",
      // so the whole section's text cannot be asked
      await expect(page.getByTestId('pack-line').filter({ hasText: oldName! })).toHaveCount(0);
    } finally {
      if (tripId) await page.request.delete(`/api/trips/${tripId}`);
    }
  });
}

test('a saved trip names archived and deleted pieces and offers to plan again', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const items = await page.request.get('/api/items');
  const closet = (await items.json()).items as { id: string; name: string }[];
  const [archived, deleted] = closet.slice(0, 2);
  const first = futureDay(8);
  const weather = tripWeather(first, first);
  const response = await page.request.post('/api/trips', {
    data: { place: PLACE, first_day: first, last_day: first, weather, pin: [archived.id, deleted.id] },
  });
  const trip = await response.json();
  try {
    await page.request.patch(`/api/items/${archived.id}`, { data: { status: 'archived' } });
    await page.request.delete(`/api/items/${deleted.id}`);
    await page.goto(`/trips/${trip.id}`);

    const archivedLine = page.getByTestId('pack-line').filter({ hasText: archived.name });
    await expect(archivedLine).toContainText('Archived');
    await expect(archivedLine.getByRole('button', { name: 'Plan again' })).toBeVisible();
    const deletedLine = page.getByTestId('pack-line').filter({ hasText: /no longer in your closet/i });
    await expect(deletedLine).toBeVisible();
    await expect(deletedLine.getByRole('button', { name: 'Plan again' })).toBeVisible();
    const replan = page.waitForResponse((result) =>
      result.request().method() === 'PATCH' && result.url().includes(`/api/trips/${trip.id}`) && result.ok());
    await archivedLine.getByRole('button', { name: 'Plan again' }).click();
    await replan;
    await expect(archivedLine).toHaveCount(0);
    await expect(deletedLine).toHaveCount(0);
  } finally {
    await page.request.delete(`/api/trips/${trip.id}`);
  }
});

test('the offline trip list is kept separately for the demo and real closet', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const first = futureDay(8);
  const weather = tripWeather(first, first);
  const response = await page.request.post('/api/trips', {
    data: { place: PLACE, first_day: first, last_day: first, weather },
  });
  const trip = await response.json();
  try {
    await page.goto('/trips');
    await expect(page.getByTestId('trip-card')).toHaveCount(1);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await useProfile(page, 'main');
    await page.context().setOffline(true);
    await page.goto('/trips');
    await expect(page.getByTestId('trip-card')).toHaveCount(0);
  } finally {
    await page.context().setOffline(false);
    await page.request.post('/api/profile', { data: { profile: 'demo' } });
    await page.request.delete(`/api/trips/${trip.id}`).catch(() => undefined);
    await page.request.post('/api/profile', { data: { profile: 'main' } });
  }
});
