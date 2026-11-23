import { describe, expect, it } from 'vitest';
import { brandLine, sizesLine, suggestionLine } from './sizes';
import type { SizeEntry, SizeKind, Sizes } from './types';

const entry = (kind: SizeKind, label: string, size: string | null, suggested: string | null = null): SizeEntry =>
  ({ kind, label, size, suggested, brands: [] });

const sizes = (...kinds: SizeEntry[]): Sizes => ({ kinds, max_size: 20, max_brand: 40, max_brands: 10 });

describe('your sizes', () => {
  it('sums up the saved sizes in one line, in order, each with its kind', () => {
    expect(sizesLine(sizes(entry('tops', 'Tops', 'M'), entry('knitwear', 'Knitwear', null, 'L'),
      entry('trousers', 'Trousers and jeans', '32x32'), entry('shoes', 'Shoes', '10.5')))).toBe('Your sizes: M tops · 32x32 trousers · 10.5 shoes');
  });

  it('says when none is saved, and never counts a suggestion as saved', () => {
    expect(sizesLine(sizes(entry('tops', 'Tops', null, 'M')))).toBe('Your sizes are not saved yet.');
    expect(sizesLine(undefined)).toBe('Your sizes are not saved yet.');
  });

  it('offers the size most of your pieces carry only while none is saved', () => {
    expect(suggestionLine(entry('trousers', 'Trousers and jeans', null, '32x32'))).toBe('The size on most of your trousers and jeans is 32x32.');
    expect(suggestionLine(entry('tops', 'Tops', 'L', 'M'))).toBeNull();
    expect(suggestionLine(entry('tops', 'Tops', null))).toBeNull();
  });

  it('says a brand that fits differently', () => {
    expect(brandLine({ brand: 'Example Brand', size: 'L' })).toBe('In Example Brand, L');
  });
});
