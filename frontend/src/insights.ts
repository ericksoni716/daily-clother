/** Insights: the shapes the server sends, plain words for them, and the pieces this device was told to keep. */
import { categoryPlural, label } from './labels';
import { amount } from './spend';
import { SAVED_PREFIX } from './today';
import { fullDate } from './wears';

/** What every finding has: a title, whether there is enough history for its numbers, and the sentence read first. */
export interface Finding {
  title: string;
  enough: boolean;
  sentence: string;
}

export interface CostPiece {
  id: string;
  price_cents: number;
  wears: number;
  /** null for a piece not worn yet: it has no cost per wear. */
  per_wear_cents: number | null;
  sentence: string;
}

export interface CostPerWear extends Finding {
  closet: { pieces: number; spent_cents: number; wears: number; per_wear_cents: number } | null;
  best: CostPiece[];
  worst: CostPiece[];
  not_worn: CostPiece[];
}

export interface UnwornPiece {
  id: string;
  sentence: string;
  /** Never worn: the day it could first be worn (added, or the log began). */
  since?: string;
  /** Not worn for a long time: the last wear. */
  last_worn?: string;
  season_days?: number;
}

export interface Unworn extends Finding {
  items: UnwornPiece[];
}

export interface Counted {
  id: string;
  wears: number;
}

export interface WornWindow extends Finding {
  /** 30, 90, or null for all time. */
  days: number | null;
  wears: number;
  items: Counted[];
}

export interface CategorySpread {
  category: string;
  pieces: number;
  wears: number;
  doing_most: number;
  share: number;
  kind: 'few' | 'even';
  sentence: string;
  items: Counted[];
}

export interface MakeupGroup {
  value: string | null;
  count: number;
  worn: number;
}

export const MAKEUP_FIELDS = ['category', 'color', 'formality', 'season'] as const;
export type MakeupField = (typeof MAKEUP_FIELDS)[number];

/** One window of Your nines: the nine pieces worn most, and a sentence when there are fewer (null with nine). */
export interface NinesWindow {
  /** 30, 90, or null for all time. */
  days: number | null;
  /** How many pieces were worn in the window (the square shows at most nine). */
  pieces: number;
  sentence: string | null;
  items: Counted[];
}

export interface SpentYear {
  year: number;
  spent_cents: number;
  pieces: number;
}

export interface PricedPiece {
  id: string;
  price_cents: number;
  wears: number;
  per_wear_cents?: number;
}

export interface WishlistCost {
  wishes: number;
  /** Wishes with no price today (no find, or none still on sale). */
  unpriced: number;
  /** By currency, never added across currencies; the currency with most wishes first. */
  totals: { currency: string; cents: number; wishes: number }[];
}

/** What the closet cost, from each piece's price and the date it was bought; the wishlist at today's prices. */
export interface Spending {
  /** The closet's prices are all in this one currency (the price field's). */
  currency: string;
  year: number;
  pieces: number;
  priced: number;
  /** With both a price and a date bought. */
  dated: number;
  unpriced: number;
  /** The piece to fill in first: the one worn most among those with no price, or with a price and no date. */
  first_missing: string | null;
  enough: boolean;
  by_year: SpentYear[];
  earned: PricedPiece[];
  not_earned: PricedPiece[];
  wishlist: WishlistCost;
}

export interface Insights {
  today: string;
  log: { wears: number; first: string | null; last?: string | null; days: number };
  cost_per_wear: CostPerWear;
  never_worn: Unworn;
  not_worn_lately: Unworn;
  worn_most: Finding & { windows: WornWindow[] };
  /** Missing from a copy saved before Your nines (offline): then the section is left out. */
  nines?: { title: string; windows: NinesWindow[] };
  /** Missing from a copy saved before what your clothes cost you (offline). */
  spending?: Spending;
  spread: Finding & { days: number; categories: CategorySpread[] };
  makeup: Finding & { pieces: number; worn: number | null; days: number; by: Record<MakeupField, MakeupGroup[]> };
}

// --------------------------------------------------------------------- words

/** The currency the price field shows; prices are kept as typed, never converted. */
export const CURRENCY = '$';

/** "$45", "$45.50", "$1,040" from cents. */
export function money(cents: number): string {
  const whole = Math.floor(cents / 100);
  const part = cents % 100;
  return `${CURRENCY}${whole.toLocaleString('en-US')}${part ? `.${String(part).padStart(2, '0')}` : ''}`;
}

/** "$2.40 a wear": always with cents, since a few cents matter here. */
export function perWear(cents: number): string {
  const whole = Math.floor(cents / 100);
  return `${CURRENCY}${whole.toLocaleString('en-US')}.${String(cents % 100).padStart(2, '0')} a wear`;
}

