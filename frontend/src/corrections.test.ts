import { describe, expect, it } from 'vitest';
import { changeLine, confirmedChanges, detailSummary, historyLine, partPhrase, shownParts, stillFor, svgSource, type HistoryEntry, type HistoryPart } from './corrections';

const entry = (over: Partial<HistoryEntry>): HistoryEntry => ({
  id: 1, at: '2026-11-13T09:41:00Z', by: 'owner', kind: 'detail', sentence: null, undoes: null, undone: false,
  can_undo: true, why_not: null, first_description: false, parts: [], ...over,
});

const part = (over: Partial<HistoryPart>): HistoryPart => ({
  target: 'detail', name: 'placket', title: 'front', before: 'front_placket', after: 'half_placket_popover',
  before_words: 'buttons', after_words: 'a half placket', ...over,
});

const buttons = part({ name: 'placket_buttons', title: 'number of buttons', before: 3, after: 2, before_words: '3', after_words: '2' });

describe('the names of details', () => {
  it('reads as a label with its value', () => {
    expect(detailSummary({ title: 'number of buttons', words: 'none' })).toBe('Number of buttons: none');
    expect(detailSummary({ title: 'V insert under the neck', words: 'yes' })).toBe('V insert under the neck: yes');
  });

  it('shows a change to confirm with its value before and after', () => {
    expect(changeLine({ name: 'trim_color', title: 'trim colour', value: 'white', before: 'same',
      before_words: 'same as the body', after_words: 'white' })).toBe('Trim colour: same as the body → white');
  });

  it('turns a drawing into an image address', () => {
    expect(svgSource('<svg a="1"/>')).toBe('data:image/svg+xml;charset=utf-8,%3Csvg%20a%3D%221%22%2F%3E');
  });
});

describe('history lines', () => {
  it('says what the owner changed by picking', () => {
    expect(historyLine(entry({ parts: [part({})] }))).toBe('You changed the front from buttons to a half placket');
    expect(historyLine(entry({ parts: [part({}), buttons] })))
      .toBe('You changed the front from buttons to a half placket and changed the number of buttons from 3 to 2');
  });

  it('says a feature was added or removed', () => {
    const insert = part({ name: 'v_insert', title: 'V insert under the neck', before: 'no', after: 'yes', before_words: 'no', after_words: 'yes' });
    expect(historyLine(entry({ parts: [insert] }))).toBe('You added the V insert under the neck');
    expect(partPhrase({ ...insert, before: 'yes', after: 'no' })).toBe('removed the V insert under the neck');
  });

  it('says a value the owner confirmed as theirs', () => {
    expect(historyLine(entry({ parts: [part({ before: 'polo', after: 'polo', before_words: 'a polo placket', after_words: 'a polo placket' })] })))
      .toBe('You set the front to a polo placket');
  });

  it('leaves out the colour shade when the colour is named', () => {
    const colour = part({ target: 'field', name: 'color', title: 'colour', before: 'navy', after: 'green', before_words: 'navy', after_words: 'green' });
    const shade = part({ target: 'field', name: 'color_hex', title: 'colour shade', before: '#27344f', after: '#3f7d4f', before_words: '#27344f', after_words: '#3f7d4f' });
    expect(shownParts([colour, shade])).toEqual([colour]);
    expect(historyLine(entry({ kind: 'field', parts: [colour, shade] }))).toBe('You changed the colour from navy to green');
  });

  it('quotes a correction by sentence', () => {
    expect(historyLine(entry({ kind: 'sentence', sentence: 'it has two buttons', parts: [buttons] })))
      .toBe('You wrote “it has two buttons” and changed the number of buttons from 3 to 2');
  });

  it('says what an undo put back', () => {
    expect(historyLine(entry({ kind: 'undo', undoes: 3, parts: [{ ...buttons, before: 2, after: 3, before_words: '2', after_words: '3' }] })))
      .toBe('You put the number of buttons back to 3');
    expect(historyLine(entry({ kind: 'undo', parts: [part({ target: 'answer', name: 'answer', title: 'description' })] })))
      .toBe("You put back Claude's earlier description");
  });

  it("says when Claude's description arrived", () => {
    expect(historyLine(entry({ kind: 'answer', by: 'claude', first_description: true, parts: [] }))).toBe('Claude described it');
    expect(historyLine(entry({ kind: 'answer', by: 'claude', parts: [] }))).toBe('Claude described it again, with no changes');
    const category = part({ target: 'field', name: 'category', title: 'kind of garment', before: 'polo', after: 'tee', before_words: 'polo', after_words: 'tee' });
    expect(historyLine(entry({ kind: 'answer', by: 'claude', parts: [category, part({ target: 'answer', name: 'answer' })] })))
      .toBe('Claude described it again and changed the kind of garment from polo to tee');
  });

  it('says a chosen kind without the category that follows from it', () => {
    const category = part({ target: 'field', name: 'category', title: 'kind of garment', before_words: 'hoodie', after_words: 'sweater' });
    const kind = part({ target: 'detail', name: 'garment', title: 'kind', before_words: 'not said', after_words: 'fleece pullover' });
    expect(historyLine(entry({ parts: [category, kind] }))).toBe('You changed the kind from not said to fleece pullover');
    expect(historyLine(entry({ kind: 'undo', parts: [{ ...category, after_words: 'hoodie' }, { ...kind, after_words: 'not said' }] })))
      .toBe('You put the kind back to not said');
  });
});

describe('confirming what Claude understood', () => {
  const change = { name: 'placket_buttons', title: 'number of buttons', value: 2, before: 3, before_words: '3', after_words: '2' };

  it('is offered only while the item is as it was when Claude read the sentence', () => {
    const answer = { state: 'understood' as const, changes: [change], sentence: 'it has two buttons' };
    expect(stillFor(answer, 'a', 'a')).toBe(answer);
    expect(stillFor(answer, 'a', 'b')).toBeNull();
    expect(stillFor(null, 'a', 'a')).toBeNull();
  });

  it('sends each change with the value it replaces', () => {
    expect(confirmedChanges([change])).toEqual([{ name: 'placket_buttons', value: 2, before: 3 }]);
  });
});

describe('a field confirmed as the owner’s', () => {
  it('says it was confirmed, not changed', () => {
    const same = part({ target: 'field', name: 'color', title: 'colour', before: 'navy', after: 'navy', before_words: 'navy', after_words: 'navy', same: true });
    expect(historyLine(entry({ kind: 'field', parts: [same] }))).toBe('You confirmed the colour as navy');
  });
});
