import { describe, expect, it } from 'vitest';
import { localDay, sinceWash, wearDay, wearSummary, whenWorn } from './wears';

// Thursday 12 November 2026
const TODAY = '2026-11-12';

describe('worn N times, last on …', () => {
  it('says when nothing has been worn', () => {
    expect(wearSummary(0, null, TODAY)).toBe('Not worn yet');
    expect(wearSummary(0, undefined, TODAY)).toBe('Not worn yet');
  });

  it('says once, then a count', () => {
    expect(wearSummary(1, '2026-11-12', TODAY)).toBe('Worn once, today');
    expect(wearSummary(1, '2026-11-11', TODAY)).toBe('Worn once, yesterday');
    expect(wearSummary(6, '2026-11-10', TODAY)).toBe('Worn 6 times, last on Tuesday');
    expect(wearSummary(2, '2026-11-12', TODAY)).toBe('Worn 2 times, last today');
  });

  it('names the weekday within the past week, the date before that, and the year only when it differs', () => {
    expect(whenWorn('2026-11-06', TODAY)).toBe('on Friday');
    expect(whenWorn('2026-11-05', TODAY)).toBe('on 5 Nov');
    expect(whenWorn('2025-12-30', TODAY)).toBe('on 30 Dec 2025');
    expect(whenWorn('2027-01-01', '2027-01-04')).toBe('on Friday');
    expect(whenWorn('2026-12-31', '2027-01-01')).toBe('yesterday');
  });

  it('lists days in plain words', () => {
    expect(wearDay('2026-11-12', TODAY)).toBe('Today');
    expect(wearDay('2026-11-11', TODAY)).toBe('Yesterday');
    expect(wearDay('2026-11-10', TODAY)).toBe('Tuesday 10 Nov');
    expect(wearDay('2026-10-01', TODAY)).toBe('1 Oct');
  });

  it('counts wears since the wash', () => {
    expect(sinceWash(0)).toBe('Not worn since it was washed');
    expect(sinceWash(1)).toBe('Worn once since it was washed');
    expect(sinceWash(3)).toBe('Worn 3 times since it was washed');
  });

  it('gives today as a local calendar day', () => {
    expect(localDay(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
  });
});
