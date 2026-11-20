/** Plain words for an item's drawing, and the closet grid's choice between photos and drawings. What the drawing's
 * place says while there is none is in progress.ts. */

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
