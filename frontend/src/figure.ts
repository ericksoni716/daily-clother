/** The outfit drawn as worn: what is asked for it, and this device's choice between it and the pieces laid out. */
import { useSyncExternalStore } from 'react';
import type { OutfitPieces } from './today';
import type { ItemSummary } from './types';

/** The item in each place of an outfit, and its accessories, as `POST /api/outfits/figure` takes them. */
export interface FigurePieces {
  base: string | null;
  mid: string | null;
  outer: string | null;
  bottom: string | null;
  shoes: string | null;
  accessories: string[];
}

/** The server takes at most this many accessories for one figure. */
export const MAX_ACCESSORIES = 8;

export function figurePieces(p: OutfitPieces): FigurePieces {
  return {
    base: p.base || null, mid: p.mid || null, outer: p.outer || null, bottom: p.bottom || null, shoes: p.shoes || null,
    accessories: (p.accessories ?? []).filter(Boolean).slice(0, MAX_ACCESSORIES),
  };
}

/**
 * What the outfit figure is drawn from, for the items `ids`: each one's drawing (its address changes with it) and, for
 * a shoe Claude drew, that drawing's version. It changes whenever the figure would, so the figure is asked for again.
 */
export function figureVersion(ids: string[], byId: Map<string, Pick<ItemSummary, 'illustration_url' | 'drawn_version'>>): string {
  return ids.map((id) => {
    const item = byId.get(id);
    return `${item?.illustration_url ?? ''}${item?.drawn_version ? `#${item.drawn_version}` : ''}`;
  }).join(' ');
}

/** The drawing as something an <img> can show (an <img> never runs anything inside an SVG). */
export function svgSource(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export type TodayView = 'pieces' | 'worn';

/** The switch's two choices, the same wherever outfits are shown (Today, a trip's days). */
export const VIEW_OPTIONS: readonly { value: TodayView; label: string }[] = [
  { value: 'pieces', label: 'Pieces' }, { value: 'worn', label: 'As worn' },
];

/** Where this device remembers whether outfits (on Today and a trip's days) are laid out as pieces or shown as worn. */
export const TODAY_VIEW_KEY = 'closet.todayView';

export function loadTodayView(): TodayView {
  try {
    return localStorage.getItem(TODAY_VIEW_KEY) === 'worn' ? 'worn' : 'pieces';
  } catch {
    return 'pieces';
  }
}

const listeners = new Set<() => void>();
let current: TodayView | null = null;

export function saveTodayView(view: TodayView): void {
  current = view;
  try {
    localStorage.setItem(TODAY_VIEW_KEY, view);
  } catch {
    /* private browsing: the choice lasts until the page is closed */
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** The choice, shared by every outfit on Today and on a trip: switching one switches them all. */
export function useTodayView(): [TodayView, (view: TodayView) => void] {
  const view = useSyncExternalStore(subscribe, () => (current ??= loadTodayView()));
  return [view, saveTodayView];
}
