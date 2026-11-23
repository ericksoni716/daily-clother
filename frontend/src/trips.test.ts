import { describe, expect, it } from 'vitest';
import { forgetSaved } from './today';
import {
  addDays, checkDates, dateRange, dayCount, dayRain, dayTemps, fitLaundry, groupPacked, laundryDays, laundryEvery, laundryMode,
  laundryWords, progress, REWEAR_KINDS, rewearWords, shortDay, sourceLabel, sourceRuns, startLaundry, swimHint, swimOn, toggleSport,
  loadSavedTrips, sameReasons, saveTrips, tripProblems,
  tripComingUp, tripDays, tripTitle, upcomingFirst, wornWords, type TripDay, type TripSummary,
} from './trips';

const day = (date: string, source: TripDay['source'], extra: Partial<TripDay> = {}): TripDay => ({
  date, low_c: 5, high_c: 11, rain: false, rain_chance: null, summary: null, source, ...extra,
});

describe('trips', () => {
  it('keeps offline trip copies separately for each closet', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
      removeItem: (key: string) => { values.delete(key); },
      clear: () => { values.clear(); },
      key: (index: number) => [...values.keys()][index] ?? null,
      get length() { return values.size; },
    } as Storage;
    const demoTrip = { id: 'demo-trip' } as TripSummary;

    saveTrips('demo', { list: [demoTrip] }, storage);
    saveTrips('main', { list: [] }, storage);

    expect(loadSavedTrips('demo', storage)?.list).toEqual([demoTrip]);
    expect(loadSavedTrips('main', storage)?.list).toEqual([]);
    forgetSaved(storage);
    expect(values.size).toBe(0);
  });

  it('counts what is packed out of the lines still in the plan', () => {
    expect(progress(['item:a', 'item:b', 'basic:socks'], ['item:a']).words).toBe('1 of 3 packed');
    expect(progress(['item:a'], ['item:a', 'item:gone']).words).toBe('All 1 packed');
    expect(progress([], []).words).toBe('0 of 0 packed');
  });

  it('says where each day of weather comes from, in runs', () => {
    expect(sourceLabel('forecast')).toBe('Forecast');
    expect(sourceLabel('usual')).toBe('Usually, on these dates');
    expect(sourceLabel('unknown')).toBe('Not known yet');
    const runs = sourceRuns([day('2026-12-01', 'forecast'), day('2026-12-02', 'forecast'), day('2026-12-03', 'usual')]);
    expect(runs.map((r) => [r.label, r.days.length])).toEqual([['Forecast', 2], ['Usually, on these dates', 1]]);
  });

  it('describes a day of weather in plain words', () => {
    expect(dayTemps(day('2026-12-01', 'unknown', { low_c: null, high_c: null }))).toBe('Not known yet');
    expect(dayRain(day('2026-12-01', 'usual', { rain: true, rain_chance: 60 }))).toBe('Rainy 60% of years');
    expect(dayRain(day('2026-12-01', 'forecast', { rain: true }))).toBe('Rain likely');
    expect(dayRain(day('2026-12-01', 'unknown', { rain: null }))).toBe('');
  });

  it('works with dates without time zones getting in the way', () => {
    expect(dayCount('2026-12-30', '2027-01-02')).toBe(4);
    expect(dayCount('2026-12-03', '2026-12-01')).toBe(0);
    expect(addDays('2026-02-28', 1)).toBe('2026-03-01');
    expect(tripDays('2026-12-30', '2027-01-01')).toEqual(['2026-12-30', '2026-12-31', '2027-01-01']);
    expect(shortDay('2026-12-01')).toEqual({ weekday: 'Tue', date: '1 Dec' });
    expect(dateRange('2026-12-01', '2026-12-05')).toBe('1–5 Dec');
    expect(dateRange('2026-11-28', '2026-12-03')).toBe('28 Nov – 3 Dec');
    expect(dateRange('2026-12-28', '2027-01-03')).toBe('28 Dec 2026 – 3 Jan 2027');
    expect(tripTitle({ place: { name: 'Lisbon, Portugal', latitude: 0, longitude: 0, timezone: 'UTC' }, first_day: '2026-12-01', last_day: '2026-12-05' }))
      .toMatch(/^Lisbon.*, 1–5 Dec$/);
  });

  it('checks the dates in the owner\'s words', () => {
    expect(checkDates('', '2026-12-01', '2026-11-13')).toMatch(/Choose/);
    expect(checkDates('2026-12-05', '2026-12-01', '2026-11-13')).toMatch(/before its first day/);
    expect(checkDates('2026-11-01', '2026-11-20', '2026-11-13')).toMatch(/today or later/);
    expect(checkDates('2026-12-01', '2026-12-31', '2026-11-13')).toMatch(/at most 30 days/);
    expect(checkDates('2026-12-01', '2026-12-30', '2026-11-13')).toBeNull();
  });

  it('groups packed pieces in a fixed order and words how often each is worn', () => {
    const groups = groupPacked([
      { id: 'b', group: 'shoes', days: 3, pinned: false },
      { id: 'a', group: 'tops', days: 1, pinned: false },
    ] as never);
    expect(groups.map((g) => g.label)).toEqual(['Tops', 'Shoes']);
    expect(wornWords(1)).toBe('Worn 1 day');
    expect(wornWords(4)).toBe('Worn 4 days');
    expect(wornWords(0)).toBe('Not in any outfit');
  });

  it('packs swim trunks last, under their own heading', () => {
    const groups = groupPacked([
      { id: 'trunks', group: 'swim', days: 0, pinned: false },
      { id: 'a', group: 'bottoms', days: 2, pinned: false },
    ] as never);
    expect(groups.map((g) => g.label)).toEqual(['Trousers and shorts', 'For swimming']);
  });

  it('turns a sport on and off, keeping the order they are offered in', () => {
    expect(toggleSport(undefined, 'golf')).toEqual(['golf']);
    expect(toggleSport(['golf'], 'tennis')).toEqual(['tennis', 'golf']);
    expect(toggleSport(['tennis', 'golf'], 'tennis')).toEqual(['golf']);
  });

  it('says whether swimming is on, and who decided', () => {
    const hot = { on: true, hot_days: 3, hot_c: 27, missing: null };
    const cool = { on: false, hot_days: 0, hot_c: 27, missing: null };
    // left to the forecast: off until a plan says otherwise
    expect(swimOn(null)).toBe(false);
    expect(swimOn(undefined, hot)).toBe(true);
    expect(swimHint(null)).toBe('It turns on by itself when the trip will be hot.');
    expect(swimHint(null, cool)).toBe('It turns on by itself when a day reaches 27°C.');
    expect(swimHint(null, hot)).toBe('It is on because 3 days reach 27°C.');
    expect(swimHint(null, { ...hot, hot_days: 1 })).toBe('It is on because a day reaches 27°C.');
    // the owner's word wins over the plan either way
    expect(swimOn(false, hot)).toBe(false);
    expect(swimOn(true, cool)).toBe(true);
    expect(swimHint(false, hot)).toBe('You turned it off. It stays off whatever the forecast.');
    expect(swimHint(true, cool)).toBe('You turned it on, so your swim trunks are packed.');
    expect(swimHint(true, { ...hot, missing: 'You have no swim trunks in your closet.' })).toBe('You turned it on.');
  });

  it('puts trips still to come before past ones', () => {
    const t = (id: string, past: boolean) => ({ id, past }) as TripSummary;
    const { upcoming, past } = upcomingFirst([t('a', false), t('b', true), t('c', false)]);
    expect(upcoming.map((x) => x.id)).toEqual(['a', 'c']);
    expect(past.map((x) => x.id)).toEqual(['b']);
  });

  it('offers laundry on the days of the trip a wash can free something, in plain words', () => {
    expect(laundryDays(7)).toEqual([2, 3, 4, 5, 6]);
    expect(laundryEvery(7)).toEqual([1, 2, 3, 4, 5]);
    expect(laundryDays(2)).toEqual([]);
    expect(laundryEvery(2)).toEqual([]);
    expect(laundryWords({ day: 4 })).toBe('Laundry on day 4');
    expect(laundryWords({ every: 3 })).toBe('Laundry every 3 days');
    expect(laundryWords({ every: 1 })).toBe('Laundry every day');
    expect(laundryWords(null)).toBeNull();
    expect(laundryWords(undefined)).toBeNull();
    expect(laundryMode({ day: 4 })).toBe('day');
    expect(laundryMode({ every: 2 })).toBe('every');
    expect(laundryMode(null)).toBe('none');
  });

  it('starts laundry in the middle of the trip and drops a choice the dates no longer allow', () => {
    expect(startLaundry('day', 7)).toEqual({ day: 4 });
    expect(startLaundry('day', 3)).toEqual({ day: 2 });
    expect(startLaundry('every', 7)).toEqual({ every: 3 });
    expect(startLaundry('every', 4)).toEqual({ every: 2 });
    expect(startLaundry('day', 2)).toBeNull();
    expect(startLaundry('none', 7)).toBeNull();
    expect(fitLaundry({ day: 6 }, 7)).toEqual({ day: 6 });
    expect(fitLaundry({ day: 6 }, 5)).toBeNull();
    expect(fitLaundry({ every: 5 }, 6)).toBeNull();
    expect(fitLaundry({ every: 4 }, 6)).toEqual({ every: 4 });
    expect(fitLaundry(undefined, 6)).toBeNull();
  });

  it('names the kinds for "Before it needs washing" without naming jeans', () => {
    expect(REWEAR_KINDS.map((k) => k.kind)).toEqual(['tops', 'knits', 'bottoms', 'outer', 'basics']);
    expect(REWEAR_KINDS.some((k) => /jeans/i.test(k.label))).toBe(false);
    expect(rewearWords(1)).toBe('Worn once');
    expect(rewearWords(3)).toBe('Worn up to 3 times');
    expect(rewearWords(null)).toBe('The whole trip');
  });
});

