import type { ItemSummary } from './types';

/** A kind from the owner's taxonomy: an oxford shirt, a fleece pullover, a chelsea boot. */
export interface KindInfo {
  id: string;
  name: string;
  /** the group it is shown in, made from its taxonomy category */
  group: string;
  /** the coarse category choosing it sets */
  category: string;
  /** every word the search finds it by: its name, signature, common words and group */
  words: string;
  /** whether it has a drawing (accessories have none) */
  drawn: boolean;
}

export interface KindGroup {
  id: string;
  title: string;
}

export interface KindCatalogue {
  groups: KindGroup[];
  kinds: KindInfo[];
}

const wordsOf = (text: string) => text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

/**
 * The kinds that answer a search: every word typed must start a word of the kind's name or of its other words
 * ("snap" finds the western shirt by its pearl snaps, "trainers" a running shoe). Those found by their name come
 * first, then the taxonomy's order.
 */
export function searchKinds(catalogue: KindCatalogue, query: string): KindInfo[] {
  const typed = wordsOf(query);
  if (!typed.length) return [];
  const found: { score: number; at: number; kind: KindInfo }[] = [];
  catalogue.kinds.forEach((kind, at) => {
    const name = wordsOf(kind.name);
    const words = wordsOf(kind.words);
    let score = 0;
    for (const t of typed) {
      if (name.some((w) => w.startsWith(t))) score += 2;
      else if (words.some((w) => w.startsWith(t))) score += 1;
      else return;
    }
    found.push({ score, at, kind });
  });
  return found.sort((a, b) => b.score - a.score || a.at - b.at).map((f) => f.kind);
}

/** The kinds in a group, in the taxonomy's order. */
export function kindsIn(catalogue: KindCatalogue, group: string): KindInfo[] {
  return catalogue.kinds.filter((k) => k.group === group);
}

export function groupTitle(groups: KindGroup[] | undefined, id: string | null | undefined): string {
  return groups?.find((g) => g.id === id)?.title ?? '';
}

/** "Fleece pullover · Activewear"; an item with no kind yet shows its group alone. */
export function kindLine(item: Pick<ItemSummary, 'kind_name' | 'group'>, groups: KindGroup[] | undefined): string {
  return [item.kind_name, groupTitle(groups, item.group)].filter(Boolean).join(' · ');
}

/** The small drawing of a kind, in the item's colour when it has one. */
export function kindDrawing(kind: string, colorHex?: string | null): string {
  const hex = colorHex && /^#[0-9a-f]{6}$/i.test(colorHex) ? colorHex.toLowerCase() : null;
  return `/api/kinds/${encodeURIComponent(kind)}.svg${hex ? `?color=${encodeURIComponent(hex)}` : ''}`;
}

/** The kinds Claude also thought of, as kinds of the catalogue, without the one the item is now. */
export function alsoThought(catalogue: KindCatalogue, alternatives: string[] | undefined, current: string | null): KindInfo[] {
  const byId = new Map(catalogue.kinds.map((k) => [k.id, k]));
  return (alternatives ?? []).filter((id) => id !== current).map((id) => byId.get(id)).filter((k): k is KindInfo => !!k);
}

/** The groups the closet's items are in, in the taxonomy's order: what the Closet can be filtered by. */
export function groupsIn(items: Pick<ItemSummary, 'group'>[], groups: KindGroup[] | undefined): KindGroup[] {
  const seen = new Set(items.map((it) => it.group).filter(Boolean));
  return (groups ?? []).filter((g) => seen.has(g.id));
}

/** The kinds the closet's items are (in one group, when one is chosen), by name. */
export function kindsOf(items: Pick<ItemSummary, 'kind' | 'kind_name' | 'group'>[], group: string | null): { id: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const it of items) if (it.kind && it.kind_name && (!group || it.group === group)) seen.set(it.kind, it.kind_name);
  return [...seen].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
}
