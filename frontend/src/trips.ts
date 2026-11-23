import { joinWords, longDate, SAVED_PREFIX, shortPlace, temps, type Outfit } from './today';
import type { Place, RewearKind } from './types';

/** Where a day's weather comes from: the forecast, what the dates are usually like, typed in, or not known. */
export type WeatherSource = 'forecast' | 'usual' | 'given' | 'unknown';

export interface TripDay {
  date: string;
  low_c: number | null;
  high_c: number | null;
  rain: boolean | null;
  rain_chance: number | null;
  summary: string | null;
  source: WeatherSource;
  /** The feels-like high, which counts the humidity, when the weather service gave one. */
  feels_high_c?: number;
}

/** Where a piece is packed; swim trunks go in `swim`, apart from the days' outfits. */
export type PackGroup = 'tops' | 'layers' | 'bottoms' | 'shoes' | 'outer' | 'accessories' | 'swim';

export interface PackedPiece {
  id: string;
  group: PackGroup;
  /** How many days of the trip it is worn. */
  days: number;
  /** The owner asked to take it. */
  pinned: boolean;
}

export interface PlanDay {
  date: string;
  occasion: string;
  weather: TripDay;
  outfit: Outfit | null;
  /** Why there is no outfit for the day, in plain words. */
  problem: string | null;
  /** Why an outfit has something to watch out for, in plain words. */
  warning: string | null;
  /** The day falls on a wash (plans made before laundry on the trip do not say). */
  laundry?: boolean;
}

export interface Basic {
  key: string;
  name: string;
  count: number;
  /** Why this many, in plain words (underwear and socks). */
  why?: string;
}

/** Laundry on the trip: on one day of it, every so many days, or none. */
export type TripLaundry = { day: number } | { every: number } | null;

/** Each kind's count in plain words: "5 shirts: one a day, laundry on day 4"; swim trunks have one of their own. */
export interface KindCount {
  kind: RewearKind | 'swim';
  count: number;
  words: string;
}

/** "Swimming or the beach" as the plan decided it: on by the owner's word, or by itself when a day reaches `hot_c`. */
export interface SwimPlan {
  on: boolean;
  /** How many days of the trip have a high of `hot_c` or more. */
  hot_days: number;
  hot_c: number;
  /** Why no swim trunks are packed while it is on ("You have no swim trunks in your closet."), or null. */
  missing: string | null;
}

/** Where a wash falls: "Wash on day 4: the shirts from days 1–3 are worn again from day 5." */
export interface WashNote {
  day: number;
  date: string;
  words: string;
}

export interface Plan {
  packed: PackedPiece[];
  days: PlanDay[];
  basics: Basic[];
  uncovered: { date: string; reason: string }[];
  warnings: { date: string; reason: string }[];
  notes: string[];
  /** Plans made before laundry on the trip and the explained counts do not have these. */
  laundry?: TripLaundry;
  counts?: KindCount[];
  washes?: WashNote[];
  /** Plans made before swimming on a trip do not have it. */
  swim?: SwimPlan;
}

export interface TripChoices {
  place: Place;
  first_day: string;
  last_day: string;
  occasion: string;
  day_occasions: Record<string, string>;
  laundry: TripLaundry;
  leave_out: string[];
  pin: string[];
  /** "Swimming or the beach": the owner's word, or null to follow the forecast (trips saved before it have none). */
  swim?: boolean | null;
  /** The sports played on the trip: their shoes are packed beside the days (trips saved before it have none). */
  sport?: TripSport[];
}

/** A plan worked out but not saved. */
export interface PlannedTrip extends TripChoices {
  weather: TripDay[];
  weather_message: string | null;
  plan: Plan;
  /** Every line that can be ticked: "item:<id>" for the pieces, then "basic:<key>". */
  lines: string[];
}

export interface Trip extends PlannedTrip {
  id: string;
  /** The lines ticked as packed. */
  packed: string[];
  planned_at: string;
  created_at: string;
  updated_at: string;
}

