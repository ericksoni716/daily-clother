import { useEffect, useState, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react';
import { flushSaves } from './leave';
import { movedTo } from './places';

const listeners = new Set<() => void>();
const notify = () => {
  flushSaves(false);
  listeners.forEach((l) => l());
};

/**
 * What the app writes into `history.state` for each of its own entries: how far into the app's history it is
 * (0 for the page the app was opened on), a name of its own for its scroll position, and the address of the
 * entry before it, so a back link knows whether the browser's Back would land where it says it goes.
 */
export interface Entry {
  idx: number;
  key: string;
  from: string | null;
}

export function entryOf(state: unknown): Entry | null {
  if (!state || typeof state !== 'object') return null;
  const { idx, key, from } = state as Record<string, unknown>;
  if (typeof idx !== 'number' || typeof key !== 'string') return null;
  return { idx, key, from: typeof from === 'string' ? from : null };
}

const newKey = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;

/** The entry a push makes after `current`, which was at the address `here`. */
export function pushedEntry(current: Entry | null, here: string): Entry {
  return { idx: (current?.idx ?? 0) + 1, key: newKey(), from: here };
}

/** The entry a replace leaves: the same place in history under a new address, so its scroll and its Back stay. */
export function replacedEntry(current: Entry | null): Entry {
  return current ?? { idx: 0, key: newKey(), from: null };
}

const pathOnly = (to: string) => to.split(/[?#]/)[0];

/** A back link to `to` can use the browser's Back: the entry before this one is that page, inside the app. */
export function backGoesTo(state: unknown, to: string): boolean {
  const entry = entryOf(state);
  return !!entry && entry.idx > 0 && entry.from !== null && pathOnly(entry.from) === pathOnly(to);
}

// ------------------------------------------------------------------ where each entry was scrolled to

const STORED = 'closet-scroll';
/** Enough history for any Back; older entries are dropped. */
const KEEP = 60;
/** How long to keep trying to reach a saved position while the page's data is still coming in. */
const PATIENCE_MS = 2500;
/** Someone scrolling on their own while we wait wins. */
const THEIR_OWN = ['wheel', 'touchstart', 'keydown', 'pointerdown'];

export function readPositions(raw: string | null): Map<string, number> {
  try {
    const saved: unknown = JSON.parse(raw ?? '[]');
    if (Array.isArray(saved)) {
      return new Map(saved.filter((e): e is [string, number] => Array.isArray(e) && typeof e[0] === 'string' && typeof e[1] === 'number'));
    }
  } catch {
    /* a damaged copy: start fresh */
  }
  return new Map();
}

export function writePositions(positions: Map<string, number>): string {
  return JSON.stringify([...positions].slice(-KEEP));
}

/**
 * Where the page should be scrolled after arriving at `to` from `from`, or null to leave it where it is.
 * A push to a new page starts at its top (see startsAtTop). A replace tidies the address of the same page and
 * stays put, unless it leaves for a different page. Back and Forward return to where that entry was left.
 */
export function arrivalScroll(how: 'push' | 'replace' | 'pop', from: string, to: string, saved: number | undefined,
  wide = window.matchMedia?.(WIDE).matches ?? false): number | null {
  const top = startsAtTop(pathOnly(from), pathOnly(to), wide);
  if (how === 'push') return top ? 0 : null;
  if (how === 'replace') return top && pathOnly(from) !== pathOnly(to) ? 0 : null;
  return top ? saved ?? 0 : null;
}

let positions = new Map<string, number>();
let current: Entry | null = null;
let here = '';
let stopScrolling: (() => void) | undefined;

function keep() {
  try {
    window.sessionStorage.setItem(STORED, writePositions(positions));
  } catch {
    /* storage is off (a private window): the positions last until the page closes */
  }
}

function saveScroll() {
  if (current) positions.set(current.key, window.scrollY);
}

/** Scrolls to `target` once the page is tall enough to have it, trying for a moment while it draws. */
function scrollWhenReady(target: number) {
  stopScrolling?.();
  const until = performance.now() + PATIENCE_MS;
  let frame = 0;
  let held = 0;
  const stop = () => {
    cancelAnimationFrame(frame);
    THEIR_OWN.forEach((e) => window.removeEventListener(e, stop));
    if (stopScrolling === stop) stopScrolling = undefined;
  };
  THEIR_OWN.forEach((e) => window.addEventListener(e, stop, { passive: true }));
  const retry = () => {
    window.scrollTo(0, target);
    // held for a few frames, so a page still drawing (and shrinking) cannot undo it
    held = Math.abs(window.scrollY - target) <= 1 ? held + 1 : 0;
    if (held < 3 && performance.now() < until) frame = requestAnimationFrame(retry);
    else stop();
  };
  stopScrolling = stop;
  frame = requestAnimationFrame(retry);
}

function arrive(how: 'push' | 'replace' | 'pop', from: string) {
  here = window.location.pathname + window.location.search;
  const target = arrivalScroll(how, from, window.location.pathname, current ? positions.get(current.key) : undefined);
  if (target === null) return;
  if (how === 'pop') scrollWhenReady(target);
  else {
    stopScrolling?.();
    window.scrollTo(0, target);
  }
}

/**
 * Called once as the app starts. The app keeps its own scroll positions, one per history entry, kept for this tab
 * through a reload: the browser's own would jump before a page has drawn, then fight with ours.
 */
export function startHistory() {
  if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  try {
    positions = readPositions(window.sessionStorage.getItem(STORED));
  } catch {
    positions = new Map();
  }
  current = replacedEntry(entryOf(window.history.state));
  window.history.replaceState(current, '');
  here = window.location.pathname + window.location.search;
  window.addEventListener('scroll', saveScroll, { passive: true });
  window.addEventListener('pagehide', keep);
  window.addEventListener('popstate', (e: PopStateEvent) => {
    const from = here;
    saveScroll();
    current = entryOf(e.state);
    if (!current) {
      // an entry the app did not write (a link to a #fragment, say): give it a name of its own
      current = replacedEntry(null);
      window.history.replaceState(current, '');
    }
    notify();
    arrive('pop', from);
    keep();
  });
  // a reload, or Back to the app from somewhere else: where this entry was, if known
  const saved = positions.get(current.key);
  if (saved) scrollWhenReady(saved);
}

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === window.location.pathname + window.location.search) return;
  const from = window.location.pathname;
  saveScroll();
  const before = current ?? entryOf(window.history.state);
  current = opts.replace ? replacedEntry(before) : pushedEntry(before, window.location.pathname + window.location.search);
  if (opts.replace) window.history.replaceState(current, '', to);
  else window.history.pushState(current, '', to);
  notify();
  arrive(opts.replace ? 'replace' : 'push', from);
  keep();
}

/**
 * A back link: the browser's Back when the page before is the one the link names, so that page comes back where you
 * left it and history does not pile up. Otherwise (the page was opened straight from its address, or reached another
 * way) the named page takes this one's place.
 */
export function goBack(to: string) {
  if (backGoesTo(window.history.state, to)) window.history.back();
  else navigate(to, { replace: true });
}

/**
 * A new page opens at its top, as it would in a browser: on a phone the item page replaces the closet and would
 * otherwise open at the grid's scroll position, near its bottom. On a computer, choosing an item opens it in the side
 * panel next to the list, so the list keeps its place, going Back or Forward included.
 */
export function startsAtTop(from: string, to: string, wide = window.matchMedia?.(WIDE).matches ?? false): boolean {
  const a = parseRoute(from), b = parseRoute(to);
  if (!wide || a.name !== b.name) return true;
  const panel = (r: Route) => ('itemId' in r ? r.itemId : null);
  return panel(a) === null && panel(b) === null;
}

export function usePath(): string {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => window.location.pathname,
  );
}

