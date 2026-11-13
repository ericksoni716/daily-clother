import { describe, expect, it } from 'vitest';
import { notReadyText, progressText, reviewChanges, reviewRows, skippedText, sureText } from './review';
import type { ReviewField } from './types';

const FIELDS: ReviewField[] = [
  { field: 'color', value: 'grey', confidence: 0.55, allowed: ['black', 'grey', 'tan'] },
  { field: 'silhouette', value: { sleeve: 'long', neck: 'turtle' }, confidence: 0.6,
    allowed: { sleeve: ['none', 'short', 'long'], neck: ['crew', 'v', 'turtle'] } },
];

describe('review wording', () => {
  it('says where you are', () => {
    expect(progressText(4, 23)).toBe('4 of 23');
  });

  it('says how sure Claude was, as a whole percentage', () => {
    expect(sureText(0.55)).toBe('Claude was 55% sure');
    expect(sureText(0.666)).toBe('Claude was 67% sure');
    expect(sureText(1.2)).toBe('Claude was 100% sure');
  });

  it('says why items are not in the queue, or nothing', () => {
    expect(notReadyText(0, 0)).toBe('');
    expect(notReadyText(1, 0)).toBe('1 item is still waiting to be described.');
    expect(notReadyText(3, 1)).toBe("3 items are still waiting to be described. 1 item couldn't be described.");
    expect(notReadyText(0, 2)).toBe("2 items couldn't be described.");
  });

  it('says what happens to skipped items', () => {
    expect(skippedText(1)).toBe('You skipped 1 item. It stays in the queue for next time.');
    expect(skippedText(3)).toBe('You skipped 3 items. They stay in the queue for next time.');
  });
});

describe('review choices', () => {
  it("puts Claude's value first and gives the silhouette one row per part", () => {
    const rows = reviewRows(FIELDS);
    expect(rows.map((r) => [r.key, r.part, r.options])).toEqual([
      ['color', null, ['grey', 'black', 'tan']],
      ['silhouette.sleeve', 'sleeve', ['long', 'none', 'short']],
      ['silhouette.neck', 'neck', ['turtle', 'crew', 'v']],
    ]);
    expect(rows[2].confidence).toBe(0.6);
  });

  it('confirms what was left alone and saves what was changed', () => {
    const rows = reviewRows(FIELDS);
    expect(reviewChanges(rows, {})).toEqual({ changes: {}, confirm: ['color', 'silhouette'] });
    expect(reviewChanges(rows, { color: 'grey' })).toEqual({ changes: {}, confirm: ['color', 'silhouette'] });
    expect(reviewChanges(rows, { color: 'tan' })).toEqual({ changes: { color: 'tan', color_hex: '#c9a97c' }, confirm: ['silhouette'] });
    expect(reviewChanges(rows, { 'silhouette.neck': 'crew' })).toEqual({ changes: { silhouette: { neck: 'crew' } }, confirm: ['color'] });
  });
});
