import { describe, expect, it } from 'vitest';
import { alsoThought, groupsIn, kindDrawing, kindLine, kindsIn, kindsOf, searchKinds, type KindCatalogue } from './kinds';

// a slice of the catalogue GET /api/kinds answers (backend/closet/kinds.py), words as it writes them
const catalogue: KindCatalogue = {
  groups: [
    { id: 'shirts', title: 'Shirts' }, { id: 'tees', title: 'Tees & polos' }, { id: 'trousers', title: 'Trousers & shorts' },
    { id: 'activewear', title: 'Activewear' }, { id: 'shoes', title: 'Shoes & boots' }, { id: 'accessories', title: 'Accessories' },
  ],
  kinds: [
    { id: 't_shirt', name: 'T-shirt', group: 'tees', category: 'tee', words: 't shirt t shirt crew neck tee tshirt tees polos', drawn: true },
    { id: 'western_shirt', name: 'Western shirt', group: 'shirts', category: 'shirt',
      words: 'western shirt pointed yokes pearl snaps smile pockets 3 snap cuffs shirts snap', drawn: true },
    { id: 'chinos', name: 'Chinos', group: 'trousers', category: 'trousers', words: 'chinos khakis pants trousers shorts', drawn: true },
    { id: 'fleece_pullover', name: 'Fleece pullover', group: 'activewear', category: 'sweater',
      words: 'fleece pullover fleece with stand collar and contrast nylon pocket fleece activewear', drawn: true },
    { id: 'joggers', name: 'Joggers', group: 'activewear', category: 'trousers', words: 'joggers tapered ribbed ankle cuffs sweatpants', drawn: true },
    { id: 'chelsea_boot', name: 'Chelsea boot', group: 'shoes', category: 'boots', words: 'chelsea boot elastic side gussets shoe shoes', drawn: true },
    { id: 'running_shoe', name: 'Running shoe', group: 'shoes', category: 'sneakers', words: 'running shoe trainers sneakers shoe shoes runner', drawn: true },
    { id: 'beanie', name: 'Beanie', group: 'accessories', category: 'hat', words: 'beanie ribbed knit cuffed hat toque accessories', drawn: false },
  ],
};
const ids = (q: string) => searchKinds(catalogue, q).map((k) => k.id);

describe('searching the kinds', () => {
  it('finds kinds by the start of a word of their name', () => {
    expect(ids('chelsea')).toEqual(['chelsea_boot']);
    expect(ids('jogger')).toEqual(['joggers']);
    expect(ids('Fleece')).toEqual(['fleece_pullover']);
  });

  it('finds them by the words of their signature and the common words they go by', () => {
    expect(ids('snap')).toEqual(['western_shirt']);
    expect(ids('trainers')).toEqual(['running_shoe']);
    expect(ids('tee')).toEqual(['t_shirt']);
    expect(ids('hat')).toEqual(['beanie']);
  });

  it('puts the kinds found by their name first, and needs every word typed', () => {
    expect(ids('shirt')).toEqual(['t_shirt', 'western_shirt']);
    expect(ids('sweatpants')).toEqual(['joggers']);
    expect(ids('running trainers')).toEqual(['running_shoe']);
    expect(ids('running jeans')).toEqual([]);
    expect(ids('  ')).toEqual([]);
  });
});

describe('the groups', () => {
  it("are the catalogue's, and a group holds the kinds the catalogue puts in it", () => {
    expect(kindsIn(catalogue, 'activewear').map((k) => k.id)).toEqual(['fleece_pullover', 'joggers']);
    expect(kindsIn(catalogue, 'shoes').map((k) => k.id)).toEqual(['chelsea_boot', 'running_shoe']);
  });

  it('say an item as its kind and group', () => {
    expect(kindLine({ kind_name: 'Fleece pullover', group: 'activewear' }, catalogue.groups)).toBe('Fleece pullover · Activewear');
    expect(kindLine({ kind_name: null, group: 'tees' }, catalogue.groups)).toBe('Tees & polos');
    expect(kindLine({ kind_name: null, group: null }, catalogue.groups)).toBe('');
  });

  it("offer the closet's groups and kinds as filters", () => {
    const items = [
      { kind: 'joggers', kind_name: 'Joggers', group: 'activewear' },
      { kind: 'fleece_pullover', kind_name: 'Fleece pullover', group: 'activewear' },
      { kind: null, kind_name: null, group: 'tees' },
      { kind: 'chelsea_boot', kind_name: 'Chelsea boot', group: 'shoes' },
    ];
    expect(groupsIn(items, catalogue.groups).map((g) => g.id)).toEqual(['tees', 'activewear', 'shoes']);
    expect(kindsOf(items, 'activewear').map((k) => k.name)).toEqual(['Fleece pullover', 'Joggers']);
    expect(kindsOf(items, null)).toHaveLength(3);
  });
});

describe('a kind', () => {
  it("is drawn in the item's colour when it has one", () => {
    expect(kindDrawing('fleece_pullover', '#33AA66')).toBe('/api/kinds/fleece_pullover.svg?color=%2333aa66');
    expect(kindDrawing('fleece_pullover', 'navy')).toBe('/api/kinds/fleece_pullover.svg');
    expect(kindDrawing('fleece_pullover', null)).toBe('/api/kinds/fleece_pullover.svg');
  });

  it("Claude also thought of: the kinds it named, without the item's kind now", () => {
    expect(alsoThought(catalogue, ['joggers', 'chinos', 'toga'], 'chinos').map((k) => k.id)).toEqual(['joggers']);
    expect(alsoThought(catalogue, undefined, null)).toEqual([]);
  });
});
