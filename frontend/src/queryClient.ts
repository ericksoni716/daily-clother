/**
 * The query cache's defaults, in one place. Each open closet (the owner's or the demo) gets a client of its own in
 * `ClosetProvider`, so the two never share what they have read. Why these numbers: docs/DECISIONS.md, "Data loading".
 */
import { QueryClient } from '@tanstack/react-query';

/** What was read stays fresh for a minute: opening a screen again within it shows what is kept, without asking. */
export const STALE_MS = 60_000;
/** What no screen shows is kept half an hour, so going back to a screen or an item opens at once. */
export const KEEP_MS = 30 * 60_000;
/** Coming back to the app after at least this long away asks again for whatever is stale; a glance away does not. */
export const AWAY_MS = 10_000;

/** Whether coming back after `awayMs` away should ask again for what is on screen (when it is stale). */
export function refetchOnReturn(awayMs: number): boolean {
  return awayMs >= AWAY_MS;
}

// How long the page was hidden before it last came back. The listener is added when this module loads, before the
// query library adds its own, so the number is up to date when the library asks `refetchOnWindowFocus`.
let hiddenAt: number | null = null;
let lastAway = 0;
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') hiddenAt = Date.now();
    else {
      lastAway = hiddenAt === null ? 0 : Date.now() - hiddenAt;
      hiddenAt = null;
    }
  });
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_MS,
        gcTime: KEEP_MS,
        // Not retried: a failure says so at once, and what was there stays on screen. A poll asks again by itself.
        retry: false,
        // Ask even when the browser says it is offline: the service worker may answer with its saved copy, and
        // `api.ts` follows whether Nines can be reached (`connection`).
        networkMode: 'always',
        refetchOnWindowFocus: () => refetchOnReturn(lastAway),
        // Back online is followed by `ClosetProvider` (when Nines answers again), not by the browser's event.
        refetchOnReconnect: false,
        // Left on (the default) and never turned off: a poll that brings the same data keeps the same objects, so
        // nothing that shows them draws again.
        structuralSharing: true,
      },
      mutations: { networkMode: 'always', retry: false },
    },
  });
}
