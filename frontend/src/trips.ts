import { longDate, SAVED_PREFIX, shortPlace, temps, type Outfit } from './today';
import type { Place } from './types';

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
}

export type PackGroup = 'tops' | 'layers' | 'bottoms' | 'shoes' | 'outer' | 'accessories';

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
}

export interface Basic {
  key: string;
  name: string;
  count: number;
}

export interface Plan {
  packed: PackedPiece[];
  days: PlanDay[];
  basics: Basic[];
  uncovered: { date: string; reason: string }[];
  warnings: { date: string; reason: string }[];
  notes: string[];
}

export interface TripChoices {
  place: Place;
  first_day: string;
  last_day: string;
  occasion: string;
  day_occasions: Record<string, string>;
  can_wash: boolean;
  leave_out: string[];
  pin: string[];
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
  can_wash: boolean;
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
  can_wash?: boolean;
  leave_out?: string[];
  pin?: string[];
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

export const GROUPS: { group: PackGroup; label: string }[] = [
  { group: 'tops', label: 'Tops' },
  { group: 'layers', label: 'Layers' },
  { group: 'bottoms', label: 'Trousers and shorts' },
  { group: 'shoes', label: 'Shoes' },
  { group: 'outer', label: 'Coats and jackets' },
  { group: 'accessories', label: 'Accessories' },
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

/** "5°C to 11°C" or "Not known yet". */
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
