import { describe, expect, it } from 'vitest';
import {
  busy, byItem, calledIt, dots, drawingOnItsWay, drawingPlaceholder, going, markLabel, partWords, progressOf, rowTitle,
  settingsFix, stepWords, stripNote, workingLine,
} from './progress';
import type { Progress, ProgressList } from './types';

const p = (over: Partial<Progress> = {}): Progress => ({
  stage: 'describing', step: 2, of: 3, state: 'working', title: 'Describing and drawing', words: 'Claude is describing it',
  about: 'By Claude, usually within a minute. The drawing appears as soon as it is described.', waiting_for: null, why: null,
  error: null, can_retry: false, retry: null, ...over,
});
const entry = (id: string, progress: Progress) =>
  ({ id, name: null, category: null, color: null, status: 'active', thumb_url: null, progress }) as ProgressList['items'][number];
const list = (items: ProgressList['items'], going: number, why: string | null = null): ProgressList =>
  ({ items, going, waiting: items.length - going, why });

describe('which progress an item shows', () => {
  it('takes the entry in the work under way over its own summary, which may be a step behind', () => {
    const listed = p({ stage: 'cutout', step: 1, state: 'waiting', waiting_for: 'model' });
    expect(progressOf({ id: 'a', progress: p({ stage: 'cutout', step: 1, state: 'queued' }) }, list([entry('a', listed)], 0))).toBe(listed);
    expect(byItem(list([entry('a', listed)], 0)).get('a')).toBe(listed);
  });

  it('falls back to the summary (a failure is never in the list), and to nothing', () => {
    const failed = p({ state: 'failed', retry: 'describe', can_retry: true });
    expect(progressOf({ id: 'a', progress: failed }, list([], 0))).toBe(failed);
    expect(progressOf({ id: 'a', progress: null }, null)).toBeNull();
    expect(progressOf(null, null)).toBeNull();
  });

  it('knows what is still on its way, and what nothing holds up', () => {
    expect(busy(p())).toBe(true);
    expect(busy(p({ state: 'waiting' }))).toBe(true);
    expect(busy(p({ state: 'failed' }))).toBe(false);
    expect(busy(null)).toBe(false);
    expect(going(p({ state: 'queued' }))).toBe(true);
    expect(going(p({ state: 'waiting' }))).toBe(false);
  });
});

describe('the strip on the item page', () => {
  it('shows the three steps as dots: done, now, still to come', () => {
    expect(dots(p({ step: 1 }))).toEqual(['now', 'later', 'later']);
    expect(dots(p({ step: 2 }))).toEqual(['done', 'now', 'later']);
    expect(dots(p({ step: 3 }))).toEqual(['done', 'done', 'now']);
    expect(stepWords(p())).toBe('Step 2 of 3');
  });

  it('says where the work runs and how long it takes, or why it waits', () => {
    expect(stripNote(p())).toMatch(/^By Claude, usually within a minute\. The drawing appears/);
    expect(stripNote(p({ state: 'waiting', waiting_for: 'claude', why: 'x' }))).toBe('It goes on by itself once Claude can be reached.');
    expect(stripNote(p({ state: 'waiting', waiting_for: 'limit', why: 'long' }))).toBe('You can see to it in Settings.');
    expect(stripNote(p({ stage: 'views', step: 3, state: 'waiting', waiting_for: 'you', why: 'Closet needs your answer.' })))
      .toBe('Closet needs your answer.');
  });

  it('offers Settings only for what can be seen to there', () => {
    for (const w of ['limit', 'sign-in', 'model', 'download'] as const) expect(settingsFix(p({ state: 'waiting', waiting_for: w }))).toBe(true);
    expect(settingsFix(p({ state: 'waiting', waiting_for: 'claude' }))).toBe(false);
    expect(settingsFix(p({ state: 'waiting', waiting_for: 'you' }))).toBe(false);
    expect(settingsFix(p())).toBe(false);
  });

  it('says what the drawing’s place waits for, once, in the same words', () => {
    expect(drawingPlaceholder(p({ state: 'queued' }), null, false)).toBe('The drawing appears as soon as Claude has described it.');
    expect(drawingPlaceholder(p({ stage: 'cutout', step: 1 }), null, false)).toBe('The drawing appears as soon as Claude has described it.');
    expect(drawingPlaceholder(p(), 'polo', true)).toBeNull();   // one drawn from the fields the owner set is shown
    expect(drawingPlaceholder(null, null, false)).toMatch(/^Choose what kind of item/);
    expect(drawingPlaceholder(p({ state: 'failed' }), null, false)).toMatch(/^Choose what kind of item/);
    expect(drawingPlaceholder(null, 'bag', false)).toBe('There is no drawing for this kind of item yet.');
    expect(drawingOnItsWay(p())).toBe(true);
    expect(drawingOnItsWay(p({ stage: 'pattern', step: 3 }))).toBe(false);   // it has one; this only finishes it
  });
});

