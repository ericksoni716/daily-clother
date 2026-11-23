import { describe, expect, it } from 'vitest';
import { forgetSaved, keptFor, type WornToday } from './today';
import {
  contextWords, dismiss, joinPages, loadDismissed, loadSavedWorn, pendingQuestion, pieceName, questionFor, ratingLabel, ratingSummary, reasonLabel,
  reasonsFor, REASONS, recordGroups, saveWorn, withOutfit, withoutOutfit, withRecorded, wornIds, type WornOutfit,
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
    expect(pendingQuestion(list, ['y'], '2026-11-12', 20)?.id).toBe('t');
    // today's own outfit is asked about in the evening, not the moment it is put on
    expect(pendingQuestion(list, ['y'], '2026-11-12', 9)).toBeNull();
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
  it('keeps one copy per closet, and forgetting the saved copies forgets it', () => {
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

describe('pages of worn outfits changed by a save', () => {
  const page = (...outfits: WornOutfit[]) => ({ outfits, next: null });

  it('joins the pages in order, each outfit once where a page read again overlaps the next', () => {
    const [a, b, c] = [worn('a', '2026-11-20'), worn('b', '2026-11-19'), worn('c', '2026-11-18')];
    expect(joinPages([page(a, b), page(b, c), undefined]).map((o) => o.id)).toEqual(['a', 'b', 'c']);
    expect(joinPages([])).toEqual([]);
  });

  it('puts a rated outfit in its place and takes a removed one out, leaving a page without it as it was', () => {
    const p = page(worn('a', '2026-11-20'), worn('b', '2026-11-19'));
    const rated = worn('b', '2026-11-19', { rating: 'loved' });
    expect(withOutfit(p, rated).outfits.map((o) => o.rating)).toEqual([null, 'loved']);
    expect(withOutfit(p, worn('z', '2026-11-01'))).toBe(p);
    expect(withoutOutfit(p, 'a').outfits.map((o) => o.id)).toEqual(['b']);
    expect(withoutOutfit(p, 'z')).toBe(p);
  });

  it('puts an outfit recorded by hand by its day, newest first, before others of the same day', () => {
    const p = page(worn('a', '2026-11-20'), worn('b', '2026-11-18'));
    expect(withRecorded(p, worn('n', '2026-11-19')).outfits.map((o) => o.id)).toEqual(['a', 'n', 'b']);
    expect(withRecorded(p, worn('n', '2026-11-20')).outfits.map((o) => o.id)).toEqual(['n', 'a', 'b']);
    expect(withRecorded(p, worn('n', '2026-11-01')).outfits.map((o) => o.id)).toEqual(['a', 'b', 'n']);
  });
});

describe('the reasons offered after a rating', () => {
  it('follows the rating: no "too cold" after "loved it", no compliments after "not again"', () => {
    expect(reasonsFor('loved')).toEqual(['compliments', 'other']);
    expect(reasonsFor('not_again')).not.toContain('compliments');
    expect(reasonsFor('not_again')).toContain('too_cold');
    expect(reasonsFor('fine')).toEqual([...REASONS]);
  });
});

describe('the day an outfit was worn for', () => {
  it('writes the temperatures as Today does', () => {
    expect(contextWords({ low_c: 9.2, high_c: 15.7, rain: true, occasion: 'casual', mood: null }, (v) => v)).toBe('9–16°C · rain · casual');
  });
});

describe('the pieces to record an outfit from', () => {
  const item = (id: string, category: string | null, last_worn: string | null, over = {}) =>
    ({ id, name: id, category, color: null, status: 'active', last_worn, ...over });
  const items = [
    item('old tee', 'tee', '2026-10-01'), item('new tee', 'tee', '2026-11-20'), item('never worn shirt', 'shirt', null),
    item('jeans', 'jeans', '2026-11-01'), item('boots', 'boots', null), item('belt', 'belt', '2026-11-02'),
    item('coat', 'coat', null), item('gone', 'tee', '2026-11-22', { status: 'archived' }), item('unsorted', null, null),
  ];
  const words = (i: { name: string | null }) => i.name ?? '';

  it('groups them as tops, bottoms, shoes and extras, most recently worn first, leaving out archived and unsorted ones', () => {
    expect(recordGroups(items, '', words).map((g) => [g.label, g.pieces.map((p) => p.id)])).toEqual([
      ['Tops', ['new tee', 'old tee', 'coat', 'never worn shirt']],
      ['Bottoms', ['jeans']],
      ['Shoes', ['boots']],
      ['Extras', ['belt']],
    ]);
  });

  it('keeps those with every word looked for, and drops the groups left empty', () => {
    expect(recordGroups(items, 'TEE new', words)).toEqual([{ group: 'tops', label: 'Tops', pieces: [items[1]] }]);
    expect(recordGroups(items, 'nothing like it', words)).toEqual([]);
  });
});
