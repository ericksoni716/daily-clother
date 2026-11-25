/** Shopping for a wish: the products Claude found and the pages the owner sent, their prices, the news when one went
 * down, and plain words for them. */
import { beFor, kindWords, type Wish } from './gaps';
import { plural } from './insights';
import { label } from './labels';
import { readAmount } from './spend';
import { SAVED_PREFIX, timeOf } from './today';
import { localDay, whenWorn } from './wears';
import type { Verdict, WouldExample, WouldPiece } from './wouldwork';

export interface PricePoint {
  at: string;
  price: number | null;
  currency: string;
  available: boolean;
  /** The price after the checkout code it was seen with, and that code; null with no code. */
  with_code?: number | null;
  code?: string | null;
}

export interface PriceDrop {
  from: number;
  to: number;
  currency: string;
  percent: number;
  /** The checkout code the price it is down to is after, when it is. */
  code?: string;
}

/** A find's checkout code: a percent or an amount off, read from its page by Nines, seen there by Claude, or typed by
 * you. */
export interface FindCode {
  code: string;
  percent: number | null;
  amount: number | null;
  by: 'page' | 'claude' | 'you';
  seen_at: string;
}

export interface Find {
  id: string;
  wish_id: string;
  name: string;
  shop: string;
  url: string;
  image_url: string | null;
  price: number | null;
  currency: string;
  available: boolean;
  /** Sent by the owner as a link: its page is read by Nines first, then Claude describes it from the page's words. */
  link: boolean;
  /** When Nines last read the page itself (a link only), whatever it found. */
  read_at: string | null;
  /** How the latest price was read: from the page's own data, or by Claude. */
  read_by: 'page' | 'claude' | null;
  /** Its description in the closet's words; null for a link Claude has not described. */
  piece: WouldPiece | null;
  piece_words: string | null;
  verdict: Verdict | null;
  verdict_words: string | null;
  reasons: string[];
  checked_at: string | null;
  /** How many example outfits the check made with it when it was judged; null when judged before they were counted. */
  outfits?: number | null;
  /** Why a link is not judged against the closet yet: its page not read, the page gave no name, Claude could not tell
   * what it is, or Claude has not been asked yet. Null when it is judged. */
  not_judged?: 'unread' | 'no_name' | 'unclear' | 'waiting' | null;
  found_at: string;
  updated_at: string;
  history: PricePoint[];
  drop: PriceDrop | null;
  /** Its checkout code, and the price after it (worked out by Nines; null when it has no price, or an amount off is
   * no longer less than it). */
  code: FindCode | null;
  with_code: number | null;
}

export interface ShopRun {
  kind: 'find' | 'prices' | 'link';
  state: 'running' | 'done' | 'failed';
  /** Who is reading now: Nines, on the shops' own pages, or Claude (reading a price, or describing a page you sent). */
  step?: 'page' | 'claude' | 'describe' | null;
  message: string | null;
  added: number | null;
  started_at: string;
  finished_at: string | null;
}

export interface FindsAnswer {
  wish_id: string;
  finds: Find[];
  run: ShopRun | null;
  found_at: string | null;
  prices_checked_at: string | null;
  demo: boolean;
  estimate: { api: boolean; find_usd: number; prices_usd: number };
}

export const SHOP_POLL_MS = 2000;

/** How often a wish's finds are asked for again: while a search or a price check runs, and not at all otherwise. Only
 * the owner starts one (a search costs money), so asking again never starts anything. */
export function shopPoll(answer: Pick<FindsAnswer, 'run'> | null | undefined): number | false {
  return answer?.run?.state === 'running' ? SHOP_POLL_MS : false;
}

/**
 * Whether the wishlist (where a wish's name and its row's price come from) is asked for again, from the run in the
 * finds answer before (`undefined` when there was no answer yet, null when it had no run) and now: as soon as the run
 * moves on from reading the pages (a link's page has named the wish by then), at each later step, when a run ends,
 * and when the first answer shows one already past its reading (the list may have been read before). Once per change.
 */
export function wishlistAgain(before: Pick<ShopRun, 'state' | 'step'> | null | undefined,
  now: Pick<ShopRun, 'state' | 'step'> | null | undefined): boolean {
  if (!now) return false;
  if (now.state !== 'running') return before === undefined || before?.state === 'running';
  if (!now.step || now.step === 'page') return false;
  return !before || before.state !== 'running' || before.step !== now.step;
}

