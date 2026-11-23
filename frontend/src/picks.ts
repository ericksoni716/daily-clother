/** You might like: three things a week Claude found from what you wear and love, and plain words for the card. */
import { LOOK_SENDS, priceWords, runWords } from './shop';
import { aboutUsd } from './spend';
import { rememberWords, savedLine } from './today';
import type { Verdict, WouldPiece } from './wouldwork';

export interface ShopPick {
  id: string;
  /** 'taste': chosen from what you wear and love. "On sale now" (BACKLOG, step 5) would add a second kind. */
  kind: 'taste' | 'sale';
  /** How the look was started: Look now, by itself each week, or More like this. */
  source: 'look' | 'weekly' | 'more';
  name: string;
  shop: string;
  url: string;
  image_url: string | null;
  price: number | null;
  /** The price before a markdown, when the shop shows one (step 5); null here. */
  price_before: number | null;
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
  /** You have tapped Look now at least once. */
  looked: boolean;
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

/** What the card shows. */
export type CardState = 'demo' | 'looking' | 'list' | 'thin' | 'never' | 'nothing';

export function cardState(a: Pick<PicksAnswer, 'demo' | 'run' | 'picks' | 'enough' | 'looked'>): CardState {
  if (a.demo) return 'demo';
  if (a.run?.state === 'running') return 'looking';
  if (a.picks.length) return 'list';
  if (!a.enough) return 'thin';
  return a.looked ? 'nothing' : 'never';
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

/** "Example Shop · $45.00"; the shop alone when the page showed no price. */
export function shopLine(p: Pick<ShopPick, 'shop' | 'price' | 'currency'>): string {
  return p.price === null ? p.shop : `${p.shop} · ${priceWords(p.price, p.currency)}`;
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
