/** What Add shows about the item a photo became: in the import list, and on the shoe's screen after "Add this shoe".
 *  The items come from the closet's own list (the store), which already follows new items while their background is
 *  removed and Claude describes them, so Add asks Closet for nothing more. */
import { tileCaption } from './labels';
import type { ItemSummary } from './types';
import type { QueueEntry } from './uploadQueue';

/** How far a new item has got: its background removed, then described by Claude. */
export type AddedState = 'removing' | 'cutout-failed' | 'describing' | 'waiting' | 'failed' | 'described';

type Progress = Pick<ItemSummary, 'cutout_state' | 'tag_state'>;

export function addedState(item: Progress): AddedState {
  if (item.cutout_state === 'failed') return 'cutout-failed';
  if (item.cutout_state === 'pending' || item.cutout_state === 'processing') return 'removing';
  if (item.tag_state === 'working') return 'describing';
  if (item.tag_state === 'waiting') return 'waiting';
  if (item.tag_state === 'failed') return 'failed';
  // described, or never to be (the demo closet's own photos, items added before describing existed)
  return 'described';
}

/** What Claude called it: its name, else its category and colour. */
export function calledIt(item: Pick<ItemSummary, 'name' | 'category' | 'color'>): string {
  return item.name || tileCaption(item.category, item.color) || 'New item';
}

/** The line a row shows for its item: what it is called once described, else how far it has got, in the words the
 *  item page uses. `removing` is what the closet says while the background is removed (or waits for the model). */
export function addedLine(item: Progress & Pick<ItemSummary, 'name' | 'category' | 'color'>, removing: string): string {
  switch (addedState(item)) {
    case 'removing': return removing;
    case 'cutout-failed': return "The background couldn't be removed";
    case 'describing': return 'Claude is describing it…';
    case 'waiting': return 'Waiting to be described by Claude';
    case 'failed': return "Claude couldn't describe this item";
    default: return calledIt(item);
  }
}

/** The item a row of the import list went into: a photo added as one item, or already in the closet as one. A photo
 *  of several pieces has none until its boxes are checked (its row links to them instead). */
export function itemIdOf(entry: Pick<QueueEntry, 'status' | 'itemId' | 'sourceId'>): string | null {
  return (entry.status === 'done' || entry.status === 'duplicate') && !entry.sourceId ? entry.itemId : null;
}

/** Why the items shown wait to be described, when Closet knows (the API key's monthly limit, or Claude Code's
 *  sign-in): every waiting item waits for the same reason, so it is said once, above the rows. */
export function waitingReason(items: Iterable<(Progress & Pick<ItemSummary, 'tag_error'>) | null | undefined>): string | null {
  for (const item of items) if (item && addedState(item) === 'waiting' && item.tag_error) return item.tag_error;
  return null;
}

/** The closet's items by id; an item in a later list wins (give the archived list first: a photo already in the closet
 *  can be an archived item's). */
export function byId(lists: (ItemSummary[] | null)[]): Map<string, ItemSummary> {
  const out = new Map<string, ItemSummary>();
  for (const list of lists) for (const item of list ?? []) out.set(item.id, item);
  return out;
}
