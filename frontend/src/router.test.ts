import { describe, expect, it, vi } from 'vitest';

// the router listens for the browser's back button as it loads; these tests run without a browser
vi.stubGlobal('window', { addEventListener: () => undefined });
const { startsAtTop } = await import('./router');

describe('where a new page opens', () => {
  it('opens at its top on a phone, the item page included', () => {
    expect(startsAtTop('/', '/item/abc', false)).toBe(true);
    expect(startsAtTop('/today', '/today/item/abc', false)).toBe(true);
    expect(startsAtTop('/', '/settings', false)).toBe(true);
  });

  it('keeps the list in place on a computer when an item opens beside it', () => {
    expect(startsAtTop('/', '/item/abc', true)).toBe(false);
    expect(startsAtTop('/item/abc', '/item/def', true)).toBe(false);
    expect(startsAtTop('/item/abc', '/', true)).toBe(false);
    expect(startsAtTop('/missing', '/missing/item/abc', true)).toBe(false);
  });

  it('opens a different screen at its top on a computer', () => {
    expect(startsAtTop('/item/abc', '/today', true)).toBe(true);
    expect(startsAtTop('/missing', '/missing/check', true)).toBe(true);
  });
});
