import { describe, expect, it, vi } from 'vitest';

// the router listens for the browser's back button as it loads; these tests run without a browser
vi.stubGlobal('window', { addEventListener: () => undefined });
const { arrivalScroll, backGoesTo, entryOf, pushedEntry, readPositions, replacedEntry, startsAtTop, writePositions } = await import('./router');

describe('the app\'s own history entries', () => {
  it('counts each push from the page the app was opened on, and remembers the address before', () => {
    const first = replacedEntry(null);
    expect(first.idx).toBe(0);
    expect(first.from).toBeNull();
    const second = pushedEntry(first, '/?kind=shirts');
    expect(second).toMatchObject({ idx: 1, from: '/?kind=shirts' });
    expect(second.key).not.toBe(first.key);
    expect(pushedEntry(second, '/item/abc').idx).toBe(2);
  });

  it('keeps an entry\'s place and name when its address is replaced', () => {
    const e = { idx: 3, key: 'k', from: '/' };
    expect(replacedEntry(e)).toEqual(e);
  });

  it('reads only what the app wrote', () => {
    expect(entryOf(null)).toBeNull();
    expect(entryOf({ usr: 1 })).toBeNull();
    expect(entryOf({ idx: 2, key: 'k' })).toEqual({ idx: 2, key: 'k', from: null });
  });
});

describe('a back link', () => {
  it('goes Back when the page before is the one it names', () => {
    expect(backGoesTo({ idx: 1, key: 'k', from: '/' }, '/')).toBe(true);
    // the closet with a filter in its address is still the closet
    expect(backGoesTo({ idx: 4, key: 'k', from: '/?kind=shirts' }, '/')).toBe(true);
    expect(backGoesTo({ idx: 2, key: 'k', from: '/trips' }, '/trips')).toBe(true);
  });

  it('takes the page\'s place when it was opened straight from its address', () => {
    expect(backGoesTo(null, '/')).toBe(false);
    expect(backGoesTo({ idx: 0, key: 'k', from: null }, '/')).toBe(false);
  });

  it('does not go Back to a different page than it names', () => {
    expect(backGoesTo({ idx: 1, key: 'k', from: '/insights' }, '/')).toBe(false);
    expect(backGoesTo({ idx: 2, key: 'k', from: '/today/item/abc' }, '/today')).toBe(false);
  });
});

describe('where a page is scrolled on arriving', () => {
  it('starts a new page at its top on a phone', () => {
    expect(arrivalScroll('push', '/', '/item/abc', 900, false)).toBe(0);
  });

  it('returns to where the entry was left on Back or Forward, or the top if unknown', () => {
    expect(arrivalScroll('pop', '/item/abc', '/', 2717, false)).toBe(2717);
    expect(arrivalScroll('pop', '/item/abc', '/', undefined, false)).toBe(0);
  });

  it('keeps the list in place on a computer while the side panel changes, Back included', () => {
    expect(arrivalScroll('push', '/', '/item/abc', undefined, true)).toBeNull();
    expect(arrivalScroll('pop', '/item/abc', '/', 300, true)).toBeNull();
    expect(arrivalScroll('pop', '/settings', '/', 300, true)).toBe(300);
  });

  it('stays put when a replace tidies the address, and goes to the top when it leaves the page', () => {
    expect(arrivalScroll('replace', '/today', '/today?ask=1', 400, false)).toBeNull();
    expect(arrivalScroll('replace', '/item/abc', '/', 400, false)).toBe(0);
  });
});

describe('the saved scroll positions', () => {
  it('survive being written and read back, keeping the most recent sixty', () => {
    const many = new Map(Array.from({ length: 70 }, (_, i) => [`k${i}`, i * 10] as [string, number]));
    const back = readPositions(writePositions(many));
    expect(back.size).toBe(60);
    expect(back.get('k69')).toBe(690);
    expect(back.has('k0')).toBe(false);
  });

  it('start fresh from nothing or a damaged copy', () => {
    expect(readPositions(null).size).toBe(0);
    expect(readPositions('{not json').size).toBe(0);
    expect([...readPositions('[["a",1],["b","x"],7]')]).toEqual([['a', 1]]);
  });
});

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
    expect(startsAtTop('/wardrobe', '/wardrobe/item/abc', true)).toBe(false);
  });

  it('opens a different screen at its top on a computer', () => {
    expect(startsAtTop('/item/abc', '/today', true)).toBe(true);
    expect(startsAtTop('/wardrobe', '/wardrobe/check', true)).toBe(true);
    expect(startsAtTop('/wardrobe', '/wardrobe/wishlist', true)).toBe(true);
    expect(startsAtTop('/wardrobe/wishlist', '/wardrobe/wish/w1', true)).toBe(true);
  });
});
