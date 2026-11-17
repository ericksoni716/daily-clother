/** Today's outfits: the shapes the server sends, plain words for them, and what this device keeps. */
import { label } from './labels';
import type { ItemSummary } from './types';

export type Place = 'outer' | 'mid' | 'base' | 'bottom' | 'shoes' | 'accessory';

export interface OutfitPieces {
  base: string;
  mid: string | null;
  outer: string | null;
  bottom: string;
  shoes: string;
  accessories: string[];
}

export interface Outfit {
  pieces: OutfitPieces;
  score: number;
  reasons: string[];
  warnings: string[];
}

/** The day the outfits were chosen for, as the server worked it out. */
export interface DayContext {
  date: string;
  low_c: number;
  high_c: number;
  rain: boolean;
  /** 'mild': no forecast could be had, so the outfits are for a mild day (and `message` says why). */
  source: 'forecast' | 'given' | 'forecast and given' | 'mild';
  old: boolean;
  place: string | null;
  rain_chance: number | null;
  summary: string | null;
  /** Why the forecast is old, or why there is none (source 'mild'), in the server's words; null otherwise. */
  message?: string | null;
  /** When the outfits start from one worn before: which of its pieces came back and which could not. */
  again?: { id: string; worn_on: string; kept: string[]; unavailable: string[] };
  /** The hours dressed for, read from the forecast hour by hour; null when it has no hours or the day was typed. */
  detail?: DayDetail | null;
  /** The day in the owner's words, if a note holds today or is coming up. */
  note?: DayNote | null;
}

/** What the hours the owner is out are like (the server's `closet/day.py`). */
export interface DayDetail {
  from_hour: number;
  to_hour: number;
  temp_low_c: number;
  temp_high_c: number;
  feels_low_c: number;
  feels_high_c: number;
  /** Whether it feels far enough from the thermometer to say so. */
  feels_apart: boolean;
  rain: { kind: string; from_hour: number; to_hour: number; chance: number | null; mm: number | null; most: boolean; words: string } | null;
  wind: { kmh: number | null; gust_kmh: number | null; words: string | null } | null;
  uv: number | null;
  humid: boolean;
  wet: boolean;
  /** The day in short plain parts, the temperatures first: ["feels like 0° to 7°", "rain 2pm to 5pm", "windy"]. */
  words: string[];
}

/** A note that today, or the days ahead, are not an ordinary day at home (the server's `closet/daynote.py`). */
export interface DayNote {
  text: string;
  from: string;
  to: string;
  /** Whether it counts today (false: it is for days still ahead). */
  active: boolean;
  place: { name: string; latitude: number; longitude: number; timezone: string } | null;
  /** The place Claude read from the sentence, kept when the map could not find it. */
  place_asked: string | null;
  outside: [number, number] | null;
  exposure: 'inside' | 'mixed' | 'outside';
  activity: string;
  occasion: string | null;
  /** What Closet took from it: ["Lisbon, Portugal", "until Sunday 15 November", "outside noon to 6pm"]. */
  words: string[];
}

export interface DayAnswer {
  note: DayNote | null;
  message: string | null;
  saved?: boolean;
}

export interface TodayAnswer {
  outfits: Outfit[];
  missing: string[];
  context: DayContext;
}

export interface TodayRequest {
  occasion: string;
  mood: string;
  build_around?: string;
  leave_out?: string[];
  low_c?: number;
  high_c?: number;
  rain?: boolean;
  /** A worn outfit's id: start from its pieces that are clean. */
  again?: string;
}

export interface WearManyAnswer {
  worn_on: string;
  recorded?: string[];
  removed?: string[];
  items: ItemSummary[];
  /** The outfit remembered with the wears (when one was sent). */
  outfit?: { id: string };
  outfit_removed?: boolean;
}

export const OCCASIONS = ['athletic', 'casual', 'smart_casual', 'business', 'formal'] as const;
export const MOODS = ['usual', 'sharp', 'relaxed'] as const;

const OCCASION_WORDS: Record<string, string> = {
  athletic: 'Sport', casual: 'Casual', smart_casual: 'Smart casual', business: 'Business', formal: 'Formal',
};
const MOOD_WORDS: Record<string, string> = { usual: 'As usual', sharp: 'Sharp', relaxed: 'Relaxed' };

/** "Smart casual" for smart_casual; works for any formality the vocabulary gains later. */
export function occasionLabel(value: string): string {
  return OCCASION_WORDS[value] ?? label('formality', value);
}

export function moodLabel(value: string): string {
  return MOOD_WORDS[value] ?? label('mood', value);
}

const PLACE_WORDS: Record<Place, string> = {
  outer: 'Outer layer', mid: 'Mid layer', base: 'Top', bottom: 'Bottom', shoes: 'Shoes', accessory: 'Extra',
};

export function placeLabel(place: Place): string {
  return PLACE_WORDS[place];
}

