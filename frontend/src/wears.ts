/**
 * Every date and time the owner reads, in one family (DECISIONS, "One way to write a date"): a day ("Thursday 12 Nov",
 * "Wed 25 Nov", "3 Nov 2025"), a day and a time ("today at 14:05", "Yesterday, 09:41"), and how long ago ("today",
 * "yesterday", "on Tuesday", "on 3 Nov"). Days are written day first, a time on the 24-hour clock, the year only when it
 * is not this one (or where a date stands alone, as in "3 Nov 2026"). Nothing here asks the browser's locale, so the
 * phone and the computer read the same; a test fails if a screen formats a date by itself. Days are local calendar days,
 * "YYYY-MM-DD"; moments are ISO times.
 */

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const pad = (n: number) => String(n).padStart(2, '0');

function weekday(day: string): string {
  const [y, m, d] = parts(day);
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

/** "Thursday 12 Nov" from "2026-11-12". */
export function longDate(day: string): string {
  const [, m, d] = parts(day);
  return `${weekday(day)} ${d} ${MONTHS[m - 1]}`;
}

/** "Wed 25 Nov" from "2026-11-25": the day where there is little room (Today's header on a phone, a trip's strip). */
export function shortDate(day: string): string {
  const [, m, d] = parts(day);
  return `${weekday(day).slice(0, 3)} ${d} ${MONTHS[m - 1]}`;
}

/** "Wed" and "25 Nov" apart, for a strip of days. */
export function dayAndDate(day: string): { weekday: string; date: string } {
  const [, m, d] = parts(day);
  return { weekday: weekday(day).slice(0, 3), date: `${d} ${MONTHS[m - 1]}` };
}

/** "3 Nov 2026" from "2026-11-03": a date standing alone, always with its year. */
export function fullDate(day: string): string {
  const [y, m, d] = parts(day);
  if (!y || !m || !d) return day;
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** "3 Nov", or "3 Nov 2025" in another year than `today`'s. */
export function dayMonth(day: string, today: string = localDay()): string {
  const [y, m, d] = parts(day);
  return `${d} ${MONTHS[m - 1]}${y === parts(today)[0] ? '' : ` ${y}`}`;
}

/** "November 2026" from "2026-11". */
export function monthYear(month: string): string {
  const [y, m] = month.split('-').map(Number);
  if (!y || !m) return month;
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

/** The local day of a moment ("2026-11-23T04:40:00Z" → "2026-11-23" here), or null when it is not a time. */
export function dayOf(iso: string): string | null {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : localDay(d);
}

/** "14:05", "09:41": the time of a moment on the 24-hour clock; empty when it is not a time. */
export function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** A moment in a sentence: "today at 14:05", "yesterday at 09:41", "on Tuesday at 08:00", "on 3 Nov at 08:00". */
export function whenAt(iso: string, today: string = localDay()): string {
  const day = dayOf(iso);
  return day ? `${whenWorn(day, today)} at ${clock(iso)}` : '';
}

/** A moment at the head of a line in a list: "Today, 14:05", "Yesterday, 09:41", "Tuesday 10 Nov, 08:00", "3 Nov, 08:00". */
export function dayAndTime(iso: string, today: string = localDay()): string {
  const day = dayOf(iso);
  return day ? `${wearDay(day, today)}, ${clock(iso)}` : '';
}

/** Today (or the given moment) as a local "YYYY-MM-DD". */
export function localDay(d: Date = new Date()): string {
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
  if (ago > 1 && ago < 7) return `on ${weekday(day)}`;
  return `on ${dayMonth(day, today)}`;
}

/** A day in a list of wears: "Today", "Yesterday", "Tuesday 10 Nov", "3 Nov 2025". */
export function wearDay(day: string, today: string = localDay()): string {
  const ago = daysBetween(day, today);
  if (ago === 0) return 'Today';
  if (ago === 1) return 'Yesterday';
  const date = dayMonth(day, today);
  return ago > 1 && ago < 7 ? `${weekday(day)} ${date}` : date;
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

/** A day near or ahead, with its weekday: "Friday 27 Nov", or "Friday 27 Nov 2027" in another year. */
export function calendarDay(day: string, today: string = localDay()): string {
  return `${weekday(day)} ${dayMonth(day, today)}`;
}

/** A day gone, short: "today", "yesterday", "3 Nov", or "3 Nov 2025" in another year. */
export function sinceDay(day: string, today: string = localDay()): string {
  const ago = daysBetween(day, today);
  if (ago <= 0) return 'today';
  if (ago === 1) return 'yesterday';
  return dayMonth(day, today);
}

/** Whether `day` is before `today` (both local "YYYY-MM-DD"). */
export function isPast(day: string, today: string = localDay()): boolean {
  return daysBetween(day, today) > 0;
}

// ------------------------------------------------------------------ days ahead (Dress for another day)

/** "2026-11-28" from "2026-11-25" and 3. */
export function addDays(day: string, n: number): string {
  const [y, m, d] = parts(day);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`;
}

/** How many days `day` is after `today` (0 for today, negative before). */
export function daysAhead(today: string, day: string): number {
  return daysBetween(today, day);
}

/** "Saturday" from "2026-11-28". */
export function weekdayOf(day: string): string {
  return weekday(day);
}

/** A day ahead by its name: "Tomorrow", "Saturday" within the week, "Sat 12 Dec" further off. */
export function dayName(day: string, today: string = localDay()): string {
  const n = daysBetween(today, day);
  if (n === 1) return 'Tomorrow';
  if (n > 1 && n < 7) return weekday(day);
  return shortDate(day);
}

/** The same in a sentence: "tomorrow", "on Saturday", "on Sat 12 Dec". */
export function onDay(day: string, today: string = localDay()): string {
  const name = dayName(day, today);
  return name === 'Tomorrow' ? 'tomorrow' : `on ${name}`;
}
