/**
 * How often to ask the server again while it works on items in the background: cutting out, describing, measuring
 * a pattern, tracing or drawing a shoe, sorting a shoe's photos. Pure, so the choice is tested here; the asking is
 * done by `usePoll` (src/queries.ts) in the closet's provider (the list) and on the item page (the item).
 */
import { drawingShoe, sortingViews, tracing } from './shoe';
import type { Item, ItemSummary, ModelInfo } from './types';

/** While the model or Claude is working on something the owner is watching. */
export const FAST_MS = 2000;
/** While a pattern is measured or a shoe traced: a minute or two. */
export const MEASURING_MS = 5000;
/** While a shoe is drawn from its photos (four to ten minutes), or its photos are sorted into views. */
export const DRAWING_MS = 4000;
/** While items wait for something outside (the model, a way to reach Claude): nothing changes until then. */
export const WAITING_MS = 10_000;
/** While a model downloads. */
export const DOWNLOAD_MS = 1500;

type Summary = Pick<ItemSummary, 'cutout_state' | 'tag_state' | 'drawn_state'>;

export const cuttingOut = (i: Summary) => i.cutout_state === 'pending' || i.cutout_state === 'processing';
export const describing = (i: Summary) => i.tag_state === 'working';
const waitingForClaude = (i: Summary) => i.tag_state === 'waiting';
/** A shoe waiting to be drawn for the outfit figure, being drawn, or its drawing being changed from the owner's note. */
const drawingForFigure = (i: Summary) =>
  i.drawn_state === 'waiting' || i.drawn_state === 'drawing' || i.drawn_state === 'correcting';

/** Work only the full item shows (the list does not carry it): a pattern measured, a shoe traced. */
export function measuring(item: Pick<Item, 'pattern_state' | 'trace'>): boolean {
  return item.pattern_state === 'waiting' || item.pattern_state === 'working' || tracing(item.trace);
}

export function modelStuck(model: ModelInfo | null | undefined): boolean {
  return model?.state === 'missing' || model?.state === 'failed';
}

export function downloading(model: ModelInfo | null | undefined): boolean {
  return model?.state === 'downloading' || model?.second?.state === 'downloading';
}

export interface ClosetPoll {
  /** How often to ask for the list again; null: not at all. */
  ms: number | null;
  /** Ask for the model's state too (a cutout waits on it). */
  model: boolean;
}

/**
 * How often the closet's list is asked for again. `measuringCount` is how many items known in full (their page was
 * opened, or a save answered with them) are having a pattern measured or a shoe traced, which the list cannot show.
 */
export function closetPoll(items: readonly Summary[] | null | undefined, model: ModelInfo | null | undefined,
  measuringCount: number, offline: boolean): ClosetPoll {
  const all = items ?? [];
  const busy = all.some(cuttingOut);
  if (offline) return { ms: null, model: false };
  if ((busy && !modelStuck(model)) || all.some(describing)) return { ms: FAST_MS, model: busy };
  if (measuringCount > 0) return { ms: MEASURING_MS, model: busy };
  if (busy || all.some(waitingForClaude) || all.some(drawingForFigure)) return { ms: WAITING_MS, model: busy };
  return { ms: null, model: false };
}

/** How often an item's page asks for the item again while something is being done to it; null: not at all. */
export function itemPoll(item: Item | null | undefined, offline: boolean): number | null {
  if (!item || offline) return null;
  if (cuttingOut(item) || describing(item) || tracing(item.trace) || item.views?.state === 'sorting') return FAST_MS;
  if (sortingViews(item.views) || drawingShoe(item.drawn)) return DRAWING_MS;
  if (item.pattern_state === 'waiting' || item.pattern_state === 'working') return MEASURING_MS;
  if (waitingForClaude(item)) return WAITING_MS;
  return null;
}

/**
 * The items of a new list whose cutout or description has just finished, compared with the list before: their full
 * item is fetched once, to learn whether a pattern is now measured or a shoe traced (which the list cannot say).
 */
export function justFinished(before: readonly ItemSummary[] | null | undefined, after: readonly ItemSummary[]): string[] {
  if (!before) return [];
  const was = new Map(before.map((i) => [i.id, i]));
  return after.filter((i) => {
    const old = was.get(i.id);
    if (!old) return false;
    return (cuttingOut(old) && i.cutout_state === 'ready') || ((describing(old) || waitingForClaude(old)) && i.tag_state === 'done');
  }).map((i) => i.id);
}