export type Route =
  | { name: 'closet'; status: 'active' | 'archived'; itemId: string | null }
  | { name: 'today'; itemId: string | null }
  | { name: 'worn' }
  | { name: 'wardrobe'; itemId: string | null; check: boolean; wishId: string | null; wish: string | null; link?: boolean }
  | { name: 'add' }
  | { name: 'several'; id: string }
  | { name: 'settings' }
  | { name: 'advanced' }
  | { name: 'review' }
  | { name: 'trips'; tripId: string | null };

const id = (part: string | undefined) => (part ? decodeURIComponent(part) : null);

/** The screen an address shows. An address that has moved (`movedTo` in places.ts) shows the screen it moved to. */
export function parseRoute(path: string): Route {
  const moved = movedTo(path);
  if (moved) return parseRoute(moved.split(/[?#]/)[0]);
  if (path === '/add') return { name: 'add' };
  const several = path.match(/^\/add\/several\/([^/]+)\/?$/);
  if (several) return { name: 'several', id: decodeURIComponent(several[1]) };
  if (path === '/settings') return { name: 'settings' };
  if (path === '/settings/advanced') return { name: 'advanced' };
  if (path === '/today/worn') return { name: 'worn' };
  const today = path.match(/^\/today(?:\/item\/([^/]+))?\/?$/);
  if (today) return { name: 'today', itemId: id(today[1]) };
  if (path === '/review') return { name: 'review' };
  const trips = path.match(/^\/trips(?:\/([^/]+))?\/?$/);
  if (trips) return { name: 'trips', tripId: id(trips[1]) };
  const wardrobe = path.match(/^\/wardrobe(?:\/item\/([^/]+))?\/?$/);
  if (wardrobe) return { name: 'wardrobe', itemId: id(wardrobe[1]), check: false, wishId: null, wish: null };
  // Would this work?, started from the page or from a wish
  const check = path.match(/^\/wardrobe\/check(?:\/wish\/([^/]+))?\/?$/);
  if (check) return { name: 'wardrobe', itemId: null, check: true, wishId: id(check[1]), wish: null };
  // a wish on its own page: its note, its shop finds and prices
  const wish = path.match(/^\/wardrobe\/wish\/([^/]+)\/?$/);
  if (wish) return { name: 'wardrobe', itemId: null, check: false, wishId: null, wish: decodeURIComponent(wish[1]) };
  // a product's page to add to the wishlist, sent from the share sheet or a Shortcut (the link is in the query)
  if (/^\/wardrobe\/link\/?$/.test(path)) return { name: 'wardrobe', itemId: null, check: false, wishId: null, wish: null, link: true };
  const archived = path.startsWith('/archived');
  const m = path.match(/^\/(?:archived\/)?item\/([^/]+)$/);
  return { name: 'closet', status: archived ? 'archived' : 'active', itemId: m ? decodeURIComponent(m[1]) : null };
}

export function itemPath(id: string, status: 'active' | 'archived'): string {
  return `${status === 'archived' ? '/archived' : ''}/item/${encodeURIComponent(id)}`;
}

/** A wish's own page in the Wardrobe: its finds and prices, its note, and what to do with it. */
export const wishPath = (id: string) => `/wardrobe/wish/${encodeURIComponent(id)}`;

export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a
      href={to}
      {...rest}
      onClick={(e: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(e);
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate(to);
      }}
    />
  );
}

export function useMediaQuery(query: string): boolean {
  // false where there is no window to ask (the component tests draw to markup in Node)
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return match;
}

export const WIDE = '(min-width: 1000px)';
