import { describe, expect, it } from 'vitest';
import { columnsFor } from './closet';

describe('how many tiles to a row on a computer', () => {
  it.each([
    // width, smallest tile, gap → tiles
    [1100, 180, 16, 5],
    [1000, 180, 16, 5],
    [964, 180, 16, 5],
    [963, 180, 16, 4],
    [180, 180, 16, 1],
    [100, 180, 16, 1],
    [1100, 130, 16, 7],
    [0, 180, 16, 1],
  ])('%ipx wide with tiles of at least %ipx and %ipx between gives %i', (width, min, gap, cols) => {
    expect(columnsFor(width, min, gap)).toBe(cols);
  });
});
