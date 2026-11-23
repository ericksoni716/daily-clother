/** Dress for another day: the plans the server keeps, the days the sheet offers, and the words for both. */
import { addDays, daysAhead, dayName, joinWords, onDay, SAVED_PREFIX, shortPlace, type OutfitPieces } from './today';
import type { TripSummary } from './trips';

/** An outfit kept for a day ahead (`GET /api/plans`): a plan, not a wear. */
export interface Plan {
  day: string;
  pieces: OutfitPieces;
  occasion: string | null;
  mood: string | null;
  /** Pieces that have left the closet since. */
  gone: string[];
  created_at: string;
  updated_at: string;
}

/** `PUT /api/plans/{day}`: the plan kept, and the one it took the place of (for Undo). */
export interface PlanSaved {
  plan: Plan;
  replaced: Plan | null;
}

/** How many days the sheet names before "Another date". */
export const NAMED_DAYS = 6;
/** The furthest a day can be dressed ahead (the server's `plans.MAX_AHEAD_DAYS`). */
export const MAX_AHEAD_DAYS = 60;

/** One day in the sheet: its name, and whether it has a plan or is part of a trip. */
export interface DayChoice {
  day: string;
  label: string;
  planned: boolean;
  /** The trip's place when the day is part of one. */
  trip: string | null;
}

/** The trip that holds a day, if any. */
export function tripOn(trips: readonly TripSummary[] | null | undefined, day: string): TripSummary | null {
  return (trips ?? []).find((t) => t.first_day <= day && day <= t.last_day) ?? null;
}

/** Tomorrow and the next days by name, each marked when it has a plan or is part of a trip. */
export function dayChoices(today: string, plans: readonly Plan[] | null | undefined, trips: readonly TripSummary[] | null | undefined,
  count = NAMED_DAYS): DayChoice[] {
  const planned = new Set((plans ?? []).map((p) => p.day));
  return Array.from({ length: count }, (_, i) => {
    const day = addDays(today, i + 1);
    const trip = tripOn(trips, day);
    return { day, label: dayName(day, today), planned: planned.has(day), trip: trip ? shortPlace(trip.place.name) || 'a trip' : null };
  });
}

/** What the sheet says beside a day: "Planned", "Your trip to Lisbon", or nothing. */
export function choiceNote(c: DayChoice): string | null {
  if (c.trip) return `Your trip to ${c.trip}`;
  return c.planned ? 'Planned' : null;
}

/** Whether a date typed in the sheet is one that can be dressed for: after today, and within reach. */
export function canChoose(day: string, today: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
  const n = daysAhead(today, day);
  return n >= 1 && n <= MAX_AHEAD_DAYS;
}

/** The plans for the days after today within a week, soonest first: Today's one line. */
export function plansSoon(plans: readonly Plan[] | null | undefined, today: string, days = 7): Plan[] {
  return (plans ?? []).filter((p) => daysAhead(today, p.day) >= 1 && daysAhead(today, p.day) <= days)
    .sort((a, b) => a.day.localeCompare(b.day));
}

/** The plan for a day, if there is one. */
export function planFor(plans: readonly Plan[] | null | undefined, day: string): Plan | null {
  return (plans ?? []).find((p) => p.day === day) ?? null;
}

/** The main button on an outfit for another day: "Wear this on Saturday", "Wear this tomorrow". */
export function wearOn(day: string, today: string): string {
  return `Wear this ${onDay(day, today)}`;
}

/** Said where the main button was, once the outfit is the day's plan: "Planned for Saturday". */
export function plannedFor(day: string, today: string): string {
  const name = dayName(day, today);
  return `Planned for ${name === 'Tomorrow' ? 'tomorrow' : name}`;
}

/** The toast once a plan is kept: "Planned for Saturday. That morning, Today opens on it." */
export function plannedToast(day: string, today: string): string {
  return `${plannedFor(day, today)}. That morning, Today opens on it.`;
}

/** The one line over the outfits when they start from the day's plan: "You planned this outfit for today.", with the word
 * about the day after it. */
export function planLine(day: string, today: string, note: string | null): string {
  const when = day === today ? 'today' : dayName(day, today) === 'Tomorrow' ? 'tomorrow' : dayName(day, today);
  return `You planned this outfit for ${when}.${note ? ` “${note}”` : ''}`;
}

/** A piece's name in the middle of a sentence, as the rules' own sentences name one: "the oatmeal henley", but "the
 * GANT polo". */
function midName(n: string): string {
  return n.length > 1 && n[1] === n[1].toLowerCase() ? n[0].toLowerCase() + n.slice(1) : n;
}

/** A piece that had to be swapped: its name, and where it is when it is away, with its verb, as the server says it
 * ("is at the cleaner's until Friday 27 November"). */
export interface Swapped { name: string; away?: string | null }

/** Where the away pieces are, as the start of a sentence: "Your navy blazer is at the cleaner's until Friday 27
 * November", "Your navy blazer is at the cleaner's and your jeans are lent out". */
export function awayClause(pieces: Swapped[]): string {
  const parts = pieces.filter((p) => p.away).map((p) => `your ${midName(p.name)} ${p.away}`);
  const said = joinWords(parts);
  return said ? said[0].toUpperCase() + said.slice(1) : '';
}

/** "The white tee can't be worn by then, so another piece takes its place." (or "pieces take their places"); a piece
 * away is named with where it is: "Your navy blazer is at the cleaner's until Friday 27 November, so another piece takes
 * its place." */
export function swapLine(given: Swapped[], day: string, today: string): string | null {
  if (!given.length) return null;
  const takes = (n: number) => (n === 1 ? 'another piece takes its place' : 'other pieces take their places');
  const away = given.filter((p) => p.away);
  const rest = given.filter((p) => !p.away).map((p) => midName(p.name));
  const when = day === today ? 'today' : 'by then';
  const lines = [];
  if (away.length) lines.push(`${awayClause(away)}, so ${takes(away.length)}.`);
  if (rest.length) lines.push(`The ${joinWords(rest)} can't be worn ${when}, so ${takes(rest.length)}.`);
  return lines.join(' ');
}

/** In a planned piece's sheet: why Today does not offer it now. */
export function heldLine(day: string, today: string): string {
  return `${plannedFor(day, today).replace('Planned', 'You planned this')}. Wearing it now would leave it in the laundry by then.`;
}

/** A day ahead inside a saved trip. */
export function tripLine(place: string | null): string {
  return `This day is part of your trip${place ? ` to ${shortPlace(place)}` : ''}, which has its outfit already.`;
}

// --------------------------------------------------------------------- kept on this device, for offline

type KV = Pick<Storage, 'getItem' | 'setItem'>;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const savedKey = (profile: string) => `${SAVED_PREFIX}:plans:${profile}`;

/** The plans as last read, kept per closet so a plan shows offline (forgotten with this device's other saved copies). */
export function loadSavedPlans(profile: string, kv: KV | null = local()): Plan[] | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const value = raw ? JSON.parse(raw) : null;
    return Array.isArray(value) ? value as Plan[] : null;
  } catch {
    return null;
  }
}

export function savePlans(profile: string, plans: Plan[], kv: KV | null = local()) {
  try {
    kv?.setItem(savedKey(profile), JSON.stringify(plans));
  } catch {
    /* private mode or full: not kept, nothing else breaks */
  }
}
