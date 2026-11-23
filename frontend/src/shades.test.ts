import { describe, expect, it } from 'vitest';
import { colourPatch, shadePatch, shadesOf } from './shades';
import type { NamedShade } from './types';

const SHADES: NamedShade[] = [
  { name: 'navy', hex: '#1f2a44', color: 'navy' },
  { name: 'sage', hex: '#a3ad8f', color: 'green' },
  { name: 'midnight', hex: '#191d2e', color: 'navy' },
  { name: 'teal', hex: '#2a6f74', color: 'green' },
];

describe('the shades of a colour', () => {
  it("offers one colour's shades at a time, in the taxonomy's order", () => {
    expect(shadesOf(SHADES, 'green').map((s) => s.name)).toEqual(['sage', 'teal']);
    expect(shadesOf(SHADES, 'navy').map((s) => s.name)).toEqual(['navy', 'midnight']);
  });

  it('offers none for a colour without shades, no colour, or shades not known', () => {
    expect(shadesOf(SHADES, 'multi')).toEqual([]);
    expect(shadesOf(SHADES, null)).toEqual([]);
    expect(shadesOf(undefined, 'green')).toEqual([]);
  });
});

describe('what a choice saves', () => {
  it('saves the colour word alone, with no colour of its own that would name a shade nobody chose (P15)', () => {
    // the server draws it in the word's own colour and names no shade until one is chosen
    expect(colourPatch('red')).toEqual({ color: 'red', color_hex: null });
    expect(colourPatch('blue')).toEqual({ color: 'blue', color_hex: null });
    expect(colourPatch('multi')).toEqual({ color: 'multi', color_hex: null });
    expect(colourPatch(null)).toEqual({ color: null, color_hex: null });
  });

  it('saves a shade with its colour word and its colour', () => {
    expect(shadePatch(SHADES[1])).toEqual({ shade: 'sage', color: 'green', color_hex: '#a3ad8f' });
  });
});
