import { useEffect, useState, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react';

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());
window.addEventListener('popstate', notify);

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === window.location.pathname + window.location.search) return;
  if (opts.replace) window.history.replaceState(null, '', to);
  else window.history.pushState(null, '', to);
  notify();
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
  | { name: 'add' }
  | { name: 'settings' }
  | { name: 'review' }
  | { name: 'trips'; tripId: string | null };

export function parseRoute(path: string): Route {
  if (path === '/add') return { name: 'add' };
  if (path === '/settings') return { name: 'settings' };
  const today = path.match(/^\/today(?:\/item\/([^/]+))?\/?$/);
  if (today) return { name: 'today', itemId: today[1] ? decodeURIComponent(today[1]) : null };
  if (path === '/review') return { name: 'review' };
  const trip = path.match(/^\/trips(?:\/([^/]+))?\/?$/);
  if (trip) return { name: 'trips', tripId: trip[1] ? decodeURIComponent(trip[1]) : null };
  const archived = path.startsWith('/archived');
  const m = path.match(/^\/(?:archived\/)?item\/([^/]+)$/);
  return { name: 'closet', status: archived ? 'archived' : 'active', itemId: m ? decodeURIComponent(m[1]) : null };
}

export function itemPath(id: string, status: 'active' | 'archived'): string {
  return `${status === 'archived' ? '/archived' : ''}/item/${encodeURIComponent(id)}`;
}

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
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
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
