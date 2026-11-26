/** Today's outfits: the shapes the server sends, plain words for them, and what this device keeps. */
import { label } from './labels';
import type { ItemSummary } from './types';
import { sinceDay } from './wears';

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
  /** The rules' score out of 100; null for an outfit Claude chose (its reasons say why instead). */
  score: number | null;
  reasons: string[];
  warnings: string[];
  /** 'claude' when Claude chose it; absent when Nines' own rules did. */
  by?: 'claude';
  /** Give it an outing: this outfit, the last of the day's, is built around a piece you like and have not worn in a
   * while (the server's `closet/outing.py`); absent on every other outfit. */
  outing?: Outing;
}

/** The piece an outing is built around: how you rated it, and the day it was last worn (or added, when never worn). */
export interface Outing {
  item_id: string;
  rating: 'love' | 'like';
  since: string;
  never_worn: boolean;
  /** Its name is plural ("dark jeans"): "them", not "it". */
  plural: boolean;
}

/** Claude choosing the day's outfits (the server's `closet/stylejobs.py`). */
export interface StylistState {
  /** 'working': still choosing, the outfits are the rules'; 'ready': Claude's come first; 'failed': the rules' (`message` says why). */
  state: 'working' | 'ready' | 'failed';
  /** The question, for `api.styleAnswer`; null when none was asked. */
  id: string | null;
  /** Claude's one sentence on what about the day shaped its choices (ready only). */
  read: string | null;
  /** Why Claude could not choose, in a sentence (failed). On ready, normally null; a sentence only on the request that
   * carried `ask_again` and was refused by the daily limit ("…so these are still the ones it chose last"). */
  message: string | null;
  /** The day's conversation with Claude about the outfits, oldest first (absent in copies saved before it existed). */
  talk?: TalkTurn[];
  /** The id of the owner's message Claude is answering now, for `api.styleAnswer`; null when none. */
  answering?: string | null;
}

/** Something Claude offered to remember from a message: about the owner's style, or about one piece. */
export interface RememberThing {
  kind: 'style' | 'piece';
  /** The piece's id (kind 'piece'); null for the owner's style. */
  item_id: string | null;
  /** The piece's name (kind 'piece'); null for the owner's style. */
  name: string | null;
  text: string;
  /** Only 'offered' things are asked about; nothing is kept until the owner saves it. */
  state: 'offered' | 'saved' | 'dismissed';
}

/** The owner's answer to a thing Claude offered to remember: keep it or not (`save`), or take back one kept (`undo`). */
export type RememberHow = { save: boolean; undo?: never } | { undo: true; save?: never };

/** One message of the owner's about the outfits, and Claude's answer to it. */
export interface TalkTurn {
  id: string;
  /** What the owner wrote. */
  said: string;
  /** 'working': Claude is answering; 'ready': `reply` is Claude's words; 'failed': `message` says why it was not answered. */
  state: 'working' | 'ready' | 'failed';
  reply: string | null;
  message: string | null;
  remember: RememberThing[];
  at: string;
}

