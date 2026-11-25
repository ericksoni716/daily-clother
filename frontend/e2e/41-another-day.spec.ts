import type { Page, Route } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, hitArea, serviceWorkerInCharge, test, useProfile } from './fixtures';

// Dress for another day, on a phone: the sheet of days, a day's own view, "Wear this on <day>" (a plan, not a wear),
// taking the plan away with Undo, the morning of a planned day, a day inside the trip, and a plan shown offline.

const PHONE = { width: 375, height: 740 };

test.afterEach(async ({ page, context }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await context.setOffline(false);
  for (const p of (await (await page.request.get('/api/plans')).json()).plans as { day: string }[]) {
    await page.request.delete(`/api/plans/${p.day}`);
  }
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

function localDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function openDemo(page: Page) {
  await page.setViewportSize(PHONE);
  await goToCloset(page);
  await useProfile(page, 'demo');
  // the demo comes with a day planned three days ahead; these tests plan their own
  await page.request.delete(`/api/plans/${localDay(3)}`);
  await page.goto('/today');
  await expect(page.locator('#today-title')).toBeVisible();
}

const current = (page: Page) => page.getByTestId('current-outfit');
const planLine = (page: Page) => page.getByTestId('plan-line');

test('another day: the sheet, the day in Today\'s layout, "Wear this tomorrow", and the plan taken away with Undo', async ({ page }) => {
  await openDemo(page);
  await page.request.put(`/api/plans/${localDay(3)}`, { data: { pieces: await firstOutfit(page) } });
  await page.reload();
  await page.getByTestId('another-day').click();
  const sheet = page.getByRole('dialog', { name: 'Dress for another day' });
  await expect(sheet).toBeVisible();
  const days = sheet.getByRole('list', { name: 'The next days' }).getByRole('button');
  await expect(days).toHaveCount(6);
  await expect(days.first()).toHaveText('Tomorrow');
  await expect(days.nth(2)).toContainText('Planned');   // three days ahead
  // the sheet sits over the page, inside the phone
  expect((await sheet.getByRole('button', { name: 'Dress for this day' }).boundingBox())!.y).toBeLessThan(PHONE.height);
  expect(await axeViolations(page)).toEqual([]);
  await days.first().click();

  await expect(page).toHaveURL(new RegExp(`/today/day/${localDay(1)}$`));
  await expect(page.getByRole('link', { name: 'Today' }).first()).toBeVisible();
  // no weather can be had in the browser tests: said once, in one short line with Try again, and the day is dressed as
  // a mild one
  await expect(page.getByTestId('day-line')).toContainText('a mild day');
  const noWeather = page.getByTestId('ahead-no-weather');
  await expect(noWeather).toHaveText('No forecast for that day. Try again');
  await expect(noWeather.getByRole('button', { name: 'Try again' })).toBeEnabled();
  await expect(planLine(page)).toHaveText('Nothing planned yet.');   // the heading names the day
  await expect(page.getByTestId('recent-outfits')).toHaveCount(0);
  const wear = current(page).getByRole('button', { name: 'Wear this tomorrow' });
  await expect(wear).toBeVisible();
  // where the outfit sits under the heading: it must not move when the plan changes (a tap may scroll the page itself)
  const offset = async () => (await current(page).boundingBox())!.y - (await page.locator('#today-title').boundingBox())!.y;
  const before = await offset();

  await wear.click();
  await expect(page.locator('.toast', { hasText: 'Planned for tomorrow. That morning, Today opens on it.' })).toBeVisible();
  await expect(current(page).getByTestId('planned-day')).toHaveText('Planned');   // the heading names the day
  // one thing, one home: the planned outfit has Remove the plan, and the line over it is the way to other outfits
  await expect(planLine(page)).toHaveText('See other outfits');
  await expect(page.getByRole('button', { name: 'Remove the plan' })).toHaveCount(1);
  // the page holds still (once the day has opened on its plan)
  await expect.poll(offset).toBe(before);
  // a plan, not a wear: nothing worn today
  const worn = (await (await page.request.get('/api/outfits/worn?limit=1')).json()).outfits as { worn_on: string }[];
  expect(worn[0]?.worn_on).not.toBe(localDay(1));

  await current(page).getByRole('button', { name: 'Remove the plan' }).click();
  await expect(planLine(page)).toContainText('The plan for tomorrow is gone.');
  await expect.poll(offset).toBe(before);
  await planLine(page).getByRole('button', { name: 'Undo' }).click();
  await expect(current(page).getByTestId('planned-day')).toHaveText('Planned');
  await expect(page.getByRole('button', { name: 'Remove the plan' })).toHaveCount(1);

  // back to today, where the plans of the coming week are one line leading to each day
  await page.getByRole('link', { name: 'Today' }).first().click();
  await expect(page.locator('#today-title')).toHaveText('Today');
  const soon = page.getByTestId('plans-soon');
  await expect(soon).toContainText('Tomorrow');
  await expect(soon).toContainText('are planned.');
  await soon.getByRole('link', { name: 'Tomorrow' }).click();
  await expect(page).toHaveURL(new RegExp(`/today/day/${localDay(1)}$`));
  await expect(current(page).getByTestId('planned-day')).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);
});

for (const weather of ['a forecast', 'no forecast']) {
  test(`a day ahead on the smallest phone, with ${weather}: five pieces and its button are on the first screen, planned or not`, async ({ page }) => {
    // as Today's own first screen (10-today.spec.ts): the phone check's smallest phone, an iPhone 13 mini with Safari's
    // bars. Before, the reason for the day's weather ran to three lines and, with the plan's line, pushed the pieces and
    // the button under the tab bar.
    await openDemo(page);
    await page.setViewportSize({ width: 375, height: 629 });
    const day = localDay(2);
    await page.route('**/api/outfits/today', async (route: Route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const response = await route.fetch(weather === 'a forecast' ? { postData: { ...body, low_c: 14, high_c: 20, rain: false } } : undefined);
      const json = await response.json();
      if (response.ok()) {
        json.outfits = json.outfits.filter((o: { pieces: Record<string, unknown> }) => Object.values(o.pieces).flat().filter(Boolean).length === 5);
        if (weather === 'a forecast') {
          Object.assign(json.context, { source: 'forecast', place: 'Brooklyn, New York, United States', rain_chance: 10, message: null });
          delete json.context.retry;
        }
      }
      await route.fulfill({ response, json });
    });
    const shoot = async (name: string, button: string) => {
      await expect(current(page).getByTestId('piece')).toHaveCount(5);
      await expect(page.getByTestId('ahead-no-weather')).toHaveCount(weather === 'a forecast' ? 0 : 1);
      // each line over the outfit is one line
      for (const line of [page.getByTestId('plan-line'), ...(weather === 'a forecast' ? [] : [page.getByTestId('ahead-no-weather')])]) {
        const lines = await line.evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
        expect(lines).toBeLessThan(1.5);
      }
      await page.screenshot({ path: test.info().outputPath(`day-first-screen-${weather.replace(' ', '-')}-${name}.png`) });
      const tabbar = (await page.locator('nav.tabbar').boundingBox())!;
      const main = (await current(page).getByRole('button', { name: button }).boundingBox())!;
      const room = tabbar.y - (main.y + main.height);
      expect(room).toBeGreaterThanOrEqual(16);
      for (const piece of await current(page).getByTestId('piece').all()) {
        const b = (await piece.boundingBox())!;
        expect(b.y + b.height).toBeLessThanOrEqual(main.y);
      }
    };

    await page.goto(`/today/day/${day}`);
    await expect(planLine(page)).toHaveText('Nothing planned yet.');
    const wear = current(page).getByRole('button', { name: /^Wear this on / });
    await expect(wear).toBeVisible();
    await shoot('not-planned', (await wear.textContent())!.trim());

    // planned: the outfit says so where its button was, and the line over it is the way to other outfits
    await page.request.put(`/api/plans/${day}`, { data: { pieces: await outfitOf(page) } });
    await page.reload();
    await expect(current(page).getByTestId('planned-day')).toBeVisible();
    await expect(planLine(page)).toHaveText('See other outfits');
    await shoot('planned', 'Remove the plan');
    expect(await axeViolations(page)).toEqual([]);
  });
}

/** An outfit of five pieces the rules offer for the day two days ahead, as pieces. */
async function outfitOf(page: Page) {
  const r = await page.request.post('/api/outfits/today', { data: { day: localDay(2), low_c: 14, high_c: 20, rain: false } });
  const outfits = (await r.json()).outfits as { pieces: Record<string, unknown> }[];
  return outfits.find((o) => Object.values(o.pieces).flat().filter(Boolean).length === 5)!.pieces;
}

/** The first outfit Today offers, as pieces. */
async function firstOutfit(page: Page) {
  const r = await page.request.post('/api/outfits/today', { data: { low_c: 9, high_c: 16, rain: false } });
  return (await r.json()).outfits[0].pieces as Record<string, unknown>;
}

test('the outfit heading never breaks inside its words, and a day ahead\'s weather reason stays clear of its weather, from 320 to 430', async ({ page }) => {
  // at 375 it read "Best for this / day · 1 of 3"; the words and the count each stay whole, whatever the width
  await openDemo(page);
  const whole = async (where: string) => {
    const head = page.locator('.today-outfits-head h2');
    await expect(head).toBeVisible();
    const lines = await head.evaluate((h2) => [...h2.childNodes].map((n) => {
      const r = document.createRange();
      r.selectNodeContents(n);
      const tops = new Set([...r.getClientRects()].filter((b) => b.width > 1).map((b) => Math.round(b.top)));
      return { text: n.textContent ?? '', lines: tops.size };
    }));
    for (const l of lines) expect(l.lines, `${where}: "${l.text}" breaks inside`).toBeLessThanOrEqual(1);
  };
  for (const width of [320, 375, 393, 430]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto('/today');
    await whole(`Today at ${width}`);
    // Another day never runs into Today's date (it did at 320)
    const date = (await page.locator('.today-header .count').boundingBox())!;
    const another = (await page.getByTestId('another-day').boundingBox())!;
    expect(another.x >= date.x + date.width || another.y >= date.y + date.height, `Today at ${width}`).toBe(true);
    await page.goto(`/today/day/${localDay(2)}`);
    await whole(`a day ahead at ${width}`);
    // no weather in the tests: the reason under the weather line never meets it (at 320 "a mild day" once wrapped into it)
    const parts = (await page.locator('.today-day-parts span').last().boundingBox())!;
    const reason = (await page.getByTestId('ahead-no-weather').boundingBox())!;
    expect(parts.y + parts.height, `a day ahead at ${width}`).toBeLessThanOrEqual(reason.y + 2);   // line boxes may touch by a pixel; the words do not
  }
});

test('at 320 the planned mark and Remove the plan never overlap', async ({ page }) => {
  // in a picture of the demo's planned day at 320, "Planned" once read "Plannec" under the button's edge
  await openDemo(page);
  await page.setViewportSize({ width: 320, height: 568 });
  const day = localDay(2);
  await page.request.put(`/api/plans/${day}`, { data: { pieces: await firstOutfit(page) } });
  await page.goto(`/today/day/${day}`);
  // the word as drawn, not its box: a box can shrink while its word runs on under the button
  const mark = await current(page).getByTestId('planned-day').evaluate((el) => {
    const r = document.createRange();
    r.selectNodeContents(el);
    const b = r.getBoundingClientRect();
    return { x: b.x, y: b.y, width: b.width, height: b.height };
  });
  const remove = (await current(page).getByRole('button', { name: 'Remove the plan' }).boundingBox())!;
  const apart = mark.x + mark.width <= remove.x || remove.x + remove.width <= mark.x
    || mark.y + mark.height <= remove.y || remove.y + remove.height <= mark.y;
  expect(apart).toBe(true);
  const card = (await current(page).boundingBox())!;
  expect(mark.x + mark.width).toBeLessThanOrEqual(card.x + card.width);
});

test('a planned piece that is away is swapped without moving the outfit, and a piece due back first is counted on in one line', async ({ page }) => {
  await openDemo(page);
  const day = localDay(2);
  const pieces = await firstOutfit(page) as Record<string, string | null>;
  const away = (pieces.bottom ?? pieces.base)!;
  try {
    // lent out with no day said: not back by then, so the plan's place is filled and the piece is named with where it is
    await page.request.put(`/api/items/${away}/away`, { data: { place: 'lent' } });
    await page.request.put(`/api/plans/${day}`, { data: { pieces } });
    await page.goto(`/today/day/${day}`);
    await expect(current(page).getByTestId('plan-swapped')).toContainText('lent out, so another piece takes its place.');
    const lines = await planLine(page).evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
    expect(lines).toBeLessThan(1.5);   // the line over the outfit keeps its one line
    await expect(planLine(page)).toHaveText('See other outfits');

    // expected back the day before: offered again, and the day says it counts on it being back
    const before = localDay(1);
    await page.request.put(`/api/items/${away}/away`, { data: { place: 'cleaner', until: before } });
    await page.reload();
    await expect(current(page).getByTestId('planned-day')).toBeVisible();
    await expect(current(page).getByTestId('plan-swapped')).toHaveCount(0);
    const counts = current(page).getByTestId('counts-on');
    await expect(counts).toHaveText(/^This counts on your .+ being back by then\.$/);
  } finally {
    await page.request.post(`/api/items/${away}/back`);
  }
});

test('another day: a word about the day says what is sent, as today\'s does', async ({ page }) => {
  await openDemo(page);
  await page.goto(`/today/day/${localDay(2)}`);
  await page.getByTestId('day-line').getByRole('button', { name: 'Change' }).click();
  const sheet = page.getByTestId('day-sheet');
  await expect(sheet.getByText('Claude reads this one sentence to find the place and the hours. Nothing from your closet is sent.')).toBeVisible();
  await sheet.getByTestId('day-note-text').fill('Dinner at eight');
  await sheet.getByRole('button', { name: 'Save' }).click();
  // the demo closet never asks Claude, here as on today
  await expect(sheet.getByTestId('day-note-message')).toContainText('The demo closet never asks Claude');
});

test('the morning of a planned day: Today opens on the plan, says a piece was swapped, and other outfits are a tap away', async ({ page }) => {
  await page.setViewportSize(PHONE);
  const asked: Record<string, unknown>[] = [];
  // the server's clock cannot be moved here: its answer is given the plan it gives on the morning of the day
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    asked.push(body);
    const response = await route.fetch({ postData: { low_c: 9, high_c: 16, rain: false, ...body } });
    const json = await response.json();
    if (response.ok() && body.planned !== false && !body.day) {
      const p = json.outfits[0].pieces;
      json.context.plan = { day: localDay(), kept: [p.bottom, p.shoes], unavailable: [p.base], note: 'Dinner at eight' };
      json.context.held = { [p.shoes]: localDay(4) };
    }
    await route.fulfill({ response, json });
  });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  await expect(planLine(page)).toContainText('You planned this outfit for today. “Dinner at eight”');
  // the swapped piece is said under the outfit's button, where a longer sentence moves nothing
  await expect(current(page).getByTestId('plan-swapped')).toContainText("can't be worn today, so another piece takes its place.");
  await expect(current(page).getByRole('button', { name: "I'm wearing this" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('morning-of-a-planned-day.png') });
  // a planned piece Today keeps out of the laundry's way says so, asked for by name
  const shoes = current(page).locator('.today-piece', { has: page.locator('.today-piece-place', { hasText: 'Shoes' }) }).locator('.today-piece-more');
  await shoes.click();
  await expect(page.getByTestId('held-line')).toContainText('Wearing it now would leave it in the laundry by then.');
  await expect(page.getByRole('button', { name: 'Build around it anyway' })).toBeVisible();
  await page.keyboard.press('Escape');

  await planLine(page).getByRole('button', { name: 'See other outfits' }).click();
  await expect(planLine(page)).toContainText('These are other outfits than the one you planned.');   // the morning's words
  expect(asked.at(-1)!.planned).toBe(false);
  await planLine(page).getByRole('button', { name: 'Back to your plan' }).click();
  await expect(planLine(page)).toContainText('You planned this outfit for today.');
});

