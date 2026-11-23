/** Shopping for a wish: the products Claude found and the pages the owner sent, their prices, the news when one went
 * down, and plain words for them. */
import type { Wish } from './gaps';
import { plural } from './insights';
import { timeOf } from './today';
import { localDay, whenWorn } from './wears';
import type { Verdict, WouldPiece } from './wouldwork';

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
  /** Sent by the owner as a link: its page is read by Nines first, and it is not judged against the closet. */
  link: boolean;
  /** When Nines last read the page itself (a link only), whatever it found. */
  read_at: string | null;
  /** How the latest price was read: from the page's own data, or by Claude. */
  read_by: 'page' | 'claude' | null;
  /** Its description in the closet's words; null for a link, which is not described. */
  piece: WouldPiece | null;
  piece_words: string | null;
  verdict: Verdict | null;
  verdict_words: string | null;
  reasons: string[];
  checked_at: string | null;
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
  /** Who is reading now: Nines, on the shops' own pages, or Claude. */
  step?: 'page' | 'claude' | null;
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
  const n = typedPrice(value.trim().replace(/%$/, ''));
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

/** What is said while a search, a price check or the reading of a link runs. */
export function runWords(run: Pick<ShopRun, 'kind' | 'step'>): string {
  if (run.kind === 'find') return 'Claude is searching shops. This can take a few minutes…';
  if (run.kind === 'link') {
    return run.step === 'claude' ? "The page doesn't show its price to Nines, so Claude is reading it…" : 'Nines is reading the page…';
  }
  return run.step === 'page' ? 'Nines is reading the pages you sent…' : 'Claude is checking the prices…';
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

/** The finds in the order the wish's page shows them: the pages you sent first, then Claude's, each as kept. */
export function findsInOrder<T extends Pick<Find, 'link'>>(finds: T[]): T[] {
  return [...finds.filter((f) => f.link), ...finds.filter((f) => !f.link)];
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

/** How often the news is asked for again while the page is open and shown (and when it comes back into view). */
export const NEWS_POLL_MS = 30 * 60 * 1000;

/** The banner's sentence: "A tan rain coat is down to $150.00 at Example Shop, from $177.00." for one wish ("…down to
 * $106.20 with code SAVE40 at Example Shop…" when the price is after a checkout code); for several, how many. */
export function newsWords(news: Pick<PriceNews, 'name' | 'shop' | 'from' | 'to' | 'currency' | 'at_price' | 'code'>[]): string {
  if (news.length !== 1) return `Prices went down for ${news.length} things on your wishlist.`;
  const [n] = news;
  const price = n.at_price ? " That's within your price." : '';
  return `${n.name} is down to ${priceWords(n.to, n.currency, n.code)} at ${n.shop}, from ${priceWords(n.from, n.currency)}.${price}`;
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

/** A price typed by the owner: a number from 0, null for an empty box, undefined when it is not a price. */
export function typedPrice(text: string): number | null | undefined {
  const t = text.trim().replace(/^[$€£]/, '').replace(/,/g, '');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}
