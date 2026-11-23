import { describe, expect, it } from 'vitest';
import { againPath, allRowsLabel, aroundOffer, aroundPath, piecesFrom, removeWearName, wornInWords } from './pieceOutfits';

const TODAY = '2026-11-23';   // a Monday

describe('aroundOffer', () => {
  it('offers the button when Today can build around the piece', () => {
    expect(aroundOffer({ build_around: null })).toEqual({ button: true, line: null });
    expect(aroundOffer({})).toEqual({ button: true, line: null });
  });

  it('says in one line when it can, instead of a button that leads to no outfit', () => {
    expect(aroundOffer({ build_around: 'laundry' })).toEqual({ button: false, line: "Once it's clean, Today can build an outfit around it." });
    expect(aroundOffer({ build_around: 'away' })).toEqual({ button: false, line: "Once it's back, Today can build an outfit around it." });
    expect(aroundOffer({ build_around: 'no_category', tag_state: 'working' }).line).toBe('Once Claude has described it, Today can build an outfit around it.');
    expect(aroundOffer({ build_around: 'no_category', tag_state: 'waiting' }).line).toBe('Once Claude has described it, Today can build an outfit around it.');
    expect(aroundOffer({ build_around: 'no_category', tag_state: 'failed' }).line).toBe('Once you choose what it is, Today can build an outfit around it.');
  });

  it('offers nothing for an archived piece or a kind no outfit has a place for', () => {
    expect(aroundOffer({ build_around: 'archived' })).toEqual({ button: false, line: null });
    expect(aroundOffer({ build_around: 'not_in_outfits' })).toEqual({ button: false, line: null });
  });
});

describe('the addresses', () => {
  it('opens Today built around the piece, or wearing an outfit again as Worn does', () => {
    expect(aroundPath('a b')).toBe('/today?around=a%20b');
    expect(againPath('o1')).toBe('/today?again=o1');
  });

  it('opens a piece of an outfit where the page is', () => {
    expect(piecesFrom('/item/x')).toBe('');
    expect(piecesFrom('/today/item/x')).toBe('/today');
    expect(piecesFrom('/today/worn/item/x')).toBe('/today/worn');
    expect(piecesFrom('/wardrobe/item/x')).toBe('/wardrobe');
    expect(piecesFrom('/archived/item/x')).toBe('');
  });
});

describe('wornInWords', () => {
  it('says the day of one wear, in the wear lists\' words', () => {
    expect(wornInWords({ days: ['2026-11-22'], rating: null }, TODAY)).toBe('Yesterday');
    expect(wornInWords({ days: ['2026-11-19'], rating: null }, TODAY)).toBe('Thursday 19 Nov');
    expect(wornInWords({ days: ['2026-11-03'], rating: 'loved' }, TODAY)).toBe('3 Nov · Loved it');
  });

  it('says an outfit worn on several days once, with how often and when last', () => {
    expect(wornInWords({ days: ['2026-11-12', '2026-11-05', '2026-10-30'], rating: null }, TODAY)).toBe('3 times, last on 12 Nov');
    expect(wornInWords({ days: ['2026-11-23', '2026-11-05'], rating: 'not_again' }, TODAY)).toBe('2 times, last today · Not again');
  });
});

describe('allRowsLabel', () => {
  it('counts what is listed in the words of what it is', () => {
    expect(allRowsLabel([{ outfit_id: 'a' }, { outfit_id: 'b' }, { outfit_id: 'c' }, { outfit_id: 'd' }])).toBe('All 4 outfits');
    expect(allRowsLabel([{ outfit_id: null }, { outfit_id: null }, { outfit_id: null }, { outfit_id: null }])).toBe('All 4 wears');
    expect(allRowsLabel([{ outfit_id: 'a' }, { outfit_id: null }, { outfit_id: 'c' }, { outfit_id: 'd' }])).toBe('All 4 outfits and wears');
  });
});

describe('the days in a row\'s sheet', () => {
  it('names each wear its Remove takes away, in the wear lists\' words', () => {
    expect(removeWearName('2026-11-20', TODAY)).toBe('Remove the wear: Friday 20 Nov');
    expect(removeWearName('2026-11-06', TODAY)).toBe('Remove the wear: 6 Nov');
    expect(removeWearName('2026-11-23', TODAY)).toBe('Remove the wear: Today');
  });
});
