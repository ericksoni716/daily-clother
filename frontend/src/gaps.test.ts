import { describe, expect, it } from 'vitest';
import {
  colorWords, type Gap, groupReasons, HELP_LEVELS, helpOf, HIDE_REASONS, loadSavedGaps, lookForLines, type LookFor,
  orWords, reasonLabel, savedWhen, saveGaps, shortWhy, whatWords,
} from './gaps';
import { forgetSaved } from './today';

class MemoryStorage {
  data = new Map<string, string>();
  get length() { return this.data.size; }
  key(i: number) { return [...this.data.keys()][i] ?? null; }
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
  removeItem(k: string) { this.data.delete(k); }
}

const look = (over: Partial<LookFor> = {}): LookFor => ({
  category: 'coat', formality: 'smart_casual', season: null, weight_class: null, colors: [], pattern: null, material: null, ...over,
});

const gap = (over: Partial<Gap> = {}): Gap => ({
  id: 'outer-rain', name: 'A rain-proof outer layer', look_for: look(), why: ['Nothing you own keeps the rain off.'], score: 70,
  found_by: ['days'], evidence: { days: [], items: ['a', 'b'] }, state: 'open', hidden_reason: null, wish_id: null, ...over,
});

describe('what to look for, in plain words', () => {
  it('names the kind of piece with the occasion it suits', () => {
    expect(whatWords({ category: 'coat', formality: 'smart_casual' })).toBe('A smart casual coat');
    expect(whatWords({ category: 'tee', formality: 'casual' })).toBe('A casual T-shirt');
    expect(whatWords({ category: 'dress_shoes', formality: 'business' })).toBe('Business dress shoes');
    expect(whatWords({ category: 'trousers', formality: null })).toBe('Trousers');
    expect(whatWords({ category: 'sweater', formality: 'athletic' })).toBe('A sport sweater');
    expect(whatWords({ category: 'other', formality: null })).toBe('A piece');
  });

  it('uses "an" before a vowel', () => {
    expect(whatWords({ category: 'oxford', formality: null })).toBe('An oxford');
  });

  it('gives season, weight, pattern and material where they matter, never field names', () => {
    const lines = lookForLines(look({
      season: 'all', weight_class: 'midweight', pattern: 'solid', material: 'waterproof (a mac, trench, waxed cotton or shell)',
    }));
    expect(lines).toEqual([
      'A smart casual coat', 'For any time of year', 'Medium-weight cloth', 'Plain, no pattern',
      'Waterproof (a mac, trench, waxed cotton or shell)',
    ]);
    for (const line of lines) expect(line).not.toMatch(/_|weight_class|formality|season:/);
    expect(lookForLines(look({ season: 'cool', weight_class: 'heavyweight' }))).toEqual([
      'A smart casual coat', 'For cool and cold weather', 'Heavy, warm cloth',
    ]);
    expect(lookForLines(look({ category: 'shorts', formality: 'casual', season: 'warm', weight_class: 'lightweight' })))
      .toEqual(['Casual shorts', 'For warm weather', 'Light, thin cloth']);
  });

  it('leaves out what does not matter, and copes with nothing', () => {
    expect(lookForLines(look({ category: 'belt', formality: 'smart_casual' }))).toEqual(['A smart casual belt']);
    expect(lookForLines(null)).toEqual([]);
    expect(lookForLines(look({ season: 'monsoon', weight_class: 'feather' }))).toEqual(['A smart casual coat']);
  });

  it('says the colours as a choice', () => {
    expect(colorWords(['navy', 'grey', 'light_blue'])).toBe('Navy, grey or light blue');
    expect(colorWords(['brown', 'black'])).toBe('Brown or black');
    expect(colorWords(['tan'])).toBe('Tan');
    expect(colorWords([])).toBe('');
    expect(colorWords(null)).toBe('');
    expect(orWords(['a', 'b', 'c'])).toBe('a, b or c');
  });

  it('shows learned fit and avoidance without requiring them in older answers', () => {
    expect(lookForLines(look({ fit: 'regular', avoid_patterns: ['plaid', 'graphic'], avoid_fits: ['extra_slim'] })))
      .toEqual(['A smart casual coat', 'Regular fit', 'Avoid plaid, graphic patterns', 'Avoid extra slim fits']);
    expect(lookForLines(look())).toEqual(['A smart casual coat']);
    expect(lookForLines(look({ kind: 'joggers or sweatpants' }))).toEqual(['A smart casual coat', 'For example joggers or sweatpants']);
  });
});

describe('how much a gap would help', () => {
  it('is a level of bars with words, never a number', () => {
    for (const s of [0, 10, 30, 50, 70, 100]) {
      const h = helpOf(s);
      expect(h.level).toBeGreaterThanOrEqual(1);
      expect(h.level).toBeLessThanOrEqual(HELP_LEVELS);
      expect(h.words).not.toMatch(/\d/);
    }
  });

  it('never goes down as the score goes up, and spreads the demo closet over the levels', () => {
    let last = 0;
    for (let s = 0; s <= 100; s++) {
      const { level } = helpOf(s);
      expect(level).toBeGreaterThanOrEqual(last);
      last = level;
    }
    // the demo closet's scores: a rain coat and smart shoes stand out from a belt
    expect(helpOf(71).level).toBe(4);
    expect(helpOf(65).level).toBe(4);
    expect(helpOf(38).level).toBe(2);
    expect(helpOf(20).level).toBe(1);
    expect(helpOf(16).words).toBe('Helps a little');
    expect(helpOf(38).words).toBe('Helps some');
    expect(helpOf(71).words).toBe('Helps a lot');
  });

  it('copes with a score that is not a number', () => {
    expect(helpOf(Number.NaN).level).toBe(1);
  });
});

