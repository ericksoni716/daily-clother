import { describe, expect, it } from 'vitest';
import { forgetSaved, keptFor, type WornToday } from './today';
import {
  dismiss, loadDismissed, loadSavedWorn, pendingQuestion, pieceName, questionFor, ratingLabel, ratingSummary, reasonLabel, REASONS,
  saveWorn, wornIds, type WornOutfit,
} from './worn';

const worn = (id: string, worn_on: string, over: Partial<WornOutfit> = {}): WornOutfit => ({
  id, worn_on, recorded_by: 'today', context: null, score: null, reasons: [], warnings: [], rating: null, rating_reasons: [],
  rating_note: null, rated_at: null, created_at: '', gone: [],
  pieces: { base: 't', mid: null, outer: 'j', bottom: 'b', shoes: 's', accessories: ['belt'] }, ...over,
});

class Mem {
  data = new Map<string, string>();
  get length() { return this.data.size; }
  key(i: number) { return [...this.data.keys()][i] ?? null; }
  removeItem(k: string) { this.data.delete(k); }
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
}

describe('worn outfits in plain words', () => {
  it('names a piece archived since as itself, marked archived, and one deleted since as gone', () => {
    const cat = (c: string) => (c === 'jacket' ? 'Jacket' : c);
    expect(pieceName({ name: 'Navy jacket', category: 'jacket', status: 'active' }, false, cat)).toBe('Navy jacket');
    expect(pieceName({ name: 'Navy jacket', category: 'jacket', status: 'archived' }, false, cat)).toBe('Navy jacket (archived)');
    expect(pieceName({ name: null, category: 'jacket', status: 'archived' }, false, cat)).toBe('Jacket (archived)');
    expect(pieceName(undefined, true, cat)).toBe('A piece since deleted');
    expect(pieceName(undefined, false, cat)).toBe('A piece of your closet');
  });

  it('names the answers and reasons', () => {
    expect(['loved', 'fine', 'not_again'].map(ratingLabel)).toEqual(['Loved it', 'Fine', 'Not again']);
    expect(REASONS.map(reasonLabel)).toEqual(['Too warm', 'Too cold', 'Too dressed up', 'Too casual', 'Colours clashed',
      'Uncomfortable', 'Got compliments', 'Other']);
    expect(ratingSummary(worn('a', '2026-11-11'))).toBe('Not rated yet');
    expect(ratingSummary(worn('a', '2026-11-11', { rating: 'not_again', rating_reasons: ['too_cold', 'other'], rating_note: 'itchy' })))
      .toBe('Not again · too cold, itchy');
  });

  it('lists pieces in the order they are put on', () => {
    expect(wornIds(worn('a', '2026-11-11').pieces)).toEqual(['j', 't', 'b', 's', 'belt']);
  });

  it('asks about yesterday first, then today, never older or rated or waved away', () => {
    const list = [worn('t', '2026-11-12'), worn('y', '2026-11-11'), worn('o', '2026-11-09')];
    expect(pendingQuestion(list, [], '2026-11-12')?.id).toBe('y');
    expect(questionFor(list[1], '2026-11-12')).toBe("How was yesterday's outfit?");
    expect(pendingQuestion(list, ['y'], '2026-11-12')?.id).toBe('t');
    expect(questionFor(list[0], '2026-11-12')).toBe("How was today's outfit?");
    expect(pendingQuestion([worn('y', '2026-11-11', { rating: 'fine' }), list[2]], [], '2026-11-12')).toBeNull();
    expect(pendingQuestion(null, [], '2026-11-12')).toBeNull();
  });

  it('remembers what was waved away per closet', () => {
    const kv = new Mem();
    dismiss('demo', 'a', kv);
    expect(loadDismissed('demo', kv)).toEqual(['a']);
    expect(loadDismissed('main', kv)).toEqual([]);
  });
});

describe('the worn list saved for offline', () => {
  it('keeps one copy per closet, and logout forgets it', () => {
    const kv = new Mem();
    saveWorn('demo', { outfits: [worn('d1', '2026-11-12')], next: null }, kv, new Date('2026-11-13T08:00:00Z'));
    expect(loadSavedWorn('demo', kv)?.page.outfits.map((o) => o.id)).toEqual(['d1']);
    expect(loadSavedWorn('demo', kv)?.saved_at).toBe('2026-11-13T08:00:00.000Z');
    expect(loadSavedWorn('main', kv)).toBeNull();
    saveWorn('main', { outfits: [], next: null }, kv);
    expect(loadSavedWorn('main', kv)?.page.outfits).toEqual([]);
    expect(loadSavedWorn('demo', kv)?.page.outfits.map((o) => o.id)).toEqual(['d1']);
    forgetSaved(kv);
    expect(loadSavedWorn('demo', kv)).toBeNull();
    expect(loadSavedWorn('main', kv)).toBeNull();
  });

  it('does not overwrite what Today keeps as worn today', () => {
    const kv = new Mem();
    const today = { day: '2026-11-13', worn_on: '2026-11-13', ids: ['t'], recorded: ['t'] } as unknown as WornToday;
    keptFor('main', kv).setWorn(today);
    saveWorn('main', { outfits: [worn('w1', '2026-11-13')], next: null }, kv);
    expect(keptFor('main', kv).worn('2026-11-13')).toEqual(today);
    expect(loadSavedWorn('main', kv)?.page.outfits.map((o) => o.id)).toEqual(['w1']);
  });

  it('ignores a damaged copy', () => {
    const kv = new Mem();
    kv.setItem('closet-today-saved:worn-list:main', '{not json');
    expect(loadSavedWorn('main', kv)).toBeNull();
    kv.setItem('closet-today-saved:worn-list:main', JSON.stringify({ saved_at: 'x', page: {} }));
    expect(loadSavedWorn('main', kv)).toBeNull();
  });
});