/** "1 piece", "3 pieces"; the plural is the word plus "s" unless given. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "Not worn yet", "1 wear", "25 wears". */
export function wears(n: number): string {
  return n === 0 ? 'Not worn yet' : plural(n, 'wear');
}

/** What is shown under a piece in the cost-per-wear card. */
export function costCaption(p: CostPiece): string {
  return p.per_wear_cents === null ? `${money(p.price_cents)} · not worn yet` : `${perWear(p.per_wear_cents)} · ${wears(p.wears)}`;
}

/** "31 Oct 2026" from "2026-10-31" (the one family of dates, wears.ts). */
export const shortDate = (day: string): string => fullDate(day);

/** What is shown under a piece that is not being worn. */
export function unwornCaption(p: UnwornPiece): string {
  if (p.last_worn) return `Last worn ${shortDate(p.last_worn)}`;
  return 'Not worn yet';
}

/** "Last 30 days", "Last 90 days", "All time". */
export function windowLabel(days: number | null): string {
  return days ? `Last ${days} days` : 'All time';
}

export const FIELD_WORDS: Record<MakeupField, string> = { category: 'Kind', color: 'Colour', formality: 'Formality', season: 'Season' };

/** The label of a value in the "made of" card; "Not set" where the item has none. */
export function groupLabel(field: MakeupField, value: string | null): string {
  if (!value) return 'Not set';
  return field === 'category' ? categoryPlural(value) : label(field, value);
}

// --------------------------------------------------------------------- Your nines

/** The window Your nines opens on: the first with nine pieces, else the one with the most (the shortest of those). */
export function ninesWindow(windows: NinesWindow[]): number {
  const full = windows.findIndex((w) => w.items.length >= 9);
  if (full >= 0) return full;
  let best = 0;
  windows.forEach((w, i) => { if (w.items.length > windows[best].items.length) best = i; });
  return best;
}

// --------------------------------------------------------------------- what your clothes cost you

function join(words: string[]): string {
  return words.length < 2 ? (words[0] ?? '') : `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

/** The one line in view: what was spent this year once a few pieces have a price and a date, else what is missing,
 * with `fill` saying what the link to the piece to start with asks for. Null for an empty closet. */
export function spentWords(s: Spending): { text: string; fill: 'price' | 'date' | null } | null {
  if (!s.pieces) return null;
  if (s.enough) {
    const year = s.by_year.find((y) => y.year === s.year);
    if (year) return { text: `You spent ${amount(year.spent_cents, s.currency)} on ${plural(year.pieces, 'piece')} this year.`, fill: null };
    const last = s.by_year[0];
    return { text: `Nothing with a price was bought this year. In ${last.year} you spent ${amount(last.spent_cents, s.currency)} on ${plural(last.pieces, 'piece')}.`, fill: null };
  }
  if (s.unpriced) {
    const text = s.unpriced === s.pieces
      ? (s.pieces === 1 ? 'Your one piece has no price yet.' : `None of your ${s.pieces} pieces has a price yet.`)
      : `${s.unpriced} of your ${s.pieces} pieces ${s.unpriced === 1 ? 'has' : 'have'} no price yet.`;
    return { text, fill: 'price' };
  }
  const undated = s.priced - s.dated;
  return { text: `${undated} of your pieces ${undated === 1 ? 'has' : 'have'} a price but no date bought.`, fill: 'date' };
}

/** "In 2026 you spent $1,240 on 9 pieces." for each year, newest first. */
export function yearWords(s: Spending): string[] {
  return s.by_year.map((y) => `In ${y.year} you spent ${amount(y.spent_cents, s.currency)} on ${plural(y.pieces, 'piece')}.`);
}

/** Under a piece that has earned its price, or not yet. */
export function earnedCaption(p: PricedPiece, currency: string): string {
  return p.per_wear_cents !== undefined && p.wears >= 1
    ? `${amount(p.per_wear_cents, currency, true)} a wear · ${wears(p.wears)}`
    : `${amount(p.price_cents, currency)} · ${wears(p.wears)}`;
}

/** What the wishlist would cost at today's prices, never adding up prices in different currencies. Null with no wishes. */
export function wishlistCostWords(w: WishlistCost): string | null {
  if (!w.wishes) return null;
  if (!w.totals.length) return w.wishes === 1 ? 'The one thing on your wishlist has no price yet.' : `Nothing on your wishlist has a price yet.`;
  const rest = w.unpriced ? ` ${plural(w.unpriced, 'thing')} ${w.unpriced === 1 ? 'has' : 'have'} no price yet.` : '';
  if (w.totals.length === 1) {
    const [t] = w.totals;
    const what = w.unpriced ? `the ${plural(t.wishes, 'thing')} on your wishlist with a price` : 'your wishlist';
    return `At today's prices, ${what} would cost ${amount(t.cents, t.currency)}.${rest}`;
  }
  const parts = w.totals.map((t) => `${amount(t.cents, t.currency)} for ${plural(t.wishes, 'thing')}`);
  return `Your wishlist is priced in ${w.totals.length} currencies, so it is not added up. At today's prices it is ${join(parts)}.${rest}`;
}

