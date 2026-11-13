import { describe, expect, it } from 'vitest';
import { dismiss, loadDismissed, pendingQuestion, questionFor, ratingLabel, ratingSummary, reasonLabel, REASONS, wornIds, type WornOutfit } from './worn';

const worn = (id: string, worn_on: string, over: Partial<WornOutfit> = {}): WornOutfit => ({
  id, worn_on, recorded_by: 'today', context: null, score: null, reasons: [], warnings: [], rating: null, rating_reasons: [],
  rating_note: null, rated_at: null, created_at: '',
  pieces: { base: 't', mid: null, outer: 'j', bottom: 'b', shoes: 's', accessories: ['belt'] }, ...over,
});

class Mem {
  data = new Map<string, string>();
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string, v: string) { this.data.set(k, v); }
}

describe('worn outfits in plain words', () => {
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
