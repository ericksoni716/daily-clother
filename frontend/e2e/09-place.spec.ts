import { expect, login, test } from './fixtures';

const BROOKLYN = { name: 'Brooklyn, New York, United States', latitude: 40.6501, longitude: -73.9496, timezone: 'America/New_York' };

test.afterEach(async ({ page }) => {
  await page.request.put('/api/settings', { data: { place: null } });
});

test('settings: search for a place (faked), choose it and see it saved', async ({ page }) => {
  // Open-Meteo is never called from a test: the search and the weather are answered here.
  await page.route('**/api/places?*', (route) => route.fulfill({
    json: { places: [BROOKLYN, { name: 'Brooklyn, Wellington, New Zealand', latitude: -41.3, longitude: 174.76, timezone: 'Pacific/Auckland' }] },
  }));
  await page.route('**/api/weather', (route) => route.fulfill({
    json: {
      place: BROOKLYN, old: false, is_today: true, message: null,
      weather: { date: '2026-11-12', low_c: 3.2, high_c: 9.8, rain_chance: 70, rain: true, summary: 'rain', fetched_at: '2026-11-12T17:00:00Z' },
    },
  }));
  await login(page);
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();

  const section = page.getByRole('region', { name: 'Where you are' });
  // with nothing chosen, Closet uses New York
  await expect(section.getByTestId('saved-place')).toHaveText('New York, United States');
  await expect(section.getByText('New York until you choose a place.')).toBeVisible();
  await expect(section.getByRole('button', { name: 'Use my location' })).toBeVisible();
  await expect(section.getByText(/sends Open-Meteo .* nothing about your clothes/)).toBeVisible();
  await section.getByLabel('Choose another place').fill('Brooklyn');
  await section.getByRole('button', { name: 'Search' }).click();
  const found = section.getByRole('list', { name: 'Places found' });
  await expect(found.getByRole('button')).toHaveCount(2);
  await found.getByRole('button', { name: BROOKLYN.name }).click();

  await expect(section.getByTestId('saved-place')).toHaveText(BROOKLYN.name);
  await expect(section.getByTestId('weather-today')).toHaveText('Today: 3°C to 10°C, rain (70% chance of rain)');
  const saved = await (await page.request.get('/api/settings')).json();
  expect(saved.place).toEqual(BROOKLYN);

  // still there after a reload, and the owner can go back to New York
  await page.reload();
  await expect(section.getByTestId('saved-place')).toHaveText(BROOKLYN.name);
  await section.getByRole('button', { name: 'Back to New York' }).click();
  await expect(section.getByTestId('saved-place')).toHaveText('New York, United States');
  expect((await (await page.request.get('/api/settings')).json()).place.name).toBe('New York, United States');
});
