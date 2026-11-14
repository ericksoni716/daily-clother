import { describe, expect, it } from 'vitest';
import {
  canDress, dayParts, forgetSaved, joinWords, keptFor, loadChoice, longDate, moodLabel, OCCASIONS, occasionLabel, outfitIds,
  parseTemp, placeLabel, rainWords, sameOutfit, saveChoice, SAVED_PREFIX, shortPlace, temps, whatToAddFirst, wornOrder,
  type DayContext, type Outfit, type SavedOutfits,
} from './today';
import type { ItemSummary } from './types';

class MemoryStorage {
  data = new Map<string, string>();
  get length() { return this.data.size; }
  key(i: number) { return [...this.data.keys()][i] ?? null; }
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
  removeItem(k: string) { this.data.delete(k); }
}

const day = (over: Partial<DayContext> = {}): DayContext => ({
  date: '2026-11-12', low_c: 3.2, high_c: 9.8, rain: true, source: 'forecast', old: false,
  place: 'Brooklyn, New York, United States', rain_chance: 70, summary: 'rain', message: null, ...over,
});

const item = (id: string, category: string | null, over: Partial<ItemSummary> = {}): ItemSummary => ({
  id, name: null, category, color: null, color_hex: null, pattern: null, location: null, rating: null, status: 'active',
  cutout_state: 'none', thumb_url: null, has_illustration: false, has_photo: false, last_worn: null, wear_count: 0,
  wears_since_wash: 0, laundry: 'clean', created_at: '', updated_at: '', ...over,
} as ItemSummary);

const outfit: Outfit = {
  pieces: { base: 'tee', mid: null, outer: 'coat', bottom: 'jeans', shoes: 'boots', accessories: ['belt'] },
  score: 80, reasons: ['Warm enough.'], warnings: [],
};

describe('plain words for the choices', () => {
  it('names every occasion and mood in plain words', () => {
    expect(OCCASIONS.map(occasionLabel)).toEqual(['Sport', 'Casual', 'Smart casual', 'Business', 'Formal']);
    expect(['usual', 'sharp', 'relaxed'].map(moodLabel)).toEqual(['As usual', 'Sharp', 'Relaxed']);
  });

  it('falls back to the vocabulary for a value it does not know yet', () => {
    expect(occasionLabel('black_tie')).toBe('Black tie');
  });

  it('names where each piece goes', () => {
    expect(placeLabel('base')).toBe('Top');
    expect(placeLabel('accessory')).toBe('Extra');
  });
});

describe('the pieces of an outfit', () => {
  it('come in the order they are put on, skipping empty places', () => {
    expect(wornOrder(outfit.pieces)).toEqual([
      { place: 'outer', id: 'coat' }, { place: 'base', id: 'tee' }, { place: 'bottom', id: 'jeans' },
      { place: 'shoes', id: 'boots' }, { place: 'accessory', id: 'belt' },
    ]);
    expect(outfitIds(outfit.pieces)).toEqual(['coat', 'tee', 'jeans', 'boots', 'belt']);
  });

  it('are the same outfit whatever their order', () => {
    expect(sameOutfit(['a', 'b', 'c'], ['c', 'a', 'b'])).toBe(true);
    expect(sameOutfit(['a', 'b'], ['a', 'b', 'c'])).toBe(false);
    expect(sameOutfit(['a', 'b'], ['a', 'c'])).toBe(false);
  });
});

describe('the day at a glance', () => {
  it('gives the temperatures, the rain and where the day came from, in one short line', () => {
    expect(dayParts(day())).toEqual(['3–10°C', 'rain 70%', 'Brooklyn']);
    expect(dayParts(day({ rain_chance: null }))).toEqual(['3–10°C', 'rain likely', 'Brooklyn']);
    expect(dayParts(day({ place: null, source: 'given', rain: false, rain_chance: null })))
      .toEqual(['3–10°C', 'no rain', 'your temperatures']);
    expect(dayParts(day({ low_c: 21.6, high_c: 22.4, rain: false, rain_chance: 10 }))).toEqual(['About 22°C', 'no rain', 'Brooklyn']);
    // no forecast could be had: a mild day, whatever place is saved
    expect(dayParts(day({ place: null, source: 'mild', low_c: 14, high_c: 20, rain: false, rain_chance: null })))
      .toEqual(['14–20°C', 'no rain', 'a mild day']);
  });

  it('says "about" when low and high round to the same degree', () => {
    expect(temps(21.6, 22.4)).toBe('About 22°C');
    expect(temps(-3.4, 1)).toBe('-3°C to 1°C');
  });

  it('words the rain with or without a chance', () => {
    expect(rainWords({ rain: false, rain_chance: 10 })).toBe('No rain expected (10%)');
    expect(rainWords({ rain: true, rain_chance: null })).toBe('Rain likely');
  });

  it('shortens a place to its first part', () => {
    expect(shortPlace('Brooklyn, New York, United States')).toBe('Brooklyn');
    expect(shortPlace(null)).toBe('');
  });

  it('writes the date as a weekday, day and month', () => {
    expect(longDate('2026-11-12')).toBe('Thursday 12 Nov');
    expect(longDate('2027-01-01')).toBe('Friday 1 Jan');
  });
});