/** The day the outfits were chosen for, as the server worked it out. */
export interface DayContext {
  date: string;
  low_c: number;
  high_c: number;
  rain: boolean;
  /** 'mild': no forecast could be had, so the outfits are for a mild day (and `message` says why). 'usual': a day
   * ahead beyond the forecast, dressed for what the date is usually like. 'trip': a day ahead inside a saved trip. */
  source: 'forecast' | 'given' | 'forecast and given' | 'usual' | 'usual and given' | 'mild' | 'trip';
  old: boolean;
  place: string | null;
  rain_chance: number | null;
  summary: string | null;
  /** Why the forecast is old, or why there is none (source 'mild'), in the server's words; null otherwise. */
  message?: string | null;
  /** When the outfits start from one worn before: which of its pieces came back and which could not. */
  again?: { id: string; worn_on: string | null; kept: string[]; unavailable: string[]; away?: Record<string, string> };
  /** The day's plan, when the outfits start from it: which of its pieces stay and which had to be swapped. `away`, in
   * both: where each swapped piece that is away is, with its verb ("is at the cleaner's until Friday 27 November"). */
  plan?: { day: string; kept: string[]; unavailable: string[]; note: string | null; away?: Record<string, string> };
  /** Planned pieces not offered, as wearing them now leaves them in the laundry on their day: id -> that day. */
  held?: Record<string, string>;
  /** Planned pieces the outfits use all the same, as holding them back left no outfit at all (the page says so once). */
  held_offered?: string[];
  /** A day dressed ahead (Dress for another day), not today. */
  ahead?: boolean;
  /** A day ahead: the pieces away now that it counts as back by then (expected back before it), as a trip packs them. */
  expected?: string[];
  /** A day ahead with no weather: whether trying again may find it (the weather service could not be reached). */
  retry?: boolean;
  /** A day ahead inside a saved trip, which has that day's outfit. */
  trip?: { id: string; place: string | null; first_day: string; last_day: string };
  /** Today inside a saved trip (the server's `closet/tripday.py`): dressed at its place from what is in the bag, or set
   * aside for the day ("Not on this trip today"). Absent when no trip holds today, or your own words win over it. */
  on_trip?: OnTrip | null;
  /** The day before a saved trip: the trip and the pieces ticked as packed for it that the outfits leave out (the
   * server's `savedtrips.packed_before`; a piece you build around is not among them). Absent when none are. */
  packed_for?: PackedFor | null;
  /** The hours dressed for, read from the forecast hour by hour; null when it has no hours or the day was typed. */
  detail?: DayDetail | null;
  /** The occasion the outfits were chosen for (on a trip day, the trip's when the request sent the kept one). */
  occasion?: string;
  /** The day in the owner's words, if a note holds today or is coming up. */
  note?: DayNote | null;
  /** Claude choosing the outfits; absent or null when Claude does not choose here (the demo closet, switched off). */
  stylist?: StylistState | null;
}

/** The saved trip that holds today, as Today dresses from it. */
/** The day before a saved trip: what you ticked as packed for it, left out of today's outfits. */
export interface PackedFor {
  id: string;
  /** The trip's place, as the owner chose it; null when it has none. */
  place: string | null;
  ids: string[];
}

export interface OnTrip {
  id: string;
  /** The trip's place, as the owner chose it ("Lisbon, Portugal"); null when it has none. */
  place: string | null;
  first_day: string;
  last_day: string;
  /** Today is day `day` (1 is the first) of `days`. */
  day: number;
  days: number;
  /** "Not on this trip today": dressed from the whole closet at home for the rest of the day. */
  aside: boolean;
  /** Today's occasion on the trip. */
  occasion: string;
  /** The first outfit is the trip's own for today: which of its pieces stay and which had to be swapped; null when
   * it is not shown first (set aside, built around a piece, another occasion). */
  planned: { kept: string[]; unavailable: string[]; away?: Record<string, string> } | null;
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
  /** What Nines took from it: ["Lisbon, Portugal", "until Sunday 15 November", "outside noon to 6pm"]. */
  words: string[];
}

export interface DayAnswer {
  note: DayNote | null;
  message: string | null;
  saved?: boolean;
}