/** "$120.00", "€89.50"; the currency's code when the browser does not know it. With the checkout code the price is
 * after: "$106.20 with code SAVE40". */
export function priceWords(price: number | null | undefined, currency: string, code?: string | null): string {
  if (price === null || price === undefined || !Number.isFinite(price)) return 'Price not shown';
  let said: string;
  try {
    said = new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(price);
  } catch {
    said = `${price.toFixed(2)} ${currency}`;
  }
  return code ? `${said} with code ${code}` : said;
}

/** "Was $120.00, now $96.00 (20% less)"; "Was $177.00, now $106.20 with code SAVE40 (40% less)". */
export function dropWords(d: PriceDrop): string {
  return `Was ${priceWords(d.from, d.currency)}, now ${priceWords(d.to, d.currency, d.code)} (${d.percent}% less)`;
}

/** "Down from $68.00 to $54.40", in the find's currency: the news on a wish's row in the wishlist; "Down from $177.00
 * to $106.20 with code SAVE40" when the price is after a checkout code. */
export function downWords(d: Pick<PriceDrop, 'from' | 'to' | 'currency' | 'code'>): string {
  return `Down from ${priceWords(d.from, d.currency)} to ${priceWords(d.to, d.currency, d.code)}`;
}

/** What a checkout code takes off: "40% off", "$20.00 off". */
export function offWords(c: Pick<FindCode, 'percent' | 'amount'>, currency: string): string {
  return c.percent !== null ? `${Number(c.percent.toFixed(2))}% off` : `${priceWords(c.amount, currency)} off`;
}

/** The line under a find's price when it has a checkout code: "$106.20 with code SAVE40 at checkout (40% off)"; with
 * no price to take it from, "Code SAVE40 takes 40% off at checkout." Null with no code. */
export function codeWords(f: Pick<Find, 'code' | 'with_code' | 'currency'>): string | null {
  if (!f.code) return null;
  const off = offWords(f.code, f.currency);
  if (f.with_code === null) return `Code ${f.code.code} takes ${off} at checkout.`;
  return `${priceWords(f.with_code, f.currency, f.code.code)} at checkout (${off})`;
}

/** Who saw a find's checkout code: Nines or Claude, on the page; nothing when you typed it. */
export function codeFromWords(c: Pick<FindCode, 'by'> | null): string | null {
  if (c?.by === 'page') return 'Nines saw this code on the page.';
  if (c?.by === 'claude') return 'Claude saw this code on the page.';
  return null;
}

/** What is sent to save a code you typed (`PUT /api/wishlist/{id}/finds/{find}/code`), or the sentence to show when
 * the boxes cannot be sent. The rest (the code's form, the percent's range, an amount less than the price) is checked
 * by Nines, which says what is wrong. */
export function typedCode(code: string, kind: 'percent' | 'amount', value: string):
  { code: string; percent?: number; amount?: number } | string {
  const c = code.trim().toUpperCase();
  if (!c) return 'Type the code as the shop shows it.';
  const n = readAmount(value.trim().replace(/\s*%$/, ''));
  if (n === null || n === undefined) {
    return kind === 'percent' ? 'Type the percent off as a number, like 40.' : 'Type the amount off as a number, like 20.';
  }
  return kind === 'percent' ? { code: c, percent: n } : { code: c, amount: n };
}

/** A wish's newest page sent as a link, as its row in the wishlist shows it. */
export interface WishLink {
  /** The product's whole name, as its page gives it. */
  name?: string;
  shop: string;
  price: number | null;
  currency: string;
  available: boolean;
  /** Its checkout code and the price after it, when it has one that applies. */
  code?: string;
  with_code?: number;
}

/** "$68.00 at Example Shop"; "$106.20 with code SAVE40 at Example Shop"; "Sold out at Example Shop"; "From Example
 * Shop" until a price is read. */
export function linkWords(l: WishLink): string {
  if (!l.available) return `Sold out at ${l.shop}`;
  if (l.price === null) return `From ${l.shop}`;
  return l.with_code != null ? `${priceWords(l.with_code, l.currency, l.code)} at ${l.shop}` : `${priceWords(l.price, l.currency)} at ${l.shop}`;
}