test('a plan that would empty Today gives way: the outfit uses its piece and says so once, under its button', async ({ page }) => {
  await page.setViewportSize(PHONE);
  // the server gives way when holding the planned piece back leaves no outfit (test_plans.py); here its answer says so
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { low_c: 9, high_c: 16, rain: false, ...body } });
    const json = await response.json();
    if (response.ok() && !body.day && json.outfits.length) {
      const base = json.outfits[0].pieces.base;
      json.context.held = { [base]: localDay(2) };
      json.context.held_offered = [base];
    }
    await route.fulfill({ response, json });
  });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.goto('/today');
  const line = current(page).getByTestId('held-offered');
  await expect(line).toHaveText(/^This outfit uses your .+, which you planned for \w+\.$/);
  await expect(page.getByTestId('held-offered')).toHaveCount(1);
  await expect(page.getByText('left out today')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('plan-gives-way.png') });
});

test('a day inside the saved trip says the trip has its outfit, and links to it', async ({ page }) => {
  await openDemo(page);
  const trip = ((await (await page.request.get('/api/trips')).json()).trips as { id: string; first_day: string }[])[0];
  await page.goto(`/today/day/${trip.first_day}`);
  const notice = page.getByTestId('trip-day');
  await expect(notice).toContainText('This day is part of your trip to Lisbon, which has its outfit already.');
  await expect(current(page)).toHaveCount(0);
  await notice.getByRole('link', { name: 'See the trip' }).click();
  await expect(page).toHaveURL(new RegExp(`/trips/${trip.id}$`));
});