/** `GET /api/style/answers/{id}`: how one question to Claude stands. */
export interface StyleAnswer {
  id: string;
  state: StylistState['state'];
  message: string | null;
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
  /** A worn (or kept) outfit's id: start from its pieces that are clean. */
  again?: string;
  /** Another day, dressed ahead (YYYY-MM-DD). */
  day?: string;
  /** false: other outfits than the day's plan. */
  planned?: boolean;
  /** The occasion is the one this device kept, not one tapped today: on a trip day the trip's is used instead. */
  occasion_kept?: boolean;
  /** Ask Claude to choose afresh (one request only: never kept with the request). */
  ask_again?: boolean;
  /** A message to Claude about the outfits on the page (one request only: never kept with the request). */
  say?: string;
  /** Which outfit was in front of the owner as they wrote (0 is the first); only sent with `say`. */
  looking_at?: number;
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

/** Building around a piece, as Today's "Build around this piece" does it: the piece becomes the one built around (in
 * place of any other), and is no longer left out; the other pieces left out stay left out. */
export function buildAroundPiece(leaveOut: readonly string[], id: string): { buildAround: string; leaveOut: string[] } {
  return { buildAround: id, leaveOut: leaveOut.filter((x) => x !== id) };
}

/** What Today's address asks for as it opens: an outfit to wear again (`again`, from Worn) or a piece to build around
 * (`around`, from the item page). */
export function askedOf(search: string): { again: string | null; around: string | null } {
  const q = new URLSearchParams(search);
  return { again: q.get('again') || null, around: q.get('around') || null };
}

/** Same pieces, whatever the order: the same outfit. */
export function sameOutfit(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
}

/**
 * A day's temperatures, the one way they are written on Today, Worn and a trip: "8–15°C", "-3 to 4°C" (a dash after a
 * minus would read as another minus), or "About 22°C" when the low and the high round to the same degree.
 */
export function temps(low: number, high: number): string {
  const l = Math.round(low);
  const h = Math.round(high);
  if (l === h) return `About ${h}°C`;
  return l < 0 ? `${l} to ${h}°C` : `${l}–${h}°C`;
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

/**
 * Today's weather line: ["8–15°C", "no rain", "New York"]. The last part says where the day came from: the place's
 * forecast, "your temperatures" when they were typed in, or "a mild day" when no forecast could be had.
 */
export function dayParts(c: DayContext): string[] {
  const known = c.rain_chance !== null && c.rain_chance !== undefined;
  const d = c.detail;
  // with the forecast's hours: what the hours ahead feel like, when the rain falls, and the wind and sun if they matter
  const parts = d
    ? [d.feels_apart ? `feels like ${temps(d.feels_low_c, d.feels_high_c).replace(/^A/, 'a')}` : temps(d.temp_low_c, d.temp_high_c),
      ...(d.rain ? [] : ['no rain']), ...d.words.slice(1)]
    : [temps(c.low_c, c.high_c), c.rain ? (known ? `rain ${c.rain_chance}%` : 'rain likely') : 'no rain'];
  if (c.source === 'usual' || c.source === 'usual and given') {
    // a day beyond the forecast: what the date is usually like, as a trip's days say it
    const usual = [temps(c.low_c, c.high_c), c.rain ? 'often rainy' : 'usually dry'];
    if (c.place) usual.push(shortPlace(c.place));
    return [...usual, 'usually, on these dates'];
  }
  // a day ahead with no weather: "14–20°C · a mild day" (a mild day is a dry one), short enough for one line at 320
  // so the reason under it never meets it
  if (c.source === 'mild' && c.ahead) return [parts[0], 'a mild day'];
  if (c.source === 'mild') parts.push('a mild day');
  else if (c.place) parts.push(shortPlace(c.place));
  else if (c.source === 'given') parts.push('your temperatures');
  return parts;
}

// the days are written by the one family of dates (wears.ts); Today and a trip read them from here too
export { clock as timeOf, longDate, shortDate } from './wears';

// days ahead (Dress for another day): written by the family too
export { addDays, dayName, daysAhead, onDay, weekdayOf } from './wears';

/** A piece's name inside a sentence: its first letter small, unless the name starts with a short form ("TV jacket") or
 * with the piece's own brand, compared without case and as a whole word ("Northfield sneaker" with the brand
 * Northfield), as the server's sentences say it (`outfits._label`). With no brand, by the first rule alone. */
export function midName(n: string, brand?: string | null): string {
  return n.length > 1 && n[1] === n[1].toLowerCase() && !startsWithBrand(n, brand) ? n[0].toLowerCase() + n.slice(1) : n;
}

function startsWithBrand(n: string, brand: string | null | undefined): boolean {
  const b = (brand ?? '').trim();
  if (!b || n.slice(0, b.length).toLowerCase() !== b.toLowerCase()) return false;
  const next = n.charAt(b.length);
  return !next || !/[\p{L}\p{N}]/u.test(next);
}

/** The one sentence under an outing's button: "An outing for your tweed jacket: you love it and have not worn it since
 * 2 Oct." (or "since you added it on 2 Oct" for a piece never worn). */
export function outingLine(o: Outing, name: string, today: string, brand?: string | null): string {
  const it = o.plural ? 'them' : 'it';
  const when = sinceDay(o.since, today);
  return `An outing for your ${midName(name, brand)}: you ${o.rating} ${it} and have not worn ${it} `
    + `${o.never_worn ? `since you added ${it} on ${when}` : `since ${when}`}.`;
}

// --------------------------------------------------------------------- a trip covers today

/** "your trip to Lisbon", or "your trip" when it has no place: the trip named by its place, as the owner chose it. */
function yourTrip(t: Pick<OnTrip, 'place'>): string {
  const where = shortPlace(t.place);
  return where ? `your trip to ${where}` : 'your trip';
}

/** The one line over the outfits on a day a trip covers: "Day 3 of 7 of your trip to Lisbon.", or for a trip of one
 * day "Today is your trip to Lisbon."; set aside, "You're not on your trip today." (with Undo beside it). */
export function tripTodayLine(t: Pick<OnTrip, 'place' | 'day' | 'days' | 'aside'>): string {
  if (t.aside) return "You're not on your trip today.";
  const trip = yourTrip(t);
  return t.days <= 1 ? `Today is ${trip}.` : `Day ${t.day} of ${t.days} of ${trip}.`;
}

/** In Where you are, before "Not on this trip today": why Today looks as it does. */
export function tripSheetLine(t: Pick<OnTrip, 'place'>): string {
  return `You're on ${yourTrip(t)}, so Today dresses you there from what you packed.`;
}

/** The day before a trip, the one line over the outfits: what you ticked as packed for it is in the suitcase, so
 * Today leaves it out ("Packed for Lisbon, so left out today.": the trip first, so a cut line still names it).
 * Unticking a piece in the trip puts it back. */
export function packedForLine(t: Pick<PackedFor, 'place'>): string {
  return `Packed for ${shortPlace(t.place) || 'your trip'}, so left out today.`;
}

/** The occasion the chips show: the one the answer was dressed for while the occasion sent is the one this device kept
 * (`kept`; on a trip day the server dresses for the trip's), so the page shows it without asking again; else the one
 * chosen. */
export function occasionShown(chosen: string, kept: boolean, answered: string | null | undefined): string {
  return kept && answered ? answered : chosen;
}

/** In a piece's choices on a trip day: where another piece comes from. */
export const TRIP_PIECE_HINT = 'Another piece comes from what you packed.';

/** Under the first outfit's button when it is the trip's own for today. */
export const TRIP_OUTFIT_LINE = 'Your trip planned this outfit for today.';

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

/** The headline of Today while the closet cannot dress you yet. */
export function addFirstTitle(items: ItemSummary[] | null | undefined): string {
  return `Add ${joinWords(whatToAddFirst(items).map((w) => w.replace(/ \(.*\)$/, '')))}, and Today can dress you`;
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

/** Everything under this prefix is closet data and is forgotten with this device's other saved copies (`clearSavedData`). */
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
  /** Kept on this phone while Nines could not be reached: the kept action's id (`outbox.ts`), until Nines has it. */
  kept?: string;
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
    outfit: { pieces, score: todays.score, reasons: todays.reasons, warnings: todays.warnings },
  };
}

const keyFor = (what: string, profile: string) => `${SAVED_PREFIX}:${what}:${profile}`;

function forToday<T extends { day: string }>(value: T | null, today: string): T | null {
  return value && value.day === today ? value : null;
}

/** The outfits changed today: the piece every outfit is built around, and the pieces left out ("Not this piece"). */
export interface TodayChanges {
  day: string;
  build_around: string | null;
  leave_out: string[];
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
    changes: (today: string) => forToday(read<TodayChanges>(keyFor('changes', profile), kv), today),
    setChanges: (value: TodayChanges | null) => write(keyFor('changes', profile), value, kv),
  };
}

