/** Washing several pieces at once: the closet's "All clean" and a worn outfit's "Put these in the laundry". */
import { api } from './api';
import type { ItemSummary, Laundry } from './types';

/** Marks each piece clean or in the laundry; resolves to how many could not be (the others are updated). */
export async function setLaundryMany(ids: string[], state: Laundry, upsert: (item: ItemSummary) => void): Promise<number> {
  const results = await Promise.allSettled(ids.map((id) => api.setLaundry(id, state)));
  results.forEach((r) => { if (r.status === 'fulfilled') upsert(r.value); });
  return results.filter((r) => r.status === 'rejected').length;
}