test('offline, a plan made earlier is shown from what this device kept, and cannot be changed', async ({ page, context }) => {
  await openDemo(page);
  await page.request.put(`/api/plans/${localDay(1)}`, { data: { pieces: await firstOutfit(page) } });
  await page.goto(`/today/day/${localDay(1)}`);
  await serviceWorkerInCharge(page);
  await expect(current(page).getByTestId('planned-day')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.reload();
  // laid out as online (second review of the screens, finding 28): "Planned", and Remove the plan off with why, the
  // banner saying offline once
  const planned = page.getByTestId('planned-offline');
  await expect(planned.getByTestId('planned-day')).toHaveText('Planned');
  const remove = planned.getByRole('button', { name: 'Remove the plan' });
  await expect(remove).toBeDisabled();
  await expect(remove).toHaveAttribute('title', /needs Nines on your computer/i);
  await expect(page.getByRole('heading', { name: 'Your plan for ' + ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(Date.now() + 86_400_000).getDay()] })).toBeVisible();
  await expect(planned.locator('.today-piece')).not.toHaveCount(0);
});


// ------------------------------------------------------------------ the second review of the screens (24 November)

const dots = (page: Page) => page.getByRole('group', { name: 'Choose an outfit' }).getByRole('button');

test('finding 7: any outfit that counts on a piece being back says so under its button, not only the first', async ({ page }) => {
  await openDemo(page);
  const day = localDay(1);
  // the server counts on a piece expected back before the day; here it is one only the third outfit has
  let counted = '';
  await page.route('**/api/outfits/today', async (route: Route) => {
    const response = await route.fetch();
    const json = await response.json();
    if (response.ok() && json.outfits.length >= 3) {
      const ids = (o: { pieces: Record<string, unknown> }) => Object.values(o.pieces).flat().filter(Boolean) as string[];
      const first = new Set([...ids(json.outfits[0]), ...ids(json.outfits[1])]);
      counted = ids(json.outfits[2]).find((id) => !first.has(id)) ?? '';
      json.context.expected = [counted];
    }
    await route.fulfill({ response, json });
  });
  await page.goto(`/today/day/${day}`);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  expect(counted).not.toBe('');
  await expect(current(page).getByTestId('counts-on')).toHaveCount(0);
  await dots(page).nth(2).click();
  await expect(current(page)).toHaveAttribute('aria-label', /^Outfit 3 of/);
  await expect(current(page).getByTestId('counts-on')).toHaveText(/^This counts on your .+ being back by then\.$/);
  await page.screenshot({ path: test.info().outputPath('day-third-outfit-counts-on.png') });
});

