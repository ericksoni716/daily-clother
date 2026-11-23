import { describe, expect, it } from 'vitest';
import {
  canChoose, choiceNote, dayChoices, heldLine, loadSavedPlans, planFor, planLine, plannedFor, plannedToast, plansSoon, savePlans,
  swapLine, tripLine, tripOn, wearOn, type Plan,
} from './plans';
import type { TripSummary } from './trips';

const TODAY = '2026-11-25';   // a Wednesday

function plan(day: string): Plan {
  return { day, pieces: { base: 't', mid: null, outer: null, bottom: 'j', shoes: 's', accessories: [] }, occasion: null, mood: null,
    gone: [], created_at: '', updated_at: '' };
}

const trip = { id: 'x', place: { name: 'Lisbon, Portugal' }, first_day: '2026-11-29', last_day: '2026-12-02' } as unknown as TripSummary;

describe('the day sheet', () => {
  it('names tomorrow and the next days, marking a plan and a trip', () => {
    const days = dayChoices(TODAY, [plan('2026-11-28')], [trip]);
    expect(days.map((d) => d.label)).toEqual(['Tomorrow', 'Friday', 'Saturday', 'Sunday', 'Monday', 'Tuesday']);
    expect(days.map(choiceNote)).toEqual([null, null, 'Planned', 'Your trip to Lisbon', 'Your trip to Lisbon', 'Your trip to Lisbon']);
    expect(tripOn([trip], '2026-12-02')?.id).toBe('x');
    expect(tripOn([trip], '2026-12-03')).toBeNull();
  });

  it('takes a date of your choice after today and within reach', () => {
    expect(canChoose('2026-11-26', TODAY)).toBe(true);
    expect(canChoose(TODAY, TODAY)).toBe(false);
    expect(canChoose('2027-03-01', TODAY)).toBe(false);
    expect(canChoose('', TODAY)).toBe(false);
  });
});

describe('the words of a plan', () => {
  it('says the day by name in the button, the mark and the line', () => {
    expect(wearOn('2026-11-28', TODAY)).toBe('Wear this on Saturday');
    expect(wearOn('2026-11-26', TODAY)).toBe('Wear this tomorrow');
    expect(wearOn('2026-12-12', TODAY)).toBe('Wear this on Sat 12 Dec');
    expect(plannedFor('2026-11-26', TODAY)).toBe('Planned for tomorrow');
    expect(plannedToast('2026-11-28', TODAY)).toBe('Planned for Saturday. That morning, Today opens on it.');
    expect(planLine(TODAY, TODAY, null)).toBe('You planned this outfit for today.');
    expect(planLine(TODAY, TODAY, 'Dinner at eight')).toBe('You planned this outfit for today. “Dinner at eight”');
    expect(planLine('2026-11-28', TODAY, null)).toBe('You planned this outfit for Saturday.');
  });

  it('says which piece was swapped, and why a planned piece is not offered', () => {
    expect(swapLine([], TODAY, TODAY)).toBeNull();
    expect(swapLine([{ name: 'Oatmeal henley' }], TODAY, TODAY)).toBe("The oatmeal henley can't be worn today, so another piece takes its place.");
    expect(swapLine([{ name: 'GANT polo' }], TODAY, TODAY)).toContain('The GANT polo');
    expect(swapLine([{ name: 'white tee' }], TODAY, TODAY)).toBe("The white tee can't be worn today, so another piece takes its place.");
    expect(swapLine([{ name: 'white tee' }, { name: 'jeans' }], '2026-11-28', TODAY)).toBe("The white tee and jeans can't be worn by then, so other pieces take their places.");
    // a piece away is named with where it is (Where a piece is), the rest as before
    expect(swapLine([{ name: 'Navy blazer', away: "is at the cleaner's until Friday 27 November" }], TODAY, TODAY))
      .toBe("Your navy blazer is at the cleaner's until Friday 27 November, so another piece takes its place.");
    expect(swapLine([{ name: 'Navy blazer', away: "is at the cleaner's" }, { name: 'Blue jeans', away: 'are lent out' }, { name: 'White tee' }], TODAY, TODAY))
      .toBe("Your navy blazer is at the cleaner's and your blue jeans are lent out, so other pieces take their places. The white tee can't be worn today, so another piece takes its place.");
    expect(heldLine('2026-11-28', TODAY)).toBe('You planned this for Saturday. Wearing it now would leave it in the laundry by then.');
    expect(tripLine('Lisbon, Portugal')).toBe('This day is part of your trip to Lisbon, which has its outfit already.');
  });

  it('keeps the coming week to one line on Today', () => {
    const plans = [plan('2026-12-10'), plan('2026-11-30'), plan('2026-11-28'), plan(TODAY)];
    expect(plansSoon(plans, TODAY).map((p) => p.day)).toEqual(['2026-11-28', '2026-11-30']);
    expect(planFor(plans, TODAY)?.day).toBe(TODAY);
  });
});

describe('kept on this device', () => {
  it('gives back the plans as last read, per closet', () => {
    const store = new Map<string, string>();
    const kv = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    expect(loadSavedPlans('own', kv)).toBeNull();
    savePlans('own', [plan('2026-11-28')], kv);
    expect(loadSavedPlans('own', kv)?.map((p) => p.day)).toEqual(['2026-11-28']);
    expect(loadSavedPlans('demo', kv)).toBeNull();
  });
});
