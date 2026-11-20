/**
 * The app's four places and Add: which one a route belongs to (the lit link in the sidebar and the tab bar), and where
 * the addresses of the places that were merged away lead now. See docs/DECISIONS.md, "Four places and Add".
 */
import type { Route } from './router';

export type AppPlace = 'today' | 'closet' | 'add' | 'wardrobe' | 'settings';

/**
 * The place a route belongs to. Worn and Trips are part of Today; an item, Archived and the review are part of the
 * closet; Would this work?, a wish and an item opened from there are part of the wardrobe; checking the pieces in a
 * photo of several is part of Add; Advanced is part of Settings.
 */
export function placeOf(route: Route): AppPlace {
  switch (route.name) {
    case 'today':
    case 'worn':
    case 'trips':
      return 'today';
    case 'closet':
    case 'review':
      return 'closet';
    case 'add':
    case 'several':
      return 'add';
    case 'wardrobe':
      return 'wardrobe';
    case 'settings':
    case 'advanced':
      return 'settings';
  }
}

/** Old addresses, and the obvious ones the app never had, with where each leads now. Exact paths. */
const MOVED: Record<string, string> = {
  '/missing': '/wardrobe',
  '/insights': '/wardrobe',
  '/missing/check': '/wardrobe/check',
  '/would-work': '/wardrobe/check',
  '/wishlist': '/wardrobe',
  '/worn': '/today/worn',
};

/**
 * Where an address that has moved leads now (keeping anything after the path), or null when it has not moved. A
 * bookmark, the home-screen app, a reload or Back to an entry made before the move all land on the new place.
 */
export function movedTo(address: string): string | null {
  const at = address.search(/[?#]/);
  const path = (at < 0 ? address : address.slice(0, at)).replace(/(.)\/+$/, '$1');
  const rest = at < 0 ? '' : address.slice(at);
  if (MOVED[path]) return MOVED[path] + rest;
  const item = path.match(/^\/missing\/item\/([^/]+)$/);
  if (item) return `/wardrobe/item/${item[1]}${rest}`;
  const wish = path.match(/^\/missing\/check\/wish\/([^/]+)$/);
  if (wish) return `/wardrobe/check/wish/${wish[1]}${rest}`;
  return null;
}
