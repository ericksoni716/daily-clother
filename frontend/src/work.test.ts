import { describe, expect, it } from 'vitest';
import type { Additions, Progress, ProgressList } from './types';
import { FAST_MS, itemPoll, movedOn, progressPoll, WAITING_MS } from './work';

const progress = (over: Partial<Progress> = {}): Progress => ({
  stage: 'cutout', step: 1, of: 3, state: 'working', title: 'Cutting out', words: 'Removing the background', about: '',
  waiting_for: null, why: null, error: null, can_retry: false, retry: null, ...over,
});
const entry = (id: string, over: Partial<Progress> = {}) =>
  ({ id, name: null, category: null, color: null, status: 'active', thumb_url: null, progress: progress(over) }) as ProgressList['items'][number];
const list = (...items: ProgressList['items']): ProgressList => {
  const waiting = items.filter((i) => i.progress.state === 'waiting').length;
  return { items, going: items.length - waiting, waiting, why: null };
};

describe('progressPoll', () => {
  const cases: [string, ProgressList | null, boolean, number | null][] = [
    ['not read yet', null, false, null],
    ['nothing under way: an edit that starts work asks again', list(), false, null],
    ['a cutout being made', list(entry('a')), false, FAST_MS],
    ['a description next in line', list(entry('a', { stage: 'describing', step: 2, state: 'queued' })), false, FAST_MS],
    // the stages the old poll missed: measuring a pattern and drawing a shoe are polled as fast as the rest
    ['a pattern measured', list(entry('a', { stage: 'pattern', step: 3 })), false, FAST_MS],
    ['a shoe drawn by Claude', list(entry('a', { stage: 'shoe', step: 3 })), false, FAST_MS],
    ['only waiting (background removal, Claude, the limit)', list(entry('a', { state: 'waiting', waiting_for: 'model' }),
      entry('b', { stage: 'describing', step: 2, state: 'waiting', waiting_for: 'limit' })), false, WAITING_MS],
    ['one going among the waiting', list(entry('a', { state: 'waiting' }), entry('b', { stage: 'trace', step: 3 })), false, FAST_MS],
    ['offline: nothing', list(entry('a')), true, null],
  ];
  it.each(cases)('%s', (_, l, offline, ms) => expect(progressPoll(l, offline)).toBe(ms));
});

describe('movedOn', () => {
  it('nothing the first time the list arrives', () => expect(movedOn(undefined, list(entry('a')))).toEqual([]));

  it('nothing while every item stays where it was', () => {
    expect(movedOn(list(entry('a'), entry('b', { state: 'waiting' })), list(entry('a'), entry('b', { state: 'waiting' })))).toEqual([]);
  });

  it('the items that finished a step, stopped waiting, are done, or are new', () => {
    const before = list(entry('cut'), entry('wait', { state: 'waiting' }), entry('done', { stage: 'pattern', step: 3 }),
      entry('same', { stage: 'describing', step: 2 }));
    const after = list(entry('cut', { stage: 'describing', step: 2, state: 'queued' }), entry('wait'),
      entry('same', { stage: 'describing', step: 2 }), entry('new'));
    expect(movedOn(before, after).sort()).toEqual(['cut', 'done', 'new', 'wait']);
  });
});

describe('itemPoll', () => {
  const with_ = (state: Additions['state']) => ({ additions: { state } as Additions });

  it('reads the item again while Claude draws onto its drawing, since the closet may never see it under way', () => {
    expect(itemPoll(with_('drawing'), false)).toBe(FAST_MS);
  });

  it('does not otherwise, nor offline', () => {
    for (const state of ['idle', 'failed', 'said'] as const) expect(itemPoll(with_(state), false)).toBeNull();
    expect(itemPoll(with_('drawing'), true)).toBeNull();
    expect(itemPoll({ additions: null }, false)).toBeNull();
    expect(itemPoll(null, false)).toBeNull();
  });
});
