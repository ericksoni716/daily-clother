/** Plain words for an item's drawing, and which picture of an item is shown: Settings' "Show drawings instead of
 * photos" and the closet grid's switch. What the drawing's place says while there is none is in progress.ts. */
import { createContext, useContext } from 'react';
import type { ItemSummary } from './types';

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

/**
 * Settings' "Show drawings instead of photos" (`show_drawings`, kept on the computer for every device): the open
 * closet's provider reads it with the settings and gives it here, so every small picture of an item follows it.
 */
export const ShowDrawings = createContext(false);

export const useShowDrawings = () => useContext(ShowDrawings);

/** Where this device keeps the last word it had on the setting, so the pictures follow it while Nines cannot be
 * reached, and do not change while the settings are read again. */
export const SHOW_DRAWINGS_KEY = 'closet.showDrawings';

export function loadShowDrawings(): boolean {
  try {
    return localStorage.getItem(SHOW_DRAWINGS_KEY) === '1';
  } catch {
    return false;
  }
}

export function keepShowDrawings(on: boolean): void {
  try {
    localStorage.setItem(SHOW_DRAWINGS_KEY, on ? '1' : '0');
  } catch {
    /* private browsing: the pictures follow the setting whenever Nines can be reached */
  }
}

/** The closet's Photos / Drawings switch, used for the moment: what was chosen, and under which setting. */
export interface MomentView { view: GridView; setting: boolean }

/**
 * What the closet grid shows: the setting, unless the switch over the grid was used since the page was opened and
 * the setting has not changed since. Nothing about the switch is kept, so the setting is where the closet starts.
 */
export function gridViewOf(showDrawings: boolean, moment: MomentView | null): GridView {
  if (moment && moment.setting === showDrawings) return moment.view;
  return showDrawings ? 'drawings' : 'photos';
}

export type SmallPicture = 'drawing' | 'cutout' | 'photo' | 'none';

/**
 * Which picture an item's small picture is. With drawings asked for (the setting, or the grid's switch), the drawing
 * when the item has one. Otherwise the cutout once it is ready, then, where the item has both, the photo before the
 * drawing on a closet tile (`photoFirst`) and the drawing before the photo on a card (Today, Worn, the Wardrobe).
 */
export function smallPicture(item: Pick<ItemSummary, 'illustration_url' | 'thumb_url' | 'cutout_state'>, drawings: boolean,
  photoFirst = false): SmallPicture {
  if (drawings && item.illustration_url) return 'drawing';
  if (item.cutout_state === 'ready' && item.thumb_url) return 'cutout';
  if (photoFirst && item.thumb_url) return 'photo';
  if (item.illustration_url) return 'drawing';
  return item.thumb_url ? 'photo' : 'none';
}
