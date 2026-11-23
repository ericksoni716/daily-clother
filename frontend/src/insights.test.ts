import { describe, expect, it } from 'vitest';
import { forgetSaved } from './today';
import {
  addDays, loadSavedInsights, saveInsights, type Insights, barWidth, costCaption, forgetKept, groupLabel, keepPiece,
  keptPieces, KEEP_DAYS, makeupHero, money, perWear, plural, shortDate, spreadHero, unwornCaption, unwornHero, wears, windowLabel,
  wornMostHero, type CategorySpread,
} from './insights';
import { earnedCaption, ninesWindow, spentWords, wishlistCostWords, yearWords, type NinesWindow, type Spending } from './insights';

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

describe('the figure each card leads with', () => {
  it('counts the pieces not being worn, only when there is something to list', () => {
    const f = { title: 'Not worn yet', enough: true, sentence: '', items: [] };
    expect(unwornHero(f, 3)).toBe('3 pieces');
    expect(unwornHero(f, 1)).toBe('1 piece');
    expect(unwornHero(f, 0)).toBeNull();
    expect(unwornHero({ ...f, enough: false }, 3)).toBeNull();
  });

  it('counts the wears of the window, the kinds a few pieces carry and the pieces in use', () => {
    expect(wornMostHero({ title: '', enough: true, sentence: '', days: 30, wears: 25, items: [] })).toBe('25 wears');
    expect(wornMostHero({ title: '', enough: false, sentence: '', days: 30, wears: 0, items: [] })).toBeNull();

    const kind = (k: 'few' | 'even') => ({ category: 'shirt', pieces: 4, wears: 10, doing_most: 1, share: 80, kind: k, sentence: '', items: [] }) as CategorySpread;
    const spread = { title: '', enough: true, sentence: '', days: 90, categories: [kind('few'), kind('even'), kind('few')] };
    expect(spreadHero(spread)).toBe('2 of 3 kinds');
    expect(spreadHero({ ...spread, categories: [kind('even')] })).toBe('Fairly even');
    expect(spreadHero({ ...spread, enough: false })).toBeNull();

    const by = { category: [], color: [], formality: [], season: [] };
    expect(makeupHero({ title: '', enough: true, sentence: '', pieces: 30, worn: 18, days: 90, by })).toBe('18 of 30 worn');
    expect(makeupHero({ title: '', enough: false, sentence: '', pieces: 30, worn: null, days: 90, by })).toBe('30 pieces');
    expect(makeupHero({ title: '', enough: false, sentence: '', pieces: 0, worn: null, days: 90, by })).toBeNull();
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

  it('is forgotten with the other saved copies, but "keep" is not', () => {
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

// --------------------------------------------------------------------- Your nines and what your clothes cost you

const win = (days: number | null, n: number): NinesWindow =>
  ({ days, pieces: n, sentence: null, items: Array.from({ length: Math.min(n, 9) }, (_, i) => ({ id: `p${i}`, wears: 9 - i })) });

describe('Your nines', () => {
  it('opens on the first time with nine pieces, else the one with the most', () => {
    expect(ninesWindow([win(30, 12), win(90, 20), win(null, 30)])).toBe(0);
    expect(ninesWindow([win(30, 4), win(90, 9), win(null, 30)])).toBe(1);
    expect(ninesWindow([win(30, 2), win(90, 5), win(null, 5)])).toBe(1);
    expect(ninesWindow([win(30, 0), win(90, 0), win(null, 0)])).toBe(0);
  });
});

const spending = (over: Partial<Spending> = {}): Spending => ({
  currency: '$', year: 2026, pieces: 40, priced: 9, dated: 9, unpriced: 31, first_missing: 'a', enough: true,
  by_year: [{ year: 2026, spent_cents: 124000, pieces: 9 }, { year: 2025, spent_cents: 31050, pieces: 2 }],
  earned: [], not_earned: [], wishlist: { wishes: 0, unpriced: 0, totals: [] }, ...over,
});

describe('what your clothes cost you', () => {
  it('says what was spent this year once a few pieces have a price and a date', () => {
    expect(spentWords(spending())).toEqual({ text: 'You spent $1,240 on 9 pieces this year.', fill: null });
    expect(spentWords(spending({ by_year: [{ year: 2026, spent_cents: 4550, pieces: 1 }] }))!.text).toBe('You spent $45.50 on 1 piece this year.');
    // nothing bought this year: the last year there was
    expect(spentWords(spending({ by_year: [{ year: 2025, spent_cents: 31050, pieces: 2 }] }))!.text)
      .toBe('Nothing with a price was bought this year. In 2025 you spent $310.50 on 2 pieces.');
  });

  it('says plainly how many pieces have no price yet, and asks for one', () => {
    expect(spentWords(spending({ enough: false, priced: 2, dated: 1, unpriced: 38 }))).toEqual({ text: '38 of your 40 pieces have no price yet.', fill: 'price' });
    expect(spentWords(spending({ enough: false, priced: 39, dated: 1, unpriced: 1 }))!.text).toBe('1 of your 40 pieces has no price yet.');
    expect(spentWords(spending({ enough: false, priced: 0, dated: 0, unpriced: 40 }))!.text).toBe('None of your 40 pieces has a price yet.');
    expect(spentWords(spending({ pieces: 1, enough: false, priced: 0, dated: 0, unpriced: 1 }))!.text).toBe('Your one piece has no price yet.');
    // every piece has a price, but too few have a date bought
    expect(spentWords(spending({ pieces: 5, enough: false, priced: 5, dated: 1, unpriced: 0 })))
      .toEqual({ text: '4 of your pieces have a price but no date bought.', fill: 'date' });
    expect(spentWords(spending({ pieces: 0, priced: 0, dated: 0, unpriced: 0, enough: false }))).toBeNull();
  });

  it('says each year, newest first', () => {
    expect(yearWords(spending())).toEqual(['In 2026 you spent $1,240 on 9 pieces.', 'In 2025 you spent $310.50 on 2 pieces.']);
    expect(yearWords(spending({ by_year: [] }))).toEqual([]);
  });

  it('puts what a wear cost under a piece that earned its price, and its price under one that has not', () => {
    expect(earnedCaption({ id: 'a', price_cents: 9000, wears: 30, per_wear_cents: 300 }, '$')).toBe('$3.00 a wear · 30 wears');
    expect(earnedCaption({ id: 'a', price_cents: 35000, wears: 0 }, '$')).toBe('$350 · Not worn yet');
    expect(earnedCaption({ id: 'a', price_cents: 6050, wears: 2 }, '$')).toBe('$60.50 · 2 wears');
  });

  it('says what the wishlist would cost at today’s prices, never adding up two currencies', () => {
    expect(wishlistCostWords({ wishes: 0, unpriced: 0, totals: [] })).toBeNull();
    expect(wishlistCostWords({ wishes: 3, unpriced: 3, totals: [] })).toBe('Nothing on your wishlist has a price yet.');
    expect(wishlistCostWords({ wishes: 1, unpriced: 1, totals: [] })).toBe('The one thing on your wishlist has no price yet.');
    expect(wishlistCostWords({ wishes: 2, unpriced: 0, totals: [{ currency: 'USD', cents: 42000, wishes: 2 }] }))
      .toBe("At today's prices, your wishlist would cost $420.");
    expect(wishlistCostWords({ wishes: 4, unpriced: 1, totals: [{ currency: 'USD', cents: 15440, wishes: 3 }] }))
      .toBe("At today's prices, the 3 things on your wishlist with a price would cost $154.40. 1 thing has no price yet.");
    const mixed = wishlistCostWords({ wishes: 5, unpriced: 2, totals: [{ currency: 'USD', cents: 42000, wishes: 2 }, { currency: 'EUR', cents: 8000, wishes: 1 }] });
    expect(mixed).toBe("Your wishlist is priced in 2 currencies, so it is not added up. At today's prices it is $420 for 2 things and €80 for 1 thing. 2 things have no price yet.");
    expect(mixed).not.toMatch(/\$500|500/);
  });
});
