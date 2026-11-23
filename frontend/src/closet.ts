/** The closet grid's rules, with no React in them: how many tiles to a row on a computer. */

/**
 * How many tiles fit a row `width` wide, each at least `min` wide with `gap` between them: what the grid's
 * `auto-fill` would choose. On a computer the grid keeps this number while a piece's panel is open beside it, so
 * opening a piece makes the tiles narrower and moves none of them to another row.
 */
export function columnsFor(width: number, min: number, gap: number): number {
  if (!(width > 0) || !(min > 0)) return 1;
  return Math.max(1, Math.floor((width + gap) / (min + gap)));
}

/** The laundry's part of the closet's line: how many pieces are in it, or that none are while it is shown. */
export function laundryPart(n: number): string {
  return n > 0 ? `${n} in the laundry` : 'Nothing in the laundry';
}

/** The line under the closet's toolbar while the laundry is shown: what is in it, or what "All clean" just did. */
export function laundryNotice(inLaundry: number, cleaned: number | null): string {
  if (cleaned !== null) return cleaned === 1 ? 'You marked it clean.' : `You marked ${cleaned} pieces clean.`;
  if (inLaundry === 0) return '';
  return inLaundry === 1 ? 'This piece is in the laundry.' : `These ${inLaundry} pieces are in the laundry.`;
}

/**
 * What the grid says when nothing is shown: the filter that is on says why in its own words ("Your laundry is empty."
 * rather than "Nothing matches"), and a search or a choice of what it is gets the general sentence.
 */
export function emptySentence(on: { check: boolean; toCheck: number; away: boolean; awayNow: number; laundry: boolean;
  inLaundry: number; searching: boolean; what: boolean }): string {
  const narrowed = on.searching || on.what;
  if (on.check && on.toCheck === 0 && !narrowed) return 'Nothing needs a check now.';
  if (on.away && on.awayNow === 0 && !narrowed) return 'Everything is in your closet.';
  if (on.laundry && on.inLaundry === 0 && !narrowed) return 'Your laundry is empty.';
  return 'Nothing matches. Try another word or filter.';
}
