import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  dressingSteps, figurePieces, figureVersion, frameOf, loadTodayView, MAX_ACCESSORIES, placeIn, saveTodayView, svgSource,
  TODAY_VIEW_KEY, type FigurePieces,
} from './figure';

describe('the outfit as worn', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('asks for every place and the accessories, missing ones as null', () => {
    expect(figurePieces({ base: 'a', mid: null, outer: 'c', bottom: 'd', shoes: 'e', accessories: ['f', 'g'] }))
      .toEqual({ base: 'a', mid: null, outer: 'c', bottom: 'd', shoes: 'e', accessories: ['f', 'g'] });
  });

  it('sends a piece not in the closet with the outfit, and keeps it in every layer it is dressed in', () => {
    const piece = { category: 'coat', color: 'tan' };
    const asked = figurePieces({ base: 'a', mid: null, outer: '~candidate', bottom: 'd', shoes: 'e', accessories: [] }, piece);
    expect(asked.piece).toEqual(piece);
    expect(dressingSteps(asked).every((s) => s.piece === piece)).toBe(true);
    expect('piece' in figurePieces({ base: 'a', mid: null, outer: null, bottom: 'd', shoes: 'e', accessories: [] }, null)).toBe(false);
  });

  it('asks for at most as many accessories as the server takes', () => {
    const many = Array.from({ length: 12 }, (_, i) => `x${i}`);
    expect(figurePieces({ base: 'a', mid: '', outer: '', bottom: '', shoes: '', accessories: many }).accessories)
      .toHaveLength(MAX_ACCESSORIES);
  });

  it('is drawn again when a piece\'s drawing changes, or a shoe Claude drew is drawn again', () => {
    const byId = new Map([
      ['tee', { illustration_url: '/api/items/tee/illustration.svg?v=1', drawn_version: null }],
      ['shoe', { illustration_url: '/api/items/shoe/illustration.svg?v=2', drawn_version: 'aaaa' }],
    ]);
    const before = figureVersion(['tee', 'shoe', 'gone'], byId);
    expect(before).toBe('/api/items/tee/illustration.svg?v=1 /api/items/shoe/illustration.svg?v=2#aaaa ');
    byId.set('shoe', { illustration_url: '/api/items/shoe/illustration.svg?v=2', drawn_version: 'bbbb' });
    expect(figureVersion(['tee', 'shoe', 'gone'], byId)).not.toBe(before);   // redrawn: its side drawing is the same
    byId.set('shoe', { illustration_url: '/api/items/shoe/illustration.svg?v=2', drawn_version: null });
    expect(figureVersion(['shoe'], byId)).toBe('/api/items/shoe/illustration.svg?v=2');   // none: as before
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

describe('dressing the outfit a layer at a time', () => {
  const none: FigurePieces = { base: null, mid: null, outer: null, bottom: null, shoes: null, accessories: [] };

  it('starts dressed in the trousers, the shoes and the innermost top, then adds each top from the inside out, then the accessories', () => {
    const outfit = { base: 'shirt', mid: 'jumper', outer: 'coat', bottom: 'jeans', shoes: 'boots', accessories: ['scarf', 'hat'] };
    expect(dressingSteps(outfit)).toEqual([
      { ...none, base: 'shirt', bottom: 'jeans', shoes: 'boots' },
      { ...none, base: 'shirt', mid: 'jumper', bottom: 'jeans', shoes: 'boots' },
      { ...none, base: 'shirt', mid: 'jumper', outer: 'coat', bottom: 'jeans', shoes: 'boots' },
      outfit,
    ]);
  });

  it('ends with the outfit itself, whatever it has', () => {
    const outfits: FigurePieces[] = [
      { ...none, base: 'tee', bottom: 'shorts', shoes: 'sneakers' },
      { ...none, mid: 'jumper', outer: 'coat', bottom: 'trousers' },
      { ...none, outer: 'coat', accessories: ['bag'] },
      { ...none, shoes: 'boots' },
      { ...none, accessories: ['watch'] },
    ];
    for (const outfit of outfits) {
      const steps = dressingSteps(outfit);
      expect(steps[steps.length - 1]).toEqual(outfit);
      // never a step with nothing to draw: the server refuses an empty outfit
      for (const step of steps) expect([step.base, step.mid, step.outer, step.bottom, step.shoes, ...step.accessories].some(Boolean)).toBe(true);
    }
  });

  it('is one step when there is nothing to layer', () => {
    expect(dressingSteps({ ...none, base: 'tee', bottom: 'shorts', shoes: 'sneakers' })).toHaveLength(1);
    expect(dressingSteps({ ...none, accessories: ['watch'] })).toHaveLength(1);
  });

  it('starts with the innermost top there is, when there is no base layer', () => {
    expect(dressingSteps({ ...none, mid: 'jumper', outer: 'coat', bottom: 'trousers' })[0]).toEqual({ ...none, mid: 'jumper', bottom: 'trousers' });
  });

  it('reads the part of the plane each drawing shows', () => {
    expect(frameOf('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-12.5 30.0 425.0 610.0" width="425">')).toEqual([-12.5, 30, 425, 610]);
    expect(frameOf('<svg viewBox="0,0,400,600">')).toEqual([0, 0, 400, 600]);
    expect(frameOf('<svg width="400" height="600">')).toBeNull();
    expect(frameOf('<svg viewBox="0 0 0 600">')).toBeNull();
    expect(frameOf('<svg viewBox="0 0 four 600">')).toBeNull();
  });

  it('places each layer where it is in the outfit, not stretched to fill it', () => {
    // a bag beside him widens the outfit to the right: the layers before it keep their size and place
    expect(placeIn([0, 0, 400, 600], [0, 0, 500, 600])).toEqual({ left: '0.000%', top: '0.000%', width: '80.000%', height: '100.000%' });
    // a hat raises the outfit's top
    expect(placeIn([10, 40, 380, 560], [10, 0, 380, 600])).toEqual({ left: '0.000%', top: '6.667%', width: '100.000%', height: '93.333%' });
    expect(placeIn([0, 0, 400, 600], [0, 0, 400, 600])).toEqual({ left: '0.000%', top: '0.000%', width: '100.000%', height: '100.000%' });
  });
});
