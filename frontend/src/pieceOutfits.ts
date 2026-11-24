/**
 * From a piece to an outfit, on the item page: whether Today can build an outfit around the piece (and if not, the one
 * line saying when it can), and the outfits the piece was worn in, grouped by the server (`worn_in` on the item).
 */
import { ratingLabel, type Rating, type WornPieces } from './worn';
import { localDay, wearDay, whenWorn } from './wears';

/** Why Today would find nothing to build around a piece (`build_around` on the item; `outfits.cannot_build_around`). */
export type AroundRefusal = 'no_category' | 'not_in_outfits' | 'archived' | 'away' | 'laundry';

/** One row of "When you wore it": an outfit the piece was worn in, with every day it was worn (newest first), or a wear
 * with no outfit (`outfit_id` and `pieces` null, one day). */
export interface WornIn {
  outfit_id: string | null;
  pieces: WornPieces | null;
  gone: string[];
  days: string[];
  rating: Rating | null;
}

/** How many rows the page shows before "All N outfits" opens the rest in a sheet. */
export const ON_PAGE = 3;

/**
 * What the item page offers for building an outfit around the piece: the button, or one line saying when Today can,
 * or nothing at all (an archived piece, or a kind no outfit has a place for, such as a tie). Never a button that leads
 * to no outfit: the refusal is the server's, from the rule Today itself uses.
 */
export function aroundOffer(item: { build_around?: AroundRefusal | null; tag_state?: string | null }): { button: boolean; line: string | null } {
  switch (item.build_around ?? null) {
    case null: return { button: true, line: null };
    case 'laundry': return { button: false, line: "Once it's clean, Today can build an outfit around it." };
    case 'away': return { button: false, line: "Once it's back, Today can build an outfit around it." };
    case 'no_category':
      return {
        button: false,
        line: item.tag_state === 'waiting' || item.tag_state === 'working'
          ? 'Once Claude has described it, Today can build an outfit around it.'
          : 'Once you choose what it is, Today can build an outfit around it.',
      };
    default: return { button: false, line: null };
  }
}

/** Today built around this piece: where the button goes. Today reads `around` once and tidies its address. */
export function aroundPath(id: string): string {
  return `/today?around=${encodeURIComponent(id)}`;
}

/** "Wear this again" for a worn outfit: the same address Worn's button goes to. */
export function againPath(outfitId: string): string {
  return `/today?again=${encodeURIComponent(outfitId)}`;
}

/** When a row was worn: "Yesterday", "Tuesday 10 Nov", or "3 times, last on Tuesday"; with its rating when it has one
 * ("Yesterday · Loved it"). */
export function wornInWords(row: Pick<WornIn, 'days' | 'rating'>, today: string = localDay()): string {
  const [last] = row.days;
  if (!last) return '';
  const when = row.days.length === 1 ? wearDay(last, today) : `${row.days.length} times, last ${whenWorn(last, today)}`;
  return row.rating ? `${when} · ${ratingLabel(row.rating)}` : when;
}

/** The accessible name of the Remove beside one day in a row's sheet: "Remove the wear: Friday 20 Nov". */
export function removeWearName(day: string, today: string = localDay()): string {
  return `Remove the wear: ${wearDay(day, today)}`;
}

/** The row that opens every row in a sheet: "All 5 outfits", "All 4 wears" when none was an outfit, or "All 5 outfits
 * and wears" when both are there. */
export function allRowsLabel(rows: readonly Pick<WornIn, 'outfit_id'>[]): string {
  const outfits = rows.some((r) => r.outfit_id);
  const plain = rows.some((r) => !r.outfit_id);
  return `All ${rows.length} ${outfits && plain ? 'outfits and wears' : outfits ? 'outfits' : 'wears'}`;
}

/** Where a piece of an outfit opens from the item page at `pathname`: in the same place (Today, Worn, the Wardrobe), or
 * the closet's own item page. */
export function piecesFrom(pathname: string): string {
  const at = pathname.indexOf('/item/');
  const base = at > 0 ? pathname.slice(0, at) : '';
  return base === '/archived' ? '' : base;
}
