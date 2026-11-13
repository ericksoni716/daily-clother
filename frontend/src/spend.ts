/** Plain words for what the API key costs: amounts, months, the limit and the estimates. */
import type { TaggingSpend } from './types';

/** "$1.20", "$1,000.00"; "$0.00" for nothing, and "under 1¢" for a sum too small to show in cents. */
export function formatUsd(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount) || amount <= 0) return '$0.00';
  if (amount < 0.005) return 'under 1¢';
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** "about $0.03": an estimate, never shown as less than a cent. */
export function aboutUsd(amount: number): string {
  return amount > 0 && amount < 0.01 ? 'under 1¢' : `about ${formatUsd(amount)}`;
}

/** "November 2026" from "2026-11". */
export function monthName(month: string): string {
  const [y, m] = month.split('-').map(Number);
  if (!y || !m) return month;
  return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

/** "3 Nov 2026" from "2026-11-03". */
export function dayName(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  if (!y || !m || !d) return day;
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

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
  return `We suggest ${formatUsd(suggested)} a month. At the prices written down on ${dayName(pricesChecked)}, that pays for at least ` +
    `${photos.toLocaleString('en-US')} photos even if your plan can't be used at all — a whole wardrobe several times over — ` +
    'while keeping any mistake small.';
}

/** Why Closet stopped using the API key by itself, or empty. */
export function turnedOffLine(off: TaggingSpend['turned_off']): string {
  if (!off) return '';
  const when = new Date(off.at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  return off.reason === 'credit'
    ? `Closet stopped using the API key on ${when} because Anthropic said your account has no credit left. Add credit in your Anthropic account, then turn the key on again.`
    : `Closet stopped using the API key on ${when} because Anthropic didn't accept the key. Check the key, then turn it on again.`;
}
