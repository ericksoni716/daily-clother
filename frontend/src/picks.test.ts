import { describe, expect, it } from 'vitest';
import {
  BEFORE_BY_CLAUDE, cardState, DEMO, IN_STOCK, LOOK_SENDS, LOOKING, lookCostWords, NEVER_LOOKED, offerWords, pickName,
  picksOf, picksPoll, PICKS_POLL_MS, SALE_NEVER, SALE_NOTHING, saleNote, salePriceLine, savedPicks, savedView, savePicks,
  saveView, SHOPS_OFFER, shopLine, shopsLine, THIN, verdictLine, VIEW_OPTIONS, withRefused, type PicksAnswer, type ShopPick,
  offersPicks, PICK_NAME_MAX, PICK_NAME_BARE_MAX,
} from './picks';
import { dropWords, SALE_SENDS, SEARCH_SENDS } from './shop';

const pick = (changes: Partial<ShopPick> = {}): ShopPick => ({
  id: 'p1', kind: 'taste', source: 'look', name: 'Olive chore coat', shop: 'Example Shop', url: 'https://shop.example/p',
  image_url: null, price: 148, price_before: null, currency: 'USD',
  piece: { category: 'jacket', color: 'olive' } as ShopPick['piece'], verdict: 'adds',
  verdict_words: 'Works, and adds something', pairs: 6, found_at: '2026-11-23T10:00:00Z', state: 'shown', wish_id: null,
  ...changes,
});

const answer = (changes: Partial<PicksAnswer> = {}): PicksAnswer => ({
  picks: [], run: null, last: null, looked: false, weekly: false, enough: true, demo: false,
  estimate: { api: false, look_usd: 0.17 }, offer: null, ...changes,
});

describe('You might like', () => {
  it('shows one state at a time: the demo, a look running, the picks, too little to go on, never looked, nothing found', () => {
    expect(cardState(answer({ demo: true, picks: [pick()] }))).toBe('demo');
    const running = { source: 'look' as const, state: 'running' as const, message: null, added: null, started_at: '', finished_at: null };
    expect(cardState(answer({ run: running, picks: [pick()] }))).toBe('looking');
    expect(cardState(answer({ picks: [pick()], enough: false }))).toBe('list');
    expect(cardState(answer({ enough: false }))).toBe('thin');
    expect(cardState(answer())).toBe('never');
    expect(cardState(answer({ looked: true }))).toBe('nothing');
    expect(picksPoll(answer({ run: running }))).toBe(PICKS_POLL_MS);
    expect(picksPoll(answer())).toBe(false);
  });

  it('says each state in one sentence, in the words used elsewhere', () => {
    for (const s of [NEVER_LOOKED, THIN, DEMO]) expect(s.split(/(?<=\.) /)).toHaveLength(s === DEMO ? 2 : 1);
    expect(THIN).toBe('Wear and rate a few more pieces and Nines can look for things you might like.');
    expect(LOOKING).toBe('Claude is searching shops. This can take a few minutes…');
    // what a look sends is the search's sentence without the wish, and where a look for sales starts: one wording
    expect(LOOK_SENDS).toBe(`${SEARCH_SENDS.replace('A search sends Claude the wish, ', 'A look sends Claude ')} ${SALE_SENDS}`);
    expect(SALE_SENDS).toBe('A look for things on sale also sends the shops you like and the shops you found things at before.');
    expect(lookCostWords({ api: true, look_usd: 0.1734 })).toBe("If your plan can't be used, a look costs about $0.17 at most with the API key.");
    expect(lookCostWords({ api: false, look_usd: 0.17 })).toBeNull();
  });

  it('says a pick in a few words', () => {
    expect(shopLine(pick())).toBe('Example Shop · $148.00');
    expect(shopLine(pick({ price: null }))).toBe('Example Shop');
    expect(verdictLine(pick())).toBe('Goes with 6 of your pieces.');
    expect(verdictLine(pick({ pairs: 1 }))).toBe('Goes with one of your pieces.');
    expect(verdictLine(pick({ verdict: 'fills_gap' }))).toBe('Fills a gap in your closet.');
    expect(verdictLine(pick({ pairs: 0, verdict: 'too_small', verdict_words: 'Not enough in the closet to say' })))
      .toBe('Not enough in the closet to say');
    const long = 'Garment-dyed heavyweight cotton canvas chore jacket with four patch pockets and corozo buttons';
    expect(pickName(long)).toBe('Garment-dyed heavyweight cotton…');
    expect(pickName('  Olive   chore coat ')).toBe('Olive chore coat');
  });

  it('offers a line for Your style with the conversation’s words', () => {
    const o = { id: 'o1', text: 'Nothing bright.', said: 'You passed on three bright colours.', state: 'offered' as const };
    expect(offerWords(o)).toEqual({ question: 'You passed on three bright colours. Keep this in Your style?',
      save: 'Save to Your style', saved: 'Saved to Your style.' });
  });

  it('keeps a pick turned down in its place for Undo, until the server lists it again', () => {
    const [a, b, c] = [pick({ id: 'a' }), pick({ id: 'b' }), pick({ id: 'c' })];
    expect(withRefused([a, c], { pick: b, index: 1 }).map((p) => [p.id, p.state])).toEqual([['a', 'shown'], ['b', 'refused'], ['c', 'shown']]);
    expect(withRefused([a, b, c], { pick: b, index: 1 })).toEqual([a, b, c]);
    expect(withRefused([a], null)).toEqual([a]);
  });

  it('keeps what it last showed on this device, without a look in progress', () => {
    const store = new Map<string, string>();
    const kv = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    const running = { source: 'look' as const, state: 'running' as const, message: null, added: null, started_at: '', finished_at: null };
    savePicks('main', answer({ picks: [pick()], run: running }), kv, new Date('2026-11-23T10:00:00Z'));
    const saved = savedPicks('main', kv);
    expect(saved?.savedAt).toBe('2026-11-23T10:00:00.000Z');
    expect(saved?.data.picks).toHaveLength(1);
    expect(saved?.data.run).toBeNull();
    expect(savedPicks('demo', kv)).toBeNull();
  });
});

