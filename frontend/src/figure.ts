/** The outfit drawn as worn: what is asked for it, and this device's choice between it and the pieces laid out. */
import { useSyncExternalStore } from 'react';
import type { OutfitPieces } from './today';
import type { ItemSummary } from './types';
import type { WouldPiece } from './wouldwork';

/** The item in each place of an outfit, and its accessories, as `POST /api/outfits/figure` takes them. */
export interface FigurePieces {
  base: string | null;
  mid: string | null;
  outer: string | null;
  bottom: string | null;
  shoes: string | null;
  accessories: string[];
  /** A piece not in the closet (a find, a piece being checked), worn wherever a place names `CANDIDATE_ID`. */
  piece?: WouldPiece;
}

/** The server takes at most this many accessories for one figure. */
export const MAX_ACCESSORIES = 8;

export function figurePieces(p: OutfitPieces, piece?: WouldPiece | null): FigurePieces {
  return {
    base: p.base || null, mid: p.mid || null, outer: p.outer || null, bottom: p.bottom || null, shoes: p.shoes || null,
    accessories: (p.accessories ?? []).filter(Boolean).slice(0, MAX_ACCESSORIES),
    ...(piece ? { piece } : {}),
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

/**
 * The outfit dressed one layer at a time, in the depth order the figure is painted in: first the trousers, the shoes
 * and the innermost top together (he is never shown undressed), then each top over it from the inside out, then the
 * accessories. Each step is the whole outfit up to that layer, so the server draws every one of them right (what is
 * under a coat is drawn as it is, not cut to where the coat shows it). The last step is the outfit itself. An outfit
 * with nothing to layer is one step.
 */
export function dressingSteps(p: FigurePieces): FigurePieces[] {
  const tops = (['base', 'mid', 'outer'] as const).filter((place) => p[place]);
  let now: FigurePieces = { base: null, mid: null, outer: null, bottom: p.bottom, shoes: p.shoes, accessories: [], ...(p.piece ? { piece: p.piece } : {}) };
  if (tops.length) now = { ...now, [tops[0]]: p[tops[0]] };
  const steps: FigurePieces[] = [];
  if (now.bottom || now.shoes || tops.length) steps.push(now);
  for (const place of tops.slice(1)) {
    now = { ...now, [place]: p[place] };
    steps.push(now);
  }
  if (p.accessories.length) steps.push({ ...now, accessories: p.accessories });
  return steps.length ? steps : [p];
}

/** The part of the figure's plane a drawing shows: its `viewBox`, or null when it has none that can be read. */
export function frameOf(svg: string): [number, number, number, number] | null {
  const m = /<svg\b[^>]*\bviewBox="([^"]+)"/.exec(svg);
  const v = m ? m[1].trim().split(/[\s,]+/).map(Number) : [];
  return v.length === 4 && v.every(Number.isFinite) && v[2] > 0 && v[3] > 0 ? [v[0], v[1], v[2], v[3]] : null;
}

/**
 * Where a step's drawing sits inside the outfit's own, as percentages of the outfit's frame. Every step is drawn in
 * the same plane, but each is framed round what it has (a bag beside him widens the outfit's), so a step is placed
 * by its frame rather than stretched to fill the outfit's.
 */
export function placeIn(step: [number, number, number, number], whole: [number, number, number, number]) {
  const pct = (v: number) => `${(v * 100).toFixed(3)}%`;
  return {
    left: pct((step[0] - whole[0]) / whole[2]), top: pct((step[1] - whole[1]) / whole[3]),
    width: pct(step[2] / whole[2]), height: pct(step[3] / whole[3]),
  };
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
