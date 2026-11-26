/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseRoute } from './router';
import {
  addedByHand, atYourPrice, canSeeWorn, checkedWords, codeFromWords, codeWords, downWords, dropWords, type FindCode, findsInOrder, withStopped, googleShoppingLink,
  historyWords, lastChecked, linkIn, linkLine, linkWords, mostWords, newsWords, notJudgedWords, offWords, typedCode, priceWords, rangeWords,
  runDoneWords, runWords, searchWords, sharedLink, SHOP_POLL_MS, shoppingWords, shopPoll, type ShopRun, watchWords,
  webLink, wishlistAgain, wishlistWords, withinWords, isTheWish, wishIsAFind, wishTitle, titleLength,
} from './shop';
import { timeOf } from './today';

describe('shopping words', () => {
  it('shows prices in their currency', () => {
    expect(priceWords(120, 'USD')).toBe('$120.00');
    expect(priceWords(89.5, 'EUR')).toBe('€89.50');
    expect(priceWords(null, 'USD')).toBe('Price not shown');
    expect(priceWords(10, 'XX')).toBe('10.00 XX');
  });

  it('says how much a price dropped', () => {
    expect(dropWords({ from: 120, to: 96, currency: 'USD', percent: 20 })).toBe('Was $120.00, now $96.00 (20% less)');
  });

  it('puts a price range in words', () => {
    expect(rangeWords({ price_min: null, price_max: null, price_currency: null })).toBe('');
    expect(rangeWords({ price_min: 50, price_max: 150, price_currency: 'USD' })).toBe('$50.00 to $150.00');
    expect(rangeWords({ price_min: null, price_max: 90, price_currency: 'GBP' })).toBe('Up to £90.00');
    expect(rangeWords({ price_min: 40, price_max: null, price_currency: undefined })).toBe('From $40.00');
  });

  it('opens only web addresses', () => {
    expect(webLink('https://shop.example/coat')).toBe('https://shop.example/coat');
    expect(webLink('http://shop.example/')).toBe('http://shop.example/');
    expect(webLink('javascript:alert(1)')).toBeNull();
    expect(webLink('data:image/png;base64,AAAA')).toBeNull();
    expect(webLink('not a link')).toBeNull();
    expect(webLink(null)).toBeNull();
  });

});

describe('asking for the finds again', () => {
  const run = (state: 'running' | 'done' | 'failed') => ({ run: { kind: 'find' as const, state, message: null, added: null, started_at: '', finished_at: null } });
  it('asks again while a search or a price check runs, and stops once it is over', () => {
    expect(shopPoll(run('running'))).toBe(SHOP_POLL_MS);
    expect(shopPoll(run('done'))).toBe(false);
    expect(shopPoll(run('failed'))).toBe(false);
  });
  it('does not ask again when nothing was ever started, or nothing has been read', () => {
    expect(shopPoll({ run: null })).toBe(false);
    expect(shopPoll(undefined)).toBe(false);
  });
});

describe('asking for the wishlist again', () => {
  type Seen = Parameters<typeof wishlistAgain>[0];
  const page = { state: 'running', step: 'page' } as const;
  const started = { state: 'running', step: null } as const;
  const describing = { state: 'running', step: 'describe' } as const;
  const claude = { state: 'running', step: 'claude' } as const;
  const done = { state: 'done', step: 'describe' } as const;
  const failed = { state: 'failed', step: 'page' } as const;
  // [what it is, the run before (undefined: no answer yet), the run now, asked again]
  const table: [string, Seen, Seen, boolean][] = [
    ['first answer, just started', undefined, started, false],
    ['first answer, still on the page', undefined, page, false],
    ['first answer, already past the page', undefined, describing, true],
    ['first answer without a run', undefined, null, false],
    ['still on the page', page, page, false],
    ['moved from starting to the page', started, page, false],
    ['moved to describing', page, describing, true],
    ['still describing', describing, describing, false],
    ['moved to Claude reading the price', page, claude, true],
    ['moved from Claude reading the price to describing', claude, describing, true],
    ['ended', describing, done, true],
    ['failed', page, failed, true],
    ['ended before the first answer', undefined, done, true],
    ['still ended', done, done, false],
    ['ended, after an answer without a run', null, done, false],
    ['a new run past its page after one ended', done, describing, true],
  ];
  it.each(table)('%s', (_, before, now, again) => {
    expect(wishlistAgain(before, now)).toBe(again);
  });
});

