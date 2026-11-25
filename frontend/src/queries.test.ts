import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { dropItem, itemSaved, pickSummary, touch, upsertSummary, writeItem } from './queries';
import { AWAY_MS, makeQueryClient, refetchOnReturn, STALE_MS } from './queryClient';
import { queryKeys } from './queryKeys';
import type { Item, ItemSummary } from './types';

const summary = (over: Partial<ItemSummary> = {}): ItemSummary => ({
  id: 'i1', name: 'Shirt', category: 'shirt', color: null, color_hex: null, pattern: null, location: null, rating: null,
  status: 'active', cutout_state: 'ready', tag_state: 'done', thumb_url: null, has_illustration: false, has_photo: true,
  last_worn: null, wear_count: 0, wears_since_wash: 0, laundry: 'clean', created_at: '', updated_at: '1', ...over,
});
const full = (over: Partial<Item> = {}) => ({ ...summary(), photos: [], silhouette: {}, ...over }) as unknown as Item;

describe('upsertSummary', () => {
  const list = [summary({ id: 'a' }), summary({ id: 'b' })];
  it('replaces the item where it was, with only the fields the list carries', () => {
    const next = upsertSummary(list, full({ id: 'b', name: 'Renamed' }), 'active');
    expect(next.map((i) => i.name)).toEqual(['Shirt', 'Renamed']);
    expect(next[1]).not.toHaveProperty('photos');
    expect(next[0]).toBe(list[0]);
  });
  it('adds a new item at the top, and takes one out that moved to the other list', () => {
    expect(upsertSummary(list, summary({ id: 'c' }), 'active').map((i) => i.id)).toEqual(['c', 'a', 'b']);
    expect(upsertSummary(list, summary({ id: 'a', status: 'archived' }), 'active').map((i) => i.id)).toEqual(['b']);
    expect(upsertSummary(list, summary({ id: 'z', status: 'archived' }), 'active')).toBe(list);
  });
  it('gives back the same list when nothing changed', () => {
    expect(upsertSummary(list, full({ id: 'a' }), 'active')).toBe(list);
  });
  it('pickSummary keeps the list’s fields only', () => {
    expect(Object.keys(pickSummary(full()))).not.toContain('photos');
  });
});

