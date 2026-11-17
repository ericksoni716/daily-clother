import { describe, expect, it } from 'vitest';
import { applySort, batches, choicesFor, choose, missingLine, pairs, shoeCheck, shoes, tooManyForAShoe, trayLine, valueOf, type TrayPhoto } from './addsort';

const photo = (key: string, over: Partial<TrayPhoto> = {}): TrayPhoto =>
  ({ key, file: new File(['x'], `${key}.jpg`), url: `blob:${key}`, kind: 'piece', shoe: 0, fixed: false, view: null, pair: false, ...over });

describe('one Add for everything', () => {
  it('sorts in batches of ten', () => {
    expect(batches(Array.from({ length: 23 }, (_, i) => i)).map((b) => b.length)).toEqual([10, 10, 3]);
  });

  it("lays Claude's answers on the tray, numbering shoes on from batch to batch and keeping the owner's choices", () => {
    const tray = [photo('a'), photo('b'), photo('c', { kind: 'pieces', fixed: true }), photo('d'), photo('e')];
    const sorted = applySort(tray, [
      [{ kind: 'shoe', shoe: 1 }, { kind: 'shoe', shoe: 1 }, { kind: 'piece', shoe: 0 }],
      [{ kind: 'shoe', shoe: 1 }, { kind: 'pieces', shoe: 0 }],
    ]);
    expect(sorted.map(valueOf)).toEqual(['shoe:1', 'shoe:1', 'pieces', 'shoe:2', 'pieces']);
    expect(shoes(sorted).map((s) => s.map((p) => p.key))).toEqual([['a', 'b'], ['d']]);
    expect(trayLine(sorted)).toBe('2 photos of several pieces, 2 shoes (2 + 1 photos)');
  });

  it('offers each shoe already there and a new one, and a choice by hand sticks', () => {
    const tray = [photo('a', { kind: 'shoe', shoe: 1 }), photo('b')];
    expect(choicesFor(tray).map((c) => c.label)).toEqual(['One piece', 'Several pieces', 'Shoe 1', 'Another shoe']);
    expect(choicesFor([photo('x')]).at(-1)).toEqual({ value: 'shoe:1', label: 'A shoe' });
    const b = choose(tray[1], 'shoe:1');
    expect(b).toMatchObject({ kind: 'shoe', shoe: 1, fixed: true });
    expect(applySort([tray[0], b], [[{ kind: 'piece', shoe: 0 }, { kind: 'piece', shoe: 0 }]]).map(valueOf)).toEqual(['piece', 'shoe:1']);
  });

  it('says when a shoe has more photos than it takes', () => {
    const tray = Array.from({ length: 8 }, (_, i) => photo(`p${i}`, { kind: 'shoe', shoe: 1 }));
    expect(tooManyForAShoe(tray)).toBe(2);
  });

  it("checks each shoe against the photos its drawing needs, and holds back a photo of the pair", () => {
    const tray = applySort([photo('a'), photo('b'), photo('c'), photo('d')], [[
      { kind: 'shoe', shoe: 1, view: 'outer' }, { kind: 'shoe', shoe: 1, view: 'front', pair: true },
      { kind: 'shoe', shoe: 1, view: 'inner' }, { kind: 'piece', shoe: 0 },
    ]]);
    const check = shoeCheck(shoes(tray)[0]);
    expect(check).toEqual([{ view: 'outer', have: true }, { view: 'front', have: false }, { view: 'inner', have: true }]);
    expect(missingLine(check)).toBe('No photo of the front yet. It can be added without, but the drawing is better with it.');
    expect(pairs(tray).map((p) => p.key)).toEqual(['b']);
    expect(missingLine(shoeCheck([photo('x', { kind: 'shoe', shoe: 1, view: 'outer' })]))).toBe(
      'No photo of the front and inner side yet. It can be added without, but the drawing is better with them.');
    expect(missingLine(shoeCheck(tray.slice(0, 1).concat([photo('f', { kind: 'shoe', shoe: 1, view: 'front' }), tray[2]])))).toBeNull();
  });
});
