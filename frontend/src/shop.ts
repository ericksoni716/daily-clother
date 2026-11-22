/** Shopping for a wish: the products Claude found and the pages the owner sent, their prices, and plain words for them. */
import type { Wish } from './gaps';
import type { Verdict, WouldPiece } from './wouldwork';

export interface PricePoint {
  at: string;
  price: number | null;
  currency: string;
  available: boolean;
}

export interface PriceDrop {
  from: number;
  to: number;
  currency: string;
  percent: number;
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

/** "$120.00", "€89.50"; the currency's code when the browser does not know it. */
export function priceWords(price: number | null | undefined, currency: string): string {
  if (price === null || price === undefined || !Number.isFinite(price)) return 'Price not shown';
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(price);
  } catch {
    return `${price.toFixed(2)} ${currency}`;
  }
}

/** "Was $120.00, now $96.00 (20% less)". */
export function dropWords(d: PriceDrop): string {
  return `Was ${priceWords(d.from, d.currency)}, now ${priceWords(d.to, d.currency)} (${d.percent}% less)`;
}

/** "Down from $68.00 to $54.40", in the find's currency: the news on a wish's row in the wishlist. */
export function downWords(d: Pick<PriceDrop, 'from' | 'to' | 'currency'>): string {
  return `Down from ${priceWords(d.from, d.currency)} to ${priceWords(d.to, d.currency)}`;
}

/** A wish's newest page sent as a link, as its row in the wishlist shows it. */
export interface WishLink {
  shop: string;
  price: number | null;
  currency: string;
  available: boolean;
}

/** "$68.00 at Example Shop"; "Sold out at Example Shop"; "From Example Shop" until a price is read. */
export function linkWords(l: WishLink): string {
  if (!l.available) return `Sold out at ${l.shop}`;
  return l.price === null ? `From ${l.shop}` : `${priceWords(l.price, l.currency)} at ${l.shop}`;
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
