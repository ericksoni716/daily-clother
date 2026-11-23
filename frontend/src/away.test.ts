import { describe, expect, it } from 'vitest';
import { awayOrder, awayPart, backByWearing, cameBackSentence, homeSentence, recordedSentence, whenBack, whereSentence } from './away';
import type { ItemSummary } from './types';
import { calendarDay, sinceDay } from './wears';

// Monday 23 November 2026
const TODAY = '2026-11-23';

const piece = (id: string, away: ItemSummary['away'], name = id) => ({ id, name, away }) as ItemSummary;

describe('the days', () => {
  it('says a day ahead with its weekday, and a day gone short', () => {
    expect(calendarDay('2026-11-27', TODAY)).toBe('Friday 27 Nov');
    expect(calendarDay('2027-01-08', TODAY)).toBe('Friday 8 Jan 2027');
    expect(sinceDay('2026-11-03', TODAY)).toBe('3 Nov');
    expect(sinceDay(TODAY, TODAY)).toBe('today');
    expect(sinceDay('2026-11-22', TODAY)).toBe('yesterday');
    expect(sinceDay('2025-12-30', TODAY)).toBe('30 Dec 2025');
  });
});

describe('where a piece is', () => {
  it('says where it is and until when, in a sentence', () => {
    expect(whereSentence({ place: 'cleaner', since: '2026-11-20', until: '2026-11-27' }, TODAY)).toBe("At the cleaner's until Friday 27 Nov");
    expect(whereSentence({ place: 'lent', since: '2026-11-03', until: null }, TODAY)).toBe('Lent out since 3 Nov');
    expect(whereSentence({ place: 'tailor', since: '2026-11-10', until: '2026-11-20' }, TODAY))
      .toBe("At the tailor's since 10 Nov, expected back on Friday 20 Nov");
    expect(whereSentence({ place: 'cleaner', since: TODAY, until: TODAY }, TODAY)).toBe("At the cleaner's until Monday 23 Nov");
  });

  it('says when it is expected on a tile', () => {
    expect(whenBack({ place: 'cleaner', since: '2026-11-20', until: '2026-11-27' }, TODAY)).toBe('Until Friday 27 Nov');
    expect(whenBack({ place: 'cleaner', since: '2026-11-10', until: '2026-11-20' }, TODAY)).toBe('Expected back on Friday 20 Nov');
    expect(whenBack({ place: 'lent', since: '2026-11-03', until: null }, TODAY)).toBe('Since 3 Nov');
  });

  it('says a piece at home, and one that needs mending', () => {
    expect(homeSentence('good')).toBe('In your closet');
    expect(homeSentence('needs_repair')).toBe('In your closet, waiting to be mended');
  });

  it('says what coming back did', () => {
    expect(cameBackSentence({ from: 'cleaner', on: TODAY, by: 'owner', mended: false })).toBe("Back from the cleaner's, and marked clean");
    expect(cameBackSentence({ from: 'tailor', on: TODAY, by: 'owner', mended: true }))
      .toBe("Back from the tailor's, and no longer marked as needing mending");
    expect(cameBackSentence({ from: 'tailor', on: TODAY, by: 'owner', mended: false })).toBe("Back from the tailor's");
    expect(cameBackSentence({ from: 'lent', on: TODAY, by: 'wear', mended: false })).toBe("You wore it today, so it's back from being lent out");
  });
});

describe('the closet', () => {
  it('lists the pieces away soonest first, the ones with no day last', () => {
    const list = [piece('a', { place: 'lent', since: '2026-11-01', until: null }), piece('b', null),
      piece('c', { place: 'cleaner', since: '2026-11-20', until: '2026-11-27' }),
      piece('d', { place: 'tailor', since: '2026-11-10', until: '2026-11-20' })];
    expect(awayOrder(list).map((p) => p.id)).toEqual(['d', 'c', 'a']);
  });

  it('counts them for the line over the grid, with those past their day', () => {
    const late = piece('d', { place: 'tailor', since: '2026-11-10', until: '2026-11-20' });
    const soon = piece('c', { place: 'cleaner', since: '2026-11-20', until: '2026-11-27' });
    expect(awayPart([soon], TODAY)).toBe('1 away');
    expect(awayPart([soon, late], TODAY)).toBe('2 away, 1 expected back');
  });
});

describe('wearing it anyway', () => {
  it('brings back only what is away, and only for today', () => {
    const list = [piece('a', { place: 'lent', since: '2026-11-01', until: null }), piece('b', null)];
    expect(backByWearing(list, TODAY, TODAY).map((p) => p.id)).toEqual(['a']);
    expect(backByWearing(list, '2026-11-20', TODAY)).toEqual([]);
    expect(recordedSentence([])).toBe('Outfit recorded');
    expect(recordedSentence(['the grey suit'])).toBe('Outfit recorded. The grey suit is back in your closet.');
    expect(recordedSentence(['the grey suit', 'the brown shoes'])).toBe('Outfit recorded. The grey suit and the brown shoes are back in your closet.');
  });
});
