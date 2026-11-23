/** Plain words for what the API key costs: amounts, months, the limit and the estimates. */
import type { ApiKeyInfo, RouteOrder, TaggingRoute, TaggingSpend } from './types';
import { dayOf, fullDate } from './wears';

/** "$1.20", "$1,000.00"; "$0.00" for nothing, and "under 1¢" for a sum too small to show in cents. */
export function formatUsd(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount) || amount <= 0) return '$0.00';
  if (amount < 0.005) return 'under 1¢';
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** What something cost, from cents: "$1,240", "$45.50", "€80"; whole amounts without cents. `currency` is a three-letter
 * code (or "$", the closet's own prices), never converted; a code the browser does not know is written after the
 * amount ("80 XYZ"). `exact` keeps the cents even when there are none ("$3.00 a wear"). */
export function amount(cents: number, currency = 'USD', exact = false): string {
  const code = currency === '$' ? 'USD' : currency;
  const whole = !exact && cents % 100 === 0;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: code, minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2,
    }).format(cents / 100);
  } catch {
    return `${(cents / 100).toFixed(whole ? 0 : 2)} ${code}`;
  }
}

/** What to say when a price box holds something that is not a price: nothing is saved. */
export const PRICE_HINT = 'Type the price as a number, like 45 or 45.50.';

const CURRENCY = /^([$€£])?\s*(.*?)\s*([$€£])?$/;

/**
 * The one reader for a price you typed, in every box that takes one (an item's price, the review card, a wish's most
 * you'd pay, a code's amount off, the monthly limit). It reads `45.50` and `45,50` alike (a phone set to a region
 * that writes 45,50 has a comma on its decimal keypad), `1,234.50` and `1.234,50`, a space between thousands, and a
 * currency sign before or after. A number from 0; null for an empty box; undefined for anything it cannot read for
 * sure (a word, a minus, three decimals, `1.234`), so nothing is saved and the box says `PRICE_HINT`.
 */
export function readAmount(text: string): number | null | undefined {
  const sign = CURRENCY.exec(text.trim());
  if (!sign || (sign[1] && sign[3])) return undefined;
  // a space (or the narrow ones a phone may type) between groups of three digits, as in "1 234,50"
  const body = sign[2].replace(/[\u00a0\u202f\u2009]/g, ' ').replace(/(\d) (?=\d{3}(?!\d))/g, '$1');
  if (!body) return null;
  if (!/^[\d.,]+$/.test(body)) return undefined;
  const lastDot = body.lastIndexOf('.');
  const lastComma = body.lastIndexOf(',');
  let whole = body;
  let cents = '';
  if (lastDot >= 0 && lastComma >= 0) {
    // both: the one written last is the decimal point, the other separates thousands
    const point = Math.max(lastDot, lastComma);
    const group = point === lastDot ? ',' : '.';
    whole = body.slice(0, point);
    cents = body.slice(point + 1);
    if (!grouped(whole, group)) return undefined;
    whole = whole.split(group).join('');
  } else if (lastDot >= 0 || lastComma >= 0) {
    const mark = lastDot >= 0 ? '.' : ',';
    const pieces = body.split(mark);
    if (pieces.length > 2) {
      if (!grouped(body, mark)) return undefined;
      whole = pieces.join('');
    } else if (pieces[1].length <= 2) {
      [whole, cents] = pieces;
    } else if (pieces[1].length === 3 && mark === ',' && grouped(body, ',')) {
      // "1,234": a thousand. "1.234" could be a thousand or one and a bit, so it is not guessed.
      whole = pieces.join('');
    } else return undefined;
  }
  if (!/^\d*$/.test(whole) || !/^\d{0,2}$/.test(cents) || (!whole && !cents)) return undefined;
  return Math.round(Number(`${whole || '0'}.${cents || '0'}`) * 100) / 100;
}

/** Thousands written with `mark` between them: "1,234,567". */
function grouped(digits: string, mark: string): boolean {
  const [first, ...rest] = digits.split(mark);
  return /^[1-9]\d{0,2}$/.test(first) && rest.every((g) => /^\d{3}$/.test(g));
}

/** `readAmount` in cents, for what is stored in cents (an item's price). */
export function readCents(text: string): number | null | undefined {
  const amount = readAmount(text);
  return amount === null || amount === undefined ? amount : Math.round(amount * 100);
}

/** "about $0.03": an estimate, never shown as less than a cent. */
export function aboutUsd(amount: number): string {
  return amount > 0 && amount < 0.01 ? 'under 1¢' : `about ${formatUsd(amount)}`;
}

/** "November 2026" from "2026-11", and "3 Nov 2026" from "2026-11-03": the one family of dates (wears.ts). */
export { monthYear as monthName, fullDate as dayName } from './wears';

function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;
}