describe('writing into the cache', () => {
  const setup = () => {
    const qc = new QueryClient();
    qc.setQueryData(queryKeys.items('active'), [summary({ id: 'a' }), summary({ id: 'b' })]);
    qc.setQueryData(queryKeys.items('archived'), [summary({ id: 'z', status: 'archived' })]);
    return qc;
  };
  const ids = (qc: QueryClient, status: 'active' | 'archived') =>
    qc.getQueryData<ItemSummary[]>(queryKeys.items(status))!.map((i) => `${i.id}:${i.name}`);

  it('a saved item goes into its list and its own entry; one archived moves across', () => {
    const qc = setup();
    writeItem(qc, full({ id: 'a', name: 'New name' }));
    expect(ids(qc, 'active')).toEqual(['a:New name', 'b:Shirt']);
    expect(qc.getQueryData<Item>(queryKeys.item('a'))?.name).toBe('New name');
    writeItem(qc, full({ id: 'b', status: 'archived' }));
    expect(ids(qc, 'active')).toEqual(['a:New name']);
    expect(ids(qc, 'archived')).toEqual(['b:Shirt', 'z:Shirt']);
  });

  it('a summary alone leaves the full item to be read again', () => {
    const qc = setup();
    qc.setQueryData(queryKeys.item('a'), full({ id: 'a' }));
    writeItem(qc, summary({ id: 'a', name: 'From the list' }));
    expect(qc.getQueryState(queryKeys.item('a'))?.isInvalidated).toBe(true);
    expect(qc.getQueryData<Item>(queryKeys.item('a'))?.name).toBe('Shirt');
  });

  it('a deleted item leaves the lists and its own entry', () => {
    const qc = setup();
    qc.setQueryData(queryKeys.item('a'), full({ id: 'a' }));
    dropItem(qc, 'a');
    expect(ids(qc, 'active')).toEqual(['b:Shirt']);
    expect(qc.getQueryState(queryKeys.item('a'))).toBeUndefined();
  });

  it('touch makes stale exactly what the kind of edit names, whatever the keys’ arguments', async () => {
    const qc = setup();
    qc.setQueryData(queryKeys.trip('t1'), {});
    qc.setQueryData(queryKeys.trips(), []);
    qc.setQueryData(queryKeys.settings(), {});
    await touch(qc, 'trip');
    expect(qc.getQueryState(queryKeys.trip('t1'))?.isInvalidated).toBe(true);
    expect(qc.getQueryState(queryKeys.trips())?.isInvalidated).toBe(true);
    expect(qc.getQueryState(queryKeys.settings())?.isInvalidated).toBe(false);
    expect(qc.getQueryState(queryKeys.items('active'))?.isInvalidated).toBe(false);
  });

  /** A read whose answers the test gives by hand, in the order they were asked for. */
  const slowRead = () => {
    const give: Array<(answer: string) => void> = [];
    return { give, queryFn: () => new Promise<string>((done) => { give.push(done); }) };
  };

  it('a first read still on its way when an edit lands is asked again: its answer, from before the edit, is never taken as the new one', async () => {
    const qc = makeQueryClient();
    const read = slowRead();
    const seen: string[] = [];
    const observer = new QueryObserver(qc, { queryKey: queryKeys.gaps(), queryFn: read.queryFn });
    const stop = observer.subscribe((r) => { seen.push(`${r.status}/${r.fetchStatus}`); });
    expect(read.give).toHaveLength(1);
    const done = touch(qc, 'wish');
    // asked again at once, and the screen never stops saying it is reading
    expect(read.give).toHaveLength(2);
    expect(qc.getQueryState(queryKeys.gaps())?.fetchStatus).toBe('fetching');
    read.give[0]('from before the edit');
    await Promise.resolve();
    expect(qc.getQueryData(queryKeys.gaps())).toBeUndefined();
    read.give[1]('from after it');
    await done;
    expect(qc.getQueryData(queryKeys.gaps())).toBe('from after it');
    expect(qc.getQueryState(queryKeys.gaps())?.isInvalidated).toBe(false);
    expect(seen).not.toContain('pending/idle');
    stop();
  });

  it('a read on its way for a screen that is not showing lands, so whoever asked gets an answer, and is marked stale once it has', async () => {
    const qc = makeQueryClient();
    const read = slowRead();
    // as Worn asks for its next page before it shows it
    const asked = qc.fetchQuery({ queryKey: queryKeys.worn('next'), queryFn: read.queryFn });
    expect(read.give).toHaveLength(1);
    await touch(qc, 'outfit');
    read.give[0]('from before the edit');
    await expect(asked).resolves.toBe('from before the edit');
    await new Promise((r) => setTimeout(r, 0));
    expect(qc.getQueryState(queryKeys.worn('next'))?.isInvalidated).toBe(true);
    expect(read.give).toHaveLength(1);
  });

  it('the same for a read again of what a screen that is not showing already held: the answer from before the edit is marked stale', async () => {
    const qc = makeQueryClient();
    const read = slowRead();
    qc.setQueryData(queryKeys.gaps(), 'what it had');
    void qc.fetchQuery({ queryKey: queryKeys.gaps(), queryFn: read.queryFn, staleTime: 0 });
    expect(read.give).toHaveLength(1);
    await touch(qc, 'wish');
    read.give[0]('from before the edit');
    await new Promise((r) => setTimeout(r, 0));
    expect(qc.getQueryData(queryKeys.gaps())).toBe('from before the edit');
    expect(qc.getQueryState(queryKeys.gaps())?.isInvalidated).toBe(true);
  });

  it('after an item save, the lists it wrote stay fresh and the rest it touches goes stale', () => {
    const qc = setup();
    qc.setQueryData(queryKeys.review(), { count: 1 });
    qc.setQueryData(queryKeys.itemDetails('a'), {});
    itemSaved(qc, full({ id: 'a', name: 'Saved' }));
    expect(qc.getQueryState(queryKeys.items('active'))?.isInvalidated).toBe(false);
    expect(qc.getQueryState(queryKeys.item('a'))?.isInvalidated).toBe(false);
    expect(qc.getQueryState(queryKeys.review())?.isInvalidated).toBe(true);
    expect(qc.getQueryState(queryKeys.itemDetails('a'))?.isInvalidated).toBe(true);
  });
});

describe('the client', () => {
  it('a poll that brings the same list keeps the same objects, so nothing showing them draws again', () => {
    const qc = makeQueryClient();
    const first = [summary({ id: 'a' }), summary({ id: 'b' })];
    qc.setQueryData(queryKeys.items('active'), first);
    qc.setQueryData(queryKeys.items('active'), [summary({ id: 'a' }), summary({ id: 'b', name: 'Changed' })]);
    const second = qc.getQueryData<ItemSummary[]>(queryKeys.items('active'))!;
    expect(second).not.toBe(first);
    expect(second[0]).toBe(first[0]);   // the unchanged item keeps its object
    qc.setQueryData(queryKeys.items('active'), second.map((i) => ({ ...i })));
    expect(qc.getQueryData(queryKeys.items('active'))).toBe(second);
  });

  it('keeps what it read fresh for a minute', () => {
    expect(makeQueryClient().getDefaultOptions().queries?.staleTime).toBe(STALE_MS);
    expect(STALE_MS).toBe(60_000);
  });

  it('asks again on coming back only after some seconds away', () => {
    expect(refetchOnReturn(0)).toBe(false);
    expect(refetchOnReturn(AWAY_MS - 1)).toBe(false);
    expect(refetchOnReturn(AWAY_MS)).toBe(true);
  });
});
