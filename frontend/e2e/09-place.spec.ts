import { expect, goToCloset, test } from './fixtures';

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
  await goToCloset(page);
  const weatherAsked = { n: 0 };
  page.on('request', (r) => { if (r.url().endsWith('/api/weather')) weatherAsked.n += 1; });
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();

  // Settings → Everyday says the place in one line; the search, and what is sent where, are behind Change
  const everyday = page.getByRole('region', { name: 'Everyday' });
  await expect(everyday.getByTestId('weather-place')).toHaveText('New York, United States');
  await expect(everyday.getByLabel('Choose another place')).toHaveCount(0);
  expect(weatherAsked.n).toBe(0);   // nothing to show the weather in yet, so it is not looked up
  await everyday.getByRole('button', { name: 'Change', exact: true }).click();
  const section = page.getByTestId('place-sheet');
  // with nothing chosen, Nines uses New York
  await expect(section.getByTestId('saved-place')).toHaveText('New York, United States');
  await expect(section.getByText('New York until you choose a place.')).toBeVisible();
  await expect(section.getByRole('button', { name: 'Use my location' })).toBeVisible();
  // the controls first; what is sent to look up the weather is one closed thing to open at the end, as on Today (it
  // led the sheet with 70 words: the review of 24 November, 57)
  const sent = section.getByText(/sends Open-Meteo .* nothing about your clothes/);
  await expect(sent).toBeHidden();
  const fold = section.locator('details').filter({ has: page.locator('summary', { hasText: 'What is sent to look up the weather' }) });
  const tops = await Promise.all([section.getByTestId('saved-place'), section.getByLabel('Choose another place'), fold]
    .map((l) => l.evaluate((el) => el.getBoundingClientRect().top)));
  expect(tops).toEqual([...tops].sort((a, b) => a - b));
  await fold.locator('summary').click();
  await expect(sent).toBeVisible();
  await section.getByLabel('Choose another place').fill('Brooklyn');
  await section.getByRole('button', { name: 'Search' }).click();
  const found = section.getByRole('list', { name: 'Places found' });
  await expect(found.getByRole('button')).toHaveCount(2);
  await found.getByRole('button', { name: BROOKLYN.name }).click();

  await expect(section.getByTestId('saved-place')).toHaveText(BROOKLYN.name);
  await expect(section.getByTestId('weather-today')).toHaveText('Today: 3°C to 10°C, rain (70% chance of rain)');
  const saved = await (await page.request.get('/api/settings')).json();
  expect(saved.place).toEqual(BROOKLYN);

  await expect(everyday.getByTestId('weather-place')).toHaveText(BROOKLYN.name);

  // still there after a reload, and the owner can go back to New York
  await page.reload();
  await expect(everyday.getByTestId('weather-place')).toHaveText(BROOKLYN.name);
  await everyday.getByRole('button', { name: 'Change', exact: true }).click();
  await expect(section.getByTestId('saved-place')).toHaveText(BROOKLYN.name);
  await section.getByRole('button', { name: 'Back to New York' }).click();
  await expect(section.getByTestId('saved-place')).toHaveText('New York, United States');
  expect((await (await page.request.get('/api/settings')).json()).place.name).toBe('New York, United States');
});

test("settings: a forecast out of reach does not offer temperatures the sheet has no box for (the review of 24 November, 57)", async ({ page }) => {
  await page.request.put('/api/settings', { data: { place: BROOKLYN } });
  await page.route('**/api/weather', (route) => route.fulfill({
    json: { place: BROOKLYN, old: false, is_today: false, hour: null, weather: null,
      message: "Couldn't reach the weather service. Check the internet connection. Try again later, or give today's temperatures yourself." },
  }));
  await goToCloset(page);
  await page.goto('/settings');
  await page.getByRole('region', { name: 'Everyday' }).getByRole('button', { name: 'Change', exact: true }).click();
  const section = page.getByTestId('place-sheet');
  await expect(section.getByText("Couldn't reach the weather service. Check the internet connection. Try again later.", { exact: true })).toBeVisible();
  await expect(section).not.toContainText("give today's temperatures");
});