/** What a find sent as a link says under its price: that it was sent, and how its price was read when that is worth
 * knowing (Claude's reading costs something). Never a price that was not read. Null for a find Claude found. */
export function linkLine(f: Pick<Find, 'link' | 'read_at' | 'read_by' | 'history'>): string | null {
  if (!f.link) return null;
  if (!f.read_at && !f.history.length) return 'You sent this link. Its page has not been read yet.';
  if (!f.history.length) return 'You sent this link. No price could be read from its page.';
  if (f.read_by === 'claude') return 'You sent this link. Claude read its price from the page.';
  return 'You sent this link.';
}

/** What a link's card says when it is not checked against your closet: why, in one sentence. Null when it is, or
 * when its page has not been read yet (`linkLine` says so). */
export function notJudgedWords(f: Pick<Find, 'not_judged'>, demo: boolean): string | null {
  switch (f.not_judged) {
    case 'no_name': return "Nines couldn't read its name from the page, so it isn't checked against your closet.";
    case 'unclear': return "Claude couldn't tell what kind of piece it is, so it isn't checked against your closet.";
    case 'waiting': return demo
      ? "The demo closet never sends anything to Claude, so it isn't checked against your closet."
      : 'Nines checks it against your closet once Claude can describe it.';
    default: return null;
  }
}

/** A find worn with your own clothes (`GET /api/wishlist/{id}/finds/{findId}/outfits`): its piece, and the example
 * outfits Would this work? makes with it, its place holding `CANDIDATE_ID`. */
export interface FindOutfits {
  piece: WouldPiece;
  outfits: WouldExample[];
}

/**
 * Whether a find's card offers "See it with your clothes": it is judged, and the check made at least one outfit with
 * it. A find judged before outfits were counted offers it unless the closet was too small to say; the sheet then says
 * when none can be made now.
 */
export function canSeeWorn(f: Pick<Find, 'piece' | 'verdict' | 'outfits'>): boolean {
  if (!f.piece || !f.verdict) return false;
  if (typeof f.outfits === 'number') return f.outfits > 0;
  return f.verdict !== 'too_small';
}

/** What is said while a search, a price check or the reading of a link runs (a price check's, in place of "Last
 * checked …"). */
export function runWords(run: Pick<ShopRun, 'kind' | 'step'>): string {
  if (run.kind === 'find') return 'Claude is searching shops. This can take a few minutes…';
  if (run.step === 'describe') return run.kind === 'link' ? 'Claude is describing it…' : 'Claude is describing the pages you sent…';
  if (run.kind === 'link') {
    return run.step === 'claude' ? "The page doesn't show its price to Nines, so Claude is reading it…" : 'Nines is reading the page…';
  }
  // said in place of "Last checked …", under the sentence that says Nines checks the price: nobody named again
  return 'Checking the price…';
}

/** What a toast says once a search, a price check or the reading of a link is over. */
export function runDoneWords(run: ShopRun, wishName: string): string {
  if (run.state === 'failed') return run.message ?? 'Something went wrong while looking.';
  if (run.kind === 'find') return run.added ? `Found ${run.added} new for “${wishName}”` : (run.message ?? 'Nothing new found');
  if (run.kind === 'link') return run.message ?? 'Nines read its price, and checks it again once a day.';
  return run.message ?? 'Prices checked';
}

/** Said when the box holds no web address. */
export const LINK_PROBLEM = 'Paste the whole address of the page, starting with https://.';

/** The first web address in some text, without the punctuation a sentence puts after it; '' when there is none.
 * Shared text often has words around the link ("Look at this: https://…"). */
export function linkIn(text: string | null | undefined): string {
  const found = (text ?? '').match(/https?:\/\/[^\s<>"'«»“”]+/i);
  return found ? found[0].replace(/[.,;:!?)\]}]+$/, '') : '';
}

/** What a page address opened by the share sheet holds (`/wardrobe/link?url=…&text=…&title=…`): the link, from
 * whichever of `url`, `text` and `title` holds one (apps put it in any of them), and whether something was shared that
 * held none. */