/** Removes everything this screen kept about the closet (when this device's saved copies are forgotten). */
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

/**
 * What Today shows about Claude choosing the outfits: nothing ('none': Claude does not choose here, or a saved copy
 * kept while Claude was still choosing), the waiting card ('waiting'), Claude's sentence with "Ask Claude again"
 * ('read'), or why Claude could not choose with "Try again" ('failed'). `saved`: the answer is a copy kept on this
 * device, shown offline, so nothing can be waited for.
 */
export function stylistView(stylist: StylistState | null | undefined, saved: boolean): 'none' | 'waiting' | 'read' | 'failed' {
  if (!stylist) return 'none';
  if (stylist.state === 'working') return saved ? 'none' : 'waiting';
  return stylist.state === 'ready' ? 'read' : 'failed';
}

/** The small line on an outfit saying who chose it, once Claude has answered (or could not); null otherwise. */
export function chosenBy(outfit: Pick<Outfit, 'by'>, stylist: StylistState | null | undefined): string | null {
  if (outfit.by === 'claude') return 'Chosen by Claude';
  return stylist && (stylist.state === 'ready' || stylist.state === 'failed') ? "From Nines' rules" : null;
}

/** Claude's reading of the day, said in "Why this works" of an outfit Claude chose (it was a line of its own under the
 * outfits); null for the rules' outfits and before Claude has answered. */
export function readFor(outfit: Pick<Outfit, 'by'>, stylist: StylistState | null | undefined): string | null {
  return outfit.by === 'claude' && stylist?.state === 'ready' ? stylist.read || null : null;
}

/** How long Claude has been choosing (seconds) before the waiting card says it is taking longer than usual. */
export const STYLIST_SLOW_S = 90;

