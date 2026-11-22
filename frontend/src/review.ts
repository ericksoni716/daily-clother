/** Plain words and small helpers for the review queue (the screen is in screens/Review.tsx). */
import { formatPrice, parsePrice, PRICE_HINT, SWATCH } from './labels';
import type { CheckBody, Item, ItemPatch, ReviewField, ReviewItem } from './types';

/** One choice to make: a field, or one part of the silhouette. */
export interface ReviewRow {
  key: string;
  field: ReviewField['field'];
  /** The silhouette part ("neck", "fit", …), or null for a field of its own. */
  part: string | null;
  /** What Claude said. */
  value: string;
  /** Claude's value first, then the other allowed values in their usual order. */
  options: string[];
  confidence: number;
}

/** The rows to show for an item's doubtful fields; the silhouette gives one row per part. */
export function reviewRows(fields: ReviewField[]): ReviewRow[] {
  const rows: ReviewRow[] = [];
  const add = (key: string, field: ReviewField['field'], part: string | null, value: string, allowed: string[], confidence: number) =>
    rows.push({ key, field, part, value, options: [value, ...allowed.filter((v) => v !== value)], confidence });
  for (const f of fields) {
    if (typeof f.value === 'string') {
      add(f.field, f.field, null, f.value, Array.isArray(f.allowed) ? f.allowed : [], f.confidence);
    } else {
      const allowed = Array.isArray(f.allowed) ? {} : f.allowed;
      for (const [part, value] of Object.entries(f.value)) add(`${f.field}.${part}`, f.field, part, value, allowed[part] ?? [], f.confidence);
    }
  }
  return rows;
}

/** What to send once the owner has chosen: the changed fields (saved as an edit) and the rest (confirmed as they are). */
export function reviewChanges(rows: ReviewRow[], chosen: Record<string, string>): { changes: ItemPatch; confirm: ReviewField['field'][] } {
  const changes: ItemPatch = {};
  const silhouette: Record<string, string> = {};
  const changed = new Set<ReviewField['field']>();
  for (const r of rows) {
    const v = chosen[r.key] ?? r.value;
    if (v === r.value) continue;
    changed.add(r.field);
    if (r.part) silhouette[r.part] = v;
    else if (r.field === 'color') Object.assign(changes, { color: v, color_hex: SWATCH[v]?.startsWith('#') ? SWATCH[v] : null });
    else Object.assign(changes, { [r.field]: v });
  }
  if (Object.keys(silhouette).length) changes.silhouette = silhouette;
  const confirm = [...new Set(rows.map((r) => r.field))].filter((f) => !changed.has(f));
  return { changes, confirm };
}

/** Who said what it is, beside the kind: "Set by you", "Claude's guess · Claude was 80% sure", or nothing to say. */
export function kindWho(item: Pick<Item, 'kind' | 'kind_by' | 'kind_confidence'>): string {
  if (item.kind_by === 'owner') return 'Set by you';
  if (item.kind_by === 'claude') return `Claude's guess${item.kind_confidence != null ? ` · ${sureText(item.kind_confidence)}` : ''}`;
  return item.kind ? '' : 'Kind not said yet';
}

/** What you typed in the review's name, brand and price boxes. */
export interface Typed {
  name: string;
  brand: string;
  price: string;
}

/** The boxes as they start: what the item has now. */
export const typedOf = (item: Pick<ReviewItem, 'name' | 'brand' | 'price_cents'>): Typed =>
  ({ name: item.name ?? '', brand: item.brand ?? '', price: formatPrice(item.price_cents) });

/**
 * What "That's right" sends for an item: what it is (the kind you chose, else the one shown, so it becomes your word),
 * the name, brand and price you changed, and the doubtful fields (changed, or confirmed as they are). An error, and
 * nothing to send, when the price is not a price.
 */
export function checkBody(item: Pick<ReviewItem, 'name' | 'brand' | 'price_cents' | 'kind'>, typed: Typed, kind: string | null,
  rows: ReviewRow[], chosen: Record<string, string>): { body: CheckBody } | { error: string } {
  const price = parsePrice(typed.price);
  if (price === undefined) return { error: PRICE_HINT };
  const { changes, confirm } = reviewChanges(rows, chosen);
  const name = typed.name.trim();
  if (name !== (item.name ?? '')) changes.name = name || null;
  const brand = typed.brand.trim();
  if (brand !== (item.brand ?? '')) changes.brand = brand || null;
  if (price !== item.price_cents) changes.price_cents = price;
  const what = kind ?? item.kind ?? null;
  return { body: { ...(what ? { kind: what } : {}), changes, fields: confirm } };
}

/** "4 of 23" */
export function progressText(position: number, total: number): string {
  return `${position} of ${total}`;
}

/** "Claude was 55% sure" */
export function sureText(confidence: number): string {
  return `Claude was ${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}% sure`;
}

const items = (n: number) => `${n} ${n === 1 ? 'item' : 'items'}`;

/** Why some items are not in the queue yet, e.g. "3 items are still waiting to be described. 1 item couldn't be described." */
export function notReadyText(waiting: number, failed: number): string {
  const out: string[] = [];
  if (waiting) out.push(`${items(waiting)} ${waiting === 1 ? 'is' : 'are'} still waiting to be described.`);
  if (failed) out.push(`${items(failed)} couldn't be described.`);
  return out.join(' ');
}

/** What the end of a round says when some items were skipped. */
export function skippedText(skipped: number): string {
  return `You skipped ${items(skipped)}. ${skipped === 1 ? 'It stays' : 'They stay'} in the queue for next time.`;
}
