/** Insights: the shapes the server sends, plain words for them, and the pieces this device was told to keep. */
import { categoryPlural, label } from './labels';
import { SAVED_PREFIX } from './today';

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

export interface Insights {
  today: string;
  log: { wears: number; first: string | null; days: number };
  cost_per_wear: CostPerWear;
  never_worn: Unworn;
  not_worn_lately: Unworn;
  worn_most: Finding & { windows: WornWindow[] };
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

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "31 Oct 2026" from "2026-10-31". */
export function shortDate(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

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

/** The last answer fetched for a closet, kept on this device so Insights opens offline; removed on logout. */
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
