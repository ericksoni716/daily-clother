import { describe, expect, it } from 'vitest';
import {
  addLabel, boxStyle, cropStyle, differsFromFound, FINDING_POLL_MS, foundVersion, MIN_SIDE, moveBox, moveCorner, pieceName, plain,
  pointAt, putBack, remember, removedFound, sameBox, sameBoxes, sourceLine, sourcePoll, UNDO_KEPT,
} from './several';
import type { PlainBox } from './types';

const box = { x0: 0.2, y0: 0.1, x1: 0.6, y1: 0.5 };

describe('moving a corner', () => {
  it('moves only the edges that meet at that corner', () => {
    expect(moveCorner(box, 'nw', 0.1, 0.05)).toEqual({ x0: 0.1, y0: 0.05, x1: 0.6, y1: 0.5 });
    expect(moveCorner(box, 'se', 0.7, 0.8)).toEqual({ x0: 0.2, y0: 0.1, x1: 0.7, y1: 0.8 });
    expect(moveCorner(box, 'ne', 0.65, 0.2)).toEqual({ x0: 0.2, y0: 0.2, x1: 0.65, y1: 0.5 });
    expect(moveCorner(box, 'sw', 0.3, 0.3)).toEqual({ x0: 0.3, y0: 0.1, x1: 0.6, y1: 0.3 });
  });

  it('stays inside the photo', () => {
    expect(moveCorner(box, 'nw', -0.5, -1)).toEqual({ x0: 0, y0: 0, x1: 0.6, y1: 0.5 });
    expect(moveCorner(box, 'se', 3, 1.2)).toEqual({ x0: 0.2, y0: 0.1, x1: 1, y1: 1 });
  });

  it('never turns the box inside out or makes it too small to hold a piece', () => {
    const out = moveCorner(box, 'nw', 0.9, 0.9);
    expect(out.x1 - out.x0).toBeCloseTo(MIN_SIDE);
    expect(out.y1 - out.y0).toBeCloseTo(MIN_SIDE);
    expect(out.x1).toBe(0.6);
    expect(out.y1).toBe(0.5);
  });
});

describe('moving the whole box', () => {
  it('keeps its size and stops at the edges', () => {
    expect(moveBox(box, 0.1, 0.1)).toEqual({ x0: 0.3, y0: 0.2, x1: 0.7, y1: 0.6 });
    expect(moveBox(box, 1, -1)).toEqual({ x0: 0.6, y0: 0, x1: 1, y1: 0.4 });
  });
});

describe('placing boxes on the screen', () => {
  it('turns a pointer into a share of the photo, kept inside it', () => {
    const rect = { left: 100, top: 50, width: 400, height: 200 };
    expect(pointAt(300, 100, rect)).toEqual({ x: 0.5, y: 0.25 });
    expect(pointAt(0, 400, rect)).toEqual({ x: 0, y: 1 });
    expect(pointAt(10, 10, { left: 0, top: 0, width: 0, height: 0 })).toEqual({ x: 0, y: 0 });
  });

  it('lays the box over the photo in percent', () => {
    const s = boxStyle(box);
    expect(parseFloat(String(s.left))).toBeCloseTo(20);
    expect(parseFloat(String(s.top))).toBeCloseTo(10);
    expect(parseFloat(String(s.width))).toBeCloseTo(40);
    expect(parseFloat(String(s.height))).toBeCloseTo(40);
  });

  it('crops the photo to the box when no cutout can be shown', () => {
    const { frame, img } = cropStyle(box, 1000, 500);
    expect(frame.aspectRatio).toBe('400 / 200');
    expect(parseFloat(String(img.width))).toBeCloseTo(250);
    expect(parseFloat(String(img.height))).toBeCloseTo(250);
    expect(parseFloat(String(img.left))).toBeCloseTo(-50);
    expect(parseFloat(String(img.top))).toBeCloseTo(-25);
  });

  it('knows a box that did not move', () => {
    expect(sameBox(box, { ...box })).toBe(true);
    expect(sameBox(box, moveBox(box, 0.01, 0))).toBe(false);
  });
});

describe('words', () => {
  it('names the button by how many items it adds', () => {
    expect(addLabel(1)).toBe('Add this item');
    expect(addLabel(3)).toBe('Add these 3 items');
  });

  it('says what a photo of several pieces is waiting for', () => {
    expect(sourceLine('finding', 0, null)).toBe('Looking for the pieces…');
    expect(sourceLine('finding', 0, "Claude can't be reached")).toBe('Waiting to look for the pieces');
    expect(sourceLine('review', 0, null)).toBe('No pieces marked yet');
    expect(sourceLine('review', 1, null)).toBe('1 piece to check');
    expect(sourceLine('review', 4, null)).toBe('4 pieces to check');
    expect(sourceLine('added', 4, null)).toBe('Added to your closet');
  });
});