describe('typed temperatures', () => {
  it('read numbers with or without a degree sign, comma decimals and a typographic minus', () => {
    expect(parseTemp('5')).toBe(5);
    expect(parseTemp(' -3 ')).toBe(-3);
    expect(parseTemp('12,5')).toBe(12.5);
    expect(parseTemp('12°C')).toBe(12);
    expect(parseTemp('−4')).toBe(-4);
  });

  it('refuse anything else, and temperatures no one dresses for', () => {
    for (const bad of ['', 'warm', '1-2', '80', '-60']) expect(parseTemp(bad)).toBeNull();
  });
});

describe('can the closet dress the owner?', () => {
  it('needs a top, something for the legs and shoes, in that order', () => {
    expect(canDress(null)).toBe(false);
    expect(whatToAddFirst([])).toEqual([
      'a top (a T-shirt, shirt or polo)', 'something for your legs (trousers, jeans or shorts)', 'a pair of shoes',
    ]);
    expect(whatToAddFirst([item('1', 'tee'), item('2', 'sneakers')])).toEqual(['something for your legs (trousers, jeans or shorts)']);
    expect(canDress([item('1', 'shirt'), item('2', 'trousers'), item('3', 'boots')])).toBe(true);
  });

  it('does not count untagged, archived or disliked clothes', () => {
    const closet = [item('1', 'tee'), item('2', 'jeans', { rating: 'dislike' }), item('3', 'boots', { status: 'archived' }), item('4', null)];
    expect(whatToAddFirst(closet)).toHaveLength(2);
  });

  it('joins words as a person would', () => {
    expect(joinWords([])).toBe('');
    expect(joinWords(['a'])).toBe('a');
    expect(joinWords(['a', 'b'])).toBe('a and b');
    expect(joinWords(['a', 'b', 'c'])).toBe('a, b and c');
  });
});

describe('kept on this device', () => {
  it('remembers the last occasion and mood, and starts from casual and as usual', () => {
    const kv = new MemoryStorage();
    expect(loadChoice(kv)).toEqual({ occasion: 'casual', mood: 'usual' });
    saveChoice({ occasion: 'business', mood: 'sharp' }, kv);
    expect(loadChoice(kv)).toEqual({ occasion: 'business', mood: 'sharp' });
    kv.setItem('closet-today-choice', JSON.stringify({ occasion: 'gala', mood: 7 }));
    expect(loadChoice(kv)).toEqual({ occasion: 'casual', mood: 'usual' });
    kv.setItem('closet-today-choice', '{not json');
    expect(loadChoice(kv)).toEqual({ occasion: 'casual', mood: 'usual' });
  });

  it('gives back what was kept only on the same day, and for the same closet', () => {
    const kv = new MemoryStorage();
    const main = keptFor('main', kv);
    const saved: SavedOutfits = {
      day: '2026-11-12', saved_at: '2026-11-12T07:30:00Z', request: { occasion: 'casual', mood: 'usual' },
      answer: { outfits: [outfit], missing: [], context: day() },
    };
    main.setOutfits(saved);
    main.setTyped({ day: '2026-11-12', low_c: 4, high_c: 11, rain: false });
    main.setWorn({ day: '2026-11-12', worn_on: '2026-11-12', ids: ['tee'], recorded: ['tee'], outfit });
    expect(main.outfits('2026-11-12')).toEqual(saved);
    expect(main.typed('2026-11-12')?.high_c).toBe(11);
    expect(main.worn('2026-11-12')?.recorded).toEqual(['tee']);
    expect(main.outfits('2026-11-13')).toBeNull();
    expect(main.worn('2026-11-13')).toBeNull();
    expect(keptFor('demo', kv).outfits('2026-11-12')).toBeNull();
    main.setWorn(null);
    expect(main.worn('2026-11-12')).toBeNull();
  });

  it('forgets everything it kept about the closet, and nothing else', () => {
    const kv = new MemoryStorage();
    keptFor('main', kv).setTyped({ day: '2026-11-12', low_c: 4, high_c: 11, rain: false });
    keptFor('demo', kv).setTyped({ day: '2026-11-12', low_c: 4, high_c: 11, rain: false });
    saveChoice({ occasion: 'formal', mood: 'usual' }, kv);
    kv.setItem('something-else', 'x');
    forgetSaved(kv);
    expect([...kv.data.keys()].some((k) => k.startsWith(SAVED_PREFIX))).toBe(false);
    expect(kv.getItem('something-else')).toBe('x');
    expect(loadChoice(kv).occasion).toBe('formal');
  });
});