describe('a product sent as a link', () => {
  it('takes the link out of whatever was shared, from url, then text, then title', () => {
    const q = (o: Record<string, string>) => `?${new URLSearchParams(o)}`;
    expect(sharedLink(q({ url: 'https://shop.example/p/1' }))).toEqual({ link: 'https://shop.example/p/1', none: false });
    // apps that put the link in the text, with words around it
    expect(sharedLink(q({ title: 'A shirt', text: 'Look at this: https://shop.example/p/2?size=m.' })))
      .toEqual({ link: 'https://shop.example/p/2?size=m', none: false });
    expect(sharedLink(q({ title: 'https://shop.example/p/3' })).link).toBe('https://shop.example/p/3');
    expect(sharedLink(q({ url: 'https://shop.example/a', text: 'https://shop.example/b' })).link).toBe('https://shop.example/a');
    // something shared with no link in it, and nothing shared at all
    expect(sharedLink(q({ text: 'A nice shirt' }))).toEqual({ link: '', none: true });
    expect(sharedLink('')).toEqual({ link: '', none: false });
  });

  it('finds a link in typed or pasted text', () => {
    expect(linkIn('  https://shop.example/p/1  ')).toBe('https://shop.example/p/1');
    expect(linkIn('(see https://shop.example/p/1)')).toBe('https://shop.example/p/1');
    expect(linkIn('http://shop.example/p')).toBe('http://shop.example/p');   // the server says why it won't open it
    expect(linkIn('shop.example/p/1')).toBe('');
    expect(linkIn(null)).toBe('');
  });

  it('says a price went down on the wish’s row, in the find’s currency', () => {
    expect(downWords({ from: 68, to: 54.4, currency: 'USD' })).toBe('Down from $68.00 to $54.40');
    expect(downWords({ from: 90, to: 72, currency: 'EUR' })).toBe('Down from €90.00 to €72.00');
  });

  it('shows the page a wish was sent as on its row', () => {
    expect(linkWords({ shop: 'Example Shop', price: 68, currency: 'USD', available: true })).toBe('$68.00 at Example Shop');
    expect(linkWords({ shop: 'Example Shop', price: null, currency: 'USD', available: true })).toBe('From Example Shop');
    expect(linkWords({ shop: 'Example Shop', price: 68, currency: 'USD', available: false })).toBe('Sold out at Example Shop');
  });

  it('says how a link’s price was read only when that is worth knowing, and never claims one it did not read', () => {
    const at = { at: 't', price: 68, currency: 'USD', available: true };
    expect(linkLine({ link: false, read_at: null, read_by: null, history: [at] })).toBeNull();
    expect(linkLine({ link: true, read_at: null, read_by: null, history: [] })).toBe('You sent this link. Its page has not been read yet.');
    expect(linkLine({ link: true, read_at: 't', read_by: null, history: [] })).toBe('You sent this link. No price could be read from its page.');
    expect(linkLine({ link: true, read_at: 't', read_by: 'page', history: [at] })).toBe('You sent this link.');
    expect(linkLine({ link: true, read_at: 't', read_by: 'claude', history: [at] })).toBe('You sent this link. Claude read its price from the page.');
  });

  it('says who is reading while it runs, and what came of it', () => {
    expect(runWords({ kind: 'link', step: 'page' })).toBe('Nines is reading the page…');
    expect(runWords({ kind: 'link', step: 'claude' })).toBe("The page doesn't show its price to Nines, so Claude is reading it…");
    // a price check is said in place of "Last checked …", under the sentence that already says Nines checks the price,
    // so it names nobody (the review of 24 November, 40)
    expect(runWords({ kind: 'prices', step: 'page' })).toBe('Checking the price…');
    expect(runWords({ kind: 'prices', step: null })).toBe('Checking the price…');
    expect(runWords({ kind: 'find' })).toBe('Claude is searching shops. This can take a few minutes…');
    expect(runWords({ kind: 'link', step: 'describe' })).toBe('Claude is describing it…');
    expect(runWords({ kind: 'prices', step: 'describe' })).toBe('Claude is describing the pages you sent…');
    const run = (r: Partial<ShopRun>): ShopRun => ({ kind: 'link', state: 'done', message: null, added: 1, started_at: '', finished_at: '', ...r });
    expect(runDoneWords(run({}), 'A shirt')).toBe('Nines read its price, and checks it again once a day.');
    expect(runDoneWords(run({ message: 'The page doesn’t give its price.', added: 0 }), 'A shirt')).toBe('The page doesn’t give its price.');
    expect(runDoneWords(run({ kind: 'find', added: 2 }), 'A coat')).toBe('Found 2 new for “A coat”');
    expect(runDoneWords(run({ kind: 'prices' }), 'A coat')).toBe('Prices checked');
    expect(runDoneWords(run({ state: 'failed' }), 'A coat')).toBe('Something went wrong while looking.');
  });

  it('is offered in the share sheet, which opens the page that takes the link', () => {
    const manifest = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'public', 'manifest.webmanifest'), 'utf8'));
    expect(manifest.share_target).toEqual({ action: '/wardrobe/link', method: 'GET', params: { title: 'title', text: 'text', url: 'url' } });
    expect(parseRoute(manifest.share_target.action)).toMatchObject({ name: 'wardrobe', link: true });
  });
});