describe('the trip Today mentions', () => {
  const trip = (id: string, first: string, last: string, extra: Partial<TripSummary> = {}): TripSummary => ({
    id, place: { name: 'Lisbon, Portugal', latitude: 38.7, longitude: -9.1, timezone: 'Europe/Lisbon' }, first_day: first, last_day: last,
    occasion: 'casual', laundry: null, lines: 15, packed: 4, uncovered: 0, warnings: 0, past: false, ...extra,
  });

  it('is the next one to start within two weeks, saying when and how much is packed', () => {
    const got = tripComingUp([trip('later', '2026-12-20', '2026-12-24'), trip('soon', '2026-11-21', '2026-11-25')], '2026-11-20');
    expect(got?.trip.id).toBe('soon');
    expect(got?.words).toBe('Lisbon, from tomorrow · 4 of 15 packed');
    expect(tripComingUp([trip('a', '2026-11-25', '2026-11-27', { packed: 15 })], '2026-11-20')?.words).toBe('Lisbon, in 5 days · all 15 packed');
  });

  it('is one under way first of all', () => {
    expect(tripComingUp([trip('now', '2026-11-18', '2026-11-22', { lines: 0, packed: 0 })], '2026-11-20')?.words).toBe('Lisbon, under way');
  });

  it('leaves out trips further off and trips that are over', () => {
    expect(tripComingUp([trip('far', '2026-12-05', '2026-12-08'), trip('over', '2026-11-10', '2026-11-19', { past: true })], '2026-11-20')).toBeNull();
    expect(tripComingUp(null, '2026-11-20')).toBeNull();
  });
});

