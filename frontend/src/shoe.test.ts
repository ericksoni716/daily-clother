import { describe, expect, it } from 'vitest';
import { checkHeadline, FRONT_VIEWS, frontPreviewUrl, NUDGE_CM, NUDGES, nudgeLabel, traceNotice, tracing } from './shoe';
import type { ShoeTrace } from './types';

const trace = (state: ShoeTrace['state'], message: string | null): ShoeTrace => ({
  state, message, drawn: false, plain: false, fixed: false, parts: [], marks: [],
});

describe('the item page about a shoe trace', () => {
  it('says nothing for anything that is not a shoe, or a shoe traced well', () => {
    expect(traceNotice(null)).toBeNull();
    expect(traceNotice(undefined)).toBeNull();
    expect(traceNotice(trace('done', null))).toBeNull();
  });

  it('says it is being traced, without offering a retake', () => {
    expect(traceNotice(trace('working', 'Drawing the shoe from its photo…'))).toEqual(
      { tone: 'info', text: 'Drawing the shoe from its photo…', retake: false });
    expect(tracing(trace('waiting', 'x'))).toBe(true);
    expect(tracing(trace('working', 'x'))).toBe(true);
    expect(tracing(trace('done', null))).toBe(false);
    expect(tracing(null)).toBe(false);
  });

  it('explains a refused or failed photo and offers to retake it', () => {
    const why = "The photo shows the shoe from the front, so it's drawn from its details instead.";
    expect(traceNotice(trace('refused', why))).toEqual({ tone: 'warn', text: why, retake: true });
    expect(traceNotice(trace('failed', 'It could not be traced.'))?.retake).toBe(true);
  });
});

describe('fixing the marks', () => {
  it('moves a mark half a centimetre each way, in plain words', () => {
    expect(NUDGES.map((n) => n.step)).toEqual([[NUDGE_CM, 0], [0, NUDGE_CM], [0, -NUDGE_CM], [-NUDGE_CM, 0]]);
    expect(NUDGE_CM).toBe(0.5);
    expect(nudgeLabel('stripe', 'toe')).toBe('Move the stripe towards the toe');
    expect(nudgeLabel('logo', 'down')).toBe('Move the logo down');
  });
});

describe("Add's instant check", () => {
  it('heads the answer in one sentence', () => {
    expect(checkHeadline({ ok: true, reasons: [] })).toBe('This photo should trace well.');
    expect(checkHeadline({ ok: false, reasons: ['x'] })).toBe('This photo may not trace well.');
  });
});

describe("a traced shoe's front view on the figure", () => {
  it('offers the two views in plain words, the shape first', () => {
    expect(FRONT_VIEWS.map((v) => v.kind)).toEqual(['shape', 'photo']);
    expect(FRONT_VIEWS.map((v) => v.title)).toEqual(["From the shoe's shape", 'From your photo']);
  });

  it('asks for each preview anew when the item changes', () => {
    const item = { id: 'a b', updated_at: '2026-11-15T06:00:00+00:00' };
    expect(frontPreviewUrl(item, 'shape')).toBe('/api/items/a%20b/trace/front.svg?kind=shape&v=2026-11-15T06%3A00%3A00%2B00%3A00');
    expect(frontPreviewUrl({ ...item, updated_at: 'later' }, 'photo')).toBe('/api/items/a%20b/trace/front.svg?kind=photo&v=later');
  });
});
