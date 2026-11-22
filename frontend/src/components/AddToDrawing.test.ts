import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Additions, Item } from '../types';
import { ADD_MAX, AddToDrawing } from './AddToDrawing';

/** "Add to the drawing" in Fix the details, drawn as the sheet draws it, in each of its states. */
const idle: Additions = {
  state: 'idle', note: null, message: null, parts: [], notes: [], said: null, at: null, took: null,
  can_go_back: false, back_newer: false, can_remove: false, moved: null,
};
const html = (additions: Additions | null, disabled = false) => renderToStaticMarkup(createElement(AddToDrawing, {
  item: { id: 'i1', additions } as unknown as Item, disabled, onSaved: () => {}, onError: () => {},
}));
const text = (out: string) => out.replace(/<[^>]+>/g, ' ').replace(/&#x27;/g, "'").replace(/\s+/g, ' ');

describe('adding to the drawing', () => {
  it('is a line for what no detail shows, sent with Draw it on, and says what it does first', () => {
    const out = html(idle);
    expect(text(out)).toContain('For what no detail shows: a patch, a panel, a tab, a line of stitching.');
    expect(out).toContain(`maxLength="${ADD_MAX}"`);
    expect(out).toContain('placeholder="e.g. a small red patch on the left sleeve"');
    expect(text(out)).toContain('Draw it on');
    expect(out).not.toContain('Go back to the drawing before');
    expect(out).not.toContain('data-testid="added-parts"');
  });

  it('is not offered for a shoe', () => {
    expect(html(null)).toBe('');
  });

  it('says what Claude added, what it took, and offers the way back and taking it off', () => {
    const out = text(html({
      ...idle, parts: ['red patch on the right sleeve', 'yellow tab'], said: 'Drew a red patch.',
      took: 'Drawn in 42 s on your Claude plan.', can_go_back: true, can_remove: true,
      moved: 'The drawing under what Claude added has changed since.',
    }));
    expect(out).toContain('Added by Claude: red patch on the right sleeve, yellow tab.');
    expect(out).toContain('Drew a red patch.');
    expect(out).toContain('Drawn in 42 s on your Claude plan.');
    expect(out).toContain('The drawing under what Claude added has changed since.');
    expect(out).toContain('Go back to the drawing before');
    expect(out).toContain("Take Claude's additions off");
  });

  it('goes to the newer drawing once the owner went back', () => {
    expect(text(html({ ...idle, can_go_back: true, back_newer: true }))).toContain('Go to the newer drawing');
  });

  it('while Claude draws, says so and takes nothing else', () => {
    const out = html({ ...idle, state: 'drawing', note: 'a patch', message: 'Claude is drawing it on: “a patch”.',
      parts: ['tab'], can_go_back: false, can_remove: false });
    expect(text(out)).toContain('Claude is drawing it on: “a patch”.');
    expect(out).toMatch(/<input[^>]* disabled=""/);
    expect(out).not.toContain('Go back to the drawing before');
  });

  it('when it could not be drawn, says why and offers to send the line again', () => {
    const out = text(html({ ...idle, state: 'failed', note: 'a patch', message: "Claude can't be reached right now." }));
    expect(out).toContain("Claude can't be reached right now.");
    expect(out).toContain('Send “a patch” again');
  });

  it("shows Claude's answer when it drew nothing", () => {
    const out = text(html({ ...idle, state: 'said', note: 'rounder collar', message: 'The collar is changed in Fix the details.' }));
    expect(out).toContain('The collar is changed in Fix the details.');
    expect(out).not.toContain('Send “');
  });
});
