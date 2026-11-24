/** The closet grid's rules, with no React in them: what the search finds, what a piece is (the filter's one list), how
 * many tiles to a row on a computer, and what the laundry's line and an empty grid say. */
import { groupsIn, kindsOf, type KindGroup } from './kinds';
import { categoryPlural, label } from './labels';
import type { ItemSummary, Laundry } from './types';

/**
 * How many tiles fit a row `width` wide, each at least `min` wide with `gap` between them: what the grid's
 * `auto-fill` would choose. On a computer the grid keeps this number while a piece's panel is open beside it, so
 * opening a piece makes the tiles narrower and moves none of them to another row.
 */
export function columnsFor(width: number, min: number, gap: number): number {
  if (!(width > 0) || !(min > 0)) return 1;
  return Math.max(1, Math.floor((width + gap) / (min + gap)));
}

/** The laundry's part of the closet's line: how many pieces are in it, or that none are while it is shown. */
export function laundryPart(n: number): string {
  return n > 0 ? `${n} in the laundry` : 'Nothing in the laundry';
}

/** The line under the closet's toolbar while the laundry is shown: what is in it, or what "All clean" just did. */
export function laundryNotice(inLaundry: number, cleaned: number | null): string {
  if (cleaned !== null) return cleaned === 1 ? 'You marked it clean.' : `You marked ${cleaned} pieces clean.`;
  if (inLaundry === 0) return '';
  return inLaundry === 1 ? 'This piece is in the laundry.' : `These ${inLaundry} pieces are in the laundry.`;
}

/**
 * What the grid says when nothing is shown: the filter that is on says why in its own words ("Your laundry is empty."
 * rather than "Nothing matches"), and a search or a choice of what it is gets the general sentence.
 */
export function emptySentence(on: { check: boolean; toCheck: number; away: boolean; awayNow: number; laundry: boolean;
  inLaundry: number; searching: boolean; what: boolean }): string {
  const narrowed = on.searching || on.what;
  if (on.check && on.toCheck === 0 && !narrowed) return 'Nothing needs a check now.';
  if (on.away && on.awayNow === 0 && !narrowed) return 'Everything is in your closet.';
  if (on.laundry && on.inLaundry === 0 && !narrowed) return 'Your laundry is empty.';
  return 'Nothing matches. Try another word or filter.';
}

/**
 * What a piece is, as the filter asks it: one list of the groups the closet's pieces are in; a group chosen opens to
 * its categories (jeans, trousers, shorts) when it has more than one, and to the kinds the pieces in it are said to be.
 * Each level belongs to the one above it, so two choices can never contradict each other.
 */
export interface What { group: string | null; category: string | null; kind: string | null }
export const ANY: What = { group: null, category: null, kind: null };

type WhatItem = Pick<ItemSummary, 'group' | 'category' | 'kind' | 'kind_name'>;
export interface Choice { id: string; name: string }

/** The choices at each level for what is chosen now; a level whose choices would narrow nothing is not offered. */
export function whatChoices(items: WhatItem[], groups: KindGroup[] | undefined, what: What): { groups: KindGroup[];
  categories: Choice[]; kinds: Choice[] } {
  const inGroup = what.group ? items.filter((it) => it.group === what.group) : [];
  const seen = [...new Set(inGroup.map((it) => it.category).filter((c): c is string => !!c))];
  const categories = seen.map((c) => ({ id: c, name: categoryPlural(c) })).sort((a, b) => a.name.localeCompare(b.name));
  const inCategory = what.category ? inGroup.filter((it) => it.category === what.category) : inGroup;
  const kinds = what.group ? kindsOf(inCategory, what.group) : [];
  // a level is offered when choosing in it narrows what is shown: two or more choices, or one kind that only some of
  // the pieces are (the others have no kind said yet)
  const narrows = kinds.length > 1 || (kinds.length === 1 && inCategory.some((it) => it.kind !== kinds[0].id));
  return { groups: groupsIn(items, groups), categories: categories.length > 1 ? categories : [], kinds: narrows ? kinds : [] };
}

/** Choosing at one level clears the levels under it; choosing what is chosen already goes back up a level. */
export function chooseWhat(what: What, level: keyof What, id: string | null): What {
  if (level === 'group') return id === null || id === what.group ? ANY : { group: id, category: null, kind: null };
  if (level === 'category') return { ...what, category: id === what.category ? null : id, kind: null };
  return { ...what, kind: id === what.kind ? null : id };
}

