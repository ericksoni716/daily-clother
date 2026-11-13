import { describe, expect, it } from 'vitest';
import { packingProgress, sortTrips, type Trip, type TripPreview } from './trips';

describe('packing progress', () => {
  const plan: TripPreview['plan'] = {
    packing: { tops: [{ id: 'shirt', name: 'Shirt', days_worn: 2, pinned: false }], shoes: [] },
    basics: [{ id: 'socks', name: 'Pairs of socks', count: 6 }],
    days: [], uncovered: [], notes: [], piece_count: 1,
  };
  it('counts packing lines, not quantities or old ticks', () => {
    expect(packingProgress({ plan, choices: {} as TripPreview['choices'], checked: {
      'item:shirt': true, 'basic:socks': false, 'item:removed': true,
    } })).toEqual({ total: 2, packed: 1 });
  });
  it('starts a preview unticked', () => {
    expect(packingProgress({ plan, choices: {} as TripPreview['choices'] })).toEqual({ total: 2, packed: 0 });
  });
  it('keeps upcoming trips first even after editing a past trip offline copy', () => {
    const trip = (id: string, first: string, last: string) => ({
      id, choices: { first_day: first, last_day: last },
    } as Trip);
    const sorted = sortTrips([trip('past', '2026-01-01', '2026-01-03'), trip('later', '2026-12-01', '2026-12-03'),
      trip('ongoing', '2026-11-12', '2026-11-15')], '2026-11-13');
    expect(sorted.map((t) => t.id)).toEqual(['ongoing', 'later', 'past']);
  });
});
