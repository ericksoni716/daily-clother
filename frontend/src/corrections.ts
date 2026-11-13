/** Correcting an item's details: by picking, by saying, and the history that can be undone. */

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
  kind: 'answer' | 'field' | 'detail' | 'sentence' | 'undo';
  sentence: string | null;
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

/** The parts worth saying: the colour's shade is left out when the colour itself is named. */
export function shownParts(parts: HistoryPart[]): HistoryPart[] {
  const hasColour = parts.some((p) => p.name === 'color');
  return parts.filter((p) => p.target !== 'answer' && !(hasColour && p.name === 'color_hex'));
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

/** When a change was made, short: "13 Nov, 09:41". */
export function historyWhen(at: string, locale?: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** A confirmed change in words: "Number of buttons: 3 → 2". */
export function changeLine(c: CorrectionChange): string {
  return `${capitalise(c.title)}: ${c.before_words} → ${c.after_words}`;
}
