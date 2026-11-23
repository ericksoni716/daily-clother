/** You might like: three things a week Claude found from what you wear and love, three on sale, and plain words for the
 * card. */
import { dropWords, LOOK_SENDS, priceWords, runWords } from './shop';
import { aboutUsd } from './spend';
import { rememberWords, savedLine } from './today';
import type { Verdict, WouldPiece } from './wouldwork';

/** 'taste': chosen from what you wear and love; 'sale': marked down now, and checked on its page by Nines. */
export type PickKind = 'taste' | 'sale';

export interface ShopPick {
  id: string;
  kind: PickKind;
  /** How the look was started: Look now, by itself each week, or More like this. */
  source: 'look' | 'weekly' | 'more';
  name: string;
  shop: string;
  url: string;
  image_url: string | null;
  price: number | null;
  /** A sale's price before the markdown; null for a taste pick. */
  price_before: number | null;
  /** Who read the price before: Nines, from the page's own data, or only Claude. */
  before_by?: 'page' | 'claude' | null;
  /** The page says your size is in stock (null: nobody said). */
  in_stock?: boolean | null;
  currency: string;
  piece: WouldPiece;
  verdict: Verdict | null;
  verdict_words: string | null;
  /** How many of your pieces it makes a good outfit with. */
  pairs: number;
  found_at: string;
  state: 'shown' | 'saved' | 'refused';
  wish_id: string | null;
}

export interface PickRun {
  source: ShopPick['source'];
  /** Which kind of look it is (absent in a copy kept before sales: a taste look). */
  kind?: PickKind;
  state: 'running' | 'done' | 'failed';
  message: string | null;
  added: number | null;
  started_at: string;
  finished_at: string | null;
}

/** A line for Your style offered after a few "Not for me" alike; kept only when you tap Save. */
export interface PickOffer {
  id: string;
  text: string;
  said: string;
  state: 'offered' | 'saved';
}

export interface PicksAnswer {
  picks: ShopPick[];
  run: PickRun | null;
  last: { source: ShopPick['source']; at: string; found: number } | null;
  /** You have tapped Look now at least once, for either kind. */
  looked: boolean;
  /** Each kind's own: whether you have looked, and its last look (absent in a copy kept before sales). */
  views?: Record<PickKind, { looked: boolean; last: PicksAnswer['last'] }>;
  /** How many shops you like (Settings): none, and the sale view offers to name some. */
  shops?: number;
  /** The weekly look is on. */
  weekly: boolean;
  /** There is enough to go on: what you wear and rate, or a line of your own in Your style. */
  enough: boolean;
  demo: boolean;
  estimate: { api: boolean; look_usd: number };
  offer: PickOffer | null;
  /** Given back by Save: the wish made from the pick. */
  wish_id?: string;
}

/** How many picks the card shows before "See earlier ones". */
export const PICKS_SHOWN = 3;
/** About two lines of a name on a phone; the whole name is the link's title. */
export const PICK_NAME_MAX = 34;
export const PICKS_POLL_MS = 2000;

export const NEVER_LOOKED = 'Nines can look for three things you might like, from what you wear and love.';
export const THIN = 'Wear and rate a few more pieces and Nines can look for things you might like.';
export const NOTHING = 'Claude found nothing new for you this time.';
export const DEMO = 'The demo closet never searches shops. Open your own closet to look for things you might like.';
export const WEEKLY_LABEL = 'Look for me each week';
export const REFUSED = "Not for me. You won't see it again.";
export { LOOK_SENDS };

// On sale
export const SALE_NEVER = 'Nines can look for things on sale that suit you, in shops you might never have found.';
export const SALE_NOTHING = "Nothing on sale this time that suits you and that Nines could check on the shop's page.";
export const SHOPS_OFFER = 'Name a few shops you like and Nines starts there.';
export const IN_STOCK = 'Your size is in stock.';
/** As a find whose price Claude read is marked ("Claude read its price from the page"). */
export const BEFORE_BY_CLAUDE = 'Claude read the earlier price from the page.';

/** Shops you like (Settings, Everyday): the sheet's one line, and the row's. */
export const SHOPS_HINT = 'Nines starts here when it looks for things on sale, and tells Claude these names.';

export function shopsLine(shops: { shops: { name: string }[] } | undefined): string {
  const names = (shops?.shops ?? []).map((s) => s.name);
  return names.length ? `Shops you like: ${names.join(' · ')}` : 'You have not named any shops you like yet.';
}

/** The card's two views, as Today's "Pieces / As worn". */
export const VIEW_OPTIONS = [{ value: 'taste', label: 'For you' }, { value: 'sale', label: 'On sale' }] as const;

/** One view's picks. */
export function picksOf(picks: ShopPick[], kind: PickKind): ShopPick[] {
  return picks.filter((p) => (p.kind ?? 'taste') === kind);
}

/** The kind of look running or last run (a copy kept before sales knew only taste looks). */
export function runKind(run: PickRun | null | undefined): PickKind {
  return run?.kind ?? 'taste';
}

/** What the card shows. */
export type CardState = 'demo' | 'looking' | 'list' | 'thin' | 'never' | 'nothing';

/** What one view of the card shows: a look of its kind running, its picks, or why there are none. */
export function cardState(a: Pick<PicksAnswer, 'demo' | 'run' | 'picks' | 'enough' | 'looked' | 'views'>,
  kind: PickKind = 'taste'): CardState {
  if (a.demo) return 'demo';
  if (a.run?.state === 'running' && runKind(a.run) === kind) return 'looking';
  if (picksOf(a.picks, kind).length) return 'list';
  if (!a.enough) return 'thin';
  const looked = a.views ? a.views[kind].looked : kind === 'taste' && a.looked;
  return looked ? 'nothing' : 'never';
}

