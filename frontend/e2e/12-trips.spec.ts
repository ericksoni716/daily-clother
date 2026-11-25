import { expect, goToCloset, openFold, test, useProfile } from './fixtures';


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
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await page.context().setOffline(false);
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

for (const viewport of [{ name: 'computer', width: 1280, height: 800 }, { name: 'phone', width: 390, height: 844 }]) {
  test(`plan, pack and swap a trip on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await goToCloset(page);
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
      // the saved trip fits the screen: its "Change the trip" chips scroll inside their row instead of widening the page
      await expect(page.getByRole('region', { name: 'Change the trip' })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);

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
      // the line's choices open in a sheet over the page, named for the piece
      const choices = page.getByRole('dialog', { name: oldName! });
      await expect(choices).toBeVisible();
      const swap = page.waitForResponse((response) =>
        response.request().method() === 'PATCH' && response.url().includes(`/api/trips/${tripId}`) && response.ok());
      await choices.getByRole('button', { name: 'Not this one' }).click();
      await swap;
      // the piece is gone from the lines to pack; it is still among the choices under "Take something else",
      // so the whole section's text cannot be asked
      await expect(page.getByTestId('pack-line').filter({ hasText: oldName! })).toHaveCount(0);
    } finally {
      if (tripId) await page.request.delete(`/api/trips/${tripId}`);
    }
  });
}

test('a trip on a phone leads with what to pack, says a forecast it could not get once, and fits five pieces to a day', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 629 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  const ids: string[] = [];
  try {
    // a mild trip whose days are dressed, some with something to watch for (rain on one day)
    const first = futureDay(10), last = futureDay(14);
    const weather = tripWeather(first, last).map((d, i) => ({ ...d, low_c: 14, high_c: 20, rain: i === 1 }));
    const mild = await (await page.request.post('/api/trips', { data: { place: PLACE, first_day: first, last_day: last, weather } })).json();
    ids.push(mild.id);
    await page.goto(`/trips/${mild.id}`);
    const pack = page.getByRole('heading', { name: /What to pack/ });
    await expect(pack).toBeVisible();
    const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
    expect((await pack.boundingBox())!.y).toBeLessThan(tabbar.y);
    if (mild.plan.warnings.length) {
      // the days to watch for are one line that opens, above the list
      const watch = page.getByTestId('trip-watch');
      await expect(watch).toContainText(/days? ha(s|ve) something to watch for/);
      expect((await watch.boundingBox())!.height).toBeLessThanOrEqual(56);
    }
    // a day's five pieces in one row, not four and one left alone on a row
    const day = page.getByTestId('trip-day').filter({ has: page.locator('.trip-day-pieces') }).first();
    const tops = await day.locator('.trip-day-pieces > li').evaluateAll((lis) => lis.map((li) => Math.round(li.getBoundingClientRect().top)));
    if (tops.length === 5) expect(new Set(tops).size).toBe(1);
    // "Why this works" on a day is a whole tap high
    expect((await day.locator('.trip-day-why summary').boundingBox())!.height).toBeGreaterThanOrEqual(44);

    // the review of 24 November. One count: the heading counts what the bar counts, the pieces and the basics (47)
    const heading = (await pack.innerText()).replace(/\s+/g, ' ');
    const [pieces, basics] = (heading.match(/(\d+) pieces? and (\d+) basics?/) ?? []).slice(1).map(Number);
    expect(pieces + basics).toBe(mild.lines.length);
    await expect(page.getByTestId('trip-progress')).toContainText(`0 of ${mild.lines.length} packed`);
    // Day by day on a phone: the pictures alone, no cut names; a tap opens the piece's sheet, which names it (48)
    await expect(day.locator('.trip-day-name').first()).toBeHidden();
    const piece = day.locator('.trip-day-pieces > li').first().getByRole('button');
    const named = (await piece.getAttribute('aria-label'))!;
    await piece.click();
    await expect(page.getByRole('dialog', { name: named.replace(/^[^:]+: /, '') })).toBeVisible();
    await page.keyboard.press('Escape');
    // the word tally: each day's temperature is in the strip at the top, not again in Day by day; "Why these counts"
    // is closed
    await expect(page.getByTestId('trip-day').first()).not.toContainText('14–20°C');
    await expect(page.locator('.trip-weather')).toContainText('14–20°C');
    await expect(page.locator('details.trip-why')).not.toHaveAttribute('open', '');
    // the list names the days with a warning in the trip's own words (49)
    if (mild.plan.warnings.length) {
      await page.goto('/trips');
      await expect(page.getByTestId('trip-card').first()).toContainText(/days? ha(s|ve) something to watch for/);
      await expect(page.locator('main')).not.toContainText('dressed with');
    }

    // the weather service out of reach (as in the tests): the days are not dressed, and that is said once
    const unknown = await (await page.request.post('/api/trips', { data: { place: PLACE, first_day: futureDay(3), last_day: futureDay(6) } })).json();
    ids.push(unknown.id);
    await page.goto(`/trips/${unknown.id}`);
    await expect(page.getByRole('heading', { name: /What to pack/ })).toBeVisible();
    await expect(page.getByText(/not known yet, so nothing was chosen/)).toHaveCount(unknown.weather_message ? 0 : 1);
    if (unknown.weather_message) await expect(page.getByText(unknown.weather_message)).toHaveCount(1);
  } finally {
    for (const id of ids) await page.request.delete(`/api/trips/${id}`);
  }
});

test('laundry on the trip and the explained counts', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await stubTripWeather(page);
  let tripId: string | null = null;
  try {
    await page.goto('/trips/new');
    await page.getByLabel('Where are you going?').fill('Lisbon');
    await page.getByRole('button', { name: 'Search' }).click();
    await page.getByRole('button', { name: PLACE.name }).click();
    const first = futureDay(7);
    await page.getByLabel('First day').fill(first);
    await page.getByLabel('Last day').fill(futureDay(13));

    const laundry = page.getByRole('group', { name: 'Laundry on the trip' });
    await expect(laundry.getByRole('button', { name: 'No laundry' })).toHaveAttribute('aria-pressed', 'true');
    await laundry.getByRole('button', { name: 'On one day' }).click();
    await expect(page.getByLabel('Laundry day')).toHaveValue('4');
    await page.getByRole('button', { name: 'Work out what to pack' }).click();

    // why these counts are what they are is one closed thing to open (the review's word tally of 24 November)
    await openFold(page, 'Why these counts');
    const counts = page.getByRole('list', { name: 'Why these counts' });
    // "one a day", or "each worn once" when some days wear two tops (a tee under a shirt): what is in the demo's
    // laundry today is packed for a trip a week away, which gives the planner more tops to layer
    await expect(counts).toContainText(/: (one a day|each worn once), laundry on day 4/);
    await expect(counts).toContainText('jacket: one for the whole trip');
    await expect(page.getByRole('list', { name: 'Laundry' })).toContainText(/^Wash on day 4: .* from days 1–3 are worn again from day 5\./);
    await expect(page.getByTestId('trip-day').nth(3)).toContainText('Laundry day');
    await expect(page.getByTestId('pack-line').filter({ hasText: 'Underwear' })).toContainText('laundry on day 4');

    await page.getByRole('button', { name: 'Save this trip' }).click();
    await expect(page.getByRole('heading', { name: 'Lisbon' })).toBeVisible();
    tripId = page.url().split('/').pop() ?? null;
    await expect(page.locator('.trip-header')).toContainText('Laundry on day 4');

    // changing it on the saved trip plans again for the new laundry
    const patch = page.waitForResponse((response) =>
      response.request().method() === 'PATCH' && response.url().includes(`/api/trips/${tripId}`) && response.ok());
    await page.getByRole('group', { name: 'Laundry on the trip' }).getByRole('button', { name: 'Every few days' }).click();
    await patch;
    await expect(page.locator('.trip-header')).toContainText('Laundry every 3 days');
    await openFold(page, 'Why these counts');
    await expect(page.getByRole('list', { name: 'Why these counts' })).toContainText('laundry every 3 days');
    await expect(page.getByLabel('How often')).toHaveValue('3');
  } finally {
    if (tripId) await page.request.delete(`/api/trips/${tripId}`);
  }
});

test('"Before it needs washing" is set in Settings, per kind of clothing', async ({ page }) => {
  await goToCloset(page);
  try {
    await page.goto('/settings');
    // Settings → Everyday, folded under the laundry
    const section = page.getByTestId('rewear');
    await section.getByText('Wears between washes').click();
    const tops = section.getByLabel('Shirts, tees and polos');
    await expect(tops).toHaveValue('1');
    await expect(section.getByLabel('Knitwear and sweatshirts')).toHaveValue('3');
    await expect(section.getByLabel('Trousers and shorts')).toHaveValue('3');
    await expect(section.getByLabel('Jackets and coats')).toHaveValue('');
    await expect(section.getByLabel('Underwear, socks and basics')).toHaveValue('1');
    const saved = page.waitForResponse((r) => r.request().method() === 'PUT' && r.url().endsWith('/api/settings') && r.ok());
    await tops.selectOption({ label: 'Worn up to 2 times' });
    await saved;
    await page.reload();
    await section.getByText('Wears between washes').click();
    await expect(section.getByLabel('Shirts, tees and polos')).toHaveValue('2');
    const settings = await (await page.request.get('/api/settings')).json();
    expect(settings.rewear).toEqual({ tops: 2, knits: 3, bottoms: 3, outer: null, basics: 1 });
  } finally {
    await page.request.put('/api/settings', { data: { rewear: null } });
  }
});

test('a saved trip names archived and deleted pieces and offers to plan again', async ({ page }) => {
  await goToCloset(page);
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
  await goToCloset(page);
  await useProfile(page, 'demo');
  const first = futureDay(8);
  const weather = tripWeather(first, first);
  const response = await page.request.post('/api/trips', {
    data: { place: PLACE, first_day: first, last_day: first, weather },
  });
  const trip = await response.json();
  try {
    await page.goto('/trips');
    // the demo closet's own saved trip, and this one
    await expect(page.getByTestId('trip-card')).toHaveCount(2);
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

for (const viewport of [{ name: 'computer', width: 1280, height: 800 }, { name: 'phone', width: 390, height: 844 }]) {
  test(`a trip's days shown as worn on ${viewport.name}, remembered with Today's choice`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await goToCloset(page);
    await useProfile(page, 'demo');
    const first = futureDay(9);
    const last = futureDay(11);
    const response = await page.request.post('/api/trips', {
      data: { place: PLACE, first_day: first, last_day: last, weather: tripWeather(first, last) },
    });
    const trip = await response.json();
    try {
      await page.goto(`/trips/${trip.id}`);
      const days = page.getByTestId('trip-day');
      await expect(days).toHaveCount(3);
      await expect(days.first().getByRole('list', { name: /^What to wear on / })).toBeVisible();

      const show = page.getByRole('group', { name: "Show each day's outfit" });
      await expect(show.getByRole('button', { name: 'Pieces' })).toHaveAttribute('aria-pressed', 'true');
      await show.getByRole('button', { name: 'As worn' }).click();
      await expect(show.getByRole('button', { name: 'As worn' })).toHaveAttribute('aria-pressed', 'true');

      // each day's outfit drawn as worn by the server, in place of its pieces
      for (let i = 0; i < 3; i++) {
        const figure = days.nth(i).getByTestId('outfit-figure').getByRole('img', { name: /^What to wear on .*, as worn: / });
        await expect(figure).toBeVisible();
        await expect.poll(() => figure.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(100);
        await expect(days.nth(i).getByRole('list', { name: /^What to wear on / })).toHaveCount(0);
      }
      const height = (await days.first().getByTestId('outfit-figure').getByRole('img').boundingBox())!.height;
      expect(height).toBeGreaterThan(200);
      expect(height).toBeLessThanOrEqual(311);
      await page.getByRole('heading', { name: 'Day by day' }).evaluate((h) => { h.scrollIntoView({ block: 'start' }); window.scrollBy(0, -90); });
      await page.screenshot({ path: test.info().outputPath(`trip-as-worn-${viewport.name}.png`) });

      // remembered on this device, and the same choice as Today's
      await page.reload();
      await expect(page.getByTestId('trip-day').first().getByTestId('outfit-figure').getByRole('img')).toBeVisible();
      await page.goto('/today');
      const today = page.getByRole('region', { name: "Today's outfits" }).getByRole('group', { name: 'Show the outfit' });
      await expect(today.getByRole('button', { name: 'As worn' })).toHaveAttribute('aria-pressed', 'true');
      await today.getByRole('button', { name: 'Pieces' }).click();
      await page.goto(`/trips/${trip.id}`);
      await expect(page.getByTestId('trip-day').first().getByRole('list', { name: /^What to wear on / })).toBeVisible();
      await expect(page.getByTestId('outfit-figure')).toHaveCount(0);
    } finally {
      await page.request.delete(`/api/trips/${trip.id}`);
    }
  });
}

test('swimming or the beach: on by itself for a hot trip, kept off when turned off, and swim trunks packed for it', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  const closet = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string; category: string }[];
  // the demo's shorts, or a pair of its trousers when an earlier test of this file archived them
  const shorts = closet.find((i) => i.category === 'shorts') ?? closet.filter((i) => i.category === 'trousers').at(-1)!;
  const first = futureDay(8);
  const last = futureDay(10);
  const hot = tripWeather(first, last).map((d) => ({ ...d, low_c: 22, high_c: 30 }));
  const response = await page.request.post('/api/trips', { data: { place: PLACE, first_day: first, last_day: last, weather: hot } });
  const trip = await response.json();
  const patched = () => page.waitForResponse((r) =>
    r.request().method() === 'PATCH' && r.url().includes(`/api/trips/${trip.id}`) && r.ok());
  try {
    // no swim trunks in the closet yet: the trip says so, and packs nothing in their place
    await page.goto(`/trips/${trip.id}`);
    const options = page.getByRole('region', { name: 'Change the trip' });
    const swim = options.getByRole('switch', { name: 'Swimming or the beach' });
    await expect(swim).toBeChecked();
    await expect(options).toContainText('It is on because 3 days reach 27°C.');
    await expect(page.getByTestId('swim-missing')).toContainText('You have no swim trunks in your closet.');
    await page.getByTestId('swim-missing').scrollIntoViewIfNeeded();
    await page.screenshot({ path: test.info().outputPath('trip-swim-none.png') });

    // the demo's shorts said to be swim trunks: planned again, they are packed for swimming and worn on no day
    expect((await page.request.put(`/api/items/${shorts.id}/kind`, { data: { kind: 'swim_trunks' } })).ok()).toBe(true);
    const replanned = patched();
    await options.getByRole('button', { name: 'Plan again' }).click();
    await replanned;
    await expect(page.getByRole('list', { name: 'For swimming' })).toContainText(shorts.name);
    await expect(page.getByTestId('swim-missing')).toHaveCount(0);
    await expect(page.getByTestId('trip-day').filter({ hasText: shorts.name })).toHaveCount(0);
    await openFold(page, 'Why these counts');
    await expect(page.getByRole('list', { name: 'Why these counts' })).toContainText('1 pair of swim trunks: one for a trip of up to a week');
    await page.getByRole('list', { name: 'For swimming' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: test.info().outputPath('trip-swim-packed.png') });
    await options.scrollIntoViewIfNeeded();
    await page.screenshot({ path: test.info().outputPath('trip-swim-on.png') });

    // turned off, it stays off when the trip is planned again, however hot
    const off = patched();
    await swim.click();
    await off;
    await expect(swim).not.toBeChecked();
    await expect(options).toContainText('You turned it off. It stays off whatever the forecast.');
    await expect(page.getByRole('list', { name: 'For swimming' })).toHaveCount(0);
    const again = patched();
    await options.getByRole('button', { name: 'Plan again' }).click();
    await again;
    await expect(swim).not.toBeChecked();
    // and given back to the forecast, it is on again for the hot days
    const back = patched();
    await options.getByRole('button', { name: 'Follow the forecast again' }).click();
    await back;
    await expect(swim).toBeChecked();
    await expect(options).toContainText('It is on because 3 days reach 27°C.');
    await expect(options.getByRole('button', { name: 'Follow the forecast again' })).toHaveCount(0);

    // tennis on the trip: the demo's sneakers said to be tennis shoes are packed beside the days, worn on none
    const sneakers = closet.find((i) => i.category === 'sneakers')!;
    const kindBefore = ((await (await page.request.get(`/api/items/${sneakers.id}`)).json()) as { kind: string | null }).kind;
    expect((await page.request.put(`/api/items/${sneakers.id}/kind`, { data: { kind: 'tennis_shoe' } })).ok()).toBe(true);
    try {
      const tennis = patched();
      await options.getByRole('group', { name: 'Playing on the trip' }).getByRole('button', { name: 'Tennis' }).click();
      await tennis;
      await expect(options.getByRole('button', { name: 'Tennis' })).toHaveAttribute('aria-pressed', 'true');
      await expect(page.getByRole('list', { name: 'Shoes' })).toContainText(sneakers.name);
      await expect(page.getByTestId('trip-day').filter({ hasText: sneakers.name })).toHaveCount(0);
    } finally {
      if (kindBefore) await page.request.put(`/api/items/${sneakers.id}/kind`, { data: { kind: kindBefore } });
      else await page.request.patch(`/api/items/${sneakers.id}`, { data: { category: 'boots' } }).then(() =>
        page.request.patch(`/api/items/${sneakers.id}`, { data: { category: 'sneakers' } }));   // drops the kind
    }

    // a new trip on cool days: off until turned on, and turning it on packs them
    await stubTripWeather(page);
    await page.goto('/trips/new');
    await page.getByLabel('Where are you going?').fill('Lisbon');
    await page.getByRole('button', { name: 'Search' }).click();
    await page.getByRole('button', { name: PLACE.name }).click();
    const form = page.getByRole('region', { name: 'The trip' });
    const choice = form.getByRole('switch', { name: 'Swimming or the beach' });
    await page.getByRole('button', { name: 'Work out what to pack' }).click();
    await expect(page.getByRole('heading', { name: /What to pack/ })).toBeVisible();
    await expect(choice).not.toBeChecked();
    await expect(form).toContainText('It turns on by itself when a day reaches 27°C.');
    await choice.click();
    await page.getByRole('button', { name: 'Work out what to pack' }).click();
    await expect(page.getByRole('list', { name: 'For swimming' })).toContainText(shorts.name);
    await expect(choice).toBeChecked();
    await expect(form).toContainText('You turned it on, so your swim trunks are packed.');
  } finally {
    await page.request.delete(`/api/trips/${trip.id}`);
    if (shorts.category === 'shorts') await page.request.put(`/api/items/${shorts.id}/kind`, { data: { kind: 'shorts' } });
    else await page.request.patch(`/api/items/${shorts.id}`, { data: { category: shorts.category } });   // drops the kind
  }
});

test('a new trip whose weather cannot be looked up says so once, with Try again and a way to type the temperatures', async ({ page }) => {
  // the review of 24 November, 51: it said so four ways, offered a packing list of nothing, and Save
  await page.setViewportSize({ width: 375, height: 667 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.route('**/api/places?*', (route) => route.fulfill({ json: { places: [PLACE] } }));
  let tripId: string | null = null;
  try {
    await page.goto('/trips/new');
    // what is sent to look up the weather is one closed thing to open, after the search (it was 30 words in the
    // form: the review of 24 November, 50)
    await expect(page.getByLabel('Where are you going?')).toBeVisible();
    await expect(page.getByText(/Nines sends Open-Meteo/)).toBeHidden();
    await expect(page.locator('details.where-sent summary')).toHaveText('What is sent to look up the weather');
    await page.getByLabel('Where are you going?').fill('Lisbon');
    await page.getByRole('button', { name: 'Search' }).click();
    await page.getByRole('button', { name: PLACE.name }).click();
    await page.getByLabel('First day').fill(futureDay(3));
    await page.getByLabel('Last day').fill(futureDay(5));
    await page.getByRole('button', { name: 'Work out what to pack' }).click();   // the test backend reaches no weather
    const none = page.getByTestId('trip-no-weather');
    await expect(none).toContainText("Couldn't reach the weather service");
    await expect(none.getByRole('button', { name: 'Try again' })).toBeVisible();
    await expect(page.getByRole('heading', { name: /What to pack/ })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Day by day' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save this trip' })).toHaveCount(0);
    await expect(page.locator('main')).not.toContainText('Not known yet');
    await expect(page.locator('main')).not.toContainText('left out of the plan');

    // the temperatures typed for each day: the plan is worked out with them, and can be saved
    await none.getByRole('button', { name: 'Type the temperatures' }).click();
    const sheet = page.getByRole('dialog', { name: 'Type the temperatures' });
    for (const low of await sheet.getByLabel('Low').all()) await low.fill('12');
    for (const high of await sheet.getByLabel('High').all()) await high.fill('19');
    await sheet.getByRole('button', { name: 'Work out what to pack' }).click();
    await expect(page.getByRole('heading', { name: /What to pack/ })).toBeVisible();
    await expect(page.locator('.trip-weather')).toContainText('Your temperatures');
    await expect(page.locator('.trip-weather')).toContainText('12–19°C');
    await page.getByRole('button', { name: 'Save this trip' }).click();
    await expect(page.getByRole('heading', { name: 'Lisbon' })).toBeVisible();
    tripId = page.url().split('/').pop() ?? null;
    await expect(page.locator('.trip-weather')).toContainText('Your temperatures');
  } finally {
    if (tripId) await page.request.delete(`/api/trips/${tripId}`);
  }
});