/** The pieces of an outfit in the order they are put on: outer layer, mid layer, base top, bottom, shoes, then accessories. */
export function wornOrder(p: OutfitPieces): { place: Place; id: string }[] {
  const out: { place: Place; id: string }[] = [];
  for (const place of ['outer', 'mid', 'base', 'bottom', 'shoes'] as const) {
    const id = p[place];
    if (id) out.push({ place, id });
  }
  for (const id of p.accessories ?? []) out.push({ place: 'accessory', id });
  return out;
}

/** Every item id in an outfit, in worn order. */
export function outfitIds(p: OutfitPieces): string[] {
  return wornOrder(p).map((x) => x.id);
}

/** Same pieces, whatever the order: the same outfit. */
export function sameOutfit(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
}

const deg = (n: number) => `${Math.round(n)}°C`;

/** "3°C to 10°C" or "About 22°C". */
export function temps(low: number, high: number): string {
  return Math.round(low) === Math.round(high) ? `About ${deg(high)}` : `${deg(low)} to ${deg(high)}`;
}

/** "Rain likely (70%)", "No rain expected (10%)", "Rain likely", "No rain expected". */
export function rainWords(c: Pick<DayContext, 'rain' | 'rain_chance'>): string {
  const chance = c.rain_chance === null || c.rain_chance === undefined ? '' : ` (${c.rain_chance}%)`;
  return c.rain ? `Rain likely${chance}` : `No rain expected${chance}`;
}

/** The first part of a place's name: "Brooklyn" from "Brooklyn, New York, United States". */
export function shortPlace(name: string | null | undefined): string {
  return (name ?? '').split(',')[0].trim();
}

/** "8–15°C" or "About 22°C": the compact form for Today's weather line. */
export function tempRange(low: number, high: number): string {
  return Math.round(low) === Math.round(high) ? `About ${deg(high)}` : `${Math.round(low)}–${deg(high)}`;
}

/**
 * Today's weather line: ["8–15°C", "no rain", "New York"]. The last part says where the day came from: the place's
 * forecast, "your temperatures" when they were typed in, or "a mild day" when no forecast could be had.
 */
