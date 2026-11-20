import { describe, expect, it } from 'vitest';
import type { Item, ItemSummary, ModelInfo } from './types';
import { closetPoll, DRAWING_MS, FAST_MS, itemPoll, justFinished, MEASURING_MS, measuring, WAITING_MS } from './work';

const summary = (over: Partial<ItemSummary> = {}): ItemSummary => ({
  id: 'i1', name: null, category: 'shirt', color: null, color_hex: null, pattern: null, location: null, rating: null,
  status: 'active', cutout_state: 'ready', tag_state: 'done', thumb_url: null, has_illustration: false, has_photo: true,
  last_worn: null, wear_count: 0, wears_since_wash: 0, laundry: 'clean', created_at: '', updated_at: '', ...over,
});
const item = (over: Partial<Item> = {}) => ({ ...summary(), pattern_state: null, trace: null, views: null, drawn: null, ...over }) as Item;
const model = (state: ModelInfo['state']) => ({ state }) as ModelInfo;
const ready = model('ready');

describe('closetPoll', () => {
  const cases: [string, ItemSummary[], ModelInfo | null, number, boolean, number | null, boolean][] = [
    ['nothing running', [summary()], ready, 0, false, null, false],
    ['a cutout being made', [summary({ cutout_state: 'processing' })], ready, 0, false, FAST_MS, true],
    ['a cutout waiting on a missing model', [summary({ cutout_state: 'pending' })], model('missing'), 0, false, WAITING_MS, true],
    ['a description being written', [summary({ tag_state: 'working' })], ready, 0, false, FAST_MS, false],
    ['a description waiting for a way to reach Claude', [summary({ tag_state: 'waiting' })], ready, 0, false, WAITING_MS, false],
    ['a shoe drawn for the figure', [summary({ drawn_state: 'drawing' })], ready, 0, false, WAITING_MS, false],
    ['a pattern measured on an item known in full', [summary()], ready, 1, false, MEASURING_MS, false],
    ['measuring beats waiting', [summary({ tag_state: 'waiting' })], ready, 1, false, MEASURING_MS, false],
    ['describing beats measuring', [summary({ tag_state: 'working' })], ready, 1, false, FAST_MS, false],
    ['offline: nothing', [summary({ tag_state: 'working' })], ready, 1, true, null, false],
    ['not read yet', [], null, 0, false, null, false],
  ];
  it.each(cases)('%s', (_, items, m, count, offline, ms, asksModel) => {
    expect(closetPoll(items, m, count, offline)).toEqual({ ms, model: asksModel });
  });
});

describe('itemPoll', () => {
  const cases: [string, Item | null, number | null][] = [
    ['nothing to follow', item(), null],
    ['not loaded', null, null],
    ['cut out', item({ cutout_state: 'pending' }), FAST_MS],
    ['described', item({ tag_state: 'working' }), FAST_MS],
    ['waiting for Claude', item({ tag_state: 'waiting' }), WAITING_MS],
    ['a pattern measured', item({ pattern_state: 'working' }), MEASURING_MS],
    ['a shoe traced', item({ trace: { state: 'working' } as Item['trace'] }), FAST_MS],
    ['a shoe drawn', item({ drawn: { state: 'drawing' } as Item['drawn'] }), DRAWING_MS],
    ['a shoe’s photos being sorted', item({ views: { state: 'sorting' } as Item['views'] }), FAST_MS],
    ['a shoe’s photos waiting to be sorted', item({ views: { state: 'waiting' } as Item['views'] }), DRAWING_MS],
  ];
  it.each(cases)('%s', (_, it, ms) => expect(itemPoll(it, false)).toBe(ms));
  it('stops offline', () => expect(itemPoll(item({ tag_state: 'working' }), true)).toBeNull());
});

describe('measuring', () => {
  it('a pattern waiting or measured, or a shoe traced', () => {
    expect(measuring(item({ pattern_state: 'waiting' }))).toBe(true);
    expect(measuring(item({ trace: { state: 'waiting' } as Item['trace'] }))).toBe(true);
    expect(measuring(item({ pattern_state: 'done' }))).toBe(false);
  });
});

describe('justFinished', () => {
  it('names the items whose cutout or description has just finished', () => {
    const before = [summary({ id: 'a', cutout_state: 'processing' }), summary({ id: 'b', tag_state: 'working' }),
      summary({ id: 'c', tag_state: 'working' }), summary({ id: 'd' })];
    const after = [summary({ id: 'a' }), summary({ id: 'b' }), summary({ id: 'c', tag_state: 'failed' }), summary({ id: 'd' }),
      summary({ id: 'e' })];
    expect(justFinished(before, after)).toEqual(['a', 'b']);
  });
  it('nothing the first time the list arrives', () => expect(justFinished(undefined, [summary()])).toEqual([]));
});