test('finding 19: a planned day is headed "Your plan for", with nothing under it', async ({ page }) => {
  await openDemo(page);
  const day = localDay(2);
  await page.request.put(`/api/plans/${day}`, { data: { pieces: await firstOutfit(page) } });
  await page.goto(`/today/day/${day}`);
  await expect(current(page).getByTestId('planned-day')).toBeVisible();
  const head = page.locator('.today-outfits-head h2');
  expect(await head.innerText()).toMatch(/^Your plan for \w{3}$/);
  await expect(page.getByText('the only outfit')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('day-planned.png') });
});

test('finding 20: a day inside the saved trip has no occasion or mood to choose', async ({ page }) => {
  await openDemo(page);
  const trip = ((await (await page.request.get('/api/trips')).json()).trips as { id: string; first_day: string }[])[0];
  await page.goto(`/today/day/${trip.first_day}`);
  await expect(page.getByTestId('trip-day')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Occasion' })).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Mood' })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('day-in-a-trip.png') });
});

test('finding 22: a day ahead whose read fails names its day, in the shared words, with one Try again', async ({ page }) => {
  await openDemo(page);
  let failing = true;
  await page.route('**/api/outfits/today', (route: Route) =>
    (failing ? route.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }) : route.fallback()));
  await page.goto(`/today/day/${localDay(1)}`);
  const failed = page.getByTestId('failed');
  await expect(failed).toContainText("Couldn't load the outfits for tomorrow.");
  await expect(page.getByText("today's outfits")).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath('day-failed.png') });
  failing = false;
  await failed.getByRole('button', { name: 'Try again' }).click();
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
});