export function sharedLink(search: string): { link: string; none: boolean } {
  const q = new URLSearchParams(search);
  for (const key of ['url', 'text', 'title']) {
    const link = linkIn(q.get(key));
    if (link) return { link, none: false };
  }
  return { link: '', none: ['url', 'text', 'title'].some((key) => (q.get(key) ?? '').trim() !== '') };
}

/** The wish's price range in words, or '' when none is set. */
export function rangeWords(w: Pick<Wish, 'price_min' | 'price_max' | 'price_currency'>): string {
  const cur = w.price_currency ?? 'USD';
  const low = w.price_min ?? null;
  const high = w.price_max ?? null;
  if (low !== null && high !== null) return `${priceWords(low, cur)} to ${priceWords(high, cur)}`;
  if (high !== null) return `Up to ${priceWords(high, cur)}`;
  if (low !== null) return `From ${priceWords(low, cur)}`;
  return '';
}

type PriceOf = Pick<Wish, 'price_min' | 'price_max' | 'price_currency'>;

/** What Claude's searches keep to, said where the price is offered when nothing is watched yet: "Claude looks at any
 * price.", "Claude looks for ones up to $150.00." (a lower limit, which older wishes may still have, as it is). */
export function searchWords(w: PriceOf): string {
  const range = rangeWords(w);
  if (!range) return 'Claude looks at any price.';
  const both = w.price_min != null && w.price_max != null;
  return `Claude looks for ones ${both ? 'from ' : ''}${range.charAt(0).toLowerCase()}${range.slice(1)}.`;
}

/** The one sentence about watching, under what is watched: the price checked once a day, and what Nines tells you. */
export function watchWords(w: PriceOf): string {
  const most = w.price_max != null ? ` to ${priceWords(w.price_max, w.price_currency ?? 'USD')} or less` : '';
  const told = `Nines checks the price once a day while it's running and tells you when it goes down${most}.`;
  return w.price_min != null ? `${told} ${searchWords(w)}` : told;
}

/** When the prices were last looked at: the last price check, the last search (its prices were read then) or the last
 * time Nines read a page sent as a link, whichever is latest. */
export function lastChecked(answer: Pick<FindsAnswer, 'prices_checked_at' | 'found_at'> & { finds: Pick<Find, 'read_at'>[] }): string | null {
  const times = [answer.prices_checked_at, answer.found_at, ...answer.finds.map((f) => f.read_at)]
    .filter((t): t is string => !!t && !Number.isNaN(new Date(t).getTime()));
  return times.length ? times.reduce((a, b) => (new Date(a) > new Date(b) ? a : b)) : null;
}

/** "Last checked today at 9:05 AM.", "Last checked yesterday.", "Last checked on 3 Nov."; "Not checked yet." */
export function checkedWords(at: string | null, today: string = localDay()): string {
  if (!at) return 'Not checked yet.';
  const when = whenWorn(localDay(new Date(at)), today);
  const time = when === 'today' ? timeOf(at) : '';
  return `Last checked ${when}${time ? ` at ${time}` : ''}.`;
}

/** The finds in the order the wish's page shows them: the pages you sent first, then Claude's, each the oldest first
 * (the server lists the newest first), so what a later search finds comes after the finds you have already read and
 * nothing you were reading moves down. */
export function findsInOrder<T extends Pick<Find, 'link'> & { found_at?: string }>(finds: T[]): T[] {
  const oldest = (group: T[]) => {
    const at = (f: T) => (f.found_at ? new Date(f.found_at).getTime() || 0 : 0);
    return group.map((f, i) => ({ f, i })).sort((a, b) => at(a.f) - at(b.f) || a.i - b.i).map((x) => x.f);
  };
  return [...oldest(finds.filter((f) => f.link)), ...oldest(finds.filter((f) => !f.link))];
}

/** The finds to show: the wish's, with each find you stopped watching on this visit back in the place it had (`at`),
 * so its Undo is where the find was and nothing below it moves. One the server lists again is not shown twice. */
export function withStopped<T extends { id: string }>(finds: T[], stopped: { find: T; at: number }[]): T[] {
  if (!stopped.length) return finds;
  const out = [...finds];
  for (const s of [...stopped].sort((a, b) => a.at - b.at)) {
    if (!out.some((f) => f.id === s.find.id)) out.splice(Math.min(s.at, out.length), 0, s.find);
  }
  return out;
}

