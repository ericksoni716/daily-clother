/** The owner's style profile in Settings ("Your style"): what counts as a change, the character count, the lines
 * with where each came from, and how often to ask how the style conversation stands. */
import type { StyleLine, StyleProfile, StyleTalk } from './types';
import { localDay, whenWorn } from './wears';

/** The count turns to the warning colour this close to the longest text allowed. */
export const STYLE_WARN_WITHIN = 200;

/** The text as the server keeps it: no space at either end, every line break as "\n". */
export function tidyStyle(text: string): string {
  return text.replace(/\r\n?/g, '\n').trim();
}

/** Whether saving the text being written would change the profile in force. */
export function styleChanged(draft: string, inForce: string): boolean {
  return tidyStyle(draft) !== tidyStyle(inForce);
}

/** "123 / 4000", and whether it is in the last few characters allowed. */
export function styleCount(length: number, max: number): { text: string; warn: boolean } {
  return { text: `${length} / ${max}`, warn: length > max - STYLE_WARN_WITHIN };
}

/** How many lines of Your style the Settings card shows before "and N more". */
export const STYLE_SHOWN = 3;

/** A line as you read it: without the "- " a list line starts with. */
export function lineText(text: string): string {
  const t = text.trim();
  return /^-(\s|$)/.test(t) ? t.slice(1).trim() : t;
}

/** Where a line came from and when, in a few words: "Starting rule", "You said this on 12 Nov", "From a conversation
 * yesterday", "Your answer today". */
export function lineSource(line: Pick<StyleLine, 'source' | 'created_at'>, today: string = localDay()): string {
  if (line.source === 'start' || !line.created_at) return 'Starting rule';
  const when = whenWorn(localDay(new Date(line.created_at)), today);
  if (line.source === 'talk') return `From a conversation ${when}`;
  if (line.source === 'question') return `Your answer ${when}`;
  return `You said this ${when}`;
}

/** The lines the Settings card shows, and how many more there are. */
export function shownLines<T>(lines: readonly T[], n: number = STYLE_SHOWN): { shown: T[]; more: number } {
  return { shown: lines.slice(0, n), more: Math.max(0, lines.length - n) };
}

/** "And 1 more line." / "And 4 more lines." */
export function moreLines(n: number): string {
  return `And ${n} more ${n === 1 ? 'line' : 'lines'}.`;
}

/** The lines of a profile, also from a copy saved before lines existed (then its text, a line each). */
export function profileLines(p: Pick<StyleProfile, 'text' | 'lines' | 'is_default'>): StyleLine[] {
  if (Array.isArray(p.lines)) return p.lines;
  return p.text.split('\n').filter((t) => t.trim()).map((text, i) => ({ id: -1 - i, text, source: p.is_default ? 'start' : 'owner', created_at: null }));
}

/** How often to ask how the style conversation stands: every 1.5 seconds while Claude is answering, else not at all. */
export function talkPoll(talk: Pick<StyleTalk, 'turns' | 'answering'> | undefined): number | false {
  return talk && (talk.answering || talk.turns.some((t) => t.state === 'working')) ? 1500 : false;
}

/** The line said once a line was removed: "Removed “No ties.”" (with a full stop only when the line has none). */
export function removedWords(text: string): string {
  const words = lineText(text);
  return `Removed “${words}”${/[.!?]$/.test(words) ? '' : '.'}`;
}
