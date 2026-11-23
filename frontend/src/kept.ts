/** Outfits you keep: the shape the server sends, finding one by its pieces, and the words on their cards. */
import { sameOutfit } from './today';
import { localDay, whenWorn } from './wears';
import { wornIds, type WornPieces } from './worn';

/** An outfit kept without wearing it (`GET /api/outfits/kept`). */
export interface KeptOutfit {
  id: string;
  /** Given later, in place; null until then. */
  name: string | null;
  pieces: WornPieces;
  /** Pieces that have left the closet since; the outfit stays, and wearing it fills their places. */
  gone: string[];
  created_at: string;
  updated_at: string;
}

/** `POST /api/outfits/kept`: the outfit, and whether these very pieces were kept before (then nothing new is kept). */
export interface KeptAnswer {
  outfit: KeptOutfit;
  already: boolean;
}

/** The longest name (the server's `kept.MAX_NAME`). */
export const KEPT_NAME_MAX = 60;

/** The kept outfit with exactly these pieces, if there is one. */
export function keptWith(kept: readonly KeptOutfit[] | null | undefined, ids: string[]): KeptOutfit | null {
  return (kept ?? []).find((o) => sameOutfit(wornIds(o.pieces), ids)) ?? null;
}

/** The toast after "Keep this outfit". */
export function keptToast(answer: Pick<KeptAnswer, 'already'>): string {
  return answer.already ? 'You keep this outfit already. It is under Worn.' : 'Kept. You will find it under Worn.';
}

/** "Kept today", "Kept on Tuesday", "Kept on 3 Nov": when an outfit was kept, by this device's calendar. */
export function keptWhen(o: Pick<KeptOutfit, 'created_at'>, today: string = localDay()): string {
  const d = new Date(o.created_at);
  return Number.isNaN(d.getTime()) ? 'Kept' : `Kept ${whenWorn(localDay(d), today)}`;
}

/** The line on an outfit whose piece has left the closet; null when every piece is there. */
export function goneLine(o: Pick<KeptOutfit, 'gone'>): string | null {
  const n = o.gone.length;
  if (!n) return null;
  return n === 1 ? 'One piece is no longer in your closet. Wearing this fills its place.'
    : `${n} pieces are no longer in your closet. Wearing this fills their places.`;
}

/** The one sentence on the empty list. */
export const KEPT_EMPTY = 'Tap “Keep this outfit” under an outfit on Today, or on one you wore, and it waits here to be worn.';
