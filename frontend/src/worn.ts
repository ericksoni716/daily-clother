/** Outfits worn: the shapes the server sends, plain words for ratings, and when Today asks how one went. */
import { SAVED_PREFIX, temps, type OutfitPieces } from './today';
import { localDay, wearDay } from './wears';

export const RATINGS = ['loved', 'fine', 'not_again'] as const;
export type Rating = (typeof RATINGS)[number];

export const REASONS = ['too_warm', 'too_cold', 'too_dressy', 'too_casual', 'colours_clashed', 'uncomfortable', 'compliments', 'other'] as const;
export type Reason = (typeof REASONS)[number];

/** The pieces of a worn outfit by place, as they were worn (a piece deleted since keeps its id: see `gone`). */
export interface WornPieces extends Omit<OutfitPieces, 'base' | 'bottom' | 'shoes'> {
  base: string | null;
  bottom: string | null;
  shoes: string | null;
}

export interface WornContext {
  low_c: number | null;
  high_c: number | null;
  rain: boolean | null;
  occasion: string | null;
  mood: string | null;
}

export interface WornOutfit {
  id: string;
  worn_on: string;
  recorded_by: 'today' | 'hand';
  pieces: WornPieces;
  context: WornContext | null;
  score: number | null;
  reasons: string[];
  warnings: string[];
  rating: Rating | null;
  rating_reasons: Reason[];
  rating_note: string | null;
  rated_at: string | null;
  created_at: string;
  /** Pieces deleted from the closet since. The outfit no longer teaches Today anything. */
  gone: string[];
}

export interface WornPage {
  outfits: WornOutfit[];
  /** Give this back as `before` for the next page; null when there is no more. */
  next: string | null;
}

/** What Today sends with "I'm wearing this" so the outfit is remembered with what it was offered for. */
export interface OutfitSent {
  pieces: OutfitPieces;
  context: Partial<WornContext>;
  score: number | null;
  reasons: string[];
  warnings: string[];
}

const RATING_WORDS: Record<Rating, string> = { loved: 'Loved it', fine: 'Fine', not_again: 'Not again' };
const REASON_WORDS: Record<Reason, string> = {
  too_warm: 'Too warm', too_cold: 'Too cold', too_dressy: 'Too dressed up', too_casual: 'Too casual',
  colours_clashed: 'Colours clashed', uncomfortable: 'Uncomfortable', compliments: 'Got compliments', other: 'Other',
};

export function ratingLabel(r: string): string {
  return RATING_WORDS[r as Rating] ?? r;
}

export function reasonLabel(r: string): string {
  return REASON_WORDS[r as Reason] ?? r;
}

/** The reasons that fit an answer: after "loved it" what went well, after "not again" what went wrong, after "fine"
 * either (what went wrong first). "Other" is always offered. */
export function reasonsFor(rating: Rating): Reason[] {
  if (rating === 'loved') return ['compliments', 'other'];
  if (rating === 'not_again') return REASONS.filter((r) => r !== 'compliments');
  return [...REASONS];
}

/** The pieces the owner can record an outfit from, in the four groups of the sheet, most recently worn first. */
export const RECORD_GROUPS = [
  { group: 'tops', label: 'Tops', categories: ['tee', 'shirt', 'polo', 'sweater', 'hoodie', 'jacket', 'coat'] },
  { group: 'bottoms', label: 'Bottoms', categories: ['jeans', 'trousers', 'shorts'] },
  { group: 'shoes', label: 'Shoes', categories: ['sneakers', 'boots', 'dress_shoes', 'sandals'] },
  { group: 'extras', label: 'Extras', categories: [] as string[] },
] as const;

interface RecordPiece { id: string; name: string | null; category: string | null; color: string | null; status: string; last_worn: string | null }

/**
 * The pieces for "Record an outfit": those still in the closet with a category, in their group (tops, bottoms, shoes,
 * then everything else as extras), most recently worn first, then by name. `query` keeps those whose name, category or
 * colour (as `words` gives them) has every word of it; groups left empty are dropped.
 */
