/** Correcting an item's details: by picking, by saying, and the history that can be undone. */
import type { AwayPlace } from './types';
import { dayAndTime } from './wears';

export interface DetailOption {
  name: string;
  /** Its name in a sentence, e.g. "number of buttons". */
  title: string;
  value: unknown;
  /** The value in plain words, e.g. "a half placket". */
  words: string;
  /** Whether the owner set it (it then stays when Claude describes the item again). */
  own: boolean;
}

export interface DetailOptions {
  kind: 'top' | 'bottom' | 'shoe' | null;
  groups: { id: string; title: string; details: DetailOption[] }[];
  message: string | null;
}

export interface DetailChoice {
  value: unknown;
  words: string;
  current: boolean;
  /** A small drawing of the item with this value; null when the drawing would not change (or for the current value). */
  svg: string | null;
}

export interface DetailChoices extends DetailOption {
  choices: DetailChoice[];
}

export interface CorrectionChange {
  name: string;
  title: string;
  value: unknown;
  before: unknown;
  before_words: string;
  after_words: string;
}

export interface CorrectionAnswer {
  state: 'understood' | 'not_understood' | 'waiting' | 'failed';
  changes: CorrectionChange[];
  not_understood?: string | null;
  message?: string | null;
  /** What was sent to Claude, in a sentence. */
  sent?: string;
  sentence: string;
  /** Waiting because this month's spending limit for the API key was reached. */
  limit?: boolean;
}

/** What Claude understood, but only while the item is as it was when Claude read the sentence. */
export function stillFor<T>(answer: T | null, askedAt: string | null, stamp: string): T | null {
  return answer && askedAt === stamp ? answer : null;
}

/** "Fix the details" shows one of two views: the box to say what's wrong, or the details one by one. */
export type FixView = 'say' | 'list';

export const FIX_DEMO = 'The demo closet is never sent to Claude, so you change its details one by one here.';
export const FIX_AWAY = "Claude can't be reached right now, so you change the details one by one here.";

/**
 * What "Fix the details" opens on. It opens on the box to say what's wrong, unless the demo closet is open (never sent
 * to Claude), Claude could not be reached the last time a sentence was sent, or a detail was asked for by name (a
 * word of the fit line); then it opens on the details one by one, with a line saying why when there is one. The box is
 * focused only on a computer: on a phone, focusing it opens the keyboard over everything.
 */
export function fixOpening({ demo, away, focus, phone }: { demo: boolean; away: boolean; focus: boolean; phone: boolean }): {
  view: FixView; why: string | null; canSay: boolean; autofocus: boolean;
} {
  const why = demo ? FIX_DEMO : away ? FIX_AWAY : null;
  const view: FixView = why || focus ? 'list' : 'say';
  return { view, why, canSay: !demo, autofocus: view === 'say' && !phone };
}

/** Whether an answer to a sentence says Claude could not be reached (not the monthly limit, which says so itself). */
export function claudeAway(answer: Pick<CorrectionAnswer, 'state' | 'limit'>): boolean {
  return answer.state === 'waiting' && !answer.limit;
}

/** The changes to confirm, each with the value it replaces, so the server can refuse if the item changed since. */
export function confirmedChanges(changes: CorrectionChange[]): { name: string; value: unknown; before: unknown }[] {
  return changes.map((c) => ({ name: c.name, value: c.value, before: c.before }));
}

export interface HistoryPart {
  target: 'field' | 'detail' | 'answer';
  name: string;
  title: string;
  before: unknown;
  after: unknown;
  before_words: string;
  after_words: string;
  /** Only who set it (or how sure the tagger was) changed: the owner confirmed it, or gave the same value again. */
  same?: boolean;
}