describe('the wish page and price news', () => {
  const none = { price_min: null, price_max: null, price_currency: null };
  const most = { price_min: null, price_max: 150, price_currency: 'USD' };
  /** A moment, local time, on a day of November 2026. */
  const at = (day: number, hour = 9, minute = 5) => new Date(2026, 10, day, hour, minute).toISOString();

  it('says in one sentence what watching does, with the most you would pay when you set it', () => {
    expect(watchWords(none)).toBe("Nines checks the price once a day while it's running and tells you when it goes down.");
    expect(watchWords(most)).toBe("Nines checks the price once a day while it's running and tells you when it goes down to $150.00 or less.");
    // a lower limit an older wish still has is said until it is changed
    expect(watchWords({ price_min: 50, price_max: 150, price_currency: 'EUR' })).toBe(
      "Nines checks the price once a day while it's running and tells you when it goes down to €150.00 or less. Claude looks for ones from €50.00 to €150.00.");
  });

  it('says what Claude looks for when nothing is watched yet', () => {
    expect(searchWords(none)).toBe('Claude looks at any price.');
    expect(searchWords(most)).toBe('Claude looks for ones up to $150.00.');
    expect(searchWords({ price_min: 50, price_max: 150, price_currency: 'USD' })).toBe('Claude looks for ones from $50.00 to $150.00.');
    expect(searchWords({ price_min: 50, price_max: null, price_currency: 'USD' })).toBe('Claude looks for ones from $50.00.');
  });

  it("says the most you'd pay in one short line, and nothing when it is not set", () => {
    expect(mostWords(none)).toBeNull();
    expect(mostWords(most)).toBe("The most you'd pay is $150.00.");
    expect(mostWords({ price_min: null, price_max: 150, price_currency: 'EUR' })).toBe("The most you'd pay is €150.00.");
    // a lower limit an older wish still has is said until it is changed
    expect(mostWords({ price_min: 50, price_max: 150, price_currency: 'USD' })).toBe("You'd pay from $50.00 to $150.00.");
    expect(mostWords({ price_min: 50, price_max: null, price_currency: 'USD' })).toBe("You'd pay from $50.00.");
  });

  it('says when the prices were last looked at, whoever looked', () => {
    expect(lastChecked({ prices_checked_at: null, found_at: null, finds: [] })).toBeNull();
    expect(lastChecked({ prices_checked_at: at(20), found_at: at(18), finds: [{ read_at: at(22) }, { read_at: null }] })).toBe(at(22));
    expect(lastChecked({ prices_checked_at: at(21), found_at: null, finds: [{ read_at: at(19) }] })).toBe(at(21));
    expect(checkedWords(null)).toBe('Not checked yet.');
    expect(checkedWords(at(23), '2026-11-23')).toBe(`Last checked today at ${timeOf(at(23))}.`);
    expect(checkedWords(at(22), '2026-11-23')).toBe('Last checked yesterday.');
    expect(checkedWords(at(3), '2026-11-23')).toBe('Last checked on 3 Nov.');
  });

  it('puts the pages you sent before Claude’s finds', () => {
    const f = (id: string, link: boolean) => ({ id, link });
    expect(findsInOrder([f('a', false), f('b', true), f('c', false), f('d', true)]).map((x) => x.id)).toEqual(['b', 'd', 'a', 'c']);
  });

  it('lists what a later search finds after the finds already there, so what you read stays where it was (the review of 24 November, 41)', () => {
    const f = (id: string, link: boolean, found_at: string) => ({ id, link, found_at });
    // as the server lists them: the newest first, each search's in the order they were kept
    const listed = [f('new-a', false, '2026-11-24T10:00:00Z'), f('new-b', false, '2026-11-24T10:00:00Z'),
      f('link-new', true, '2026-11-24T09:00:00Z'), f('old-a', false, '2026-11-23T09:00:00Z'), f('link-old', true, '2026-11-22T09:00:00Z')];
    expect(findsInOrder(listed).map((x) => x.id)).toEqual(['link-old', 'link-new', 'old-a', 'new-a', 'new-b']);
  });

  it('keeps a find you stopped watching in its place until you leave, so Undo is where it was (A8)', () => {
    const f = (id: string) => ({ id, link: false });
    const shown = [f('a'), f('c')];   // what the server lists once b has gone
    expect(withStopped(shown, [{ find: f('b'), at: 1 }]).map((x) => x.id)).toEqual(['a', 'b', 'c']);
    expect(withStopped(shown, [{ find: f('d'), at: 9 }]).map((x) => x.id)).toEqual(['a', 'c', 'd']);
    // put back: listed by the server again, it is not shown twice
    expect(withStopped([f('a'), f('b'), f('c')], [{ find: f('b'), at: 1 }]).map((x) => x.id)).toEqual(['a', 'b', 'c']);
    expect(withStopped(shown, [])).toBe(shown);
  });

  it('keeps a wish from a link from calling itself added by hand while its stopped find is on the page', () => {
    const hand = { gap_id: null, link: null };
    expect(addedByHand(hand, null)).toBe(true);
    expect(addedByHand(hand, [{ link: false }])).toBe(true);
    // its only link was stopped: the server no longer gives the wish a link, but the stopped find is still shown
    expect(addedByHand(hand, [{ link: false }, { link: true }])).toBe(false);
    expect(addedByHand({ gap_id: 'g', link: null }, null)).toBe(false);
    expect(addedByHand({ gap_id: null, link: { name: 'Shirt', shop: 'Shop', price: 1, currency: 'USD', available: true } }, [])).toBe(false);
  });

  it('says how a price went only when it changed, a price for each change', () => {
    const p = (day: number, price: number | null, currency = 'USD') => ({ at: at(day), price, currency, available: true });
    expect(historyWords([], '2026-11-23')).toBeNull();
    expect(historyWords([p(20, 68), p(21, 68), p(22, null)], '2026-11-23')).toBeNull();
    expect(historyWords([p(3, 177), p(4, 177), p(17, 160), p(18, 160), p(22, 150)], '2026-11-23'))
      .toBe('The price was $177.00 on 3 Nov, $160.00 on Tuesday and $150.00 yesterday.');
    // the last three changes only
    expect(historyWords([p(1, 200), p(3, 177), p(17, 160), p(22, 150)], '2026-11-23'))
      .toBe('The price was $177.00 on 3 Nov, $160.00 on Tuesday and $150.00 yesterday.');
    expect(historyWords([p(22, 68), p(23, 54.4)], '2026-11-23')).toBe('The price was $68.00 yesterday and $54.40 today.');
    // checked again the same day: the day's last price stands for it, and a day that ends where it began is no change
    expect(historyWords([p(23, 180), { ...p(23, 144), at: at(23, 10) }], '2026-11-23')).toBeNull();
    expect(historyWords([p(22, 100), p(23, 90), { ...p(23, 100), at: at(23, 18) }], '2026-11-23')).toBeNull();
  });

  it('says on the wishlist row when a drop is within your price, never across currencies', () => {
    const drop = { from: 68, to: 54.4, currency: 'USD', percent: 20, shop: 'Example Shop' };
    expect(withinWords({ ...none, drop })).toBeNull();
    expect(withinWords({ ...most, drop })).toBe("That's within your price.");
    expect(withinWords({ ...most, price_max: 50, drop })).toBeNull();
    expect(withinWords({ ...most, price_currency: 'EUR', drop })).toBeNull();
    expect(withinWords({ ...most, drop: null })).toBeNull();
    expect(atYourPrice(most, { to: 150, currency: 'USD' })).toBe(true);
    expect(atYourPrice({ ...most, price_currency: null }, { to: 150, currency: 'USD' })).toBe(true);
  });

  it('tells the news in one sentence, counting several', () => {
    const n = { name: 'A tan rain coat', shop: 'Example Shop', from: 177, to: 150, currency: 'USD', at_price: false };
    expect(newsWords([n])).toBe('A tan rain coat is down to $150.00 at Example Shop, from $177.00.');
    expect(newsWords([{ ...n, at_price: true }])).toBe("A tan rain coat is down to $150.00 at Example Shop, from $177.00. That's within your price.");
    expect(newsWords([n, { ...n, name: 'A belt' }, n])).toBe('Prices went down for 3 things on your wishlist.');
    // a name that is a pair takes "are", as the server's sentences do
    expect(newsWords([{ ...n, name: 'Tan suede chukka boots', to: 179, from: 210 }])).toBe('Tan suede chukka boots are down to $179.00 at Example Shop, from $210.00.');
    expect(newsWords([{ ...n, name: 'A pair of black jeans' }])).toMatch(/^A pair of black jeans is down/);
  });
});