export function recordGroups<T extends RecordPiece>(items: T[], query: string, words: (item: T) => string):
  { group: string; label: string; pieces: T[] }[] {
  const asked = query.toLowerCase().split(/\s+/).filter(Boolean);
  const usable = items.filter((i) => i.status !== 'archived' && i.category)
    .filter((i) => asked.every((w) => words(i).toLowerCase().includes(w)))
    .sort((a, b) => (b.last_worn ?? '').localeCompare(a.last_worn ?? '') || words(a).localeCompare(words(b)));
  const known = new Set<string>(RECORD_GROUPS.flatMap((g) => g.categories));
  return RECORD_GROUPS.map((g) => ({
    group: g.group, label: g.label,
    pieces: usable.filter((i) => (g.group === 'extras' ? !known.has(i.category!) : (g.categories as readonly string[]).includes(i.category!))),
  })).filter((g) => g.pieces.length > 0);
}

/** "Loved it · too warm, got compliments" — what a rating says, in one line. */
export function ratingSummary(o: Pick<WornOutfit, 'rating' | 'rating_reasons' | 'rating_note'>): string {
  if (!o.rating) return 'Not rated yet';
  const reasons = o.rating_reasons.map((r) => (r === 'other' && o.rating_note ? o.rating_note : reasonLabel(r).toLowerCase()));
  return reasons.length ? `${ratingLabel(o.rating)} · ${reasons.join(', ')}` : ratingLabel(o.rating);
}

/** What a piece of a worn outfit is called: an archived piece as itself, marked archived; one deleted since, as that. */
export function pieceName(
  item: { name: string | null; category: string | null; status: string } | undefined, deleted: boolean,
  categoryLabel: (c: string) => string,
): string {
  if (deleted) return 'A piece since deleted';
  if (!item) return 'A piece of your closet';
  const name = item.name || (item.category ? categoryLabel(item.category) : '') || 'An item';
  return item.status === 'archived' ? `${name} (archived)` : name;
}

/** Every item id of a worn outfit in the order they are put on. */
export function wornIds(p: WornPieces): string[] {
  const out: string[] = [];
  for (const place of ['outer', 'mid', 'base', 'bottom', 'shoes'] as const) {
    const id = p[place];
    if (id) out.push(id);
  }
  return [...out, ...(p.accessories ?? [])];
}

function daysBefore(day: string, n: number): string {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d - n)).toISOString().slice(0, 10);
}

/** "How was yesterday's outfit?" or "How was today's outfit?". */
export function questionFor(o: Pick<WornOutfit, 'worn_on'>, today: string = localDay()): string {
  return o.worn_on === today ? "How was today's outfit?" : "How was yesterday's outfit?";
}

/** "Yesterday", "Tuesday 10 Nov", like the wear lists. */
export function wornDay(o: Pick<WornOutfit, 'worn_on'>, today: string = localDay()): string {
  return wearDay(o.worn_on, today);
}

/** "9–16°C · casual" — the day an outfit was worn for, if it was remembered. */
export function contextWords(c: WornContext | null, occasionLabel: (v: string) => string): string {
  if (!c) return '';
  const parts: string[] = [];
  if (c.low_c !== null && c.high_c !== null) {
    parts.push(temps(c.low_c, c.high_c));
  }
  if (c.rain) parts.push('rain');
  if (c.occasion) parts.push(occasionLabel(c.occasion).toLowerCase());
  return parts.join(' · ');
}

/**
 * The outfit Today asks about: the newest one worn today or yesterday that has no rating and was not
 * waved away on this device. Yesterday's comes first: today's outfit is still being worn.
 */
/** Today's own outfit is asked about from this hour (local time): asking the moment it is put on is too soon. */
export const ASK_TODAY_FROM_HOUR = 18;

