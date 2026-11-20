import { createElement as h, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

// These tests run without a browser: there is no screen size to ask, so a list is drawn as on a wider screen, and the
// router is loaded with a window that only listens.
vi.stubGlobal('window', { addEventListener: () => undefined });
const { Fold } = await import('./Fold');
const { HowItWorks } = await import('./HowItWorks');
const { SAVE_WORDS, SaveStatus } = await import('./SaveStatus');
const { seeAllWords, ShowMore } = await import('./ShowMore');

const draw = (node: ReactNode) => renderToStaticMarkup(node);
const NINE = Array.from({ length: 9 }, (_, i) => `piece ${i + 1}`);

describe('Fold', () => {
  it('is closed by default, with its title as the line to tap', () => {
    const html = draw(h(Fold, { title: 'More numbers', testId: 'more-numbers', children: h('p', null, 'the charts') }));
    expect(html).toMatch(/^<details class="more fold" data-testid="more-numbers"><summary>More numbers<\/summary>/);
    expect(html).not.toContain(' open');
    expect(html).toContain('<p>the charts</p>');
  });

  it('can start open', () => {
    expect(draw(h(Fold, { title: 'Hidden', open: true, children: 'x' }))).toContain('<details class="more fold" open=""');
  });

  it('draws nothing inside until it is opened when it is lazy', () => {
    const html = draw(h(Fold, { title: 'More numbers', lazy: true, children: h('p', null, 'the charts') }));
    expect(html).toContain('<summary>More numbers</summary>');
    expect(html).not.toContain('the charts');
  });
});

describe('HowItWorks', () => {
  it('is one quiet closed line that opens the explanation', () => {
    const html = draw(h(HowItWorks, { children: 'Tap a piece to see it.' }));
    expect(html).toMatch(/^<details class="how">/);
    expect(html).not.toContain(' open');
    expect(html).toContain('How this works</summary>');
    expect(html).toContain('<div class="how-body">Tap a piece to see it.</div>');
  });

  it('takes a title of its own', () => {
    expect(draw(h(HowItWorks, { title: 'How to change an outfit', children: 'x' }))).toContain('How to change an outfit</summary>');
  });
});

describe('ShowMore', () => {
  const list = (props: Record<string, unknown>) => draw(h(ShowMore<string>, {
    items: NINE, first: 3, keyOf: (s: string) => s, render: (s: string) => s, label: 'Pieces', ...props,
  }));

  it('shows every item on a wider screen unless told how many', () => {
    const html = list({});
    expect((html.match(/<li>/g) ?? []).length).toBe(9);
    expect(html).not.toContain('See all');
  });

  it('cuts a wider screen to its own number, with "See all N" after', () => {
    const html = list({ wide: 3 });
    expect((html.match(/<li>/g) ?? []).length).toBe(3);
    expect(html).toContain('piece 3');
    expect(html).not.toContain('piece 4');
    expect(html).toContain('>See all 9</button>');
  });

  it('goes to the page with the whole list when it has one', () => {
    const html = list({ wide: 3, to: '/today/worn', total: null });
    expect(html).toContain('href="/today/worn"');
    expect(html).toContain('>See all</a>');
  });

  it('says nothing more when everything already shows', () => {
    expect(list({ wide: 12 })).not.toContain('See all');
  });

  it('counts what is there to see', () => {
    expect(seeAllWords(9)).toBe('See all 9');
    expect(seeAllWords(null)).toBe('See all');
  });
});

describe('SaveStatus', () => {
  it('keeps its place and says nothing while nothing is being saved', () => {
    expect(draw(h(SaveStatus, { state: 'idle' }))).toBe('<span class="save-status" role="status"></span>');
  });

  it('says it is saving, then saved', () => {
    expect(draw(h(SaveStatus, { state: 'saving' }))).toContain('>Saving…</span>');
    expect(draw(h(SaveStatus, { state: 'saved' }))).toContain('>Saved</span>');
  });

  it('says it did not save, with Try again', () => {
    const html = draw(h(SaveStatus, { state: 'failed', onRetry: () => undefined }));
    expect(html).toContain('is-failed');
    expect(html).toContain("Didn&#x27;t save · <button");
    expect(html).toContain('>Try again</button>');
  });

  it('words its lines in the app\'s voice: no exclamation marks', () => {
    for (const words of Object.values(SAVE_WORDS)) expect(words).not.toContain('!');
  });
});
