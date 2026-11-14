/** Boxes around the pieces in a photo of several: moving their corners, and placing them on the screen. Pure, so
 * it is tested without a browser. Every box is fractions of the photo (0 left/top, 1 right/bottom). */
import type { CSSProperties } from 'react';
import type { BoxEdges } from './types';

/** The smallest a box can be made, as a share of the photo's width or height (the server refuses smaller). */
export const MIN_SIDE = 0.04;

export type Corner = 'nw' | 'ne' | 'sw' | 'se';
export const CORNERS: readonly Corner[] = ['nw', 'ne', 'sw', 'se'];

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const round = (v: number) => Math.round(v * 10000) / 10000;
const tidy = (b: BoxEdges): BoxEdges => ({ x0: round(b.x0), y0: round(b.y0), x1: round(b.x1), y1: round(b.y1) });

/** Where a pointer is on the photo, as fractions, kept inside it. */
export function pointAt(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): { x: number; y: number } {
  return {
    x: rect.width > 0 ? clamp((clientX - rect.left) / rect.width, 0, 1) : 0,
    y: rect.height > 0 ? clamp((clientY - rect.top) / rect.height, 0, 1) : 0,
  };
}

/** The box with one corner dragged to (x, y): kept inside the photo, never smaller than MIN_SIDE and never
 * turned inside out (the corner stops at the opposite edges). */
export function moveCorner(box: BoxEdges, corner: Corner, x: number, y: number): BoxEdges {
  const out = { ...box };
  if (corner === 'nw' || corner === 'sw') out.x0 = clamp(x, 0, box.x1 - MIN_SIDE);
  else out.x1 = clamp(x, box.x0 + MIN_SIDE, 1);
  if (corner === 'nw' || corner === 'ne') out.y0 = clamp(y, 0, box.y1 - MIN_SIDE);
  else out.y1 = clamp(y, box.y0 + MIN_SIDE, 1);
  return tidy(out);
}

/** The whole box moved by (dx, dy), stopping at the photo's edges. */
export function moveBox(box: BoxEdges, dx: number, dy: number): BoxEdges {
  const w = box.x1 - box.x0;
  const h = box.y1 - box.y0;
  const x0 = clamp(box.x0 + dx, 0, 1 - w);
  const y0 = clamp(box.y0 + dy, 0, 1 - h);
  return tidy({ x0, y0, x1: x0 + w, y1: y0 + h });
}

/** A new box for the owner to drag into place: the middle of the photo. */
export function newBox(): BoxEdges {
  return { x0: 0.3, y0: 0.3, x1: 0.7, y1: 0.7 };
}

/** The same place, so a drag that ends where it began sends nothing. */
export function sameBox(a: BoxEdges, b: BoxEdges): boolean {
  return a.x0 === b.x0 && a.y0 === b.y0 && a.x1 === b.x1 && a.y1 === b.y1;
}

/** The box laid over the photo, in percent of it. */
export function boxStyle(box: BoxEdges): CSSProperties {
  return {
    left: `${box.x0 * 100}%`, top: `${box.y0 * 100}%`,
    width: `${(box.x1 - box.x0) * 100}%`, height: `${(box.y1 - box.y0) * 100}%`,
  };
}

/** The box's part of the photo, shown while its cutout cannot be made: a frame the box's shape, and the photo
 * inside it scaled and shifted so the box fills the frame. */
export function cropStyle(box: BoxEdges, width: number, height: number): { frame: CSSProperties; img: CSSProperties } {
  const w = Math.max(box.x1 - box.x0, 0.001);
  const h = Math.max(box.y1 - box.y0, 0.001);
  return {
    frame: {
      aspectRatio: `${Math.max(1, Math.round(w * width))} / ${Math.max(1, Math.round(h * height))}`,
      ...(w * width >= h * height ? { width: '100%' } : { height: '100%' }),   // fits its square, as a contained image
    },
    img: {
      width: `${100 / w}%`, height: `${100 / h}%`,
      left: `${(-box.x0 / w) * 100}%`, top: `${(-box.y0 / h) * 100}%`,
    },
  };
}

/** The button that makes the items: "Add this item", "Add these 3 items". */
export function addLabel(n: number): string {
  return n === 1 ? 'Add this item' : `Add these ${n} items`;
}

/** What the open photo of several pieces is waiting for, in a few words, for the list on Add. */
export function sourceLine(state: 'finding' | 'review' | 'added', boxes: number, note: string | null): string {
  if (state === 'added') return 'Added to your closet';
  if (state === 'finding') return note ? 'Waiting to look for the pieces' : 'Looking for the pieces…';
  if (!boxes) return 'No pieces marked yet';
  return `${boxes} ${boxes === 1 ? 'piece' : 'pieces'} to check`;
}
