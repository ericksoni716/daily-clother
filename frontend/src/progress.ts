/**
 * Background work on an item, in one set of words: how far it has got (cutting out, describing and drawing,
 * finishing the drawing), shown as one strip on the item page, a small step mark on the closet tile, one line above
 * the closet grid and each row on Add. The server works the progress out and writes its words
 * (`backend/closet/progress.py`); this file chooses which to show and lays out nothing.
 */
import { tileCaption } from './labels';
import type { ItemSummary, Progress, ProgressList } from './types';

export type { Progress, ProgressList };

/** Still on its way (working, next in line, or waiting), as against done or failed. */
export const busy = (p: Progress | null | undefined): p is Progress => !!p && p.state !== 'failed';

/** Being done, or next in line: nothing outside holds it up. */
export const going = (p: Progress | null | undefined) => p?.state === 'working' || p?.state === 'queued';

/**
 * An item's progress: its entry in the list of work under way (`GET /api/progress`, which also knows what the whole
 * program waits on) when it has one, else what its own summary says (a failure, or work the list has not caught up
 * with yet).
 */
export function progressOf(item: Pick<ItemSummary, 'id' | 'progress'> | null | undefined,
  list: ProgressList | null | undefined): Progress | null {
  if (!item) return null;
  return list?.items.find((i) => i.id === item.id)?.progress ?? item.progress ?? null;
}

/** The entries of the list by id, for a screen that shows many items. */
export function byItem(list: ProgressList | null | undefined): Map<string, Progress> {
  return new Map((list?.items ?? []).map((i) => [i.id, i.progress]));
}

export type DotState = 'done' | 'now' | 'later';

/** The strip's three dots: steps before this one done, this one now, the rest still to come. */
export function dots(p: Pick<Progress, 'step' | 'of'>): DotState[] {
  return Array.from({ length: p.of }, (_, i) => (i + 1 < p.step ? 'done' : i + 1 === p.step ? 'now' : 'later'));
}

/** "Step 2 of 3", said beside the dots. */
export const stepWords = (p: Pick<Progress, 'step' | 'of'>) => `Step ${p.step} of ${p.of}`;

/** What a screen reader hears for the tile's step mark: "Step 2 of 3. Claude is describing it." */
export const markLabel = (p: Progress) => `${stepWords(p)}. ${p.words}.`;

/** The waits you can do something about in Settings. */
export const settingsFix = (p: Progress | null | undefined) =>
  p?.state === 'waiting' && (p.waiting_for === 'limit' || p.waiting_for === 'sign-in' || p.waiting_for === 'model' || p.waiting_for === 'download');

/** The line under the strip's words: where the work runs and how long it takes, or why it waits. */
export function stripNote(p: Progress): string {
  if (p.state === 'waiting' && p.waiting_for === 'claude') return 'It goes on by itself once Claude can be reached.';
  if (p.state === 'waiting' && p.waiting_for === 'you') return p.why ?? '';
  if (settingsFix(p)) return 'You can see to it in Settings.';
  return p.about;
}

const plural = (n: number) => `${n} ${n === 1 ? 'item' : 'items'}`;

/** The one line above the closet grid while items are worked on: "Working on 3 items", or, when all of them wait,
 * "3 items waiting". Null when nothing is. */
export function workingLine(list: ProgressList | null | undefined): string | null {
  const n = list?.items.length ?? 0;
  if (!n) return null;
  return list!.going > 0 ? `Working on ${plural(n)}` : `${plural(n)} waiting`;
}

/** What Claude called it: its name, else its category and colour. */
export function calledIt(item: Pick<ItemSummary, 'name' | 'category' | 'color'>): string {
  return item.name || tileCaption(item.category, item.color) || 'New item';
}

/** The title of a row on Add (and in the list of work under way) for an item: what is happening to it, or why it
 * stopped, while there is something to say; else what it is called. */
export function rowTitle(item: Pick<ItemSummary, 'name' | 'category' | 'color'>, p: Progress | null | undefined): string {
  return p ? p.words : calledIt(item);
}

/** What the drawing's place on the item page says when there is no drawing to show, or null when there is one. */
export function drawingPlaceholder(p: Progress | null | undefined, category: string | null, hasDrawing: boolean): string | null {
  if (hasDrawing) return null;
  if (busy(p) && p.step <= 2) return 'The drawing appears as soon as Claude has described it.';
  if (!category) return 'Choose what kind of item it is below, and a drawing is made.';
  return 'There is no drawing for this kind of item yet.';
}

/** Whether the drawing's place is offered while there is no drawing yet, so it can say one is on its way. */
export const drawingOnItsWay = (p: Progress | null | undefined) => busy(p) && p.step <= 2;

/**
 * What a shoe's own section (its photos, its drawing) says about its part of the work while that part is the one
 * going on: the same words as the strip (with the owner's note, while a drawing is changed from it), or why it waits.
 * Null when that part is not the one under way, so the section says what it has to say itself.
 */
export function partWords(p: Progress | null | undefined, stage: Progress['stage'], note?: string | null): string | null {
  if (!busy(p) || p.stage !== stage || p.waiting_for === 'you') return null;   // an answer: the section asks itself
  if (p.state === 'waiting') return p.why ?? p.words;
  return note ? `${p.words}: “${note}”` : p.words;
}