/** Whether a find is the wish itself: the wish was made from it (a link sent, a pick saved) and carries its name, or
 * that name cut short as the server cuts a wish's name ("…"). */
export function isTheWish(find: Pick<Find, 'name'>, wish: Pick<Wish, 'name'>): boolean {
  const name = find.name.trim();
  const own = wish.name.trim();
  if (name === own) return true;
  if (!own.endsWith('…')) return false;
  const start = own.slice(0, -1).trimEnd();
  // cut at a word: what follows the cut in the find's name starts a new word (or punctuation the cut dropped)
  return start.length > 0 && name.startsWith(start) && name.length > start.length && /^[\s,;:-]/.test(name.slice(start.length));
}

/** The wish's page heading: its name, or the whole name of the find it was made from when its own is that name cut
 * short. */
export function wishTitle(wish: Pick<Wish, 'name'>, finds: Pick<Find, 'name'>[] | null | undefined): string {
  if (!wish.name.trim().endsWith('…')) return wish.name;
  return (finds ?? []).find((f) => isTheWish(f, wish))?.name ?? wish.name;
}

/** Whether a wish's page says "Added by hand": it came from no gap and no page was sent for it. The server knows a
 * wish's link only while its find is watched, so the finds the page shows count too, a link's find you stopped
 * watching on this visit among them: the line does not appear, and push that find down, until you leave the page.
 * `shown` is null while the finds are still being asked for. */
export function addedByHand(wish: Pick<Wish, 'gap_id' | 'link'>, shown: Pick<Find, 'link'>[] | null): boolean {
  return !wish.gap_id && !wish.link && !(shown ?? []).some((f) => f.link);
}

/** How a find's price went, when it changed from one day to another: "The price was $177.00 on 3 Nov, $160.00 on
 * Tuesday and $150.00 yesterday.", the last three prices it changed to, each from the day it was first seen at it (a
 * day's last price stands for the day). Null when it never did. */
export function historyWords(history: PricePoint[], today: string = localDay()): string | null {
  const days: { day: string; point: PricePoint }[] = [];
  for (const point of history) {
    if (point.price === null) continue;
    const day = localDay(new Date(point.at));
    const last = days[days.length - 1];
    if (last?.day === day) last.point = point;
    else days.push({ day, point });
  }
  const same = (a: PricePoint, b: PricePoint) => a.currency === b.currency && Math.abs((a.price ?? 0) - (b.price ?? 0)) < 0.005;
  const changes = days.filter((d, i) => i === 0 || !same(days[i - 1].point, d.point));
  if (changes.length < 2) return null;
  const said = changes.slice(-3).map((d) => `${priceWords(d.point.price, d.point.currency)} ${whenWorn(d.day, today)}`);
  return `The price was ${said.slice(0, -1).join(', ')} and ${said[said.length - 1]}.`;
}

/** Whether a price is no more than the most you'd pay for the wish; never when none is set, or set in another currency
 * (prices are never converted). */
export function atYourPrice(w: PriceOf, price: { to: number; currency: string }): boolean {
  return w.price_max != null && (w.price_currency ?? 'USD') === price.currency && price.to <= w.price_max + 0.005;
}

/** Said beside the drop on a wish's row in the wishlist ("Down from $68.00 to $54.40") when the price is no more than
 * the most you'd pay; null otherwise. */
export function withinWords(w: PriceOf & Pick<Wish, 'drop'>): string | null {
  return w.drop && atYourPrice(w, w.drop) ? "That's within your price." : null;
}

/** What the Wardrobe's row to the wishlist says under its name: how many things are on it ("3 things", or "Nothing on it
 * yet"), and how many of their prices went down ("2 prices went down", null when none did), counting the wishes whose
 * row in the list shows a drop. */
export function wishlistWords(wishes: Pick<Wish, 'drop'>[]): { count: string; down: string | null } {
  const down = wishes.filter((w) => w.drop).length;
  return {
    count: wishes.length ? plural(wishes.length, 'thing') : 'Nothing on it yet',
    down: down ? `${plural(down, 'price')} went down` : null,
  };
}