export interface TripSummary {
  id: string;
  place: Place;
  first_day: string;
  last_day: string;
  occasion: string;
  laundry: TripLaundry;
  lines: number;
  packed: number;
  uncovered: number;
  warnings: number;
  past: boolean;
}

export type TripRequest = Partial<Omit<TripChoices, 'place' | 'first_day' | 'last_day'>> &
  Pick<TripChoices, 'place' | 'first_day' | 'last_day'> &
  { weather?: Pick<TripDay, 'date' | 'low_c' | 'high_c' | 'rain'>[] };

export interface TripPatch {
  ticks?: Record<string, boolean>;
  occasion?: string;
  day_occasions?: Record<string, string>;
  laundry?: TripLaundry;
  leave_out?: string[];
  pin?: string[];
  swim?: boolean | null;
  sport?: TripSport[];
  replan?: boolean;
}

export interface WeatherCheck {
  checked: boolean;
  changed: boolean;
  days: TripDay[] | null;
  message: string | null;
}

export interface SavedTrips {
  saved_at: string;
  list: TripSummary[] | null;
  details: Record<string, Trip>;
}

type KV = Pick<Storage, 'getItem' | 'setItem'>;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const savedKey = (profile: string) => `${SAVED_PREFIX}:trips:${profile}`;

export function loadSavedTrips(profile: string, kv: KV | null = local()): SavedTrips | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const saved = raw ? JSON.parse(raw) as SavedTrips : null;
    return saved && typeof saved.saved_at === 'string' ? saved : null;
  } catch {
    return null;
  }
}

export function saveTrips(profile: string, part: Partial<Omit<SavedTrips, 'saved_at'>>, kv: KV | null = local(), now = new Date()) {
  const before = loadSavedTrips(profile, kv);
  const saved: SavedTrips = { saved_at: now.toISOString(), list: before?.list ?? null, details: before?.details ?? {}, ...part };
  try {
    kv?.setItem(savedKey(profile), JSON.stringify(saved));
  } catch {
    /* private mode or full: not kept, nothing else breaks */
  }
}

export const MAX_TRIP_DAYS = 30;

/** The heading swim trunks are packed under, and where the plan says when none can be. */
export const SWIM_LABEL = 'For swimming';

export const GROUPS: { group: PackGroup; label: string }[] = [
  { group: 'tops', label: 'Tops' },
  { group: 'layers', label: 'Layers' },
  { group: 'bottoms', label: 'Trousers and shorts' },
  { group: 'shoes', label: 'Shoes' },
  { group: 'outer', label: 'Coats and jackets' },
  { group: 'accessories', label: 'Accessories' },
  { group: 'swim', label: SWIM_LABEL },
];

/** The packed pieces in their groups, in the order of GROUPS; empty groups left out. */
export function groupPacked(packed: PackedPiece[]): { group: PackGroup; label: string; pieces: PackedPiece[] }[] {
  return GROUPS.map((g) => ({ ...g, pieces: packed.filter((p) => p.group === g.group) })).filter((g) => g.pieces.length > 0);
}

export const itemLine = (id: string) => `item:${id}`;
export const basicLine = (key: string) => `basic:${key}`;

/** "9 of 14 packed", counting only lines still in the plan. */
export function progress(lines: string[], packed: string[]): { done: number; total: number; words: string } {
  const have = new Set(packed);
  const done = lines.filter((l) => have.has(l)).length;
  const total = lines.length;
  return { done, total, words: total && done === total ? `All ${total} packed` : `${done} of ${total} packed` };
}

export function sourceLabel(source: WeatherSource): string {
  if (source === 'forecast') return 'Forecast';
  if (source === 'usual') return 'Usually, on these dates';
  if (source === 'given') return 'Your temperatures';
  return 'Not known yet';
}

/** The trip's days cut into runs of the same source, so the strip can say "Forecast" over the first ones and
 * "Usually, on these dates" over the rest. */