describe("the Wardrobe's row to the wishlist", () => {
  const drop = { from: 68, to: 54.4, currency: 'USD', percent: 20, shop: 'Example Shop' };

  it('says how many things are on the list', () => {
    expect(wishlistWords([])).toEqual({ count: 'Nothing on it yet', down: null });
    expect(wishlistWords([{ drop: null }])).toEqual({ count: '1 thing', down: null });
    expect(wishlistWords([{}, { drop: null }, {}])).toEqual({ count: '3 things', down: null });
  });

  it('and how many of their prices went down, as their rows in the list show', () => {
    expect(wishlistWords([{ drop }])).toEqual({ count: '1 thing', down: '1 price went down' });
    expect(wishlistWords([{ drop }, { drop: null }, { drop }])).toEqual({ count: '3 things', down: '2 prices went down' });
  });
});

describe('a checkout code', () => {
  const code = (over: Partial<FindCode> = {}): FindCode => ({ code: 'SAVE40', percent: 40, amount: null, by: 'page', seen_at: '', ...over });

  it('says the price after the code under the find’s price, and what it takes off', () => {
    expect(codeWords({ code: code(), with_code: 106.2, currency: 'USD' })).toBe('$106.20 with code SAVE40 at checkout (40% off)');
    expect(codeWords({ code: code({ code: 'TAKE20', percent: null, amount: 20 }), with_code: 157, currency: 'USD' }))
      .toBe('$157.00 with code TAKE20 at checkout ($20.00 off)');
    expect(codeWords({ code: code({ percent: 12.5 }), with_code: 154.88, currency: 'EUR' })).toBe('€154.88 with code SAVE40 at checkout (12.5% off)');
    // with no price to take it from, what it takes off
    expect(codeWords({ code: code(), with_code: null, currency: 'USD' })).toBe('Code SAVE40 takes 40% off at checkout.');
    expect(codeWords({ code: null, with_code: null, currency: 'USD' })).toBeNull();
    expect(offWords({ percent: null, amount: 15 }, 'GBP')).toBe('£15.00 off');
  });

  it('says who saw it on the page, and nothing when you typed it', () => {
    expect(codeFromWords(code())).toBe('Nines saw this code on the page.');
    expect(codeFromWords(code({ by: 'claude' }))).toBe('Claude saw this code on the page.');
    expect(codeFromWords(code({ by: 'you' }))).toBeNull();
    expect(codeFromWords(null)).toBeNull();
  });

  it('says the price after it in the drop, on the wishlist row and in the news', () => {
    expect(priceWords(106.2, 'USD', 'SAVE40')).toBe('$106.20 with code SAVE40');
    expect(priceWords(null, 'USD', 'SAVE40')).toBe('Price not shown');
    expect(dropWords({ from: 177, to: 106.2, currency: 'USD', percent: 40, code: 'SAVE40' }))
      .toBe('Was $177.00, now $106.20 with code SAVE40 (40% less)');
    expect(downWords({ from: 177, to: 106.2, currency: 'USD', code: 'SAVE40' })).toBe('Down from $177.00 to $106.20 with code SAVE40');
    expect(linkWords({ shop: 'Example Shop', price: 177, currency: 'USD', available: true, code: 'SAVE40', with_code: 106.2 }))
      .toBe('$106.20 with code SAVE40 at Example Shop');
    expect(linkWords({ shop: 'Example Shop', price: 177, currency: 'USD', available: false, code: 'SAVE40', with_code: 106.2 }))
      .toBe('Sold out at Example Shop');
    const n = { name: 'A tan rain coat', shop: 'Example Shop', from: 177, to: 106.2, currency: 'USD', at_price: true, code: 'SAVE40' };
    expect(newsWords([n])).toBe("A tan rain coat is down to $106.20 with code SAVE40 at Example Shop, from $177.00. That's within your price.");
    // within your price counts the price after the code
    const most = { price_min: null, price_max: 120, price_currency: 'USD' };
    expect(withinWords({ ...most, drop: { from: 177, to: 106.2, currency: 'USD', percent: 40, shop: 'Example Shop', code: 'SAVE40' } }))
      .toBe("That's within your price.");
  });

  it('takes a typed code upper-case with its percent or its amount, and says what is missing', () => {
    expect(typedCode(' save40 ', 'percent', '40')).toEqual({ code: 'SAVE40', percent: 40 });
    expect(typedCode('SAVE40', 'percent', '40%')).toEqual({ code: 'SAVE40', percent: 40 });
    expect(typedCode('TAKE20', 'amount', '$20')).toEqual({ code: 'TAKE20', amount: 20 });
    expect(typedCode('  ', 'percent', '40')).toBe('Type the code as the shop shows it.');
    expect(typedCode('SAVE40', 'percent', '')).toBe('Type the percent off as a number, like 40.');
    expect(typedCode('TAKE20', 'amount', 'twenty')).toBe('Type the amount off as a number, like 20.');
    // the rest is checked by Nines, which says what is wrong
    expect(typedCode('SAVE95', 'percent', '95')).toEqual({ code: 'SAVE95', percent: 95 });
  });
});

