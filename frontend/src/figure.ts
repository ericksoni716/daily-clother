/** The outfit drawn as worn: what is asked for it, and this device's choice between it and the pieces laid out. */
import { useSyncExternalStore } from 'react';
import type { OutfitPieces } from './today';

/** The item in each place of an outfit, as `POST /api/outfits/figure` takes them (accessories are not drawn). */
export interface FigurePieces {
  base: string | null;
  mid: string | null;
  outer: string | null;
  bottom: string | null;
  shoes: string | null;
}

export function figurePieces(p: OutfitPieces): FigurePieces {
  return { base: p.base || null, mid: p.mid || null, outer: p.outer || null, bottom: p.bottom || null, shoes: p.shoes || null };
}

/** The drawing as something an <img> can show (an <img> never runs anything inside an SVG). */
export function svgSource(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export type TodayView = 'pieces' | 'worn';

/** Where this device remembers whether Today lays the pieces out or shows the outfit as worn. */
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

/** The choice, shared by every outfit card on the screen: switching one switches them all. */
export function useTodayView(): [TodayView, (view: TodayView) => void] {
  const view = useSyncExternalStore(subscribe, () => (current ??= loadTodayView()));
  return [view, saveTodayView];
}