describe('On sale', () => {
  const sale = (changes: Partial<ShopPick> = {}) => pick({
    id: 's1', kind: 'sale', price: 84, price_before: 120, before_by: 'page', in_stock: null, ...changes,
  });
  const running = (kind: 'taste' | 'sale') => ({ source: 'look' as const, kind, state: 'running' as const, message: null,
    added: null, started_at: '', finished_at: null });
  const views = (taste: boolean, onSale: boolean) => ({ taste: { looked: taste, last: null }, sale: { looked: onSale, last: null } });

  it('says a sale row in the wishlist words, with the size and who read the earlier price', () => {
    expect(salePriceLine(sale())).toBe('Was $120.00, now $84.00 (30% less)');
    expect(salePriceLine(sale())).toBe(dropWords({ from: 120, to: 84, currency: 'USD', percent: 30 }));
    expect(salePriceLine(pick())).toBeNull();
    expect(salePriceLine(sale({ price_before: 84 }))).toBeNull();
    expect(shopLine(sale())).toBe('Example Shop');   // its prices have their own line
    expect(saleNote(sale())).toBeNull();
    expect(saleNote(sale({ in_stock: true }))).toBe(IN_STOCK);
    expect(saleNote(sale({ before_by: 'claude' }))).toBe(BEFORE_BY_CLAUDE);
    expect(saleNote(sale({ in_stock: true, before_by: 'claude' })))
      .toBe('Your size is in stock. Claude read the earlier price from the page.');
    expect(saleNote(pick({ in_stock: true }))).toBeNull();
  });

  it('shows each view its own picks and its own state', () => {
    const both = answer({ picks: [pick(), sale()], views: views(true, true) });
    expect(picksOf(both.picks, 'sale').map((p) => p.id)).toEqual(['s1']);
    expect(cardState(both, 'sale')).toBe('list');
    expect(cardState(answer({ picks: [pick()], looked: true, views: views(true, false) }), 'sale')).toBe('never');
    expect(cardState(answer({ looked: true, views: views(false, true) }), 'sale')).toBe('nothing');
    expect(cardState(answer({ looked: true, views: views(false, true) }), 'taste')).toBe('never');
    // a look runs in its own view; the other shows what it has
    expect(cardState(answer({ picks: [pick()], run: running('sale'), views: views(true, true) }), 'sale')).toBe('looking');
    expect(cardState(answer({ picks: [pick()], run: running('sale'), views: views(true, true) }), 'taste')).toBe('list');
    expect(cardState(answer({ enough: false }), 'sale')).toBe('thin');
    expect(cardState(answer({ demo: true }), 'sale')).toBe('demo');
    expect(VIEW_OPTIONS.map((o) => o.label)).toEqual(['For you', 'On sale']);
  });

  it('says each sale state in one sentence', () => {
    for (const s of [SALE_NEVER, SALE_NOTHING, SHOPS_OFFER]) expect(s.split(/(?<=\.) /)).toHaveLength(1);
    expect(shopsLine(undefined)).toBe('You have not named any shops you like yet.');
    expect(shopsLine({ shops: [{ name: 'Example Shop' }, { name: 'shop.example' }] })).toBe('Shops you like: Example Shop · shop.example');
  });

  it('remembers the view on this device', () => {
    const kept = new Map<string, string>();
    const kv = { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => void kept.set(k, v) };
    expect(savedView(kv)).toBe('taste');
    saveView('sale', kv);
    expect(savedView(kv)).toBe('sale');
    expect(savedView(null)).toBe('taste');
  });
});

describe('the review of 24 November', () => {
  it('offers no You might like card while the closet is empty (55)', () => {
    expect(offersPicks({ checked: { items: 0 } })).toBe(false);
    expect(offersPicks({ checked: { items: 3 } })).toBe(true);
  });
  it('gives a name beside a hanger three lines, so the kind of piece is not cut off (44)', () => {
    const trench = 'Water-repellent cotton gabardine single-breasted trench coat with a removable warm lining';
    expect(pickName(trench, PICK_NAME_MAX)).not.toContain('coat');
    expect(pickName(trench, PICK_NAME_BARE_MAX)).toContain('trench coat');
    expect(pickName('Garment-dyed heavyweight cotton canvas chore jacket with four patch pockets and corozo buttons', PICK_NAME_BARE_MAX))
      .toContain('chore jacket');
  });
});
