/**
 * How often to ask the server again while it works on items in the background, and what to read again when that
 * work moves on. Pure, so the choices are tested here; the asking is done in the closet's provider (`store.tsx`),
 * which follows `GET /api/progress` for every screen.
 */
import { going } from './progress';
import type { Item, ModelInfo, ProgressList } from './types';

/** While anything is being done (or is next in line), measuring a pattern and drawing a shoe included. */
export const FAST_MS = 2000;
/** While items only wait for something outside (background removal, a way to reach Claude, your answer). */
export const WAITING_MS = 10_000;
/** While a model downloads. */
export const DOWNLOAD_MS = 1500;

/** How often an item's page reads the item again by itself: every FAST_MS while Claude draws the owner's line onto its
 * drawing, since a line can be done (or refused) before the closet's poll ever sees it under way; null otherwise. */
export function itemPoll(item: Pick<Item, 'additions'> | null | undefined, offline: boolean): number | null {
  return !offline && item?.additions?.state === 'drawing' ? FAST_MS : null;
}

export function downloading(model: ModelInfo | null | undefined): boolean {
  return model?.state === 'downloading' || model?.second?.state === 'downloading';
}

/** How often the list of work under way is asked for again; null: not at all (nothing is under way, or offline: an
 * edit that starts work makes it stale, and it is asked again then). */
export function progressPoll(list: ProgressList | null | undefined, offline: boolean): number | null {
  if (offline || !list?.items.length) return null;
  return list.items.some((i) => going(i.progress)) ? FAST_MS : WAITING_MS;
}

/** One item's place in the work: its part and state, e.g. "describing:working". */
const where = (i: ProgressList['items'][number]) => `${i.progress.stage}:${i.progress.state}`;

/**
 * The items whose work moved on between two answers of `GET /api/progress`: a step finished or started, or the item
 * stopped (or started) waiting, or it is done (gone from the list) or new to it. Their summaries and their pages are
 * read again; nothing the first time the list arrives.
 */
export function movedOn(before: ProgressList | null | undefined, after: ProgressList): string[] {
  if (!before) return [];
  const was = new Map(before.items.map((i) => [i.id, where(i)]));
  const now = new Map(after.items.map((i) => [i.id, where(i)]));
  const out = new Set<string>();
  for (const [id, at] of was) if (now.get(id) !== at) out.add(id);
  for (const id of now.keys()) if (!was.has(id)) out.add(id);
  return [...out];
}

