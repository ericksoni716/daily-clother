/** Plain words for when something was worn. Dates are local calendar days, "YYYY-MM-DD". */

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Today (or the given moment) as a local "YYYY-MM-DD". */
export function localDay(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parts(day: string): [number, number, number] {
  const [y, m, d] = day.split('-').map(Number);
  return [y, m, d];
}

function daysBetween(earlier: string, later: string): number {
  const [y1, m1, d1] = parts(earlier);
  const [y2, m2, d2] = parts(later);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86_400_000);
}

/** "today", "yesterday", "on Tuesday" (within the past week), "on 3 Nov", or "on 3 Nov 2025" (another year). */
export function whenWorn(day: string, today: string = localDay()): string {
  const ago = daysBetween(day, today);
  if (ago === 0) return 'today';
  if (ago === 1) return 'yesterday';
  const [y, m, d] = parts(day);
  if (ago > 1 && ago < 7) return `on ${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}`;
  return `on ${d} ${MONTHS[m - 1]}${y === parts(today)[0] ? '' : ` ${y}`}`;
}

/** A day in a list of wears: "Today", "Yesterday", "Tuesday 10 Nov", "3 Nov 2025". */
export function wearDay(day: string, today: string = localDay()): string {
  const ago = daysBetween(day, today);
  if (ago === 0) return 'Today';
  if (ago === 1) return 'Yesterday';
  const [y, m, d] = parts(day);
  const date = `${d} ${MONTHS[m - 1]}${y === parts(today)[0] ? '' : ` ${y}`}`;
  return ago > 1 && ago < 7 ? `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${date}` : date;
}

/** "Not worn yet", "Worn once, yesterday", "Worn 6 times, last on Tuesday". */
export function wearSummary(count: number, lastWorn: string | null | undefined, today: string = localDay()): string {
  if (!count || !lastWorn) return 'Not worn yet';
  if (count === 1) return `Worn once, ${whenWorn(lastWorn, today)}`;
  return `Worn ${count} times, last ${whenWorn(lastWorn, today)}`;
}

/** "Not worn since it was washed", "Worn once since it was washed", "Worn 3 times since it was washed". */
export function sinceWash(n: number): string {
  if (!n) return 'Not worn since it was washed';
  return `Worn ${n === 1 ? 'once' : `${n} times`} since it was washed`;
}