/** Whether a piece is what is chosen. */
export function isWhat(item: WhatItem, what: What): boolean {
  if (what.group && item.group !== what.group) return false;
  if (what.category && item.category !== what.category) return false;
  if (what.kind && item.kind !== what.kind) return false;
  return true;
}

/** What is chosen, kept to what the closet still has (a piece archived or changed can take a choice away with it). */
export function whatIn(items: WhatItem[], groups: KindGroup[] | undefined, what: What): What {
  if (!what.group || !groupsIn(items, groups).some((g) => g.id === what.group)) return ANY;
  const inGroup = items.filter((it) => it.group === what.group);
  const category = what.category && inGroup.some((it) => it.category === what.category) ? what.category : null;
  const kind = what.kind && inGroup.some((it) => it.kind === what.kind && (!category || it.category === category)) ? what.kind : null;
  return { group: what.group, category, kind };
}

/** The name of what is chosen, for its one chip: the narrowest level chosen ("Jeans", "Fleece pullover"). */
export function whatName(items: WhatItem[], groups: KindGroup[] | undefined, what: What): string {
  if (what.kind) return items.find((it) => it.kind === what.kind)?.kind_name ?? '';
  if (what.category) return categoryPlural(what.category);
  return groups?.find((g) => g.id === what.group)?.title ?? '';
}

/** Words as the search compares them: small letters, accents taken off ("Écru" is "ecru"), split at anything that is
 * not a letter or a digit ("off-white" is "off white"). */
