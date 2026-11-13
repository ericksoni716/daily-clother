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

export type FigurePieces = Record<'base' | 'mid' | 'outer' | 'bottom' | 'shoes', string | null>;

export function figurePieces(p: OutfitPieces): FigurePieces {
  return { base: p.base, mid: p.mid, outer: p.outer, bottom: p.bottom, shoes: p.shoes };
}

export function figureKey(profile: string, pieces: OutfitPieces, items: Map<string, ItemSummary>): string {
  return JSON.stringify([profile, Object.entries(figurePieces(pieces)).map(([place, id]) => {
    const item = id ? items.get(id) : undefined;
    return [place, id, item?.updated_at, item?.illustration_url];
  })]);
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
  source: 'forecast' | 'given' | 'forecast and given';
  old: boolean;
  place: string | null;
  rain_chance: number | null;
  summary: string | null;
  /** Why the forecast is old, in the server's words; null when it is not. */
  message?: string | null;
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
}

export interface WearManyAnswer {
  worn_on: string;
  recorded?: string[];
  removed?: string[];
  items: ItemSummary[];
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

/** The day at a glance: ["Brooklyn", "3°C to 10°C", "Rain likely (70%)"]; "Your temperatures" when they were typed in. */
export function dayParts(c: DayContext): string[] {
  const parts: string[] = [];
  if (c.place) parts.push(shortPlace(c.place));
  else if (c.source === 'given') parts.push('Your temperatures');
  parts.push(temps(c.low_c, c.high_c));
  parts.push(rainWords(c));
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
const VIEW_KEY = 'closet-today-view';

export type TodayView = 'pieces' | 'as-worn';

export function loadTodayView(kv: KV | null = local()): TodayView {
  return read<string>(VIEW_KEY, kv) === 'as-worn' ? 'as-worn' : 'pieces';
}

export function saveTodayView(view: TodayView, kv: KV | null = local()) {
  write(VIEW_KEY, view, kv);
}

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