/** A sale's prices in the wishlist's words: "Was $120.00, now $84.00 (30% less)"; null for a taste pick or a price
 * missing. */
export function salePriceLine(p: Pick<ShopPick, 'kind' | 'price' | 'price_before' | 'currency'>): string | null {
  if (p.kind !== 'sale' || p.price === null || p.price_before === null || p.price_before <= p.price) return null;
  const percent = Math.round(((p.price_before - p.price) / p.price_before) * 100);
  return dropWords({ from: p.price_before, to: p.price, currency: p.currency, percent });
}

/** What a sale row says under its prices: that your size is in stock, when the page said so, and that only Claude
 * read the earlier price, when only Claude did. */
export function saleNote(p: Pick<ShopPick, 'kind' | 'in_stock' | 'before_by'>): string | null {
  if (p.kind !== 'sale') return null;
  const said = [p.in_stock ? IN_STOCK : '', p.before_by === 'claude' ? BEFORE_BY_CLAUDE : ''].filter(Boolean);
  return said.length ? said.join(' ') : null;
}

/** While a look runs, the card asks again every two seconds; otherwise never (a look costs money, and only you or the
 * weekly round start one). */
export function picksPoll(a: Pick<PicksAnswer, 'run'> | null | undefined): number | false {
  return a?.run?.state === 'running' ? PICKS_POLL_MS : false;
}

/** Said while a look runs, in the words a wish's search uses. */
export const LOOKING = runWords({ kind: 'find', step: null });

/** The product's name cut at a word to about two lines, with "…" when it was cut. */
export function pickName(name: string, limit = PICK_NAME_MAX): string {
  const text = name.split(/\s+/).filter(Boolean).join(' ');
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit - 1);
  return `${(cut.includes(' ') ? cut.slice(0, cut.lastIndexOf(' ')) : cut).replace(/[ ,;:-]+$/, '')}…`;
}

/** "Example Shop · $45.00"; the shop alone when the page showed no price, or for a sale (its prices have a line of
 * their own, `salePriceLine`). */
export function shopLine(p: Pick<ShopPick, 'shop' | 'price' | 'currency'> & { kind?: PickKind }): string {
  return p.price === null || p.kind === 'sale' ? p.shop : `${p.shop} · ${priceWords(p.price, p.currency)}`;
}

/** One line from the verdict: "Fills a gap in your closet.", "Goes with 6 of your pieces."; the verdict's own words
 * when it goes with none of them yet (a closet too small to say). */
export function verdictLine(p: Pick<ShopPick, 'verdict' | 'verdict_words' | 'pairs'>): string | null {
  if (p.verdict === 'fills_gap') return 'Fills a gap in your closet.';
  if (!p.pairs) return p.verdict_words ?? null;
  return `Goes with ${p.pairs === 1 ? 'one' : p.pairs} of your pieces.`;
}

/** What a look costs through the API key, said beside Look now the way Find some says it; null when the key is off. */
export function lookCostWords(estimate: PicksAnswer['estimate']): string | null {
  return estimate.api ? `If your plan can't be used, a look costs ${aboutUsd(estimate.look_usd)} at most with the API key.` : null;
}

/** The line offered for Your style, as the card asks it, with the words of a line offered in a conversation. */
export function offerWords(o: PickOffer): { question: string; save: string; saved: string } {
  const thing = { kind: 'style' as const, item_id: null, name: null, text: o.text, state: o.state };
  return { question: `${o.said} Keep this in Your style?`, save: rememberWords(thing).save, saved: savedLine(thing) };
}

/** A pick with Not for me just tapped, kept in its place so Undo has somewhere to be (the server no longer lists it). */
export function withRefused(list: ShopPick[], refused: { pick: ShopPick; index: number } | null): ShopPick[] {
  if (!refused || list.some((p) => p.id === refused.pick.id)) return list;
  const out = [...list];
  out.splice(Math.min(refused.index, out.length), 0, { ...refused.pick, state: 'refused' });
  return out;
}

// ------------------------------------------------------------------ the copy kept on this device (offline)
type KV = Pick<Storage, 'getItem' | 'setItem'>;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const savedKey = (profile: string) => `nines:picks:${profile}`;
const VIEW_KEY = 'nines:picks-view';

/** The view you last chose, remembered on this device: For you until you choose On sale. */
export function savedView(kv: KV | null = local()): PickKind {
  try {
    return kv?.getItem(VIEW_KEY) === 'sale' ? 'sale' : 'taste';
  } catch {
    return 'taste';
  }
}

export function saveView(kind: PickKind, kv: KV | null = local()): void {
  try {
    kv?.setItem(VIEW_KEY, kind);
  } catch {
    /* private mode: the view is not remembered */
  }
}

/** What the card last showed, kept for when Nines cannot be reached. */
export function savePicks(profile: string, answer: PicksAnswer, kv: KV | null = local(), now = new Date()): void {
  try {
    kv?.setItem(savedKey(profile), JSON.stringify({ saved_at: now.toISOString(), answer: { ...answer, run: null } }));
  } catch {
    /* private mode or full: not kept, nothing else breaks */
  }
}

export function savedPicks(profile: string, kv: KV | null = local()): { data: PicksAnswer; savedAt: string } | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const value = raw ? (JSON.parse(raw) as { saved_at?: unknown; answer?: PicksAnswer }) : null;
    return value && typeof value.saved_at === 'string' && value.answer && Array.isArray(value.answer.picks)
      ? { data: value.answer, savedAt: value.saved_at } : null;
  } catch {
    return null;
  }
}
