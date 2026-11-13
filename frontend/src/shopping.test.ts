import { describe, expect, it } from 'vitest';
import { forgetShopping, helpLevel, lookForWords, readShopping, saveShopping, type LookFor, type SavedShopping } from './shopping';

const look: LookFor = {
  category: 'dress_shoes', formality: 'smart_casual', season: 'all', weight_class: null,
  colors: ['brown', 'black'], pattern: 'solid', material: 'smooth leather',
};

describe('what to look for', () => {
  it('uses plain words for every part of the suggestion', () => {
    expect(lookForWords(look)).toEqual([
      'Plain dress shoes', 'For smart casual days', 'All year', 'Smooth leather', 'Brown or black',
    ]);
  });
  it('explains seasons, weight and colours without field names or underscores', () => {
    const words = lookForWords({ ...look, category: 'tee', season: 'warm', weight_class: 'super_heavy', colors: ['light_blue'] });
    expect(words).toContain('Plain T-shirt');
    expect(words).toContain('For warm weather');
    expect(words).toContain('Very heavy fabric');
    expect(words).toContain('Light blue');
    expect(words.join(' ')).not.toContain('_');
    expect(lookForWords({ ...look, season: 'cool', weight_class: 'lightweight' })).toContain('Light fabric');
    expect(lookForWords({ ...look, weight_class: 'midweight' })).toContain('Medium-weight fabric');
    expect(lookForWords({ ...look, weight_class: 'heavyweight' })).toContain('Heavy fabric');
  });
  it('omits unspecified attributes and handles manual wishes', () => {
    expect(lookForWords(null)).toEqual([]);
    expect(lookForWords({ category: 'coat', formality: null, season: null, weight_class: null, colors: [], pattern: null, material: null })).toEqual(['Coat']);
  });
});

describe('how much a gap would help', () => {
  it('compares by fixed bands, not the current list or a number out of 100', () => {
    expect(helpLevel(100)).toEqual({ bars: 5, words: 'Big difference' });
    expect(helpLevel(70).words).toBe('Big difference');
    expect(helpLevel(69).words).toBe('Useful addition');
    expect(helpLevel(40).words).toBe('Useful addition');
    expect(helpLevel(39).words).toBe('A little more choice');
    expect(helpLevel(0).bars).toBe(1);
    const bars = [0, 20, 40, 60, 80, 100].map((n) => helpLevel(n).bars);
    expect(bars).toEqual([...bars].sort());
  });
});

describe('saved shopping', () => {
  const memory = () => {
    const values = new Map<string, string>();
    return {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
      removeItem: (key: string) => { values.delete(key); },
    };
  };
  const saved: SavedShopping = {
    saved_at: '2026-11-12T12:00:00Z',
    answer: { enough: false, message: 'Add more clothes.', gaps: [], notes: [], checked: { items: 0, wears: 0, days: 0 } },
    hidden: [], wishes: [],
  };
  it('keeps closets apart and clears both on logout', () => {
    const kv = memory();
    saveShopping('demo', saved, kv);
    expect(readShopping('demo', kv)).toEqual(saved);
    expect(readShopping('main', kv)).toBeNull();
    saveShopping('main', saved, kv);
    forgetShopping(kv);
    expect(readShopping('main', kv)).toBeNull();
    expect(readShopping('demo', kv)).toBeNull();
  });
  it('ignores corrupt or unavailable storage', () => {
    const kv = memory();
    kv.setItem('closet-shopping:demo', '{"broken":true}');
    expect(readShopping('demo', kv)).toBeNull();
    kv.setItem('closet-shopping:demo', 'not json');
    expect(readShopping('demo', kv)).toBeNull();
    const blocked = { ...kv, setItem: () => { throw new Error('full'); } };
    expect(() => saveShopping('demo', saved, blocked)).not.toThrow();
  });
});
