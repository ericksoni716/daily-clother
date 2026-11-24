/** Where a piece is: in your closet, or away at the cleaner's, at the tailor's or lent out. The words and the order. */
import { isPairCategory } from './gaps';
import type { Away, AwayPlace, CameBack, ItemSummary } from './types';
import { calendarDay, isPast, localDay, sinceDay } from './wears';

export const AWAY_PLACES: AwayPlace[] = ['cleaner', 'tailor', 'lent'];

/** "At the cleaner's", "At the tailor's", "Lent out". */
export const PLACE_WORDS: Record<AwayPlace, string> = { cleaner: "At the cleaner's", tailor: "At the tailor's", lent: 'Lent out' };

/** Where it was, after "back from": "the cleaner's", "the tailor's", "being lent out". */
const FROM_WORDS: Record<AwayPlace, string> = { cleaner: "the cleaner's", tailor: "the tailor's", lent: 'being lent out' };

/** Whether the day it was expected back has gone by. */
export function overdue(away: Away, today: string = localDay()): boolean {
  return !!away.until && isPast(away.until, today);
}

/** When it is expected back, for a tile or a second line: "Until Friday 27 Nov", "Expected back on Friday 20 Nov"
 * (the day has gone by), "Since 3 Nov" (no day was said). */
export function whenBack(away: Away, today: string = localDay()): string {
  if (away.until) return overdue(away, today) ? `Expected back on ${calendarDay(away.until, today)}` : `Until ${calendarDay(away.until, today)}`;
  return away.since ? `Since ${sinceDay(away.since, today)}` : '';
}

/** Where it is, in one sentence: "At the cleaner's until Friday 27 Nov", "Lent out since 3 Nov", "At the tailor's
 * since 3 Nov, expected back on Friday 20 Nov". */
export function whereSentence(away: Away, today: string = localDay()): string {
  const place = PLACE_WORDS[away.place];
  const since = away.since ? ` since ${sinceDay(away.since, today)}` : '';
  if (away.until && !overdue(away, today)) return `${place} until ${calendarDay(away.until, today)}`;
  if (away.until) return `${place}${since}, expected back on ${calendarDay(away.until, today)}`;
  return `${place}${since}`;
}

/** The row's sentence for a piece in the closet: "In your closet", or "In your closet, waiting to be mended". */
export function homeSentence(condition: string | null | undefined): string {
  return condition === 'needs_repair' ? 'In your closet, waiting to be mended' : 'In your closet';
}

/** What coming back did, said once with Undo beside it: "Back from the cleaner's, and marked clean". */
export function cameBackSentence(back: CameBack): string {
  const from = FROM_WORDS[back.from];
  const what = back.from === 'cleaner' ? ', and marked clean' : back.mended ? ', and no longer marked as needing mending' : '';
  if (back.by === 'wear') return `You wore it today, so it's back from ${from}${what}`;
  return `Back from ${from}${what}`;
}

/** The pieces away, the soonest expected back first (the overdue first of all), then those with no day, by name. */
export function awayOrder<T extends ItemSummary>(pieces: T[]): T[] {
  const key = (it: T) => it.away?.until ?? '9999-99-99';
  return [...pieces].filter((it) => it.away).sort((a, b) => key(a).localeCompare(key(b)) || (a.name ?? '').localeCompare(b.name ?? ''));
}

/** The closet line's part: how many are away, "2 away". Which are past their day the list it opens says, on each one
 * ("Expected back on Friday 20 Nov"), so the line stays short enough to sit with the others. */
export function awayPart(pieces: ItemSummary[]): string {
  return `${pieces.length} away`;
}

/** The mark on a tile in the full grid, for those who cannot see it: "At the cleaner's". */
export function tileMarkLabel(away: Away): string {
  return PLACE_WORDS[away.place];
}

/** The pieces of an outfit recorded for `day` that come back by being worn: those away, when the day is today (or the
 * computer's tomorrow, a phone a time zone ahead). */
export function backByWearing<T extends ItemSummary>(pieces: T[], day: string, today: string = localDay()): T[] {
  return isPast(day, today) ? [] : pieces.filter((it) => it.away);
}

/** What recording an outfit says: "Outfit recorded", and "Outfit recorded. The grey suit is back in your closet." The
 * verb goes by the pieces, as the server's (`outfits.be`): "Blue jeans are back". */
export function recordedSentence(back: { name: string; category: string | null }[]): string {
  if (!back.length) return 'Outfit recorded';
  const all = back.map((p) => p.name);
  const names = all.length === 1 ? all[0] : `${all.slice(0, -1).join(', ')} and ${all[all.length - 1]}`;
  const verb = back.length > 1 || isPairCategory(back[0].category) ? 'are' : 'is';
  return `Outfit recorded. ${names[0].toUpperCase()}${names.slice(1)} ${verb} back in your closet.`;
}
