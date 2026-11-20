import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LookLine, NotesBox } from './ItemAbout';

/** The item page's own pieces, drawn as the page draws them (the page as a whole needs the server; these do not). */
const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);

const polo = {
  kind_name: 'Polo shirt', category: 'polo', color: 'navy', pattern: 'solid', shade: null,
  as_worn: [{ part: 'fit' as const, value: 'slim', field: 'fit_detail' }, { part: 'sleeve' as const, value: 'short', field: 'sleeve_length' }],
};

describe('the summary line on the item page', () => {
  it('is one line, with a button for each word of how it sits', () => {
    const out = html(createElement(LookLine, { item: polo, disabled: false, onPick: () => {} }));
    expect(out.replace(/<[^>]+>/g, '')).toBe('Polo shirt · Navy · Slim fit · Short sleeves');   // read as one line
    expect(out.match(/<button/g)).toHaveLength(2);
    expect(out).toContain('title="Fix the slim fit in the details"');
  });

  it('has no buttons while the item is read, and keeps its place when there is nothing to say yet', () => {
    const out = html(createElement(LookLine, { item: { kind_name: null, category: 'polo', color: 'navy', pattern: null }, disabled: true }));
    expect(out).not.toContain('<button');
    expect(out).toContain('Polo');
    expect(html(createElement(LookLine, { item: { kind_name: null, category: null, color: null, pattern: null }, disabled: true })))
      .toBe('<p class="detail-look" data-testid="look-line"></p>');
  });
});

describe('the one notes box on the item page', () => {
  it('shows every note kept about the item in one box, with one line under it', () => {
    const out = html(createElement(NotesBox, {
      item: { wear_notes: 'With chinos', fit_notes: 'Runs small', notes: null, rating_reason: 'Soft' },
      disabled: false, onSave: () => {},
    }));
    expect(out.match(/<textarea/g)).toHaveLength(1);
    expect(out).toContain('Notes for you and Claude');
    expect(out).toContain('>With chinos\nRuns small\nSoft</textarea>');
    expect(out).toContain('Claude reads these when it chooses your outfits.');
  });
});
