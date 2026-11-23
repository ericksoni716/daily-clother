import { createElement as h, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

// These tests run without a browser: there is no screen size to ask, so a list is drawn as on a wider screen, and the
// router is loaded with a window that only listens.
vi.stubGlobal('window', { addEventListener: () => undefined });
const { Fold } = await import('./Fold');
const { Failed, FAILED, failedReason } = await import('./Failed');
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

describe('Failed', () => {
  const fault = Object.assign(new Error('Something went wrong on the computer running Nines. Try again in a moment.'), { status: 500 });
  const away = Object.assign(new Error("Can't reach Nines."), { status: 0 });
  const read = (over: Record<string, unknown>) => ({ error: null, refetch: () => undefined, ...over });

  it('says why in plain words: out of reach, a fault, or the sentence Nines answered with', () => {
    expect(failedReason(away)).toBe(FAILED.unreachable);
    expect(failedReason(fault)).toBe(FAILED.fault);
    expect(failedReason(Object.assign(new Error('That trip is no longer in your closet.'), { status: 404 }))).toBe('That trip is no longer in your closet.');
    // a status text that got through is never shown, nor an answer the page could not read
    expect(failedReason(Object.assign(new Error('Not Found'), { status: 404 }))).toBe(FAILED.fault);
    expect(failedReason(new TypeError('x.map is not a function'))).toBe(FAILED.unreadable);
  });

  it('draws nothing while the read has not failed', () => {
    expect(draw(h(Failed, { query: read({}), what: 'your closet' }))).toBe('');
  });

  it('with nothing read before: says what could not be loaded and why, with Try again, and no status code', () => {
    const html = draw(h(Failed, { query: read({ error: fault }), what: 'your closet' }));
    expect(html).toContain('role="alert"');
    expect(html).toContain('Couldn&#x27;t load your closet.');
    expect(html).toContain('answered with a fault');
    expect(html).toContain('>Try again</button>');
    expect(html).not.toMatch(/500|Internal Server Error/);
  });

  it('with an earlier answer: the line above it says it is from earlier; offline, the banner says it instead', () => {
    const html = draw(h(Failed, { query: read({ error: fault, data: [] }), what: 'your closet' }));
    expect(html).toContain('This is your closet as it was earlier. Nines on your computer answered with a fault.');
    expect(html).toContain('>Try again</button>');
    expect(draw(h(Failed, { query: read({ error: away, data: [] }), what: 'your closet' }))).toBe('');
  });

  it('says it is trying again while it does', () => {
    expect(draw(h(Failed, { query: read({ error: fault, isFetching: true }), what: 'this trip' }))).toContain('Trying again…');
  });
});