test('finding 24: a day past 60 days says so in one sentence with the way back, and so does the days sheet', async ({ page }) => {
  await openDemo(page);
  await page.goto(`/today/day/${localDay(90)}`);
  const far = page.getByTestId('too-far');
  await expect(far).toContainText('Nines dresses days up to 60 days ahead.');
  await expect(page.getByRole('button', { name: 'Try again' })).toHaveCount(0);
  await expect(page.getByText(/Couldn't/)).toHaveCount(0);
  await far.getByRole('link', { name: 'Back to Today' }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.getByTestId('another-day').click();
  const sheet = page.getByTestId('another-day-sheet');
  await sheet.getByTestId('another-date').fill(localDay(61));
  await expect(sheet.getByText('Nines dresses days up to 60 days ahead.')).toBeVisible();
  await sheet.getByTestId('another-date').fill(localDay(20));
  await expect(sheet.getByText('Nines dresses days up to 60 days ahead.')).toHaveCount(0);
});

test('finding 18: the arrow back from a day ahead takes 44px', async ({ page }) => {
  await openDemo(page);
  await page.goto(`/today/day/${localDay(1)}`);
  await expect(current(page).getByTestId('piece').first()).toBeVisible();
  expect((await hitArea(page.locator('.today-ahead-header .page-back'))).height).toBeGreaterThanOrEqual(44);
});

test('finding 28: offline, a planned day is laid out as it is online', async ({ page, context }) => {
  await openDemo(page);
  await page.request.put(`/api/plans/${localDay(1)}`, { data: { pieces: await firstOutfit(page) } });
  await page.goto(`/today/day/${localDay(1)}`);
  await serviceWorkerInCharge(page);
  await expect(current(page).getByTestId('planned-day')).toBeVisible();
  const rowOnline = await current(page).locator('.today-piece').evaluateAll((all) => all.map((p) => Math.round(p.getBoundingClientRect().top)));
  await page.waitForLoadState('networkidle');
  await context.setOffline(true);
  await page.reload();
  const planned = page.getByTestId('planned-offline');
  await expect(planned).toBeVisible();
  const rowOffline = await planned.locator('.today-piece').evaluateAll((all) => all.map((p) => Math.round(p.getBoundingClientRect().top)));
  // as many to a row as online (four on a phone), and no layer written over the names
  expect(rowOffline.filter((t) => t === rowOffline[0]).length).toBe(rowOnline.filter((t) => t === rowOnline[0]).length);
  for (const place of await planned.locator('.today-piece-place').all()) expect((await place.boundingBox())!.width).toBeLessThanOrEqual(1);
  await expect(planned.getByTestId('planned-day')).toHaveText('Planned');
  await expect(planned.getByRole('button', { name: 'Remove the plan' })).toBeDisabled();
  await page.screenshot({ path: test.info().outputPath('day-planned-offline.png') });
});
