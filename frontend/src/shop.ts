/** Shopping for a wish: the products Claude found, their prices, and plain words for them. */
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
  piece: WouldPiece;
  piece_words: string;
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
  kind: 'find' | 'prices';
  state: 'running' | 'done' | 'failed';
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
