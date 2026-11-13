import { afterEach, describe, expect, it, vi } from 'vitest';
import { canDress, clearTodayData, dayWeather, lastChoices, missingBasics, outfitPieces, pieceName, savedToday, swipeDirection, writeTodayValue, type Outfit, type TodayResult } from './today';
import type { ItemSummary } from './types';

const outfit: Outfit = {
  pieces: { outer: 'coat', mid: 'knit', base: 'shirt', bottom: 'jeans', shoes: 'boots', accessories: ['belt', 'scarf'] },
  score: 85, reasons: [], warnings: [],
};

describe('Today helpers', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('lays pieces out in wearing order and omits absent layers', () => {
    expect(outfitPieces(outfit).map((p) => p.id)).toEqual(['coat', 'knit', 'shirt', 'jeans', 'boots', 'belt', 'scarf']);
    expect(outfitPieces({ ...outfit, pieces: { ...outfit.pieces, outer: null, mid: null } }).map((p) => p.place))
      .toEqual(['Base top', 'Bottom', 'Shoes', 'Accessory', 'Accessory']);
  });
  it('uses plain weather and garment names', () => {
    expect(dayWeather({ low_c: -2.2, high_c: 9.8, rain: true } as TodayResult['context']))
      .toBe('Low -2°C · High 10°C · Rain expected');
    expect(dayWeather({ low_c: 18, high_c: 25, rain: false } as TodayResult['context'])).toContain('No rain expected');
    expect(pieceName({ name: null, category: 'dress_shoes' } as ItemSummary)).toBe('Dress shoes');
    expect(pieceName(undefined)).toBe('Item');
  });
  it('opens Today only with a usable base top, bottom and shoes', () => {
    const items = ['shirt', 'jeans', 'boots'].map((category) => ({ category, status: 'active', laundry: 'clean' } as ItemSummary));
    expect(canDress(items)).toBe(true);
    expect(canDress(items.slice(1))).toBe(false);
    expect(canDress([...items.slice(1), { ...items[0], laundry: 'laundry' }])).toBe(false);
    expect(canDress([...items.slice(1), { ...items[0], rating: 'dislike' }])).toBe(false);
    expect(canDress([...items.slice(1), { ...items[0], status: 'archived' }])).toBe(false);
    expect(canDress([...items.slice(1), { ...items[0], category: 'sweater' }])).toBe(false);
  });
  it('distinguishes horizontal outfit swipes from scrolling and taps', () => {
    expect(swipeDirection(-90, 12)).toBe(1);
    expect(swipeDirection(90, 12)).toBe(-1);
    expect(swipeDirection(10, 4)).toBe(0);
    expect(swipeDirection(-80, 100)).toBe(0);
  });
  it('explains which basics to add before weather is available', () => {
    expect(missingBasics([])).toEqual([
      'Start with a clean shirt, T-shirt or polo.',
      'Add a clean pair of trousers, jeans or shorts.',
      'Add a clean pair of shoes.',
    ]);
  });
  it('separates closets, expires saved outfits, and clears data without losing preferences', () => {
    const data = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => data.set(key, value),
      removeItem: (key: string) => data.delete(key),
    });
    writeTodayValue('demo', { day: '2026-11-13', result: { outfits: [outfit] }, items: [] });
    expect(savedToday('demo', '2026-11-13')?.result.outfits).toEqual([outfit]);
    expect(savedToday('main', '2026-11-13')).toBeNull();
    expect(savedToday('demo', '2026-11-14')).toBeNull();
    writeTodayValue('choices', { occasion: 'business', mood: 'sharp' });
    clearTodayData();
    expect(savedToday('demo', '2026-11-13')).toBeNull();
    expect(lastChoices()).toEqual({ occasion: 'business', mood: 'sharp', leave_out: [] });
    writeTodayValue('choices', { occasion: 'unexpected', mood: 'unexpected' });
    expect(lastChoices()).toEqual({ occasion: 'casual', mood: 'usual', leave_out: [] });
  });
  it('works when browser storage is unavailable or malformed', () => {
    vi.stubGlobal('localStorage', { getItem: () => '{', setItem: () => { throw new Error('full'); } });
    expect(savedToday('demo')).toBeNull();
    expect(() => writeTodayValue('demo', {})).not.toThrow();
    expect(lastChoices().occasion).toBe('casual');
  });
});