/** A price that came down since you last looked at the wish (`GET /api/wishlist/news`): the banner's news. */
export interface PriceNews {
  wish_id: string;
  name: string;
  shop: string;
  from: number;
  to: number;
  currency: string;
  percent: number;
  at: string;
  /** No more than the most you'd pay, when you set it in this currency. */
  at_price: boolean;
  /** The checkout code `to` is after, when it is. */
  code?: string;
}

type KV = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const newsKey = (profile: string) => `${SAVED_PREFIX}:news:${profile}`;
function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The last price news this device was told (kept with its other saved copies, and forgotten with them), so the
 * banner is drawn with the page when it opens rather than arriving after it. Null when none was kept. */
export function keptNews(profile: string, kv: KV | null = local()): PriceNews[] | null {
  try {
    const raw = kv?.getItem(newsKey(profile));
    const news = raw ? JSON.parse(raw) as unknown : null;
    return Array.isArray(news) ? news as PriceNews[] : null;
  } catch {
    return null;
  }
}

export function keepNews(profile: string, news: PriceNews[], kv: KV | null = local()) {
  try {
    if (news.length) kv?.setItem(newsKey(profile), JSON.stringify(news));
    else kv?.removeItem(newsKey(profile));
  } catch {
    /* private mode or full: the banner waits for the next screen instead */
  }
}

/** How often the news is asked for again while the page is open and shown (and when it comes back into view). */
export const NEWS_POLL_MS = 30 * 60 * 1000;

/** The banner's sentence: "A tan rain coat is down to $150.00 at Example Shop, from $177.00." for one wish ("…down to
 * $106.20 with code SAVE40 at Example Shop…" when the price is after a checkout code); for several, how many. */
export function newsWords(news: Pick<PriceNews, 'name' | 'shop' | 'from' | 'to' | 'currency' | 'at_price' | 'code'>[]): string {
  if (news.length !== 1) return `Prices went down for ${news.length} things on your wishlist.`;
  const [n] = news;
  const price = n.at_price ? " That's within your price." : '';
  return `${n.name} ${beFor(n.name)} down to ${priceWords(n.to, n.currency, n.code)} at ${n.shop}, from ${priceWords(n.from, n.currency)}.${price}`;
}

/** The words a Google Shopping search is made of: "men's", the first colour to look for and the kind of piece in plain
 * words, or the wish's own name when it says nothing to look for. Nothing else about you or your closet. */
export function shoppingWords(what: Pick<Wish, 'name' | 'look_for'>): string {
  const bare = (words: string) => words.trim().replaceAll('_', ' ').replace(/^(a pair of|an|a|the)\s+/i, '');
  const look = what.look_for;
  if (look?.category) {
    const color = look.colors?.length ? label('color', look.colors[0]).toLowerCase() : '';
    const kind = look.kind ? bare(look.kind) : kindWords(look);
    return ["men's", color, kind].filter(Boolean).join(' ');
  }
  const name = bare(what.name);
  return /\bmen'?s\b/i.test(name) ? name : `men's ${name}`;
}

/** A Google Shopping search for a gap or a wish (`shoppingWords`), opened in your browser. */
export function googleShoppingLink(what: Pick<Wish, 'name' | 'look_for'>): string {
  return `https://www.google.com/search?tbm=shop&q=${encodeURIComponent(shoppingWords(what))}`;
}

/** Only a web address may be opened or shown: anything else gives null (the server checks too). */
export function webLink(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : null;
  } catch {
    return null;
  }
}

/** What the closet tells Claude about you when it looks for something, never more (DECISIONS, "What the search is told
 * about you"): the one wording, said under "Find some" and on You might like. */
const SENDS_ABOUT_YOU = 'your style, what you tend to wear, the brands you own and your size, never a photo or a note.';

/** What a search sends to Claude, said under "Find some"; the demo closet searches nothing, so it is not said there. */
export const SEARCH_SENDS = `A search sends Claude the wish, ${SENDS_ABOUT_YOU}`;

/** What a look for things on sale sends besides (DECISIONS, "On sale now"): where it starts. */
export const SALE_SENDS = 'A look for things on sale also sends the shops you like and the shops you found things at before.';

/** What a look for things you might like sends to Claude: the same, without a wish, and where a look for sales starts.
 * The one place this is said. */
export const LOOK_SENDS = `A look sends Claude ${SENDS_ABOUT_YOU} ${SALE_SENDS}`;
