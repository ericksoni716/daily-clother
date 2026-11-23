/** Washing several pieces at once: the closet's "All clean" and a worn outfit's "Put these in the laundry". */
import { api } from './api';
import type { ItemSummary, Laundry, LaundryUndo } from './types';

/** Marks each piece clean or in the laundry; resolves to how many could not be (the others are updated). */
export async function setLaundryMany(ids: string[], state: Laundry, upsert: (item: ItemSummary) => void): Promise<number> {
  const results = await Promise.allSettled(ids.map((id) => api.setLaundry(id, state)));
  results.forEach((r) => { if (r.status === 'fulfilled') upsert(r.value); });
  return results.filter((r) => r.status === 'rejected').length;
}

/** What "All clean" did: each piece marked clean with what its wash changed, to put it back with Undo. */
export interface Cleaned { failed: number; undo: { id: string; undo: LaundryUndo }[] }

/** Marks every piece clean, keeping what each wash changed so `putBack` can undo it. */
export async function cleanAll(ids: string[], upsert: (item: ItemSummary) => void): Promise<Cleaned> {
  const results = await Promise.allSettled(ids.map((id) => api.setLaundry(id, 'clean')));
  const undo: Cleaned['undo'] = [];
  results.forEach((r, i) => {
    if (r.status !== 'fulfilled') return;
    const { undo: back, ...item } = r.value;
    upsert(item);
    if (back) undo.push({ id: ids[i], undo: back });
  });
  return { failed: results.filter((r) => r.status === 'rejected').length, undo };
}

/** Puts the pieces "All clean" washed back in the laundry as they were; resolves to how many could not be. */
export async function putBack(cleaned: Cleaned['undo'], upsert: (item: ItemSummary) => void): Promise<number> {
  const results = await Promise.allSettled(cleaned.map((c) => api.setLaundry(c.id, 'laundry', c.undo)));
  results.forEach((r) => { if (r.status === 'fulfilled') upsert(r.value); });
  return results.filter((r) => r.status === 'rejected').length;
}
