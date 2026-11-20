import type { Item } from './types';

type Retaken = Pick<Item, 'pattern' | 'pattern_state' | 'cutout_state' | 'pattern_error'> & { trace?: Item['trace'] };

/** A shoe (it has a trace, even one not made yet): its new photo is traced again, and it says so its own way. */
export const isShoe = (item: { trace?: Item['trace'] }) => item.trace != null;

/** What a shoe says once its new photo is in (as it always has). */
export const SHOE_RETAKEN = 'New photo added; the shoe is traced again from it';

/** What the item page says once a new photo is in ("Retake the photo"), in the owner's words: what happens next. */
export function retakeSaid(item: Retaken, demo: boolean): string {
  if (isShoe(item)) return SHOE_RETAKEN;
  if (demo) return 'New photo added. Its background is removed again; the demo closet keeps its description';
  const patterned = item.pattern_state != null || (item.pattern != null && item.pattern !== 'solid');
  return patterned
    ? 'New photo added. Nines removes its background, Claude describes it again, then its pattern is measured again'
    : 'New photo added. Nines removes its background, then Claude describes it again';
}

/** Where the item page offers a piece of clothing a new photo: in the notice that its background couldn't be
 * removed, or beside the note that its pattern couldn't be measured. Never both at once, so the owner sees one
 * button; shoes offer theirs with their trace. */
export function retakeOffer(item: Retaken): 'cutout' | 'pattern' | null {
  if (isShoe(item)) return null;
  if (item.cutout_state === 'failed') return 'cutout';
  if (item.pattern_state === 'failed' && item.pattern_error) return 'pattern';
  return null;
}
