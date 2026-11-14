import { describe, expect, it } from 'vitest';
import { addLabel, boxStyle, cropStyle, MIN_SIDE, moveBox, moveCorner, pointAt, sameBox, sourceLine } from './several';

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