describe('a link checked against the closet, and a search on Google Shopping', () => {
  it('says in one sentence why a link is not checked against your closet', () => {
    expect(notJudgedWords({ not_judged: null }, false)).toBeNull();
    expect(notJudgedWords({ not_judged: 'unread' }, false)).toBeNull();   // the link's own line says it is not read yet
    expect(notJudgedWords({}, false)).toBeNull();
    expect(notJudgedWords({ not_judged: 'no_name' }, false)).toBe("Nines couldn't read its name from the page, so it isn't checked against your closet.");
    expect(notJudgedWords({ not_judged: 'unclear' }, false)).toBe("Claude couldn't tell what kind of piece it is, so it isn't checked against your closet.");
    expect(notJudgedWords({ not_judged: 'waiting' }, false)).toBe('Nines checks it against your closet once Claude can describe it.');
    expect(notJudgedWords({ not_judged: 'waiting' }, true)).toBe("The demo closet never sends anything to Claude, so it isn't checked against your closet.");
  });

  const look = { category: 'coat', formality: 'smart_casual', season: 'cool', weight_class: 'heavyweight', colors: ['navy', 'grey'],
    pattern: 'solid', material: 'wool', fit: 'slim', avoid_patterns: ['plaid'] };

  it('searches for the first colour and the kind of piece, and nothing else from what to look for', () => {
    expect(shoppingWords({ name: 'A warm winter coat', look_for: look })).toBe("men's navy smart casual coat");
    expect(shoppingWords({ name: 'Plain sneakers', look_for: { ...look, category: 'dress_shoes', formality: 'business', colors: [] } }))
      .toBe("men's business dress shoes");
    expect(shoppingWords({ name: 'A training tee', look_for: { ...look, category: 'tee', formality: null, colors: ['white'], kind: 'a training tee' } }))
      .toBe("men's white training tee");
  });

  it('searches for a wish with nothing to look for by its own name', () => {
    expect(shoppingWords({ name: 'Brown suede loafers', look_for: null })).toBe("men's Brown suede loafers");
    expect(shoppingWords({ name: 'A pair of white sneakers', look_for: null })).toBe("men's white sneakers");
    expect(shoppingWords({ name: "Men's linen shirt", look_for: null })).toBe("Men's linen shirt");
  });

  it('opens Google Shopping with only those words in the address', () => {
    const link = new URL(googleShoppingLink({ name: 'A warm winter coat', look_for: look }));
    expect(`${link.origin}${link.pathname}`).toBe('https://www.google.com/search');
    expect([...link.searchParams.keys()]).toEqual(['tbm', 'q']);
    expect(link.searchParams.get('tbm')).toBe('shop');
    expect(link.searchParams.get('q')).toBe("men's navy smart casual coat");
    expect(googleShoppingLink({ name: 'Shirt & tie', look_for: null })).toBe("https://www.google.com/search?tbm=shop&q=men's%20Shirt%20%26%20tie");
  });
});