/** What this month has cost: "$0.42 of your $5.00 limit, 12 photos sent with the API key." */
export function spentLine(s: Pick<TaggingSpend, 'spent_usd' | 'cap_usd' | 'api_calls' | 'plan_calls'>): string {
  const spent = s.cap_usd ? `${formatUsd(s.spent_usd)} of your ${formatUsd(s.cap_usd)} limit` : `${formatUsd(s.spent_usd)}`;
  const calls = s.api_calls ? `${count(s.api_calls, 'request', 'requests')} to Claude with the API key` : 'nothing sent with the API key';
  const plan = s.plan_calls ? ` ${count(s.plan_calls, 'request', 'requests')} went through your Claude plan, at no extra cost.` : '';
  return `${spent} spent; ${calls}.${plan}`;
}

/** What the items waiting would cost if the plan can't be used; empty when nothing waits. */
export function waitingLine(w: TaggingSpend['waiting']): string {
  if (!w.items) return '';
  const items = w.items === 1 ? 'the item waiting' : `the ${w.items.toLocaleString('en-US')} items waiting`;
  return `If your plan can't be used, describing ${items} with the API key would cost ${aboutUsd(w.at_most_usd)} at most.`;
}

/** "About $0.03 for these 10 photos with the API key, if your plan can't be used." during an import. */
export function importLine(photos: number, perPhotoUsd: number): string {
  const cost = aboutUsd(photos * perPhotoUsd);
  const which = photos === 1 ? 'this photo' : `these ${photos.toLocaleString('en-US')} photos`;
  return `${cost[0].toUpperCase()}${cost.slice(1)} for ${which} with the API key, if your plan can't be used.`;
}

/** Why the suggested limit, with the date the prices were written down. */
export function suggestionLine(suggested: number, perPhotoUsd: number, pricesChecked: string): string {
  const photos = perPhotoUsd > 0 ? Math.floor(suggested / perPhotoUsd) : 0;
  return `We suggest ${formatUsd(suggested)} a month. At the prices written down on ${fullDate(pricesChecked)}, that pays for at least ` +
    `${photos.toLocaleString('en-US')} photos even if your plan can't be used at all — a whole wardrobe several times over — ` +
    'while keeping any mistake small.';
}

/** Why Nines stopped using the API key by itself, or empty. */
export function turnedOffLine(off: TaggingSpend['turned_off']): string {
  if (!off) return '';
  const when = fullDate(dayOf(off.at) ?? off.at);
  return off.reason === 'credit'
    ? `Nines stopped using the API key on ${when} because Anthropic said your account has no credit left. Add credit in your Anthropic account, then turn the key on again.`
    : `Nines stopped using the API key on ${when} because Anthropic didn't accept the key. Check the key, then turn it on again.`;
}

/** Where the API key comes from, in a sentence; never the key itself. Read on the phone (`onComputer` false), "this
 * Mac's keychain" is the computer's, so it says "your Mac's keychain". */
export function apiKeyLine(info: ApiKeyInfo, onComputer = true): string {
  const where = info.where ?? "this computer's keychain";
  if (info.source === 'keychain') return `Your API key is saved in ${onComputer ? where : where.replace(/^this /, 'your ')}.`;
  if (info.source === 'environment') return `Your API key comes from ANTHROPIC_API_KEY, set on ${onComputer ? 'this computer' : 'your computer'}.`;
  return 'No API key yet.';
}

/** What to say after a key was saved. */
export function apiKeySavedLine(info: ApiKeyInfo, allowed: boolean): string {
  const checked = info.checked === false
    ? 'Key saved. Nines couldn\'t reach Anthropic to check it, so it will find out the first time the key is used.'
    : 'Key saved. Anthropic accepted it.';
  return allowed ? checked : `${checked} Turn on Allow the API key below to use it.`;
}

/** The orders the owner can choose in Settings, in plain words; `needsKey` ones put the API key first. */
export const ROUTE_ORDERS: { value: RouteOrder; label: string; needsKey: boolean }[] = [
  { value: 'auto', label: "Use my Claude plan first, the key only if the plan can't", needsKey: false },
  { value: 'api-first', label: 'Use the API key first', needsKey: true },
  { value: 'plan', label: 'Only my Claude plan', needsKey: false },
  { value: 'api', label: 'Only the API key', needsKey: true },
];

/** Which route Nines will try first, in a sentence: the first in `order` that is ready (the key only once allowed).
 *  Empty when none is. */
export function firstRouteLine(order: TaggingRoute['id'][], routes: TaggingRoute[], apiAllowed: boolean): string {
  const ready = new Set(routes.filter((r) => r.available && (r.id !== 'api' || apiAllowed)).map((r) => r.id));
  const first = order.find((id) => ready.has(id));
  if (first === 'plan') return 'Nines will try your Claude plan first.';
  if (first === 'api') return 'Nines will try your API key first.';
  return '';
}
