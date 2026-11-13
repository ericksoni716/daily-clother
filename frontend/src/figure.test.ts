import { afterEach, describe, expect, it, vi } from 'vitest';
import { figurePieces, loadTodayView, saveTodayView, svgSource, TODAY_VIEW_KEY } from './figure';

describe('the outfit as worn', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('asks for every place but the accessories, missing ones as null', () => {
    expect(figurePieces({ base: 'a', mid: null, outer: 'c', bottom: 'd', shoes: 'e', accessories: ['f'] }))
      .toEqual({ base: 'a', mid: null, outer: 'c', bottom: 'd', shoes: 'e' });
  });

  it('shows the drawing through an image source, never as markup on the page', () => {
    const src = svgSource('<svg xmlns="http://www.w3.org/2000/svg"><path d="M 0,0"/></svg>');
    expect(src.startsWith('data:image/svg+xml;charset=utf-8,')).toBe(true);
    expect(src).not.toMatch(/[<>"# ]/);
  });

  it('remembers on this device whether Today shows the pieces or the outfit as worn', () => {
    const kept = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => kept.set(k, v) });
    expect(loadTodayView()).toBe('pieces');
    saveTodayView('worn');
    expect(kept.get(TODAY_VIEW_KEY)).toBe('worn');
    expect(loadTodayView()).toBe('worn');
    kept.set(TODAY_VIEW_KEY, 'nonsense');
    expect(loadTodayView()).toBe('pieces');
  });

  it('falls back to the pieces where nothing can be kept', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } });
    expect(loadTodayView()).toBe('pieces');
    expect(() => saveTodayView('worn')).not.toThrow();
  });
});
