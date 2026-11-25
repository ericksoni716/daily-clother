/**
 * Reading and saving through the query cache: the queries more than one screen reads, how a save writes what it got
 * back and says what it touched, and polling while work runs. The keys are in `queryKeys.ts`, the defaults in
 * `queryClient.ts`. The recipe: docs/DEVELOPING.md, "Reading and saving data".
 */
import { queryOptions, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { api, ApiError, connection } from './api';
import { loadSavedPlans, savePlans } from './plans';
import { queryKeys, touched, type EditKind, type ItemStatus, type KeyName } from './queryKeys';
import type { Item, ItemSummary, Progress, ProgressList } from './types';

const STATUSES: ItemStatus[] = ['active', 'archived'];

// ------------------------------------------------------------ queries

/** Today's plan and the plans of the days ahead (Today and the day sheet read them). Kept on this device per closet, so
 * a plan made earlier still shows offline. */
export const plansQuery = (profile: string) => queryOptions({
  queryKey: queryKeys.plans(),
  queryFn: async () => {
    try {
      const plans = await api.plans();
      if (!connection.offline) savePlans(profile, plans);
      return plans;
    } catch (e) {
      const saved = (e as ApiError).status === 0 ? loadSavedPlans(profile) : null;
      if (saved) return saved;
      throw e;
    }
  },
});

/** The outfits you keep (Worn lists them; Today says when an outfit on it is one). */
export const keptQuery = () => queryOptions({ queryKey: queryKeys.kept(), queryFn: api.keptOutfits });

/** The closet's list, In use or Archived. */
export const itemsQuery = (status: ItemStatus) => queryOptions({
  queryKey: queryKeys.items(status),
  queryFn: () => api.items(status),
});

/**
 * One item in full. Always asked again when its page opens (it shows what is kept at once meanwhile), since
 * background work changes it; and whenever it arrives the closet's lists take its summary, so the grid follows.
 * When it comes back described again or drawn anew by work in the background, its details and history are stale.
 */
export const itemQuery = (id: string) => queryOptions({
  queryKey: queryKeys.item(id),
  queryFn: async ({ client }) => {
    const before = client.getQueryData<Item>(queryKeys.item(id));
    const item = await api.item(id);
    writeSummary(client, item);
    if (before && (before.tagged_at !== item.tagged_at || before.illustration_url !== item.illustration_url)) {
      void client.invalidateQueries({ queryKey: queryKeys.itemDetails(id) });
      void client.invalidateQueries({ queryKey: queryKeys.history(id) });
    }
    return item;
  },
  staleTime: 0,
});

/** The vocabulary changes only with a new version of Nines, so it is read once per open closet. */
export const vocabQuery = () => queryOptions({ queryKey: queryKeys.vocab(), queryFn: api.vocab, staleTime: Infinity });

export const modelQuery = () => queryOptions({ queryKey: queryKeys.model(), queryFn: api.model });

/** The items being worked on in the background (`GET /api/progress`). The closet's provider asks for it and polls it;
 * a screen only reads it (`useProgress`). Always asked again when it is made stale: it is small. */
export const progressQuery = () => queryOptions({ queryKey: queryKeys.progress(), queryFn: api.progress, staleTime: 0 });

export const reviewQuery = () => queryOptions({ queryKey: queryKeys.review(), queryFn: api.review });

/** The details of an item that can be fixed, with their values. */
export const detailOptionsQuery = (id: string) => queryOptions({
  queryKey: queryKeys.itemDetails(id),
  queryFn: () => api.detailOptions(id),
});

/** The closet's list; `data` is undefined until it has been read once. */
export function useItems(status: ItemStatus = 'active', enabled = true) {
  return useQuery({ ...itemsQuery(status), enabled });
}

/** One item's summary from whichever list holds it (null when neither list has been read or holds it). Draws again
 * only when that one summary changes. */
export function useItemSummary(id: string): ItemSummary | null {
  const pick = useCallback((list: ItemSummary[]) => list.find((i) => i.id === id) ?? null, [id]);
  const active = useQuery({ ...itemsQuery('active'), select: pick, enabled: false }).data;
  const archived = useQuery({ ...itemsQuery('archived'), select: pick, enabled: false }).data;
  return active ?? archived ?? null;
}

export function useVocab() {
  return useQuery(vocabQuery()).data ?? null;
}

export function useModel() {
  return useQuery(modelQuery()).data ?? null;
}

/** The work under way, as last read by the closet's provider (null until it has been read once). */
export function useProgress(): ProgressList | null {
  return useQuery({ ...progressQuery(), enabled: false }).data ?? null;
}

/** One item's progress: its entry in the work under way, else its own summary's (see `progressOf`). Draws again only
 * when that one entry changes. */
export function useItemProgress(item: Pick<ItemSummary, 'id' | 'progress'> | null | undefined): Progress | null {
  const id = item?.id ?? '';
  const pick = useCallback((list: ProgressList) => list.items.find((i) => i.id === id)?.progress ?? null, [id]);
  const listed = useQuery({ ...progressQuery(), select: pick, enabled: false }).data;
  return listed ?? item?.progress ?? null;
}

// ------------------------------------------------------------ writing into the cache

/** The fields of an item the lists carry (what `GET /api/items` sends for each). */
const SUMMARY_KEYS: (keyof ItemSummary)[] = ['id', 'name', 'category', 'color', 'color_hex', 'pattern', 'location', 'rating',
  'status', 'cutout_state', 'tag_state', 'tag_error', 'thumb_url', 'has_illustration', 'illustration_url', 'has_photo', 'last_worn', 'wear_count',
  'wears_since_wash', 'laundry', 'away', 'created_at', 'updated_at', 'kind', 'kind_name', 'group', 'drawn_state', 'drawn_version', 'progress'];

/** Two values of a summary's field alike: by value for the one that is an object (`progress`). */
const same = (a: unknown, b: unknown) => a === b || (typeof a === 'object' && typeof b === 'object' && JSON.stringify(a) === JSON.stringify(b));

export function pickSummary(item: ItemSummary): ItemSummary {
  const out = {} as Record<string, unknown>;
  for (const k of SUMMARY_KEYS) out[k] = item[k];
  return out as unknown as ItemSummary;
}

/**
 * A list with this item's summary put in: replaced where it was, added at the top if it is new to this list, taken
 * out if its status says it belongs in the other one. The same list comes back when nothing changed.
 */
export function upsertSummary(list: ItemSummary[], item: ItemSummary, status: ItemStatus): ItemSummary[] {
  const at = list.findIndex((x) => x.id === item.id);
  if (item.status !== status) return at === -1 ? list : list.filter((x) => x.id !== item.id);
  const next = { ...(at === -1 ? {} : list[at]), ...pickSummary(item) };
  if (at === -1) return [next, ...list];
  if (SUMMARY_KEYS.every((k) => same(list[at][k], next[k]))) return list;
  return list.map((x, i) => (i === at ? next : x));
}

/** Puts an item's summary into the lists that have been read. */
export function writeSummary(qc: QueryClient, item: ItemSummary): void {
  for (const status of STATUSES) {
    qc.setQueryData<ItemSummary[]>(queryKeys.items(status), (list) => (list ? upsertSummary(list, item, status) : list));
  }
}

const isFull = (item: ItemSummary): item is Item => 'photos' in item;

/**
 * A save answered with this item: it goes into the lists and, when it is the whole item, into its own entry. A list
 * still being read is called off and read again afterwards, and a read of the item itself is called off, so an
 * answer from before the save cannot undo it.
 */
export function writeItem(qc: QueryClient, item: ItemSummary): void {
  for (const status of STATUSES) {
    const key = queryKeys.items(status);
    if (qc.getQueryState(key)?.fetchStatus === 'fetching') {
      void qc.cancelQueries({ queryKey: key, exact: true });
      void qc.invalidateQueries({ queryKey: key, exact: true });
    }
  }
  writeSummary(qc, item);
  if (isFull(item)) {
    void qc.cancelQueries({ queryKey: queryKeys.item(item.id), exact: true });   // a read from before the save
    qc.setQueryData(queryKeys.item(item.id), item);
  } else void qc.invalidateQueries({ queryKey: queryKeys.item(item.id), exact: true });
}

/** An item deleted: out of the lists, and its own entry forgotten. */
export function dropItem(qc: QueryClient, id: string): void {
  for (const status of STATUSES) {
    qc.setQueryData<ItemSummary[]>(queryKeys.items(status), (list) => list?.filter((x) => x.id !== id));
  }
  qc.removeQueries({ queryKey: queryKeys.item(id), exact: true });
}

/**
 * Marks every key an edit of this kind touches as stale (less `written`): the ones on screen are asked again.
 *
 * A read still on its way was asked for before the edit, so its answer may be from before it, and taking it would
 * mark that old answer fresh. The library drops such a read only for a screen that is showing and already holds an
 * earlier answer. The others are seen to here: a first read for a screen that is showing is dropped (quietly, since
 * it is asked again in the same breath, so the screen never stops saying it is reading); a read for a screen that is
 * not showing is let land, so whoever asked for it gets an answer, and marked stale once it has.
 */
export function touch(qc: QueryClient, kind: EditKind, written: readonly KeyName[] = []): Promise<void> {
  const names = touched(kind, written);
  for (const name of names) readsOnTheirWay(qc, [name], false);
  return Promise.all(names.map((name) => qc.invalidateQueries({ queryKey: [name] }))).then(() => undefined);
}

/**
 * Marks one key stale (and the keys under it, unless `exact`), with the same care as `touch` for a read still on its
 * way: for the places that know the one key a change made out of date rather than a kind of edit (back from a check,
 * a finished upload, Check again). Coming back online asks again for everything with the library's own call.
 */
export function stale(qc: QueryClient, queryKey: readonly unknown[], { exact = false }: { exact?: boolean } = {}): Promise<void> {
  readsOnTheirWay(qc, queryKey, exact);
  return qc.invalidateQueries({ queryKey, exact });
}

/** `touch`'s care for the reads under a key that are still on their way when it is marked stale. */
function readsOnTheirWay(qc: QueryClient, queryKey: readonly unknown[], exact: boolean): void {
  for (const q of qc.getQueryCache().findAll({ queryKey, exact, fetchStatus: 'fetching' })) {
    if (!q.isActive()) void q.fetch().then(() => q.invalidate(), () => undefined);
    else if (q.state.data === undefined) void q.cancel({ silent: true });
  }
}

/** After a save that answered with the item: written where it shows, and the rest of what it touches made stale. */
export function itemSaved(qc: QueryClient, item: ItemSummary, kind: EditKind = 'item'): void {
  writeItem(qc, item);
  void touch(qc, kind, ['items', 'item']);
}

// ------------------------------------------------------------ saving

/**
 * A save: `run(call)` sends it and, once it succeeds, marks what an edit of `kind` touches as stale. It returns what
 * the server answered and throws what it threw, so the screen still says "Saved" or the error itself.
 */
export function useEdit(kind: EditKind): <T>(call: () => Promise<T>) => Promise<T> {
  const qc = useQueryClient();
  return useCallback(async <T,>(call: () => Promise<T>) => {
    const answer = await call();
    void touch(qc, kind);
    return answer;
  }, [qc, kind]);
}

/** A save that answers with the item (most item calls do): the item is written into the cache, then the rest of
 * what `kind` touches is made stale. */
export function useItemEdit(kind: EditKind = 'item'): (call: () => Promise<Item>) => Promise<Item> {
  const qc = useQueryClient();
  return useCallback(async (call: () => Promise<Item>) => {
    const item = await call();
    itemSaved(qc, item, kind);
    return item;
  }, [qc, kind]);
}

// ------------------------------------------------------------ polling

/**
 * Calls `tick` every `ms` while `ms` is a number (null stops it), skipping ticks while the page is hidden. For work
 * the server does in the background, when the query's own `refetchInterval` does not fit: when several screens show
 * the same data (one poll for all of them, in one place) or when a save in progress must hold the poll back.
 */
export function usePoll(ms: number | null, tick: () => void): void {
  const latest = useRef(tick);
  useEffect(() => {
    latest.current = tick;
  });
  useEffect(() => {
    if (ms === null) return;
    const t = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') latest.current();
    }, ms);
    return () => window.clearInterval(t);
  }, [ms]);
}

/** Every item in the closet by id, archived ones too: a worn outfit may hold a piece archived since. */
export function useAllItems(): Map<string, ItemSummary> {
  const active = useItems('active').data;
  const archived = useItems('archived').data;
  return useMemo(() => new Map([...(archived ?? []), ...(active ?? [])].map((i) => [i.id, i])), [active, archived]);
}
