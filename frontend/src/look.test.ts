import { describe, expect, it } from 'vitest';
import { fixLabel, lastFoldTitle, lookLine, lookWords, notesPatch, notesText } from './look';

const shirt: Parameters<typeof lookLine>[0] = {
  kind_name: 'Oxford shirt', category: 'shirt', color: 'light_blue', pattern: 'solid', shade: 'oxford_blue',
  as_worn: [
    { part: 'fit', value: 'regular', field: 'fit_detail' },
    { part: 'sleeve', value: 'long', field: 'sleeve_length' },
  ],
};

describe('the summary line under the name', () => {
  it('says what it is, its colour and how it sits, in one line', () => {
    expect(lookWords(lookLine(shirt))).toBe('Oxford shirt · Light blue (oxford blue) · Regular fit · Long sleeves');
  });

  it('lets each word of how it sits open the detail that corrects it, and nothing else', () => {
    expect(lookLine(shirt).map((p) => p.field)).toEqual([undefined, undefined, 'fit_detail', 'sleeve_length']);
  });

  it('says the pattern beside the colour when there is one', () => {
    expect(lookWords(lookLine({ ...shirt, pattern: 'plaid', shade: null, as_worn: [] }))).toBe('Oxford shirt · Light blue, plaid');
  });

  it('falls back to the category, and says only what the closet summary knows while the item is read', () => {
    expect(lookWords(lookLine({ kind_name: null, category: 'tee', color: 'navy', pattern: null }))).toBe('T-shirt · Navy');
    expect(lookLine({ kind_name: null, category: null, color: null, pattern: null })).toEqual([]);
  });

  it('leaves out a word of how it sits that has no words', () => {
    expect(lookWords(lookLine({ ...shirt, as_worn: [{ part: 'fit', value: 'made_up' as 'regular', field: 'fit_detail' }] })))
      .toBe('Oxford shirt · Light blue (oxford blue)');
  });
});

describe('the one notes box', () => {
  const none = { wear_notes: null, fit_notes: null, notes: null, rating_reason: null };

  it('shows every note kept about the item, each once', () => {
    expect(notesText({ wear_notes: 'With the navy blazer', fit_notes: 'Runs small', notes: null, rating_reason: 'Warm' }))
      .toBe('With the navy blazer\nRuns small\nWarm');
    expect(notesText({ ...none, notes: 'Warm', rating_reason: ' Warm ' })).toBe('Warm');
    expect(notesText(none)).toBe('');
  });

  it('changes nothing until the text changes', () => {
    const item = { ...none, fit_notes: 'Runs small', notes: 'From the market' };
    expect(notesPatch('Runs small\nFrom the market', item)).toBeNull();
    expect(notesPatch('  Runs small\nFrom the market ', item)).toBeNull();
  });

  it('keeps the whole text in wear_notes and empties the older boxes in the same save, so nothing is lost or kept twice', () => {
    const item = { ...none, wear_notes: 'With chinos', fit_notes: 'Runs small', rating_reason: 'Soft' };
    expect(notesPatch('With chinos\nRuns small\nSoft\nDry flat', item))
      .toEqual({ wear_notes: 'With chinos\nRuns small\nSoft\nDry flat', fit_notes: null, rating_reason: null });
  });

  it('empties every box when the text is cleared', () => {
    expect(notesPatch('', { ...none, wear_notes: 'a', notes: 'b' })).toEqual({ wear_notes: null, notes: null });
  });
});

describe('the words around the page', () => {
  it('names the last fold by what is in it', () => {
    expect(lastFoldTitle(false, true)).toBe('Describe it again, archive or delete');
    expect(lastFoldTitle(false, false)).toBe('Archive or delete');
    expect(lastFoldTitle(true, true)).toBe('Put it back or delete it');
  });

  it('offers Claude where Claude can be told, and the details one by one in the demo', () => {
    expect(fixLabel(false)).toBe('Something wrong? Tell Claude');
    expect(fixLabel(true)).toBe('Something wrong? Change the details');
  });
});