describe('the tile’s mark and the rows', () => {
  it('reads the mark out as the step and its words', () => {
    expect(markLabel(p())).toBe('Step 2 of 3. Claude is describing it.');
  });

  it('titles a row with what is happening, else with what it is called', () => {
    expect(rowTitle({ name: 'Navy polo', category: 'polo', color: 'navy' }, p())).toBe('Claude is describing it');
    expect(rowTitle({ name: 'Navy polo', category: 'polo', color: 'navy' }, null)).toBe('Navy polo');
    expect(rowTitle({ name: null, category: null, color: null }, p({ state: 'failed', words: "Claude couldn't describe this item" })))
      .toBe("Claude couldn't describe this item");
  });

  it('calls an item by its name, else its category and colour', () => {
    expect(calledIt({ name: 'Navy polo', category: 'polo', color: 'navy' })).toBe('Navy polo');
    expect(calledIt({ name: null, category: 'polo', color: 'navy' })).toBe('Polo · Navy');
    expect(calledIt({ name: null, category: 'jeans', color: null })).toBe('Jeans');
    expect(calledIt({ name: '', category: null, color: null })).toBe('New item');
  });
});

describe('the one line above the closet grid', () => {
  it('counts what is worked on, and says when all of it waits', () => {
    expect(workingLine(null)).toBeNull();
    expect(workingLine(list([], 0))).toBeNull();
    expect(workingLine(list([entry('a', p())], 1))).toBe('Working on 1 item');
    expect(workingLine(list([entry('a', p()), entry('b', p({ state: 'waiting' }))], 1))).toBe('Working on 2 items');
    expect(workingLine(list([entry('a', p({ state: 'waiting' })), entry('b', p({ state: 'waiting' }))], 0))).toBe('2 items waiting');
  });
});

describe('a shoe’s own sections', () => {
  it('speak in the progress’s words while their part is the one under way', () => {
    expect(partWords(p({ stage: 'views', step: 3, words: "Sorting the shoe's photos into views" }), 'views'))
      .toBe("Sorting the shoe's photos into views");
    expect(partWords(p({ stage: 'shoe', step: 3, words: 'Changing the drawing as you asked' }), 'shoe', 'black laces'))
      .toBe('Changing the drawing as you asked: “black laces”');
    expect(partWords(p({ stage: 'shoe', step: 3, state: 'waiting', waiting_for: 'claude', why: 'Waiting for Claude to draw the shoe.' }), 'shoe'))
      .toBe('Waiting for Claude to draw the shoe.');
  });

  it('leave the words to the section itself otherwise', () => {
    expect(partWords(p({ stage: 'trace', step: 3 }), 'shoe')).toBeNull();
    expect(partWords(p({ stage: 'views', step: 3, state: 'waiting', waiting_for: 'you' }), 'views')).toBeNull();   // it asks
    expect(partWords(null, 'shoe')).toBeNull();
  });
});