export function sourceRuns<T extends { source: WeatherSource }>(days: T[]): { source: WeatherSource; label: string; days: T[] }[] {
  const runs: { source: WeatherSource; label: string; days: T[] }[] = [];
  for (const d of days) {
    const last = runs[runs.length - 1];
    if (last && last.source === d.source) last.days.push(d);
    else runs.push({ source: d.source, label: sourceLabel(d.source), days: [d] });
  }
  return runs;
}

/** "5–11°C" or "Not known yet". */
export function dayTemps(d: TripDay): string {
  return d.low_c === null || d.high_c === null ? 'Not known yet' : temps(d.low_c, d.high_c);
}

/** "Rain likely", "Rain in 3 of 5 years", "Dry" and so on, by where the day's weather came from. */
export function dayRain(d: TripDay): string {
  if (d.rain === null) return '';
  if (d.source === 'usual') {
    if (d.rain_chance === null) return d.rain ? 'Often rainy' : 'Usually dry';
    return d.rain ? `Rainy ${d.rain_chance}% of years` : `Usually dry (rain ${d.rain_chance}% of years)`;
  }
  if (d.rain_chance !== null && d.rain_chance !== undefined) return d.rain ? `Rain likely (${d.rain_chance}%)` : `Dry (${d.rain_chance}%)`;
  return d.rain ? 'Rain likely' : 'Dry';
}

const SHORT_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function parts(day: string): [number, number, number] {
  const [y, m, d] = day.split('-').map(Number);
  return [y, m, d];
}

/** "Tue 1" from "2026-12-01": a day in the weather strip. */
export function shortDay(day: string): { weekday: string; date: string } {
  const [y, m, d] = parts(day);
  return { weekday: SHORT_DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()], date: `${d} ${MONTHS[m - 1]}` };
}

/** "1–5 Dec", "28 Nov – 3 Dec", "28 Dec 2026 – 3 Jan 2027", or one day. */
export function dateRange(first: string, last: string): string {
  const [y1, m1, d1] = parts(first);
  const [y2, m2, d2] = parts(last);
  if (first === last) return longDate(first);
  if (y1 !== y2) return `${d1} ${MONTHS[m1 - 1]} ${y1} – ${d2} ${MONTHS[m2 - 1]} ${y2}`;
  if (m1 !== m2) return `${d1} ${MONTHS[m1 - 1]} – ${d2} ${MONTHS[m2 - 1]}`;
  return `${d1}–${d2} ${MONTHS[m1 - 1]}`;
}

/** "Lisbon, 1–5 Dec": what a trip is called in the list. */
export function tripTitle(t: { place: Place; first_day: string; last_day: string }): string {
  return `${shortPlace(t.place.name)}, ${dateRange(t.first_day, t.last_day)}`;
}

/** Number of days from first to last, both included (0 when the dates are not right). */
export function dayCount(first: string, last: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(first) || !/^\d{4}-\d{2}-\d{2}$/.test(last)) return 0;
  const [y1, m1, d1] = parts(first);
  const [y2, m2, d2] = parts(last);
  const n = Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86400000) + 1;
  return n > 0 ? n : 0;
}

