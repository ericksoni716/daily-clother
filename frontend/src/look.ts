/**
 * The item page's words about a garment's look and the owner's own words about it. The look comes from one place on
 * the server (`backend/closet/look.py`): the description the drawing was made from, with the owner's corrections
 * folded over it. So the one summary line under the name says what the drawing shows: what it is, its colour, its
 * pattern, and how it sits (`as_worn`, each word opening the detail that corrects it).
 */
import { label, shadeLabel, wornWords } from './labels';
import type { Item, ItemPatch, ItemSummary } from './types';

export interface LookPart {
  text: string;
  /** the detail that corrects this word in "Fix the details" (only the words of how it sits have one) */
  field?: string;
  part: string;
}

/** The one line under the name: "Oxford shirt · Light blue (oxford blue) · Regular fit · Long sleeves". From the
 * closet's summary alone (while the item is read) it says what it is and its colour. */
export function lookLine(item: Pick<ItemSummary, 'kind_name' | 'category' | 'color' | 'pattern'> & Partial<Pick<Item, 'shade' | 'as_worn'>>): LookPart[] {
  const out: LookPart[] = [];
  const what = item.kind_name || label('category', item.category);
  if (what) out.push({ text: what, part: 'kind' });
  const colour = shadeLabel(label('color', item.color), item.shade);
  const pattern = item.pattern && item.pattern !== 'solid' ? label('pattern', item.pattern) : '';
  if (colour && pattern) out.push({ text: `${colour}, ${pattern.toLowerCase()}`, part: 'colour' });
  else if (colour || pattern) out.push({ text: colour || pattern, part: 'colour' });
  const worn = wornWords(item.as_worn);
  for (const w of worn) out.push({ text: w.text.charAt(0).toUpperCase() + w.text.slice(1), field: w.field, part: w.part });
  return out;
}

/** The words of the line read as one, for a screen reader or a test. */
export const lookWords = (parts: LookPart[]) => parts.map((p) => p.text).join(' · ');

/** The owner's own boxes about an item that the one notes box takes in, in the order they are shown. `wear_notes` is
 * the box itself (the stylist reads it, and keeps what you tell it there); the others are older boxes. */
export const NOTE_FIELDS = ['wear_notes', 'fit_notes', 'notes', 'rating_reason'] as const;
type NoteField = (typeof NOTE_FIELDS)[number];
type Notes = Pick<Item, NoteField>;

/** What the one notes box shows: every note kept about the item, each once, one after the other. */
export function notesText(item: Notes): string {
  const seen: string[] = [];
  for (const f of NOTE_FIELDS) {
    const t = (item[f] ?? '').trim();
    if (t && !seen.includes(t)) seen.push(t);
  }
  return seen.join('\n');
}

/**
 * What saving the notes box changes, or null when nothing changed. The text goes into `wear_notes`, and the older boxes
 * it took in are emptied in the same save, so nothing is lost and nothing is kept twice. Until the box is changed the
 * older boxes stay as they are.
 */
export function notesPatch(text: string, item: Notes): ItemPatch | null {
  const t = text.trim();
  if (t === notesText(item)) return null;
  const patch: ItemPatch = { wear_notes: t || null };
  for (const f of NOTE_FIELDS) if (f !== 'wear_notes' && item[f]) patch[f] = null;
  return patch;
}

/** The title of the last fold, which holds what is done to an item rarely: describing it again, archiving, deleting. */
export function lastFoldTitle(archived: boolean, canRetag: boolean): string {
  if (archived) return 'Put it back or delete it';
  return canRetag ? 'Describe it again, archive or delete' : 'Archive or delete';
}

/** The words of the button under the summary line that opens "Fix the details": Claude reads a sentence there, unless
 * the demo closet is open (never sent to Claude), where the details are changed one by one. */
export const fixLabel = (demo: boolean) => (demo ? 'Something wrong? Change the details' : 'Something wrong? Tell Claude');
