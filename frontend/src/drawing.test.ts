import { afterEach, describe, expect, it, vi } from 'vitest';
import { gridViewOf, keepShowDrawings, loadShowDrawings, notInDrawing, SHOW_DRAWINGS_KEY, smallPicture } from './drawing';

describe('drawing wording', () => {
  it('lists what is not in the drawing once each, as plain sentences', () => {
    expect(notInDrawing(['embroidered chest logo', 'Embroidered chest logo'], ['the stripes: the drawing shows only the colour for now', 'cuff barrel_1 drawn plain']))
      .toEqual(['Embroidered chest logo', 'The stripes: the drawing shows only the colour for now', 'Cuff barrel 1 drawn plain']);
    expect(notInDrawing(null, undefined)).toEqual([]);
    expect(notInDrawing(['  ', ''], [])).toEqual([]);
  });
});

describe('show drawings instead of photos', () => {
  const both = { illustration_url: '/d.svg', thumb_url: '/t.webp', cutout_state: 'ready' as const };
  const uncut = { illustration_url: '/d.svg', thumb_url: '/t.webp', cutout_state: 'pending' as const };
  const noDrawing = { illustration_url: null, thumb_url: '/t.webp', cutout_state: 'ready' as const };

  it('shows the drawing wherever the item has one when drawings are asked for', () => {
    expect(smallPicture(both, true)).toBe('drawing');
    expect(smallPicture(both, true, true)).toBe('drawing');
    expect(smallPicture(uncut, true, true)).toBe('drawing');
  });

  it('shows the photo, as before, for an item with no drawing yet', () => {
    expect(smallPicture(noDrawing, true)).toBe('cutout');
    expect(smallPicture({ ...noDrawing, cutout_state: 'pending' }, true)).toBe('photo');
    expect(smallPicture({ illustration_url: null, thumb_url: null, cutout_state: 'none' as const }, true)).toBe('none');
  });

  it('with the setting off, keeps each place as it was: a tile the photo first, a card the drawing first', () => {
    expect(smallPicture(both, false)).toBe('cutout');
    expect(smallPicture(both, false, true)).toBe('cutout');
    expect(smallPicture(uncut, false, true)).toBe('photo');
    expect(smallPicture(uncut, false)).toBe('drawing');
    expect(smallPicture({ illustration_url: '/d.svg', thumb_url: null, cutout_state: 'none' as const }, false, true)).toBe('drawing');
  });
});

describe('the closet grid', () => {
  it('starts from the setting', () => {
    expect(gridViewOf(false, null)).toBe('photos');
    expect(gridViewOf(true, null)).toBe('drawings');
  });

  it('shows what its switch chose for the moment, until the setting changes', () => {
    expect(gridViewOf(false, { view: 'drawings', setting: false })).toBe('drawings');
    expect(gridViewOf(true, { view: 'photos', setting: true })).toBe('photos');
    // the setting changed (here or on another device) since the switch was used: the setting wins
    expect(gridViewOf(true, { view: 'photos', setting: false })).toBe('drawings');
    expect(gridViewOf(false, { view: 'drawings', setting: true })).toBe('photos');
  });
});

describe('the setting kept on this device', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the last word from Nines, off until it said on', () => {
    const kept = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => kept.set(k, v) });
    expect(loadShowDrawings()).toBe(false);
    keepShowDrawings(true);
    expect(kept.get(SHOW_DRAWINGS_KEY)).toBe('1');
    expect(loadShowDrawings()).toBe(true);
    keepShowDrawings(false);
    expect(loadShowDrawings()).toBe(false);
  });

  it('is off where nothing can be kept', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } });
    expect(loadShowDrawings()).toBe(false);
    expect(() => keepShowDrawings(true)).not.toThrow();
  });
});
