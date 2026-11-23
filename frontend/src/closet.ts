/** The closet grid's rules, with no React in them: what a piece is (the filter's one list), how many tiles to a row on
 * a computer, and what the laundry's line and an empty grid say. */
import { groupsIn, kindsOf, type KindGroup } from './kinds';
import { categoryPlural } from './labels';
import type { ItemSummary } from './types';

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