describe('seeing a find with your clothes', () => {
  const piece = { category: 'coat', color: 'tan' };
  it('is offered for a judged find the check made an outfit with', () => {
    expect(canSeeWorn({ piece, verdict: 'adds', outfits: 2 })).toBe(true);
    expect(canSeeWorn({ piece, verdict: 'hard_to_wear', outfits: 0 })).toBe(false);
  });
  it('is not offered before the find is judged, or when the closet was too small to say', () => {
    expect(canSeeWorn({ piece: null, verdict: null, outfits: null })).toBe(false);
    expect(canSeeWorn({ piece, verdict: null, outfits: null })).toBe(false);
    expect(canSeeWorn({ piece, verdict: 'too_small', outfits: undefined })).toBe(false);
  });
  it('is offered for a find judged before outfits were counted', () => {
    expect(canSeeWorn({ piece, verdict: 'have_it', outfits: undefined })).toBe(true);
  });
});

describe('a wish made from one product names it once (the review of 24 November, 38)', () => {
  const whole = 'Water-repellent cotton gabardine single-breasted trench coat with a removable warm lining';
  const cut = 'Water-repellent cotton gabardine single-breasted trench…';   // as the server cuts a wish's name
  it('heads the page with the whole name when the wish has its find\'s name cut short', () => {
    expect(wishTitle({ name: cut }, [{ name: 'Navy pique polo' }, { name: whole }])).toBe(whole);
    expect(wishTitle({ name: cut }, null)).toBe(cut);
    expect(wishTitle({ name: 'A tan rain coat' }, [{ name: 'Tan gabardine rain coat' }])).toBe('A tan rain coat');
  });
  it('steps a long heading down in size, so a whole name keeps to a few lines', () => {
    expect(titleLength('A tan rain coat')).toBeNull();
    expect(titleLength('x'.repeat(40))).toBeNull();
    expect(titleLength('x'.repeat(41))).toBe('long');
    expect(titleLength(cut)).toBe('long');
    expect(titleLength('x'.repeat(71))).toBe('longer');
    expect(titleLength(whole)).toBe('longer');
    expect(titleLength(`  ${'x'.repeat(40)}  `)).toBeNull();   // the spaces around it are not letters
  });
  it('names the find by its shop and price alone when it is the wish itself', () => {
    expect(isTheWish({ name: whole }, { name: cut })).toBe(true);
    expect(isTheWish({ name: 'A plain shirt' }, { name: 'A plain shirt' })).toBe(true);
    expect(isTheWish({ name: 'Tan gabardine rain coat' }, { name: 'A tan rain coat' })).toBe(false);
    expect(isTheWish({ name: 'Water-repellent' }, { name: cut })).toBe(false);
  });
  it("knows a wish made from one of its finds, so its page does not offer to check one you found", () => {
    const linked = { name: cut, link: { name: whole } };
    // from the wishlist's row, before its finds are read
    expect(wishIsAFind(linked, undefined)).toBe(true);
    // from its finds, when the row does not carry the page's name
    expect(wishIsAFind({ name: 'A plain shirt', link: null }, [{ name: 'A plain shirt' }])).toBe(true);
    // a wish added by hand, or from a gap, with what Claude found for it
    expect(wishIsAFind({ name: 'A tan rain coat', link: null }, [{ name: 'Tan gabardine rain coat' }])).toBe(false);
    expect(wishIsAFind({ name: 'A tan rain coat' }, [])).toBe(false);
    expect(wishIsAFind({ name: 'A tan rain coat', link: { name: 'Tan gabardine rain coat' } }, undefined)).toBe(false);
  });
});
