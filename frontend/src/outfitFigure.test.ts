import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, connection } from './api';
import { loadOutfitFigure } from './outfitFigure';
import { figureKey, figurePieces, loadTodayView, saveTodayView, type FigurePieces } from './today';
import type { ItemSummary } from './types';

const pieces: FigurePieces = { base: 'shirt', mid: null, outer: 'coat', bottom: 'jeans', shoes: 'boots' };
const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 20"/>';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  connection.set(false);
});

describe('Today view', () => {
  it('remembers only the local view, defaults to Pieces, and tolerates unavailable storage', () => {
    const data = new Map<string, string>();
    const kv = { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value); }, removeItem: (key: string) => { data.delete(key); } };
    expect(loadTodayView(kv)).toBe('pieces');
    saveTodayView('as-worn', kv);
    expect(loadTodayView(kv)).toBe('as-worn');
    saveTodayView('pieces', kv);
    expect(loadTodayView(kv)).toBe('pieces');
    kv.setItem('closet-today-view', '"unexpected"');
    expect(loadTodayView(kv)).toBe('pieces');
    kv.setItem('closet-today-view', 'broken JSON');
    expect(loadTodayView(kv)).toBe('pieces');
    const denied = { ...kv, getItem: () => { throw Error('denied'); }, setItem: () => { throw Error('denied'); } };
    expect(loadTodayView(denied)).toBe('pieces');
    expect(() => saveTodayView('as-worn', denied)).not.toThrow();
  });
});

describe('figure API', () => {
  it('posts only the five slots with authentication and returns an SVG blob', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(svg, { headers: { 'Content-Type': 'image/svg+xml; charset=utf-8' } }));
    vi.stubGlobal('fetch', fetch);
    const slots = figurePieces({ ...pieces, base: 'shirt', bottom: 'jeans', shoes: 'boots', accessories: ['hat'] });
    const signal = new AbortController().signal;
    const blob = await api.figure(slots, signal);
    expect(fetch).toHaveBeenCalledWith('/api/outfits/figure', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pieces), signal,
    });
    expect(blob.type).toBe('image/svg+xml;charset=utf-8');
    expect(await blob.text()).toBe(svg);
  });

  it('rejects non-SVG replies and gives readable server and offline errors', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response('<html/>', { headers: { 'Content-Type': 'text/html' } }))
      .mockResolvedValueOnce(new Response('{"detail":"That item is not in this closet."}', { status: 404 }))
      .mockRejectedValueOnce(new TypeError('network'));
    vi.stubGlobal('fetch', fetch);
    await expect(api.figure(pieces)).rejects.toThrow('did not send a drawing');
    await expect(api.figure(pieces)).rejects.toThrow('That item is not in this closet.');
    await expect(api.figure(pieces)).rejects.toMatchObject({ status: 0 });
    expect(connection.offline).toBe(true);
  });

  it('still handles an expired login and does not treat an abort as offline', async () => {
    const unauthorized = vi.fn();
    const unsubscribe = connection.onUnauthorized(unauthorized);
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockRejectedValueOnce(new DOMException('Aborted', 'AbortError')));
    await expect(api.figure(pieces)).rejects.toThrow('Log in');
    expect(unauthorized).toHaveBeenCalledOnce();
    unsubscribe();
    await expect(api.figure(pieces)).rejects.toMatchObject({ name: 'AbortError' });
    expect(connection.offline).toBe(false);
  });
});

describe('figure lifetime', () => {
  it('keys figures by closet, ordered slots and item revisions, not object identity', () => {
    const outfit = { ...pieces, base: 'shirt', bottom: 'jeans', shoes: 'boots', accessories: [] };
    const items = new Map<string, ItemSummary>([['shirt', { updated_at: 'before', illustration_url: '/drawing?v=1' } as ItemSummary]]);
    const before = figureKey('main', outfit, items);
    expect(figureKey('main', { ...outfit }, new Map(items))).toBe(before);
    expect(figureKey('demo', outfit, items)).not.toBe(before);
    expect(figureKey('main', { ...outfit, base: 'other' }, items)).not.toBe(before);
    items.set('shirt', { updated_at: 'after', illustration_url: '/drawing?v=1' } as ItemSummary);
    expect(figureKey('main', outfit, items)).not.toBe(before);
    items.set('shirt', { updated_at: 'before', illustration_url: '/drawing?v=2' } as ItemSummary);
    expect(figureKey('main', outfit, items)).not.toBe(before);
  });

  it('revokes its blob URL when the view, outfit or closet is left', async () => {
    vi.spyOn(api, 'figure').mockResolvedValue(new Blob([svg]));
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:figure');
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const ready = vi.fn();
    const stop = loadOutfitFigure(pieces, ready, vi.fn());
    await vi.waitFor(() => expect(ready).toHaveBeenCalledWith('blob:figure'));
    expect(create).toHaveBeenCalledOnce();
    stop();
    expect(revoke).toHaveBeenCalledWith('blob:figure');
  });

  it('ignores a late response from a previous outfit or closet even if cancellation was too late', async () => {
    let finish!: (blob: Blob) => void;
    const figure = vi.spyOn(api, 'figure').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const create = vi.spyOn(URL, 'createObjectURL');
    const ready = vi.fn();
    const failed = vi.fn();
    const stop = loadOutfitFigure(pieces, ready, failed);
    stop();
    expect(figure.mock.calls[0][1]?.aborted).toBe(true);
    finish(new Blob([svg]));
    await Promise.resolve();
    expect(create).not.toHaveBeenCalled();
    expect(ready).not.toHaveBeenCalled();
    expect(failed).not.toHaveBeenCalled();
  });

  it('shows current failures but ignores failures after leaving the view', async () => {
    vi.spyOn(api, 'figure').mockRejectedValue(new Error('Please try again.'));
    const failed = vi.fn();
    const stop = loadOutfitFigure(pieces, vi.fn(), failed);
    await vi.waitFor(() => expect(failed).toHaveBeenCalledWith('Please try again.'));
    stop();
    failed.mockClear();
    loadOutfitFigure(pieces, vi.fn(), failed)();
    await Promise.resolve();
    await Promise.resolve();
    expect(failed).not.toHaveBeenCalled();
  });
});
