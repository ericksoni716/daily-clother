import { describe, expect, it, vi } from 'vitest';
import { navSection, tabFor } from './nav';

// the router listens for the browser's back button as it loads; these tests run without a browser
vi.stubGlobal('window', { addEventListener: () => undefined });
const { parseRoute } = await import('./router');

const lit = (path: string) => {
  const section = navSection(parseRoute(path));
  return { sidebar: section, tab: tabFor(section) };
};

describe('the lit navigation link', () => {
  it.each([
    ['/', 'closet', 'closet'],
    ['/archived', 'closet', 'closet'],
    ['/item/abc', 'closet', 'closet'],
    ['/archived/item/abc', 'closet', 'closet'],
    ['/insights', 'closet', 'closet'],
    ['/review', 'review', 'closet'],
    ['/today', 'today', 'today'],
    ['/today/item/abc', 'today', 'today'],
    ['/today/worn', 'today', 'today'],
    ['/trips', 'trips', 'today'],
    ['/trips/t1', 'trips', 'today'],
    ['/missing', 'missing', 'missing'],
    ['/missing/item/abc', 'missing', 'missing'],
    ['/missing/check', 'missing', 'missing'],
    ['/missing/check/wish/w1', 'missing', 'missing'],
    ['/add', 'add', 'add'],
    ['/settings', 'settings', 'settings'],
  ])('%s lights %s in the sidebar and %s on the phone', (path, sidebar, tab) => {
    expect(lit(path)).toEqual({ sidebar, tab });
  });
});
