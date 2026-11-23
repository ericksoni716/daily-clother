import { describe, expect, it } from 'vitest';
import { checkBody, kindWho, notReadyText, progressText, reviewChanges, reviewRows, skippedText, sureText, typedOf } from './review';
import type { ReviewField } from './types';

const FIELDS: ReviewField[] = [
  { field: 'color', value: 'grey', confidence: 0.55, allowed: ['black', 'grey', 'tan'] },
  { field: 'silhouette', value: { sleeve: 'long', neck: 'turtle' }, confidence: 0.6,
    allowed: { sleeve: ['none', 'short', 'long'], neck: ['crew', 'v', 'turtle'] } },
];

describe('review wording', () => {
  it('says where you are', () => {
    expect(progressText(4, 23)).toBe('4 of 23');
  });

  it('says how sure Claude was, as a whole percentage', () => {
    expect(sureText(0.55)).toBe('Claude was 55% sure');
    expect(sureText(0.666)).toBe('Claude was 67% sure');
    expect(sureText(1.2)).toBe('Claude was 100% sure');
  });

  it('says why items are not in the queue, or nothing', () => {
    expect(notReadyText(0, 0)).toBe('');
    expect(notReadyText(1, 0)).toBe('1 item is still waiting to be described.');
    expect(notReadyText(3, 1)).toBe("3 items are still waiting to be described. 1 item couldn't be described.");
    expect(notReadyText(0, 2)).toBe("2 items couldn't be described.");
  });

  it('says what happens to skipped items', () => {
    expect(skippedText(1)).toBe('You skipped 1 item. It stays in the queue for next time.');
    expect(skippedText(3)).toBe('You skipped 3 items. They stay in the queue for next time.');
  });
});

describe('review choices', () => {
  it("puts Claude's value first and gives the silhouette one row per part", () => {
    const rows = reviewRows(FIELDS);
    expect(rows.map((r) => [r.key, r.part, r.options])).toEqual([
      ['color', null, ['grey', 'black', 'tan']],
      ['silhouette.sleeve', 'sleeve', ['long', 'none', 'short']],
      ['silhouette.neck', 'neck', ['turtle', 'crew', 'v']],
    ]);
    expect(rows[2].confidence).toBe(0.6);
  });

  it('confirms what was left alone and saves what was changed', () => {
    const rows = reviewRows(FIELDS);
    expect(reviewChanges(rows, {})).toEqual({ changes: {}, confirm: ['color', 'silhouette'] });
    expect(reviewChanges(rows, { color: 'grey' })).toEqual({ changes: {}, confirm: ['color', 'silhouette'] });
    expect(reviewChanges(rows, { color: 'tan' })).toEqual({ changes: { color: 'tan', color_hex: '#c9a97c' }, confirm: ['silhouette'] });
    expect(reviewChanges(rows, { 'silhouette.neck': 'crew' })).toEqual({ changes: { silhouette: { neck: 'crew' } }, confirm: ['color'] });
  });
});

describe('checking a new item', () => {
  const item = { name: 'Navy polo', brand: null, price_cents: null, kind: 'polo' };
  const typed = { name: 'Navy polo', brand: '', price: '' };

  it("says who said what it is", () => {
    expect(kindWho({ kind: 'polo', kind_by: 'owner', kind_confidence: null })).toBe('Set by you');
    expect(kindWho({ kind: 'polo', kind_by: 'claude', kind_confidence: 0.8 })).toBe("Claude's guess · Claude was 80% sure");
    expect(kindWho({ kind: 'polo', kind_by: 'claude', kind_confidence: null })).toBe("Claude's guess");
    expect(kindWho({ kind: null, kind_by: null, kind_confidence: null })).toBe('Kind not said yet');
  });

  it('starts the boxes from what the item has', () => {
    expect(typedOf({ name: null, brand: 'Made-up Mills', price_cents: 4550 })).toEqual({ name: '', brand: 'Made-up Mills', price: '45.50' });
  });

  it("with nothing changed, makes Claude's kind your word and changes nothing else", () => {
    expect(checkBody(item, typed, null, [], {})).toEqual({ body: { kind: 'polo', changes: {}, fields: [] } });
  });

  it('sends the name, brand and price you changed, and the kind you chose', () => {
    const got = checkBody(item, { name: '  Weekend polo ', brand: 'Made-up Mills', price: '$42.50' }, 'henley', [], {});
    expect(got).toEqual({ body: { kind: 'henley', changes: { name: 'Weekend polo', brand: 'Made-up Mills', price_cents: 4250 }, fields: [] } });
  });

  it('clears a name or a price you emptied, and sends no kind when there is none', () => {
    const got = checkBody({ ...item, kind: null, price_cents: 1000 }, { name: ' ', brand: '', price: '' }, null, [], {});
    expect(got).toEqual({ body: { changes: { name: null, price_cents: null }, fields: [] } });
  });

  it('takes the doubtful fields along: changed ones as changes, the rest to confirm', () => {
    const rows = reviewRows(FIELDS);
    const got = checkBody(item, typed, null, rows, { color: 'black' });
    expect(got).toEqual({ body: { kind: 'polo', changes: { color: 'black', color_hex: expect.anything() }, fields: ['silhouette'] } });
  });

  it('sends nothing and says so when the price is not a price', () => {
    expect(checkBody(item, { ...typed, price: 'about forty' }, null, [], {})).toEqual({ error: 'Type the price as a number, like 45 or 45.50.' });
  });

  it('reads a price written with a decimal comma as the same price, not a hundred times more', () => {
    const sent = checkBody(item, { ...typed, price: '45,50' }, null, [], {});
    expect('body' in sent && sent.body.changes.price_cents).toBe(4550);
  });
});
