import { describe, expect, it } from 'vitest';
import { ANY, chooseWhat, filtersFromSearch, filtersToSearch, NO_FILTERS, columnsFor, shortName, TILE_MIN_WIDE, emptySentence, isWhat, laundryNotice, laundryPart, matchesSearch, searchedText, searchWords, whatChoices, whatIn, whatName } from './closet';
import type { KindGroup } from './kinds';

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

describe('what a piece is: one list that opens level by level', () => {
  const groups: KindGroup[] = [
    { id: 'shirts', title: 'Shirts' }, { id: 'knitwear', title: 'Knitwear & mid layers' }, { id: 'trousers', title: 'Trousers & shorts' },
    { id: 'activewear', title: 'Activewear' }, { id: 'shoes', title: 'Shoes & boots' },
  ];
  // the demo's pieces have no kind; a few of the owner's do
  const items = [
    { group: 'trousers', category: 'jeans', kind: null, kind_name: null },
    { group: 'trousers', category: 'jeans', kind: 'selvedge_jeans', kind_name: 'Selvedge jeans' },
    { group: 'trousers', category: 'trousers', kind: 'chinos', kind_name: 'Chinos' },
    { group: 'trousers', category: 'shorts', kind: null, kind_name: null },
    { group: 'knitwear', category: 'sweater', kind: null, kind_name: null },
    { group: 'knitwear', category: 'hoodie', kind: null, kind_name: null },
    { group: 'activewear', category: 'sweater', kind: 'fleece_pullover', kind_name: 'Fleece pullover' },
    { group: 'activewear', category: 'trousers', kind: 'joggers', kind_name: 'Joggers' },
    { group: 'shirts', category: 'shirt', kind: 'oxford', kind_name: 'Oxford shirt' },
    { group: 'shirts', category: 'shirt', kind: 'flannel', kind_name: 'Flannel shirt' },
  ];
  const shown = (what: typeof ANY) => items.filter((it) => isWhat(it, what)).length;

  it('starts from the groups the closet has, in the taxonomy\'s order, and nothing under them', () => {
    const c = whatChoices(items, groups, ANY);
    expect(c.groups.map((g) => g.id)).toEqual(['shirts', 'knitwear', 'trousers', 'activewear']);
    expect(c.categories).toEqual([]);
    expect(c.kinds).toEqual([]);
  });

  it('opens a group to its categories, and its kinds where pieces have them', () => {
    const trousers = chooseWhat(ANY, 'group', 'trousers');
    const c = whatChoices(items, groups, trousers);
    expect(c.categories.map((x) => x.name)).toEqual(['Jeans', 'Shorts', 'Trousers']);
    expect(c.kinds.map((x) => x.name)).toEqual(['Chinos', 'Selvedge jeans']);
    expect(shown(trousers)).toBe(4);
    // a category narrows the kinds offered to its own; one kind is offered while some pieces are not it
    const jeans = chooseWhat(trousers, 'category', 'jeans');
    expect(shown(jeans)).toBe(2);
    expect(whatChoices(items, groups, jeans).kinds.map((x) => x.name)).toEqual(['Selvedge jeans']);
    expect(whatChoices(items, groups, chooseWhat(trousers, 'category', 'trousers')).kinds).toEqual([]);
    // a group of one category goes straight to its kinds
    const shirts = whatChoices(items, groups, chooseWhat(ANY, 'group', 'shirts'));
    expect(shirts.categories).toEqual([]);
    expect(shirts.kinds.map((x) => x.name)).toEqual(['Flannel shirt', 'Oxford shirt']);
  });

  it('never stacks two choices into nothing: another group starts again, the same one goes back up', () => {
    const jeans = chooseWhat(chooseWhat(ANY, 'group', 'trousers'), 'category', 'jeans');
    const shirts = chooseWhat(jeans, 'group', 'shirts');
    expect(shirts).toEqual({ group: 'shirts', category: null, kind: null });
    expect(shown(shirts)).toBe(2);
    expect(chooseWhat(shirts, 'group', 'shirts')).toEqual(ANY);
    expect(chooseWhat(jeans, 'category', 'jeans')).toEqual({ group: 'trousers', category: null, kind: null });
    expect(chooseWhat(jeans, 'category', 'shorts')).toEqual({ group: 'trousers', category: 'shorts', kind: null });
    const chinos = chooseWhat(chooseWhat(ANY, 'group', 'trousers'), 'kind', 'chinos');
    expect(shown(chinos)).toBe(1);
    expect(chooseWhat(chinos, 'kind', 'chinos')).toEqual({ group: 'trousers', category: null, kind: null });
  });

  it('keeps every sort of piece the three lists offered within reach', () => {
    const reach = new Set<string>();
    for (const g of whatChoices(items, groups, ANY).groups) {
      const inG = chooseWhat(ANY, 'group', g.id);
      const c = whatChoices(items, groups, inG);
      for (const x of c.kinds) reach.add(`kind:${x.id}`);
      for (const x of c.categories) {
        reach.add(`category:${x.id}`);
        for (const k of whatChoices(items, groups, chooseWhat(inG, 'category', x.id)).kinds) reach.add(`kind:${k.id}`);
      }
      // a group with one category is that category
      if (!c.categories.length) items.filter((it) => it.group === g.id).forEach((it) => reach.add(`category:${it.category}`));
    }
    for (const it of items) if (it.kind) expect(reach).toContain(`kind:${it.kind}`);
    for (const c of ['jeans', 'trousers', 'shorts', 'sweater', 'hoodie', 'shirt']) expect(reach).toContain(`category:${c}`);
  });

  it('is named by the narrowest level chosen, and lets go of what the closet no longer has', () => {
    const trousers = chooseWhat(ANY, 'group', 'trousers');
    expect(whatName(items, groups, trousers)).toBe('Trousers & shorts');
    expect(whatName(items, groups, chooseWhat(trousers, 'category', 'jeans'))).toBe('Jeans');
    expect(whatName(items, groups, chooseWhat(trousers, 'kind', 'chinos'))).toBe('Chinos');
    expect(whatIn(items, groups, { group: 'shoes', category: null, kind: null })).toEqual(ANY);
    expect(whatIn(items, groups, { group: 'trousers', category: 'jeans', kind: 'chinos' })).toEqual({ group: 'trousers', category: 'jeans', kind: null });
  });
});