export function pendingQuestion(list: WornOutfit[] | null | undefined, dismissed: string[], today: string = localDay(),
  hour: number = new Date().getHours()): WornOutfit | null {
  const yesterday = daysBefore(today, 1);
  const open = (list ?? []).filter((o) => !o.rating && !dismissed.includes(o.id));
  return open.find((o) => o.worn_on === yesterday)
    ?? (hour >= ASK_TODAY_FROM_HOUR ? open.find((o) => o.worn_on === today) : undefined) ?? null;
}

// --------------------------------------------------------------------- pages as read, changed by a save

/** The outfits of the pages read so far, in order, each once (a page read again may overlap the next). */
export function joinPages(pages: readonly (WornPage | undefined)[]): WornOutfit[] {
  const seen = new Set<string>();
  const out: WornOutfit[] = [];
  for (const page of pages) {
    for (const o of page?.outfits ?? []) {
      if (seen.has(o.id)) continue;
      seen.add(o.id);
      out.push(o);
    }
  }
  return out;
}

/** A page with this outfit put in where it was (a rating changed); the same page when it does not hold it. */
export function withOutfit(page: WornPage, o: WornOutfit): WornPage {
  return page.outfits.some((x) => x.id === o.id) ? { ...page, outfits: page.outfits.map((x) => (x.id === o.id ? o : x)) } : page;
}

/** A page without this outfit (removed); the same page when it does not hold it. */
export function withoutOutfit(page: WornPage, id: string): WornPage {
  return page.outfits.some((x) => x.id === id) ? { ...page, outfits: page.outfits.filter((x) => x.id !== id) } : page;
}

/** The first page with an outfit just recorded put in by its day, newest first. */
export function withRecorded(page: WornPage, o: WornOutfit): WornPage {
  const rest = page.outfits.filter((x) => x.id !== o.id);
  const at = rest.findIndex((x) => x.worn_on <= o.worn_on);
  return { ...page, outfits: at === -1 ? [...rest, o] : [...rest.slice(0, at), o, ...rest.slice(at)] };
}

// --------------------------------------------------------------------- kept on this device

type KV = Pick<Storage, 'getItem' | 'setItem'>;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The first page of worn outfits as last fetched, kept per closet for offline (forgotten with this device's other saved copies). */
export interface SavedWorn {
  saved_at: string;
  page: WornPage;
}

const savedKey = (profile: string) => `${SAVED_PREFIX}:worn-list:${profile}`;

export function loadSavedWorn(profile: string, kv: KV | null = local()): SavedWorn | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const value = raw ? (JSON.parse(raw) as SavedWorn) : null;
    return value && typeof value.saved_at === 'string' && Array.isArray(value.page?.outfits) ? value : null;
  } catch {
    return null;
  }
}

export function saveWorn(profile: string, page: WornPage, kv: KV | null = local(), now = new Date()) {
  try {
    kv?.setItem(savedKey(profile), JSON.stringify({ saved_at: now.toISOString(), page }));
  } catch {
    /* private mode or full: not kept, nothing else breaks */
  }
}

/** Under the Today screen's prefix, so it is forgotten with this device's other saved copies. */
const dismissedKey = (profile: string) => `${SAVED_PREFIX}:asked:${profile}`;
/** Only the last few are kept: the question is only ever about today or yesterday. */
const DISMISSED_KEPT = 10;

export function loadDismissed(profile: string, kv: KV | null = local()): string[] {
  try {
    const v = JSON.parse(kv?.getItem(dismissedKey(profile)) ?? '[]');
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function dismiss(profile: string, id: string, kv: KV | null = local()): string[] {
  const next = [...loadDismissed(profile, kv).filter((x) => x !== id), id].slice(-DISMISSED_KEPT);
  try {
    kv?.setItem(dismissedKey(profile), JSON.stringify(next));
  } catch {
    /* not remembered: the question comes back next time, nothing else breaks */
  }
  return next;
}