export interface HistoryEntry {
  id: number;
  at: string;
  by: 'owner' | 'claude';
  kind: 'answer' | 'field' | 'detail' | 'sentence' | 'undo' | 'away';
  sentence: string | null;
  /** with kind "away": the piece went away or came back (where it is: away.ts) */
  away?: { event: 'went' | 'back'; place: AwayPlace; by: 'owner' | 'wear' };
  undoes: number | null;
  undone: boolean;
  can_undo: boolean;
  why_not: string | null;
  first_description: boolean;
  parts: HistoryPart[];
}

export function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

/** "Number of buttons: 3" */
export function detailSummary(d: Pick<DetailOption, 'title' | 'words'>): string {
  return `${capitalise(d.title)}: ${d.words}`;
}

/** A drawing given as SVG text, as an image address. */
export function svgSource(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const isFlag = (v: unknown) => v === 'yes' || v === 'no';

/** The parts worth saying: the colour's shade is left out when the colour itself is named, the category when the kind is. */
export function shownParts(parts: HistoryPart[]): HistoryPart[] {
  const hasColour = parts.some((p) => p.name === 'color');
  // the kind of garment follows from the kind the owner chose: saying the kind says it
  const hasKind = parts.some((p) => p.target === 'detail' && p.name === 'garment');
  return parts.filter((p) => p.target !== 'answer' && !(hasColour && p.name === 'color_hex') && !(hasKind && p.name === 'category'));
}

/** One change in words, without who made it: "the front from buttons to a half placket". */
export function partPhrase(p: HistoryPart): string {
  if (p.same) return `confirmed the ${p.title} as ${p.after_words}`;
  if (p.target === 'detail' && isFlag(p.before) && isFlag(p.after) && p.before !== p.after) {
    return `${p.after === 'yes' ? 'added' : 'removed'} the ${p.title}`;
  }
  if (p.before_words === p.after_words) return `set the ${p.title} to ${p.after_words}`;
  return `changed the ${p.title} from ${p.before_words} to ${p.after_words}`;
}

function joinAnd(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** A history entry in plain words, e.g. "You changed the front from buttons to a half placket". */
export function historyLine(e: HistoryEntry): string {
  if (e.kind === 'away' && e.away) return awayHistoryLine(e.away);
  const parts = shownParts(e.parts);
  if (e.kind === 'answer') {
    if (e.first_description) return 'Claude described it';
    return parts.length ? `Claude described it again and ${joinAnd(parts.map(partPhrase))}` : 'Claude described it again, with no changes';
  }
  if (e.kind === 'undo') {
    if (e.parts.some((p) => p.target === 'answer')) return "You put back Claude's earlier description";
    const back = parts.map((p) => `the ${p.title} back to ${p.after_words}`);
    return back.length ? `You put ${joinAnd(back)}` : 'You undid a change';
  }
  const said = parts.length ? joinAnd(parts.map(partPhrase)) : 'changed nothing';
  if (e.kind === 'sentence' && e.sentence) return `You wrote “${e.sentence}” and ${said}`;
  return `You ${said}`;
}

const WENT: Record<AwayPlace, string> = { cleaner: "You took it to the cleaner's", tailor: "You took it to the tailor's", lent: 'You lent it out' };
const CAME: Record<AwayPlace, string> = { cleaner: "the cleaner's", tailor: "the tailor's", lent: 'being lent out' };

/** Going away and coming back, in the history's words: "You took it to the cleaner's", "It came back from the
 * tailor's", "It came back from being lent out when you wore it". */
export function awayHistoryLine(a: NonNullable<HistoryEntry['away']>): string {
  if (a.event === 'went') return WENT[a.place];
  return `It came back from ${CAME[a.place]}${a.by === 'wear' ? ' when you wore it' : ''}`;
}

/** When a change was made, at the head of its line: "Today, 14:05", "13 Nov, 09:41" (the one family of dates). */
export function historyWhen(at: string): string {
  return dayAndTime(at);
}

/** A confirmed change in words: "Number of buttons: 3 → 2". */
export function changeLine(c: CorrectionChange): string {
  return `${capitalise(c.title)}: ${c.before_words} → ${c.after_words}`;
}
