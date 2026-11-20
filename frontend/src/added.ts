/** What Add knows about the item a photo became: in the import list, and on the shoe's screen after "Add this shoe".
 *  The items come from the closet's own list, and how far the work on each has got from the work under way that the
 *  closet's provider follows (progress.ts), so Add asks Closet for nothing more. */
import { settingsFix } from './progress';
import type { ItemSummary, Progress } from './types';
import type { QueueEntry } from './uploadQueue';

/** The item a row of the import list went into: a photo added as one item, or already in the closet as one. A photo
 *  of several pieces has none until its boxes are checked (its row links to them instead). */
export function itemIdOf(entry: Pick<QueueEntry, 'status' | 'itemId' | 'sourceId'>): string | null {
  return (entry.status === 'done' || entry.status === 'duplicate') && !entry.sourceId ? entry.itemId : null;
}

/** Why the items shown wait, when it is something you can see to in Settings (the API key's monthly limit, Claude
 *  Code's sign-in, background removal): every such item waits for the same reason, so it is said once, above the rows. */
export function waitingReason(progress: Iterable<Progress | null | undefined>): string | null {
  for (const p of progress) if (settingsFix(p) && p?.why) return p.why;
  return null;
}

/** The closet's items by id; an item in a later list wins (give the archived list first: a photo already in the closet
 *  can be an archived item's). */
export function byId(lists: (ItemSummary[] | null)[]): Map<string, ItemSummary> {
  const out = new Map<string, ItemSummary>();
  for (const list of lists) for (const item of list ?? []) out.set(item.id, item);
  return out;
}