/** The line under "Claude is choosing today's outfits…", after `seconds` of waiting. */
export function waitingLine(seconds: number): string {
  return seconds >= STYLIST_SLOW_S ? 'This is taking longer than usual.'
    : 'This usually takes under a minute. They are kept for the rest of the day.';
}

// --------------------------------------------------------------------- talking to Claude about the outfits

/** The longest message to Claude (the server's `styling.MAX_SAY`). */
export const MAX_SAY = 500;

/** The conversation and the message being answered, from a stylist state, also from a copy saved before they existed. */
export function talkOf(stylist: StylistState | null | undefined): { talk: TalkTurn[]; answering: string | null } {
  return { talk: Array.isArray(stylist?.talk) ? stylist.talk : [], answering: stylist?.answering ?? null };
}

/** Whether a message can be sent: something other than spaces. */
export function canSay(text: string): boolean {
  return text.trim().length > 0;
}

/**
 * Which outfit is in front of the owner, for `looking_at`: the carousel shows one outfit at a time, so it is the one at
 * its place (kept within the outfits shown); null when there is none.
 */
export function lookingAt(index: number, count: number): number | null {
  if (count <= 0) return null;
  return Math.max(0, Math.min(index, count - 1));
}

/** The question on a thing Claude offered to remember, and the button that keeps it. */
export function rememberWords(thing: RememberThing): { question: string; save: string } {
  return thing.kind === 'piece'
    ? { question: `Keep this on ${thing.name || 'this piece'}?`, save: 'Save to its notes' }
    : { question: 'Keep this for other days?', save: 'Save to Your style' };
}

/** The quiet line in place of a thing once it is saved. */
export function savedLine(thing: RememberThing): string {
  return thing.kind === 'piece' ? `Saved to ${thing.name || 'the piece'}'s notes.` : 'Saved to Your style.';
}

/** The answer with one thing of one turn as it now stands (after Save or No thanks); the same answer when not found. */
export function withThing(answer: TodayAnswer, turnId: string, index: number, thing: RememberThing): TodayAnswer {
  const stylist = answer.context.stylist;
  const talk = talkOf(stylist).talk;
  if (!stylist || !talk.some((t) => t.id === turnId && index >= 0 && index < t.remember.length)) return answer;
  const next = talk.map((t) => (t.id !== turnId ? t : { ...t, remember: t.remember.map((r, i) => (i === index ? thing : r)) }));
  return { ...answer, context: { ...answer.context, stylist: { ...stylist, talk: next } } };
}

/** Whether two lists of outfits are the same outfits in the same order (after Claude answered a message). */
export function sameOutfits(a: Outfit[], b: Outfit[]): boolean {
  return a.length === b.length && a.every((o, i) => outfitIds(o.pieces).join(',') === outfitIds(b[i].pieces).join(','));
}

/** The outfits to show while an outfit is worn today: as they are when the worn one is among them, else with the worn
 * one first (asked again after the wear, or on another visit, the outfits no longer hold it), so it is always on a card
 * that says so, never in a line above them. */
export function withWorn(outfits: Outfit[], worn: Pick<WornToday, 'ids' | 'outfit'> | null): Outfit[] {
  if (!worn || outfits.some((o) => sameOutfit(outfitIds(o.pieces), worn.ids))) return outfits;
  return [worn.outfit, ...outfits];
}

/**
 * What of the closet today's outfits depend on: each item's place, availability and rating, in one string (null until
 * the list is read). It is part of the question asked, so outfits kept from earlier are shown again only while these
 * are the same; an item's name, photo or drawing changing does not ask again.
 */
export function closetKey(items: readonly Pick<ItemSummary, 'id' | 'category' | 'status' | 'laundry' | 'rating'>[] | null | undefined): string | null {
  if (!items) return null;
  return JSON.stringify(items.map((i) => JSON.stringify([i.id, i.category, i.status, i.laundry, i.rating])).sort());
}

/**
 * Of the answers kept for today's question (`[day, updatedAt, answer]`, any choices), the newest one asked on `day`:
 * shown while the outfits for other choices are asked for, as the outfits on screen were before.
 */
export function newestOn<T>(kept: readonly (readonly [string, number, T | undefined])[], day: string): T | undefined {
  let best: { at: number; answer: T } | undefined;
  for (const [d, at, answer] of kept) {
    if (d === day && answer !== undefined && (!best || at > best.at)) best = { at, answer };
  }
  return best?.answer;
}