/** "2026-12-03" from "2026-12-01" and 2. */
export function addDays(day: string, n: number): string {
  const [y, m, d] = parts(day);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

/** Every day from first to last. */
export function tripDays(first: string, last: string): string[] {
  return Array.from({ length: dayCount(first, last) }, (_, i) => addDays(first, i));
}

/** What is wrong with the dates chosen, in plain words, or null. */
export function checkDates(first: string, last: string, today: string): string | null {
  if (!first || !last) return 'Choose the first and last day of the trip.';
  if (last < first) return "The trip's last day is before its first day.";
  if (first < today) return 'The trip has to start today or later.';
  if (dayCount(first, last) > MAX_TRIP_DAYS) return `A trip can be at most ${MAX_TRIP_DAYS} days long.`;
  return null;
}

/** "Worn 3 days", "Worn 1 day", or for a pinned piece no outfit uses, "Not in any outfit". */
export function wornWords(days: number): string {
  if (days <= 0) return 'Not in any outfit';
  return days === 1 ? 'Worn 1 day' : `Worn ${days} days`;
}

/** The list cut in two: trips still to come (or under way), then past ones; the server sends them in that order. */
export function upcomingFirst(trips: TripSummary[]): { upcoming: TripSummary[]; past: TripSummary[] } {
  return { upcoming: trips.filter((t) => !t.past), past: trips.filter((t) => t.past) };
}

/** How far ahead Today mentions a trip: a trip within the next two weeks is one you may be packing for. */
export const TRIP_AHEAD_DAYS = 14;

/**
 * The trip Today mentions: one under way, else the next to start within `TRIP_AHEAD_DAYS`, with a line saying when
 * ("Lisbon, from tomorrow · 4 of 15 packed"). Null when none is near.
 */
export function tripComingUp(trips: TripSummary[] | null | undefined, today: string): { trip: TripSummary; words: string } | null {
  const near = (trips ?? [])
    .filter((t) => t.last_day >= today && t.first_day <= addDays(today, TRIP_AHEAD_DAYS))
    .sort((a, b) => a.first_day.localeCompare(b.first_day));
  const trip = near[0];
  if (!trip) return null;
  const days = dayCount(today, trip.first_day) - 1;
  const when = trip.first_day <= today ? 'under way' : days === 1 ? 'from tomorrow' : `in ${days} days`;
  const packed = trip.lines > 0 ? (trip.packed === trip.lines ? ` · all ${trip.lines} packed` : ` · ${trip.packed} of ${trip.lines} packed`) : '';
  return { trip, words: `${shortPlace(trip.place.name)}, ${when}${packed}` };
}

/** The kinds of clothing for "Before it needs washing", in the order Settings shows them. */
export const REWEAR_KINDS: { kind: RewearKind; label: string }[] = [
  { kind: 'tops', label: 'Shirts, tees and polos' },
  { kind: 'knits', label: 'Knitwear and sweatshirts' },
  { kind: 'bottoms', label: 'Trousers and shorts' },
  { kind: 'outer', label: 'Jackets and coats' },
  { kind: 'basics', label: 'Underwear, socks and basics' },
];

/** The most wears the setting offers for one kind; past it, "The whole trip". */
export const MAX_REWEAR = 10;

export type LaundryMode = 'none' | 'day' | 'every';

export function laundryMode(l: TripLaundry | undefined): LaundryMode {
  if (!l) return 'none';
  return 'day' in l ? 'day' : 'every';
}

/** The laundry days a trip of n days can have: day 2 to the day before the last. */
export function laundryDays(n: number): number[] {
  return Array.from({ length: Math.max(0, n - 2) }, (_, i) => i + 2);
}

/** How often laundry can come round on a trip of n days: every day to every n − 2 days. */
export function laundryEvery(n: number): number[] {
  return Array.from({ length: Math.max(0, n - 2) }, (_, i) => i + 1);
}

/** The laundry choice when it still fits a trip of n days, or null (none) when it no longer does. */
export function fitLaundry(l: TripLaundry | undefined, n: number): TripLaundry {
  if (!l) return null;
  if ('day' in l) return laundryDays(n).includes(l.day) ? l : null;
  return laundryEvery(n).includes(l.every) ? l : null;
}

/** A first choice when the owner picks a way of doing laundry: the middle day, or every 3 days. */
export function startLaundry(mode: LaundryMode, n: number): TripLaundry {
  if (mode === 'none' || n < 3) return null;
  if (mode === 'day') return { day: Math.min(n - 1, Math.max(2, Math.ceil(n / 2))) };
  return { every: Math.min(3, n - 2) };
}

/** "Laundry on day 4", "Laundry every 3 days", "Laundry every day", or null for none. */
export function laundryWords(l: TripLaundry | undefined): string | null {
  if (!l) return null;
  if ('day' in l) return `Laundry on day ${l.day}`;
  return l.every === 1 ? 'Laundry every day' : `Laundry every ${l.every} days`;
}

/** Whether "Swimming or the beach" is on: the owner's word, else what the plan decided from the forecast; off before a
 * plan has been worked out. */
export function swimOn(choice: boolean | null | undefined, plan?: SwimPlan | null): boolean {
  return choice ?? plan?.on ?? false;
}

/** The line under "Swimming or the beach": who decided, and what turns it on by itself. */
export function swimHint(choice: boolean | null | undefined, plan?: SwimPlan | null): string {
  if (choice === true) return plan?.missing ? 'You turned it on.' : 'You turned it on, so your swim trunks are packed.';
  if (choice === false) return 'You turned it off. It stays off whatever the forecast.';
  if (plan?.on) return `It is on because ${plan.hot_days === 1 ? 'a day reaches' : `${plan.hot_days} days reach`} ${plan.hot_c}°C.`;
  return `It turns on by itself when ${plan ? `a day reaches ${plan.hot_c}°C` : 'the trip will be hot'}.`;
}

/** The sports a trip can include, as the trip's choice and as the owner reads them. */
export type TripSport = 'tennis' | 'golf';
export const TRIP_SPORTS: { value: TripSport; label: string }[] = [{ value: 'tennis', label: 'Tennis' }, { value: 'golf', label: 'Golf' }];

/** The sports with one turned on or off, in the order they are offered. */
export function toggleSport(chosen: TripSport[] | undefined, sport: TripSport): TripSport[] {
  const on = new Set(chosen ?? []);
  if (on.has(sport)) on.delete(sport);
  else on.add(sport);
  return TRIP_SPORTS.map((s) => s.value).filter((s) => on.has(s));
}

/** "Worn once", "Worn up to 3 times", "The whole trip": a choice of the setting. */
export function rewearWords(n: number | null): string {
  if (n === null) return 'The whole trip';
  return n === 1 ? 'Worn once' : `Worn up to ${n} times`;
}

/** Days of a trip with the same sentence about them, said once: "Monday 7 Dec and Tuesday 8 Dec" and the sentence. */
export function sameReasons(list: { date: string; reason: string }[]): { days: string; reason: string }[] {
  const by = new Map<string, string[]>();
  for (const { date, reason } of list) by.set(reason, [...(by.get(reason) ?? []), date]);
  return [...by].map(([reason, dates]) => ({ days: joinWords(dates.map(longDate)), reason }));
}

/**
 * What a trip has to say about its days, each said once. The days whose weather is not known are not dressed; when
 * the trip already says why (it could not reach the weather service), that is not said again for each of them, and
 * otherwise it is said in one sentence. The rest of the days with no outfit, and the days dressed with something to
 * watch for, each with the days that share a sentence put together.
 */
export function tripProblems(trip: Pick<PlannedTrip, 'weather' | 'weather_message'> & { plan: Pick<PlannedTrip['plan'], 'uncovered' | 'warnings'> }): {
  unknown: string | null; unknownDays: Set<string>; uncovered: { days: string; reason: string }[];
  watch: { title: string; lines: { days: string; reason: string }[] } | null;
} {
  const unknownDays = new Set(trip.weather.filter((d) => d.source === 'unknown').map((d) => d.date));
  const n = unknownDays.size;
  const unknown = n === 0 || trip.weather_message ? null
    : n === 1 ? 'The weather for one day is not known yet, so nothing was chosen for it. Try again later.'
      : `The weather for ${n} days is not known yet, so nothing was chosen for them. Try again later.`;
  const uncovered = sameReasons(trip.plan.uncovered.filter((u) => !unknownDays.has(u.date)));
  const w = trip.plan.warnings;
  const watch = w.length === 0 ? null : {
    title: w.length === 1 ? '1 day has something to watch for' : `${w.length} days have something to watch for`,
    lines: sameReasons(w),
  };
  return { unknown, unknownDays, uncovered, watch };
}
