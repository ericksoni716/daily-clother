/** Plain words for an item's drawing, and the closet grid's choice between photos and drawings. */
import type { TagState } from './types';

/** What is beside the drawing: the things Claude saw and the drawing's own notes, once each, as plain sentences. */
export function notInDrawing(seen: readonly string[] | null | undefined, notes: readonly string[] | null | undefined): string[] {
  const out: string[] = [];
  const had = new Set<string>();
  for (const raw of [...(seen ?? []), ...(notes ?? [])]) {
    const text = raw.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
    if (!text || had.has(text.toLowerCase())) continue;
    had.add(text.toLowerCase());
    out.push(text[0].toUpperCase() + text.slice(1));
  }
  return out;
}

/** What the drawing's place says when there is no drawing to show, or null when there is one. */
export function drawingPlaceholder(tagState: TagState | undefined, category: string | null, hasDrawing: boolean): string | null {
  if (hasDrawing) return null;
  if (tagState === 'waiting' || tagState === 'working') return 'Waiting to be described; the drawing comes after.';
  if (!category) return 'Choose what kind of item it is below, and a drawing is made.';
  return 'There is no drawing for this kind of item yet.';
}

export type GridView = 'photos' | 'drawings';

/** Where this device remembers whether the closet shows photos or drawings. */
export const GRID_VIEW_KEY = 'closet.gridView';

export function loadGridView(): GridView {
  try {
    return localStorage.getItem(GRID_VIEW_KEY) === 'drawings' ? 'drawings' : 'photos';
  } catch {
    return 'photos';
  }
}

export function saveGridView(view: GridView): void {
  try {
    localStorage.setItem(GRID_VIEW_KEY, view);
  } catch {
    /* private browsing: the choice lasts until the page is closed */
  }
}