describe('what the closet search finds', () => {
  const groups: KindGroup[] = [{ id: 'shirts', title: 'Shirts' }, { id: 'trousers', title: 'Trousers & shorts' }];
  const shirt = {
    name: 'Summer shirt', category: 'shirt', color: 'blue', pattern: 'solid', kind_name: 'Camp collar shirt', group: 'shirts',
    brand: 'Example Mill', material: 'Linen', shade: 'navy', own_notes: 'For the wedding in June\nRuns large',
  };
  const chinos = {
    name: 'Écru chinos', category: 'trousers', color: 'cream', pattern: null, kind_name: null, group: 'trousers',
    brand: null, material: 'Cotton twill', shade: 'off_white', own_notes: '',
  };
  const finds = (item: typeof shirt | typeof chinos, q: string) => matchesSearch(searchedText(item, groups), q);

  it.each([
    ['navy', true],            // the shade
    ['linen', true],           // the material
    ['example', true],         // the brand
    ['wedding', true],         // a word of the owner's note
    ['camp', true],            // the kind
    ['blue', true],            // the colour
    ['shirts', true],          // the group
    ['tweed', false],
  ])('finds the shirt by "%s": %s', (q, found) => {
    expect(finds(shirt, q)).toBe(found);
  });

  it('takes no notice of accents or capitals, either way round', () => {
    expect(finds(chinos, 'ecru')).toBe(true);
    expect(finds(chinos, 'ÉCRU')).toBe(true);
    expect(finds(shirt, 'NAVY Linen')).toBe(true);
    expect(searchWords('Écru, off-white')).toEqual(['ecru', 'off', 'white']);
  });

  it('needs every word typed, each found in any part of the piece', () => {
    expect(finds(shirt, 'navy linen')).toBe(true);          // the shade and the material
    expect(finds(shirt, 'linen wedding large')).toBe(true); // the material and two notes
    expect(finds(shirt, 'navy wool')).toBe(false);
    expect(finds(chinos, 'off white')).toBe(true);          // the shade in words
    expect(finds(chinos, 'off-white chinos')).toBe(true);
  });

  it('finds a word inside a longer one, and everything when nothing is typed', () => {
    expect(matchesSearch('Flannel overshirt', 'shirt')).toBe(true);
    expect(matchesSearch('Flannel overshirt', '  ')).toBe(true);
    expect(matchesSearch('Flannel overshirt', '')).toBe(true);
  });
});

describe('smaller pictures', () => {
  it('fit more to a row on a computer', () => {
    expect(columnsFor(1100, TILE_MIN_WIDE.larger, 16)).toBe(5);
    expect(columnsFor(1100, TILE_MIN_WIDE.smaller, 16)).toBe(7);
  });

  it.each([
    ['Navy polo', 'Navy polo'],
    ['Light wash jeans', 'Light wash jeans'],
    ['Heavyweight brushed cotton flannel overshirt in faded forest green', 'Heavyweight brushed…'],
    ['Grey wool trousers, pleated', 'Grey wool trousers…'],
    ['Extraordinarilylongsinglewordname', 'Extraordinarilylong…'],
    ['  Two   spaces  ', 'Two spaces'],
  ])('a small tile names "%s" as "%s"', (name, shown) => {
    expect(shortName(name, 20)).toBe(shown);
  });

  it('ends a name cut short with the one-character ellipsis the rest of the app uses', () => {
    const cut = shortName('Heavyweight brushed cotton flannel overshirt', 20);
    expect(cut.endsWith('\u2026')).toBe(true);
    expect(cut).not.toContain('...');
  });
});

describe('the search and filters in the address', () => {
  it.each([
    [{ ...NO_FILTERS }, ''],
    [{ ...NO_FILTERS, query: 'navy linen' }, '?q=navy+linen'],
    [{ ...NO_FILTERS, what: { group: 'trousers', category: 'jeans', kind: null } }, '?group=trousers&category=jeans'],
    [{ ...NO_FILTERS, query: 'écru', laundry: 'laundry' as const, check: true, away: true }, '?q=%C3%A9cru&laundry=laundry&check=1&away=1'],
  ])('%o is kept as "%s" and read back the same', (filters, search) => {
    expect(filtersToSearch(filters)).toBe(search);
    expect(filtersFromSearch(search)).toEqual(search ? filters : null);
  });

  it('reads an address that says nothing of them as nothing, and sets aside what it cannot be', () => {
    expect(filtersFromSearch('')).toBeNull();
    expect(filtersFromSearch('?signin=1')).toBeNull();
    expect(filtersFromSearch('?laundry=wet&kind=chinos')).toEqual(NO_FILTERS);
    expect(filtersFromSearch('?q=')).toEqual(NO_FILTERS);
  });
});