describe('asking for the photo again', () => {
  it('asks again while Claude looks for the pieces, and not once it has found them or they are added', () => {
    expect(sourcePoll({ state: 'finding' })).toBe(FINDING_POLL_MS);
    expect(sourcePoll({ state: 'review' })).toBe(false);
    expect(sourcePoll({ state: 'added' })).toBe(false);
    expect(sourcePoll(null)).toBe(false);
  });
});

describe('undoing a change, and putting back the boxes Claude found', () => {
  // Claude's three boxes, as the server keeps them
  const found: PlainBox[] = [
    { id: 'a1', x0: 0.05, y0: 0.1, x1: 0.35, y1: 0.9, label: 'red shirt' },
    { id: 'b2', x0: 0.4, y0: 0.1, x1: 0.65, y1: 0.9, label: 'blue jeans' },
    { id: 'c3', x0: 0.7, y0: 0.2, x1: 0.95, y1: 0.6, label: null },
  ];
  const [shirt, jeans, cap] = found;

  it('removing a box: it is listed as removed, put back in its turn, and Undo has the boxes from before', () => {
    const now = [shirt, cap];
    expect(removedFound(now, found)).toEqual([jeans]);
    expect(differsFromFound(now, found)).toBe(true);
    expect(putBack(now, found, 'b2')).toEqual(found);   // between the two it was between
    expect(putBack([cap], found, 'a1')).toEqual([shirt, cap]);   // first, as it was
    const undos = remember([], found, 'Removed box 2 (blue jeans).');
    expect(undos).toEqual([{ before: found, words: 'Removed box 2 (blue jeans).' }]);
    expect(sameBoxes(undos[0].before, found)).toBe(true);
  });

  it('reshaping a box: it is offered back as Claude found it, and only that box changes', () => {
    const reshaped = { ...jeans, ...moveCorner(jeans, 'se', 0.8, 0.95) };
    const now = [shirt, reshaped, cap];
    expect(foundVersion(reshaped, found)).toEqual(jeans);
    expect(foundVersion(shirt, found)).toBeNull();
    expect(putBack(now, found, 'b2')).toEqual(found);
    expect(differsFromFound(putBack(now, found, 'b2'), found)).toBe(false);
  });

  it('a joined box can be put back, and the box it was joined into too', () => {
    const joined = { ...shirt, x1: 0.65 };   // the shirt and the jeans joined: the shirt keeps its id
    const now = [joined, cap];
    expect(foundVersion(joined, found)).toEqual(shirt);
    expect(removedFound(now, found)).toEqual([jeans]);
    expect(putBack(putBack(now, found, 'b2'), found, 'a1')).toEqual(found);
  });

  it('a box the owner drew is never offered back, and is dropped by going back to all of Claude\'s', () => {
    const drawn = { id: 'd4', x0: 0.3, y0: 0.3, x1: 0.7, y1: 0.7, label: null };
    expect(foundVersion(drawn, found)).toBeNull();
    expect(putBack([...found, drawn], found, 'd4')).toEqual([...found, drawn]);
    expect(differsFromFound([...found, drawn], found)).toBe(true);
  });

  it('nothing is offered when Claude found nothing, or the boxes are as it found them', () => {
    expect(differsFromFound([shirt], [])).toBe(false);
    expect(differsFromFound(found.map((b) => ({ ...b, n: 1, cutout_url: '/x' } as PlainBox)), found)).toBe(false);
    expect(removedFound(found, found)).toEqual([]);
  });

  it('keeps the boxes as they were, without what the page adds to them, and only so many changes back', () => {
    expect(plain({ ...shirt, n: 1, cutout_url: '/c' } as PlainBox)).toEqual(shirt);
    let stack = remember([], found, 'first');
    for (let i = 0; i < UNDO_KEPT + 5; i += 1) stack = remember(stack, [shirt], `change ${i}`);
    expect(stack).toHaveLength(UNDO_KEPT);
    expect(stack[stack.length - 1].words).toBe(`change ${UNDO_KEPT + 4}`);
  });

  it('names a box by its number and what Claude called it', () => {
    expect(pieceName({ n: 2, label: 'blue jeans' })).toBe('box 2 (blue jeans)');
    expect(pieceName({ n: 3, label: null })).toBe('box 3');
    expect(pieceName({ label: 'red shirt' })).toBe('red shirt');
  });
});
