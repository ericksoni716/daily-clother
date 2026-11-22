/** Boxes around the pieces in a photo of several: moving their corners, placing them on the screen, undoing a change
 * and putting Claude's boxes back. Pure, so it is tested without a browser. Every box is fractions of the photo
 * (0 left/top, 1 right/bottom). */
import type { CSSProperties } from 'react';
import type { BoxEdges, PlainBox, SourcePhoto } from './types';

/** While Claude looks for the pieces in the photo. */
export const FINDING_POLL_MS = 2000;

/** How often the photo is asked for again: while Claude looks for the pieces in it, and not at all once it is done. */
export function sourcePoll(src: Pick<SourcePhoto, 'state'> | null | undefined): number | false {
  return src?.state === 'finding' ? FINDING_POLL_MS : false;
}

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

// ------------------------------------------------------------------ undo, and Claude's boxes put back

/** A box as it is sent back whole: its place, its id (so its cutout is kept) and what Claude called it. */
export function plain(b: PlainBox): PlainBox {
  return { id: b.id, x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, label: b.label };
}

/** One change the owner can undo: the boxes as they were before it, and what it was, in a few words. */
export interface Undo {
  before: PlainBox[];
  words: string;
}

/** How many changes Undo can go back through. */
export const UNDO_KEPT = 30;

/** The changes so far with one more, the oldest dropped past UNDO_KEPT. */
export function remember(stack: readonly Undo[], before: readonly PlainBox[], words: string): Undo[] {
  return [...stack, { before: before.map(plain), words }].slice(-UNDO_KEPT);
}

/** The same boxes, in the same order, in the same places. */
export function sameBoxes(a: readonly PlainBox[], b: readonly PlainBox[]): boolean {
  return a.length === b.length && a.every((x, i) => x.id === b[i].id && sameBox(x, b[i]) && x.label === b[i].label);
}

/** Whether the boxes are no longer what Claude found: "Back to what Claude found" is offered then. */
export function differsFromFound(boxes: readonly PlainBox[], found: readonly PlainBox[]): boolean {
  return found.length > 0 && !sameBoxes(boxes, found);
}

/** Claude's box with this id when the owner has moved, reshaped or joined it since; null when it is as Claude found
 * it, or Claude never found it. */
export function foundVersion(box: PlainBox, found: readonly PlainBox[]): PlainBox | null {
  const was = found.find((f) => f.id === box.id);
  return was && !(sameBox(was, box) && was.label === box.label) ? was : null;
}

/** Claude's boxes the owner has removed (or joined into another), in Claude's order. */
export function removedFound(boxes: readonly PlainBox[], found: readonly PlainBox[]): PlainBox[] {
  return found.filter((f) => !boxes.some((b) => b.id === f.id));
}

/** The boxes with one of Claude's put back as it found it: in its place when it is there, else back in its turn
 * (after the nearest of Claude's boxes before it that is still there). */
export function putBack(boxes: readonly PlainBox[], found: readonly PlainBox[], id: string): PlainBox[] {
  const was = found.find((f) => f.id === id);
  const now = boxes.map(plain);
  if (!was) return now;
  const at = now.findIndex((b) => b.id === id);
  if (at >= 0) {
    now[at] = plain(was);
    return now;
  }
  const order = found.findIndex((f) => f.id === id);
  let after = -1;
  for (let i = order - 1; i >= 0 && after < 0; i -= 1) after = now.findIndex((b) => b.id === found[i].id);
  now.splice(after + 1, 0, plain(was));
  return now;
}

/** What a box is called in the words about a change: "box 2 (red shirt)", "box 3", or Claude's name alone when it
 * has no number on the photo any more. */
export function pieceName(b: { n?: number; label: string | null }): string {
  if (!b.n) return b.label ?? 'a piece';
  return b.label ? `box ${b.n} (${b.label})` : `box ${b.n}`;
}
