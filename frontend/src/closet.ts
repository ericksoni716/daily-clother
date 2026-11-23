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