describe('why, day by day', () => {
  const belt = 'A leather belt finishes trousers and jeans; the engine adds one to every outfit that has them. You have none.';
  const shoes = 'Smart leather shoes (oxfords, derbies or loafers) are what business and formal days need. You have none.';

  it('says a reason given for several kinds of day once, and lists the days under it', () => {
    const groups = groupReasons([
      `For work, most days: on the cold, cool, mild or hot days here, about 365 a year. ${belt}`,
      `For everyday, most days: on the cold, cool, mild or hot days here, about 365 a year. ${belt}`,
      `For going out, about once a week: on the cold, cool, mild or hot days here, about 365 a year. ${belt}`,
      `For vacation, most days during about 2 weeks away a year: on mild or hot days away. ${belt}`,
    ]);
    expect(groups).toEqual([{
      text: belt,
      days: [
        { occasion: 'Work', when: 'most days: on the cold, cool, mild or hot days here, about 365 a year' },
        { occasion: 'Everyday', when: 'most days: on the cold, cool, mild or hot days here, about 365 a year' },
        { occasion: 'Going out', when: 'about once a week: on the cold, cool, mild or hot days here, about 365 a year' },
        { occasion: 'Vacation', when: 'most days during about 2 weeks away a year: on mild or hot days away' },
      ],
    }]);
  });

  it('keeps different reasons apart, in the order they came', () => {
    const groups = groupReasons([
      `For work, most days: on the hot days here, about 55 a year. ${shoes}`,
      `For lounging at home, most days: indoors. ${belt}`,
      `For work, most days: on the cold days here, about 91 a year. ${shoes}`,
    ]);
    expect(groups.map((g) => g.text)).toEqual([shoes, belt]);
    expect(groups[0].days.map((d) => d.when)).toEqual(['most days: on the hot days here, about 55 a year', 'most days: on the cold days here, about 91 a year']);
    expect(groups[1].days).toEqual([{ occasion: 'Lounging at home', when: 'most days: indoors' }]);
  });

  it('keeps reasons written before the owner said how they live, without days, and merges exact repeats', () => {
    expect(groupReasons([belt, shoes, belt])).toEqual([{ text: belt, days: [] }, { text: shoes, days: [] }]);
    expect(groupReasons([])).toEqual([]);
    expect(groupReasons(undefined)).toEqual([]);
  });
});

describe('not for me', () => {
  it('offers the four reasons in plain words', () => {
    expect(HIDE_REASONS.map((r) => r.value)).toEqual(['have_one', 'never_wear', 'too_expensive', 'other']);
    expect(reasonLabel('too_expensive')).toBe('Too expensive');
    expect(reasonLabel(null)).toBe('');
  });
});

describe('the copy kept on this device', () => {
  it('is kept per closet, merged part by part, and removed with the other saved copies', () => {
    const kv = new MemoryStorage();
    expect(loadSavedGaps('demo', kv)).toBeNull();
    const answer = { enough: true, message: null, gaps: [gap()], notes: [], checked: { items: 30, wears: 3, days: 40 } };
    saveGaps('demo', { gaps: answer }, kv, new Date('2026-11-12T10:00:00Z'));
    saveGaps('demo', { wishes: [] }, kv, new Date('2026-11-12T10:05:00Z'));
    expect(loadSavedGaps('demo', kv)).toEqual({ saved_at: '2026-11-12T10:05:00.000Z', gaps: answer, wishes: [] });
    expect(loadSavedGaps('main', kv)).toBeNull();
    kv.setItem('closet-other', 'kept');
    forgetSaved(kv);
    expect(loadSavedGaps('demo', kv)).toBeNull();
    expect(kv.getItem('closet-other')).toBe('kept');
  });

  it('ignores a damaged copy', () => {
    const kv = new MemoryStorage();
    kv.setItem('closet-today-saved:gaps:main', '{not json');
    expect(loadSavedGaps('main', kv)).toBeNull();
  });
});

describe('savedWhen', () => {
  it('says the day a saved copy was kept as the rest of the page says days', () => {
    const now = new Date(2026, 10, 23, 15, 0);
    expect(savedWhen(new Date(2026, 10, 23, 9, 5).toISOString(), now)).toMatch(/^ today, at 9:05/);
    expect(savedWhen(new Date(2026, 10, 22, 9, 5).toISOString(), now)).toBe(', yesterday');
    expect(savedWhen(new Date(2026, 10, 3, 9, 5).toISOString(), now)).toBe(', on 3 Nov');
    expect(savedWhen('not a time', now)).toBe('');
  });
});

describe('the one line of why on a closed card', () => {
  it('is the first reason’s first sentence, up to its colon or semicolon', () => {
    expect(shortWhy(['Every outfit for hot business days rests on your stone pleated chinos: they are the only bottoms that suit. If they are in the wash, there is nothing to change to.']))
      .toBe('Every outfit for hot business days rests on your stone pleated chinos.');
    expect(shortWhy(["Nothing you own keeps the rain off; on cold days all Today can say is 'take an umbrella'."])).toBe('Nothing you own keeps the rain off.');
    expect(shortWhy(['A mac, trench or waxed jacket keeps the rain off without an umbrella. You have none.']))
      .toBe('A mac, trench or waxed jacket keeps the rain off without an umbrella.');
    expect(shortWhy([])).toBe('');
    expect(shortWhy(null)).toBe('');
  });
});
