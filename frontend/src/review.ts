/** Plain words and small helpers for the review queue (the screen is in screens/Review.tsx). */
import { SWATCH } from './labels';
import type { ItemPatch, ReviewField } from './types';

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