export function dayParts(c: DayContext): string[] {
  const known = c.rain_chance !== null && c.rain_chance !== undefined;
  const d = c.detail;
  // with the forecast's hours: what the hours ahead feel like, when the rain falls, and the wind and sun if they matter
  const parts = d
    ? [d.feels_apart ? `feels like ${tempRange(d.feels_low_c, d.feels_high_c).replace(/^A/, 'a')}` : tempRange(d.temp_low_c, d.temp_high_c),
      ...(d.rain ? [] : ['no rain']), ...d.words.slice(1)]
    : [tempRange(c.low_c, c.high_c), c.rain ? (known ? `rain ${c.rain_chance}%` : 'rain likely') : 'no rain'];
  if (c.source === 'mild') parts.push('a mild day');
  else if (c.place) parts.push(shortPlace(c.place));
  else if (c.source === 'given') parts.push('your temperatures');
  return parts;
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Thursday 12 Nov" from "2026-11-12". */
export function longDate(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MONTHS[m - 1]}`;
}

/** A temperature typed by hand ("5", "-3", "12.5", "12°"); null if it is not a number this app plans for. */
export function parseTemp(text: string): number | null {
  const cleaned = text.replace(/[°\sC]/gi, '').replace(',', '.').replace('−', '-');
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return n >= -50 && n <= 55 ? n : null;
}

// --------------------------------------------------------------------- can the closet dress the owner?

const PLACE_CATEGORIES = {
  top: ['tee', 'shirt', 'polo'],
  bottom: ['jeans', 'trousers', 'shorts'],
  shoes: ['sneakers', 'boots', 'dress_shoes', 'sandals'],
} as const;

const NEED_WORDS: Record<keyof typeof PLACE_CATEGORIES, string> = {
  top: 'a top (a T-shirt, shirt or polo)',
  bottom: 'something for your legs (trousers, jeans or shorts)',
  shoes: 'a pair of shoes',
};

/** What the closet still needs before outfits can be made, in the order to add them (empty when it has enough). */
export function whatToAddFirst(items: ItemSummary[] | null | undefined): string[] {
  const usable = (items ?? []).filter((i) => i.status !== 'archived' && i.rating !== 'dislike' && i.category);
  return (Object.keys(PLACE_CATEGORIES) as (keyof typeof PLACE_CATEGORIES)[])
    .filter((need) => !usable.some((i) => (PLACE_CATEGORIES[need] as readonly string[]).includes(i.category!)))
    .map((need) => NEED_WORDS[need]);
}

/** True when the closet holds at least a top, a bottom and shoes the owner has not rated dislike. */
export function canDress(items: ItemSummary[] | null | undefined): boolean {
  return !!items && whatToAddFirst(items).length === 0;
}

/** "a, b and c" */
export function joinWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

// --------------------------------------------------------------------- kept on this device

/** Everything under this prefix is closet data and is removed on logout with the other saved copies. */
export const SAVED_PREFIX = 'closet-today-saved';
const CHOICE_KEY = 'closet-today-choice';

type KV = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function local(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function read<T>(key: string, kv: KV | null): T | null {
  try {
    const raw = kv?.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown, kv: KV | null) {
  try {
    if (value === null) kv?.removeItem(key);
    else kv?.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode or full: not remembered, nothing else breaks */
  }
}

export interface Choice {
  occasion: string;
  mood: string;
}

/** The occasion and mood last chosen on this device (casual, as usual, the first time). */
export function loadChoice(kv: KV | null = local()): Choice {
  const saved = read<Partial<Choice>>(CHOICE_KEY, kv);
  const occasion = saved?.occasion && (OCCASIONS as readonly string[]).includes(saved.occasion) ? saved.occasion : 'casual';
  const mood = saved?.mood && (MOODS as readonly string[]).includes(saved.mood) ? saved.mood : 'usual';
  return { occasion, mood };
}

export function saveChoice(c: Choice, kv: KV | null = local()) {
  write(CHOICE_KEY, c, kv);
}

/** Temperatures typed in by hand, kept for the day they were typed on. */
export interface TypedDay {
  day: string;
  low_c: number;
  high_c: number;
  rain: boolean;
}

/** The last outfits fetched, kept so they can be shown offline later the same day. */
export interface SavedOutfits {
  day: string;
  saved_at: string;
  request: TodayRequest;
  answer: TodayAnswer;
}

/** An outfit recorded as worn from this screen, kept so the screen says so for the rest of the day and can undo it. */
export interface WornToday {
  /** This device's date when it was recorded. */
  day: string;
  /** The date the server recorded the wears on (used to undo them). */
  worn_on: string;
  /** Every piece of the outfit. */
  ids: string[];
  /** The pieces whose wear was new (only these are removed on undo). */
  recorded: string[];
  outfit: Outfit;
  /** The worn outfit remembered on the server, removed with the wears on undo. */
  outfit_id?: string;
  /** When this device recorded it (ms), so an older list of worn outfits does not undo it. */
  at?: number;
}

/** The fields of a worn outfit (as the Worn screen lists them) that say what was worn today. */
export interface WornRecord {
  id: string;
  worn_on: string;
  pieces: { [P in keyof OutfitPieces]: OutfitPieces[P] | null };
  score: number | null;
  reasons: string[];
  warnings: string[];
}

/**
 * What is being worn today, from this device's memory and the server's list of worn outfits (`recent`, fetched at
 * `fetchedAt`; null while unknown or offline). The server's list wins once it is newer than what this device
 * recorded: an outfit removed on the Worn screen is no longer "worn today", and one recorded on another device
 * (or before a reload that lost this device's memory) is, so it is not recorded twice.
 */
export function wornNow(local: WornToday | null, recent: WornRecord[] | null, fetchedAt: number | null, today: string): WornToday | null {
  if (!recent || fetchedAt === null) return local;
  if (local) {
    const newer = local.at === undefined || fetchedAt > local.at;
    if (!newer || !local.outfit_id || recent.some((o) => o.id === local.outfit_id)) return local;
  }
  const todays = recent.find((o) => o.worn_on === today && o.pieces.base && o.pieces.bottom && o.pieces.shoes);
  if (!todays) return null;
  const pieces = { ...todays.pieces, accessories: todays.pieces.accessories ?? [] } as OutfitPieces;
  const ids = outfitIds(pieces);
  return {
    day: today, worn_on: todays.worn_on, ids, recorded: ids, outfit_id: todays.id,
    outfit: { pieces, score: todays.score ?? 0, reasons: todays.reasons, warnings: todays.warnings },
  };
}

const keyFor = (what: string, profile: string) => `${SAVED_PREFIX}:${what}:${profile}`;

function forToday<T extends { day: string }>(value: T | null, today: string): T | null {
  return value && value.day === today ? value : null;
}

/** What this screen keeps per closet; each is only given back on the day it was kept. */
export function keptFor(profile: string, kv: KV | null = local()) {
  return {
    typed: (today: string) => forToday(read<TypedDay>(keyFor('typed', profile), kv), today),
    setTyped: (value: TypedDay | null) => write(keyFor('typed', profile), value, kv),
    outfits: (today: string) => forToday(read<SavedOutfits>(keyFor('outfits', profile), kv), today),
    setOutfits: (value: SavedOutfits | null) => write(keyFor('outfits', profile), value, kv),
    worn: (today: string) => forToday(read<WornToday>(keyFor('worn', profile), kv), today),
    setWorn: (value: WornToday | null) => write(keyFor('worn', profile), value, kv),
  };
}

/** Removes everything this screen kept about the closet (on logout). */
export function forgetSaved(kv: Pick<Storage, 'length' | 'key' | 'removeItem'> | null = local()) {
  if (!kv) return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < kv.length; i++) {
      const k = kv.key(i);
      if (k?.startsWith(SAVED_PREFIX)) keys.push(k);
    }
    keys.forEach((k) => kv.removeItem(k));
  } catch {
    /* nothing kept */
  }
}

/** "8:05 AM" or "20:05" in the viewer's locale, for "saved at". */
export function timeOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}
