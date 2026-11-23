import { describe, expect, it, vi } from 'vitest';
import { movedTo, placeOf } from './places';

// the router listens for the browser's back button as it loads; these tests run without a browser
vi.stubGlobal('window', { addEventListener: () => undefined });
const { parseRoute } = await import('./router');

describe('the place each address belongs to', () => {
  it.each([
    ['/', 'closet'],
    ['/archived', 'closet'],
    ['/item/abc', 'closet'],
    ['/archived/item/abc', 'closet'],
    ['/review', 'closet'],
    ['/today', 'today'],
    ['/today/item/abc', 'today'],
    ['/today/worn', 'today'],
    ['/trips', 'today'],
    ['/trips/new', 'today'],
    ['/trips/t1', 'today'],
    ['/wardrobe', 'wardrobe'],
    ['/wardrobe/item/abc', 'wardrobe'],
    ['/wardrobe/check', 'wardrobe'],
    ['/wardrobe/check/wish/w1', 'wardrobe'],
    ['/wardrobe/wish/w1', 'wardrobe'],
    ['/wardrobe/link', 'wardrobe'],
    ['/wardrobe/wishlist', 'wardrobe'],
    ['/add', 'add'],
    ['/add/several/s1', 'add'],
    ['/settings', 'settings'],
    ['/settings/advanced', 'settings'],
    // the old addresses light the place they moved to
    ['/missing', 'wardrobe'],
    ['/missing/check', 'wardrobe'],
    ['/insights', 'wardrobe'],
    ['/wishlist', 'wardrobe'],
    ['/worn', 'today'],
  ])('%s lights %s', (path, place) => {
    expect(placeOf(parseRoute(path))).toBe(place);
  });
});

describe('the addresses that moved', () => {
  it.each([
    ['/missing', '/wardrobe'],
    ['/missing/', '/wardrobe'],
    ['/insights', '/wardrobe'],
    ['/missing/check', '/wardrobe/check'],
    ['/missing/check/wish/w%201', '/wardrobe/check/wish/w%201'],
    ['/missing/item/abc', '/wardrobe/item/abc'],
    ['/would-work', '/wardrobe/check'],
    ['/wishlist', '/wardrobe/wishlist'],
    ['/wishlist/', '/wardrobe/wishlist'],
    ['/worn', '/today/worn'],
    // what follows the path comes along
    ['/missing?from=bookmark', '/wardrobe?from=bookmark'],
  ])('%s now leads to %s', (from, to) => {
    expect(movedTo(from)).toBe(to);
  });

  it('leaves every address that has not moved as it is', () => {
    for (const path of ['/', '/today', '/today/worn', '/review', '/trips', '/trips/t1', '/wardrobe', '/wardrobe/check', '/wardrobe/link',
      '/wardrobe/wishlist', '/item/abc', '/archived', '/add', '/settings', '/settings/advanced']) {
      expect(movedTo(path)).toBeNull();
    }
  });

  it('shows the screen an old address moved to, with what it names', () => {
    expect(parseRoute('/missing/item/abc')).toEqual({ name: 'wardrobe', itemId: 'abc', check: false, wishId: null, wish: null });
    expect(parseRoute('/missing/check/wish/w1')).toEqual({ name: 'wardrobe', itemId: null, check: true, wishId: 'w1', wish: null });
    expect(parseRoute('/insights')).toEqual({ name: 'wardrobe', itemId: null, check: false, wishId: null, wish: null });
  });

  it('opens the wishlist on its own page, from its old address too', () => {
    const wishlist = { name: 'wardrobe', itemId: null, check: false, wishId: null, wish: null, wishlist: true };
    expect(parseRoute('/wardrobe/wishlist')).toEqual(wishlist);
    expect(parseRoute('/wardrobe/wishlist/')).toEqual(wishlist);
    expect(parseRoute('/wishlist')).toEqual(wishlist);
    expect(parseRoute('/wardrobe')).not.toHaveProperty('wishlist');
  });

  it('opens a wish on its own page', () => {
    expect(parseRoute('/wardrobe/wish/w%201')).toEqual({ name: 'wardrobe', itemId: null, check: false, wishId: null, wish: 'w 1' });
  });

  it('opens the page a shared link lands on, the link being in the query', () => {
    expect(parseRoute('/wardrobe/link')).toEqual({ name: 'wardrobe', itemId: null, check: false, wishId: null, wish: null, link: true });
    expect(parseRoute('/wardrobe/link/')).toMatchObject({ link: true });
    expect(parseRoute('/wardrobe')).not.toHaveProperty('link');
  });
});