export function searchWords(text: string): string[] {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

type Searched = Pick<ItemSummary, 'name' | 'category' | 'color' | 'pattern' | 'kind_name' | 'group' | 'brand' | 'material' | 'shade' | 'own_notes'>;

/** Everything a piece is found by: its name, what it is (category, kind, group), its colour and shade, pattern, brand,
 * material, and every note the owner kept on it. */
export function searchedText(item: Searched, groups: KindGroup[] | undefined): string {
  return [item.name, label('category', item.category), categoryPlural(item.category ?? ''), item.kind_name,
    groups?.find((g) => g.id === item.group)?.title, label('color', item.color), item.shade ? label('shade', item.shade) : null,
    label('pattern', item.pattern), item.brand, item.material, item.own_notes].filter(Boolean).join(' ');
}

/**
 * Whether a piece answers a search: every word typed is found in what the piece is found by, each in any part of it
 * ("navy linen" finds the navy shirt whose material is linen) and anywhere in a word ("shirt" finds an overshirt).
 * Nothing typed finds everything.
 */
export function matchesSearch(text: string, query: string): boolean {
  const typed = searchWords(query);
  if (!typed.length) return true;
  const hay = searchWords(text).join(' ');
  return typed.every((t) => hay.includes(t));
}

/** How large the closet's pictures are: "larger", two across on a phone, or "smaller", three across. A habit of the
 * device (how many fit depends on its screen), so it is kept on it, not on the computer. */
export type TileSize = 'larger' | 'smaller';
export const TILE_SIZE_KEY = 'closet.tileSize';

export function loadTileSize(): TileSize {
  try {
    return localStorage.getItem(TILE_SIZE_KEY) === 'smaller' ? 'smaller' : 'larger';
  } catch {
    return 'larger';
  }
}

export function keepTileSize(size: TileSize): void {
  try {
    localStorage.setItem(TILE_SIZE_KEY, size);
  } catch {
    /* private browsing: the choice lasts until the page closes */
  }
}

/** The smallest a tile may be on a computer, for each size (styles.css, "grid & tiles"). */
export const TILE_MIN_WIDE: Record<TileSize, number> = { larger: 180, smaller: 130 };

/**
 * A piece's name as a small tile shows it, on two short lines: whole when it fits in `max` letters, else cut after
 * the last whole word that fits, with "…" (never in the middle of a word, unless the first word alone is too long).
 */
export function shortName(name: string, max: number): string {
  const text = name.replace(/\s+/g, ' ').trim();
  if (text.length <= max) return text;
  const room = text.slice(0, max);
  const space = room.lastIndexOf(' ');
  const kept = (space > 0 ? room.slice(0, space) : room.slice(0, max - 1)).replace(/[\s,;:·–-]+$/u, '');
  return `${kept}…`;
}

/**
 * A piece's name as a narrow tile shows it on two lines: whole when its words fit two lines `width` wide (as the page
 * breaks them, between words), else cut after the last whole word that fits on the second line with "…". `measure`
 * gives a text's width in the tile's font. Larger tiles beside a piece's panel on a computer are narrow, so their
 * names take two lines there, as small tiles' do, rather than one line cut in the middle of a word.
 */
export function twoLineName(name: string, width: number, measure: (text: string) => number): string {
  const words = name.replace(/\s+/g, ' ').trim().split(' ');
  const fits = (text: string) => measure(text) <= width;
  const trim = (text: string) => text.replace(/[\s,;:·–-]+$/u, '');
  // a first word too long for a line is broken by the page over both lines: nothing else fits after it
  if (!fits(words[0])) return words.length > 1 ? `${trim(words[0])}…` : words[0];
  // the first line: as many words as fit
  let first = 1;
  while (first < words.length && fits(words.slice(0, first + 1).join(' '))) first++;
  let second = first;
  while (second < words.length && fits(words.slice(first, second + 1).join(' '))) second++;
  if (second === words.length) return words.join(' ');
  for (let end = second; end > first; end--) {
    const line = `${trim(words.slice(first, end).join(' '))}…`;
    if (fits(line)) return `${words.slice(0, first).join(' ')} ${line}`;
  }
  return `${trim(words.slice(0, first).join(' '))}…`;
}

/** The closet's search and filters: kept in its address, so a reload, Back and a link keep them. */
export interface ClosetFilters { what: What; query: string; laundry: Laundry | null; check: boolean; away: boolean }
export const NO_FILTERS: ClosetFilters = { what: ANY, query: '', laundry: null, check: false, away: false };
const PARAMS = ['q', 'group', 'category', 'kind', 'laundry', 'check', 'away'] as const;

/** The address's query for the search and filters ("" when none is on): `?q=navy&group=trousers&laundry=laundry`. */
export function filtersToSearch(f: ClosetFilters): string {
  const q = new URLSearchParams();
  if (f.query) q.set('q', f.query);
  if (f.what.group) q.set('group', f.what.group);
  if (f.what.group && f.what.category) q.set('category', f.what.category);
  if (f.what.group && f.what.kind) q.set('kind', f.what.kind);
  if (f.laundry) q.set('laundry', f.laundry);
  if (f.check) q.set('check', '1');
  if (f.away) q.set('away', '1');
  const out = q.toString();
  return out ? `?${out}` : '';
}

/** The search and filters an address keeps, or null when it says nothing about them (the closet's own address). */
export function filtersFromSearch(search: string): ClosetFilters | null {
  const q = new URLSearchParams(search);
  if (!PARAMS.some((p) => q.has(p))) return null;
  const group = q.get('group') || null;
  const laundry = q.get('laundry');
  return {
    what: { group, category: group ? q.get('category') || null : null, kind: group ? q.get('kind') || null : null },
    query: q.get('q') ?? '',
    laundry: laundry === 'clean' || laundry === 'laundry' ? laundry : null,
    check: q.get('check') === '1',
    away: q.get('away') === '1',
  };
}

/**
 * What the closet opens on, from the search and filters it was left with (or its address asks for) and the pieces it
 * has: a kept view with nothing in it would be a view of nothing, with a "0 away" or "Nothing in the laundry" to tap
 * away, so the closet opens on everything instead; the search and the other filters stay as they were. The Away view
 * goes when no piece is away, the laundry's when no piece is in that state, and "Needs a check" when `toCheck` (the
 * pieces the review holds, which arrives after the list: null until it has) is nought. Only on opening: in the view,
 * a piece just brought back keeps its row with Undo (`AwayView`), and the laundry just marked clean its line with Undo.
 */
export function openedFilters(f: ClosetFilters, items: (Pick<ItemSummary, 'away'> & { laundry?: Laundry | null })[], toCheck: number | null = null): ClosetFilters {
  let out = f;
  if (out.away && !items.some((it) => it.away)) out = { ...out, away: false };
  if (out.laundry && !items.some((it) => (it.laundry ?? 'clean') === out.laundry)) out = { ...out, laundry: null };
  if (out.check && toCheck === 0) out = { ...out, check: false };
  return out;
}

/** The search and filters last used on this tab, per closet and per In use or Archived: what the closet comes back to
 * when it is opened from its plain address (the tab bar, a back link). Kept for the tab, as its scroll positions are. */
const KEPT = 'closet-filters';

export function keptFilters(key: string): ClosetFilters | null {
  try {
    const search = window.sessionStorage.getItem(`${KEPT}:${key}`);
    return search === null ? null : filtersFromSearch(search) ?? NO_FILTERS;
  } catch {
    return null;
  }
}

export function keepFilters(key: string, search: string): void {
  try {
    window.sessionStorage.setItem(`${KEPT}:${key}`, search);
  } catch {
    /* storage is off (a private window): the address still keeps them */
  }
}
