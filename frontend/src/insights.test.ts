import { describe, expect, it } from 'vitest';
import { forgetSaved } from './today';
import {
  addDays, loadSavedInsights, saveInsights, type Insights, barWidth, costCaption, forgetKept, groupLabel, keepPiece, keptPieces, KEEP_DAYS, money, perWear, plural, shortDate,
  unwornCaption, wears, windowLabel,
} from './insights';

class MemoryStorage {
  data = new Map<string, string>();
  get length() { return this.data.size; }
  key(i: number) { return [...this.data.keys()][i] ?? null; }
  removeItem(k: string) { this.data.delete(k); }
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
}

describe('money', () => {
  it('shows whole amounts without cents and others with two digits', () => {
    expect(money(4500)).toBe('$45');
    expect(money(4550)).toBe('$45.50');
    expect(money(4505)).toBe('$45.05');
    expect(money(104000)).toBe('$1,040');
    expect(money(0)).toBe('$0');
  });

  it('always shows cents for a cost per wear, as "a wear"', () => {
    expect(perWear(240)).toBe('$2.40 a wear');
    expect(perWear(4500)).toBe('$45.00 a wear');
    expect(perWear(7)).toBe('$0.07 a wear');
    expect(perWear(123456)).toBe('$1,234.56 a wear');
  });
});

describe('plurals', () => {
  it('says one and many', () => {
    expect(plural(1, 'piece')).toBe('1 piece');
    expect(plural(0, 'piece')).toBe('0 pieces');
    expect(plural(3, 'piece')).toBe('3 pieces');
    expect(plural(2, 'is', 'are')).toBe('2 are');
  });

  it('counts wears, and says "not worn yet" rather than zero', () => {
    expect(wears(0)).toBe('Not worn yet');
    expect(wears(1)).toBe('1 wear');
    expect(wears(25)).toBe('25 wears');
  });
});

describe('captions', () => {
  it('shows a cost per wear, or the price of a piece not worn yet (never zero or infinity)', () => {
    expect(costCaption({ id: 'a', price_cents: 6000, wears: 25, per_wear_cents: 240, sentence: '' })).toBe('$2.40 a wear · 25 wears');
    expect(costCaption({ id: 'a', price_cents: 6000, wears: 1, per_wear_cents: 6000, sentence: '' })).toBe('$60.00 a wear · 1 wear');
    expect(costCaption({ id: 'a', price_cents: 6000, wears: 0, per_wear_cents: null, sentence: '' })).toBe('$60 · not worn yet');
  });

  it('says when a piece not being worn was last worn', () => {
    expect(unwornCaption({ id: 'a', sentence: '', last_worn: '2026-03-04' })).toBe('Last worn 4 Mar 2026');
    expect(unwornCaption({ id: 'a', sentence: '', since: '2026-10-31' })).toBe('Not worn yet');
    expect(unwornCaption({ id: 'a', sentence: '' })).toBe('Not worn yet');
    expect(shortDate('2026-01-09')).toBe('9 Jan 2026');
  });

  it('names the windows and the groups', () => {
    expect(windowLabel(30)).toBe('Last 30 days');
    expect(windowLabel(null)).toBe('All time');
    expect(groupLabel('category', null)).toBe('Not set');
    expect(groupLabel('category', 'trousers')).toBe('Trousers');
    expect(groupLabel('category', 'shirt')).toBe('Shirts');
    expect(groupLabel('color', 'navy')).toBe('Navy');
  });

  it('draws bars relative to the largest, with a sliver for small ones', () => {
    expect(barWidth(10, 10)).toBe(100);
    expect(barWidth(5, 10)).toBe(50);
    expect(barWidth(1, 1000)).toBe(4);
    expect(barWidth(0, 10)).toBe(0);
    expect(barWidth(3, 0)).toBe(0);
  });
});

describe('keep', () => {
  it('adds days across months and years', () => {
    expect(addDays('2026-11-13', 90)).toBe('2027-02-11');
    expect(addDays('2026-02-28', 1)).toBe('2026-03-01');
  });

  it(`stops a piece being listed for ${KEEP_DAYS} days, per closet`, () => {
    const kv = new MemoryStorage();
    const until = keepPiece('main', 'abc', '2026-11-13', kv);
    expect(until).toBe('2027-02-11');
    expect(keptPieces('main', '2026-11-13', kv)).toEqual({ abc: '2027-02-11' });
    expect(keptPieces('main', '2027-02-10', kv)).toEqual({ abc: '2027-02-11' });
    expect(keptPieces('main', '2027-02-11', kv)).toEqual({});
    expect(keptPieces('demo', '2026-11-13', kv)).toEqual({});
  });

  it('forgets every kept piece, and survives bad or missing storage', () => {
    const kv = new MemoryStorage();
    keepPiece('main', 'a', '2026-11-13', kv);
    keepPiece('main', 'b', '2026-11-13', kv);
    expect(Object.keys(keptPieces('main', '2026-11-13', kv))).toEqual(['a', 'b']);
    forgetKept('main', kv);
    expect(keptPieces('main', '2026-11-13', kv)).toEqual({});
    kv.setItem('closet-insights-keep:main', 'not json');
    expect(keptPieces('main', '2026-11-13', kv)).toEqual({});
    expect(keptPieces('main', '2026-11-13', null)).toEqual({});
    expect(keepPiece('main', 'a', '2026-11-13', null)).toBe('2027-02-11');
  });
});

describe('the saved answer', () => {
  const answer = (sentence: string) => ({ today: '2026-11-13', cost_per_wear: { sentence } }) as unknown as Insights;

  it('is kept per closet, so one closet never shows the other\'s', () => {
    const kv = new MemoryStorage();
    saveInsights('demo', answer('demo'), kv, new Date('2026-11-13T08:00:00Z'));
    expect(loadSavedInsights('main', kv)).toBeNull();
    expect(loadSavedInsights('demo', kv)).toEqual({ saved_at: '2026-11-13T08:00:00.000Z', answer: answer('demo') });
    saveInsights('main', answer('main'), kv);
    expect(loadSavedInsights('main', kv)?.answer.cost_per_wear.sentence).toBe('main');
    expect(loadSavedInsights('demo', kv)?.answer.cost_per_wear.sentence).toBe('demo');
  });

  it('is removed on logout with the other saved copies, but "keep" is not', () => {
    const kv = new MemoryStorage();
    saveInsights('main', answer('main'), kv);
    keepPiece('main', 'a', '2026-11-13', kv);
    forgetSaved(kv);
    expect(loadSavedInsights('main', kv)).toBeNull();
    expect(keptPieces('main', '2026-11-13', kv)).toEqual({ a: '2027-02-11' });
  });

  it('survives bad or missing storage', () => {
    const kv = new MemoryStorage();
    kv.setItem('closet-today-saved:insights:main', '{oops');
    expect(loadSavedInsights('main', kv)).toBeNull();
    expect(loadSavedInsights('main', null)).toBeNull();
    saveInsights('main', answer('x'), null);
  });
});
