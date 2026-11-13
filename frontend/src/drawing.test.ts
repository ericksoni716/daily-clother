import { afterEach, describe, expect, it, vi } from 'vitest';
import { drawingPlaceholder, GRID_VIEW_KEY, loadGridView, notInDrawing, saveGridView } from './drawing';

describe('drawing wording', () => {
  it('lists what is not in the drawing once each, as plain sentences', () => {
    expect(notInDrawing(['embroidered chest logo', 'Embroidered chest logo'], ['the stripes: the drawing shows only the colour for now', 'cuff barrel_1 drawn plain']))
      .toEqual(['Embroidered chest logo', 'The stripes: the drawing shows only the colour for now', 'Cuff barrel 1 drawn plain']);
    expect(notInDrawing(null, undefined)).toEqual([]);
    expect(notInDrawing(['  ', ''], [])).toEqual([]);
  });

  it('says why there is no drawing to show', () => {
    expect(drawingPlaceholder('waiting', 'polo', true)).toBe('Waiting to be described; the drawing comes after.');
    expect(drawingPlaceholder('working', null, false)).toBe('Waiting to be described; the drawing comes after.');
    expect(drawingPlaceholder('done', 'polo', true)).toBeNull();
    expect(drawingPlaceholder('none', null, false)).toMatch(/^Choose what kind of item/);
    expect(drawingPlaceholder('done', 'bag', false)).toBe('There is no drawing for this kind of item yet.');
  });
});

describe('grid view', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('is remembered on this device, photos unless drawings were chosen', () => {
    const kept = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => kept.set(k, v) });
    expect(loadGridView()).toBe('photos');
    saveGridView('drawings');
    expect(kept.get(GRID_VIEW_KEY)).toBe('drawings');
    expect(loadGridView()).toBe('drawings');
    kept.set(GRID_VIEW_KEY, 'nonsense');
    expect(loadGridView()).toBe('photos');
  });

  it('falls back to photos where nothing can be kept', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } });
    expect(loadGridView()).toBe('photos');
    expect(() => saveGridView('drawings')).not.toThrow();
  });
});
