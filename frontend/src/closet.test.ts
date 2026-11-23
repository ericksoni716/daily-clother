import { describe, expect, it } from 'vitest';
import { columnsFor, emptySentence, laundryNotice, laundryPart } from './closet';

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

describe('the laundry on the closet', () => {
  it('says how many are in it, and that none are once it is empty', () => {
    expect(laundryPart(4)).toBe('4 in the laundry');
    expect(laundryPart(0)).toBe('Nothing in the laundry');
  });

  it.each([
    [6, null, 'These 6 pieces are in the laundry.'],
    [1, null, 'This piece is in the laundry.'],
    [0, null, ''],
    [0, 6, 'You marked 6 pieces clean.'],
    [0, 1, 'You marked it clean.'],
  ])('with %i in it and %s just marked clean: "%s"', (n, cleaned, words) => {
    expect(laundryNotice(n, cleaned)).toBe(words);
  });
});

describe('what the grid says when nothing is shown', () => {
  const none = { check: false, toCheck: 0, away: false, awayNow: 0, laundry: false, inLaundry: 0, searching: false, what: false };
  it.each([
    [{ ...none, laundry: true }, 'Your laundry is empty.'],
    [{ ...none, check: true }, 'Nothing needs a check now.'],
    [{ ...none, away: true }, 'Everything is in your closet.'],
    [{ ...none, laundry: true, inLaundry: 3, searching: true }, 'Nothing matches. Try another word or filter.'],
    [{ ...none, laundry: true, searching: true }, 'Nothing matches. Try another word or filter.'],
    [{ ...none, what: true }, 'Nothing matches. Try another word or filter.'],
  ])('%o', (on, words) => {
    expect(emptySentence(on)).toBe(words);
  });
});
