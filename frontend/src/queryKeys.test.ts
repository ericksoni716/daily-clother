import { describe, expect, it } from 'vitest';
import { queryKeys, touched, TOUCHES, type KeyName } from './queryKeys';

// One call of each key function, with made-up arguments.
const SAMPLE: { [K in KeyName]: () => readonly unknown[] } = {
  items: () => queryKeys.items('active'),
  progress: () => queryKeys.progress(),
  item: () => queryKeys.item('i1'),
  itemDetails: () => queryKeys.itemDetails('i1', 'collar'),
  history: () => queryKeys.history('i1'),
  vocab: () => queryKeys.vocab(),
  kinds: () => queryKeys.kinds(),
  review: () => queryKeys.review(),
  sources: () => queryKeys.sources(),
  source: () => queryKeys.source('s1'),
  today: () => queryKeys.today({} as Parameters<typeof queryKeys.today>[0]),
  styleAnswer: () => queryKeys.styleAnswer('a1'),
  day: () => queryKeys.day(),
  weather: () => queryKeys.weather(),
  figure: () => queryKeys.figure({} as Parameters<typeof queryKeys.figure>[0]),
  worn: () => queryKeys.worn('2026-01-01'),
  trips: () => queryKeys.trips(),
  trip: () => queryKeys.trip('t1'),
  tripWeather: () => queryKeys.tripWeather('t1'),
  gaps: () => queryKeys.gaps(),
  wishlist: () => queryKeys.wishlist(),
  finds: () => queryKeys.finds('w1'),
  findOutfits: () => queryKeys.findOutfits('w1', 'f1'),
  news: () => queryKeys.news(),
  wouldWork: () => queryKeys.wouldWork('c1'),
  insights: () => queryKeys.insights(),
  picks: () => queryKeys.picks(),
  settings: () => queryKeys.settings(),
  pictures: () => queryKeys.pictures(),
  styleProfile: () => queryKeys.styleProfile(),
  styleTalk: () => queryKeys.styleTalk(),
  storage: () => queryKeys.storage(),
  tagging: () => queryKeys.tagging(),
  spend: () => queryKeys.spend(),
  model: () => queryKeys.model(),
  updates: () => queryKeys.updates(),
  restoreNotice: () => queryKeys.restoreNotice(),
  places: () => queryKeys.places('lis'),
  placeNear: () => queryKeys.placeNear(1, 2),
};

describe('query keys', () => {
  it('each key starts with its own name, so a name in TOUCHES covers every key that function makes', () => {
    expect(Object.keys(SAMPLE).sort()).toEqual(Object.keys(queryKeys).sort());
    for (const [name, make] of Object.entries(SAMPLE)) expect(make()[0]).toBe(name);
  });

  it('a key with an argument differs by that argument, and one detail sits under its item’s details', () => {
    expect(queryKeys.item('a')).not.toEqual(queryKeys.item('b'));
    expect(queryKeys.items('active')).not.toEqual(queryKeys.items('archived'));
    expect(queryKeys.itemDetails('a', 'collar').slice(0, 2)).toEqual(queryKeys.itemDetails('a'));
    expect(queryKeys.worn()).toEqual(['worn', null]);
  });
});

describe('TOUCHES', () => {
  it('names only keys that exist', () => {
    const names = new Set(Object.keys(queryKeys));
    for (const [kind, keys] of Object.entries(TOUCHES)) {
      for (const key of keys) expect(names.has(key), `${kind} touches ${key}`).toBe(true);
    }
  });

  it('never makes today stale: asking for it again can ask Claude', () => {
    for (const keys of Object.values(TOUCHES)) expect(keys as readonly string[]).not.toContain('today');
  });

  it('an item edit makes its details, history and the review queue stale; touched leaves out what the save wrote', () => {
    expect(touched('item')).toEqual(expect.arrayContaining(['items', 'item', 'itemDetails', 'history', 'review']));
    expect(touched('item', ['items', 'item'])).not.toEqual(expect.arrayContaining(['items']));
    expect(touched('item', ['items', 'item'])).toContain('itemDetails');
  });
});