// --------------------------------------------------------------------- the figure each card leads with

/** "3 pieces" not being worn; null when there is too little history, or nothing to list. */
export function unwornHero(f: Unworn, listed: number): string | null {
  return f.enough && listed > 0 ? plural(listed, 'piece') : null;
}

/** "25 wears" recorded in the chosen window; null when there are none. */
export function wornMostHero(w: WornWindow): string | null {
  return w.wears > 0 ? plural(w.wears, 'wear') : null;
}

/** "2 of 5 kinds" where a few pieces do most of the wearing, or "Fairly even". */
export function spreadHero(f: Insights['spread']): string | null {
  if (!f.enough || !f.categories.length) return null;
  const few = f.categories.filter((c) => c.kind === 'few').length;
  return few ? `${few} of ${plural(f.categories.length, 'kind')}` : 'Fairly even';
}

/** "18 of 30 worn" once there are enough wears, else how many pieces there are. */
export function makeupHero(f: Insights['makeup']): string | null {
  if (!f.pieces) return null;
  return f.enough && f.worn !== null ? `${f.worn} of ${f.pieces} worn` : plural(f.pieces, 'piece');
}

/** A bar's width as a percentage of the largest, at least a sliver when there is anything to show. */
export function barWidth(n: number, max: number): number {
  if (!max || n <= 0) return 0;
  return Math.max(4, Math.round((100 * n) / max));
}

// --------------------------------------------------------------------- kept on this device

/** How long "Keep" stops a piece being listed as not worn. */
export const KEEP_DAYS = 90;
const KEEP_KEY = 'closet-insights-keep';

type KV = Pick<Storage, 'getItem' | 'setItem'>;

function local(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The day `n` days after `day` (both YYYY-MM-DD). */
export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

function readKept(profile: string, kv: KV | null): Record<string, string> {
  try {
    const raw = kv?.getItem(`${KEEP_KEY}:${profile}`);
    const value = raw ? JSON.parse(raw) : null;
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

function writeKept(profile: string, value: Record<string, string>, kv: KV | null) {
  try {
    kv?.setItem(`${KEEP_KEY}:${profile}`, JSON.stringify(value));
  } catch {
    /* private mode or full: not remembered, nothing else breaks */
  }
}

/** Pieces of this closet the owner chose to keep, with the day each is listed again; only those still kept on `today`. */
export function keptPieces(profile: string, today: string, kv: KV | null = local()): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, until] of Object.entries(readKept(profile, kv))) if (typeof until === 'string' && until > today) out[id] = until;
  return out;
}

/** "Keep": not listed as not worn for KEEP_DAYS days. Returns the day it is listed again. */
export function keepPiece(profile: string, id: string, today: string, kv: KV | null = local()): string {
  const until = addDays(today, KEEP_DAYS);
  writeKept(profile, { ...keptPieces(profile, today, kv), [id]: until }, kv);
  return until;
}

/** Lists every kept piece again. */
export function forgetKept(profile: string, kv: KV | null = local()) {
  writeKept(profile, {}, kv);
}

// --------------------------------------------------------------------- the last answer, saved per closet for offline

/** The last answer fetched for a closet, kept on this device so Insights opens offline; forgotten with this device's other saved copies. */
export interface SavedInsights {
  saved_at: string;
  answer: Insights;
}

const savedKey = (profile: string) => `${SAVED_PREFIX}:insights:${profile}`;

export function loadSavedInsights(profile: string, kv: KV | null = local()): SavedInsights | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const value = raw ? (JSON.parse(raw) as SavedInsights) : null;
    return value && typeof value.saved_at === 'string' && value.answer && typeof value.answer === 'object' ? value : null;
  } catch {
    return null;
  }
}

export function saveInsights(profile: string, answer: Insights, kv: KV | null = local(), now = new Date()) {
  try {
    kv?.setItem(savedKey(profile), JSON.stringify({ saved_at: now.toISOString(), answer } satisfies SavedInsights));
  } catch {
    /* private mode or full: not saved, nothing else breaks */
  }
}