describe('what a trip says about its days', () => {
  const unknownText = 'The weather for this day is not known yet, so nothing was chosen for it. Try again later.';
  const jacket = 'The jacket is roomy and the chinos are tapered.';

  it('says the days that share a sentence together, once', () => {
    expect(sameReasons([
      { date: '2026-12-07', reason: jacket }, { date: '2026-12-06', reason: 'Take an umbrella.' }, { date: '2026-12-08', reason: jacket },
    ])).toEqual([
      { days: 'Monday 7 Dec and Tuesday 8 Dec', reason: jacket }, { days: 'Sunday 6 Dec', reason: 'Take an umbrella.' },
    ]);
  });

  it('says a forecast that could not be had once, not again for every day', () => {
    const days = ['2026-12-05', '2026-12-06', '2026-12-07'];
    const trip = {
      weather: days.map((d) => day(d, 'unknown', { low_c: null, high_c: null, rain: null })),
      weather_message: "Couldn't reach the weather service.",
      plan: { uncovered: days.map((date) => ({ date, reason: unknownText })), warnings: [] },
    };
    const said = tripProblems(trip);
    expect(said.unknown).toBeNull();
    expect(said.uncovered).toEqual([]);
    expect(said.watch).toBeNull();
    expect([...said.unknownDays]).toEqual(days);
    // with nothing else saying why, one sentence for all of them
    expect(tripProblems({ ...trip, weather_message: null }).unknown).toBe(
      'The weather for 3 days is not known yet, so nothing was chosen for them. Try again later.');
  });

  it('counts the days with something to watch for, for the one line that opens them', () => {
    const trip = {
      weather: [day('2026-12-06', 'forecast'), day('2026-12-07', 'forecast')], weather_message: null,
      plan: { uncovered: [{ date: '2026-12-06', reason: 'Nothing warm enough.' }], warnings: [{ date: '2026-12-07', reason: jacket }] },
    };
    const said = tripProblems(trip);
    expect(said.uncovered).toEqual([{ days: 'Sunday 6 Dec', reason: 'Nothing warm enough.' }]);
    expect(said.watch).toEqual({ title: '1 day has something to watch for', lines: [{ days: 'Monday 7 Dec', reason: jacket }] });
  });
});
