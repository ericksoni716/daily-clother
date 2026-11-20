import { describe, expect, it } from 'vitest';
import { isShoe, retakeOffer, retakeSaid, SHOE_RETAKEN } from './retake';
import type { ShoeTrace } from './types';

const PLAID_FAILED = 'Nines could not measure the checks from this photo, so the drawing shows only the colour.';
const trace: ShoeTrace = { state: null, message: null, drawn: false, plain: false, fixed: false, parts: [], marks: [] };
const shirt = (over: Partial<Parameters<typeof retakeOffer>[0]> = {}) => ({
  pattern: 'solid', pattern_state: null, pattern_error: null, cutout_state: 'ready' as const, trace: null, ...over,
});

describe('"Retake the photo" for clothes', () => {
  it('is offered beside the note that the pattern could not be measured', () => {
    expect(retakeOffer(shirt({ pattern: 'plaid', pattern_state: 'failed', pattern_error: PLAID_FAILED }))).toBe('pattern');
  });

  it('is offered in the notice that the background could not be removed', () => {
    expect(retakeOffer(shirt({ cutout_state: 'failed' }))).toBe('cutout');
  });

  it('is offered once when both went wrong: with the background, which comes first', () => {
    expect(retakeOffer(shirt({ cutout_state: 'failed', pattern: 'plaid', pattern_state: 'failed', pattern_error: 'x' })))
      .toBe('cutout');
  });

  it('is not offered when nothing went wrong, while measuring, or for a failure with nothing to say', () => {
    expect(retakeOffer(shirt())).toBeNull();
    expect(retakeOffer(shirt({ pattern: 'plaid', pattern_state: 'done' }))).toBeNull();
    expect(retakeOffer(shirt({ pattern: 'plaid', pattern_state: 'waiting' }))).toBeNull();
    expect(retakeOffer(shirt({ pattern: 'plaid', pattern_state: 'failed', pattern_error: null }))).toBeNull();
  });

  it('leaves shoes to their own retake, with their trace', () => {
    expect(isShoe({ trace })).toBe(true);
    expect(isShoe({ trace: null })).toBe(false);
    expect(isShoe({})).toBe(false);
    expect(retakeOffer(shirt({ trace, cutout_state: 'failed' }))).toBeNull();
    expect(retakeOffer(shirt({ trace, pattern_state: 'failed', pattern_error: 'x' }))).toBeNull();
  });

  it('says what happens next in plain words', () => {
    expect(retakeSaid(shirt(), false)).toBe('New photo added. Nines removes its background, then Claude describes it again');
    const plaid = retakeSaid(shirt({ pattern: 'plaid', pattern_state: 'failed', pattern_error: PLAID_FAILED }), false);
    expect(plaid).toBe('New photo added. Nines removes its background, Claude describes it again, then its pattern is measured again');
    expect(retakeSaid(shirt({ pattern: 'stripe' }), false)).toContain('pattern is measured again');
    expect(retakeSaid(shirt({ pattern: 'plaid' }), true))
      .toBe('New photo added. Its background is removed again; the demo closet keeps its description');
  });

  it('says what a shoe always said', () => {
    expect(SHOE_RETAKEN).toBe('New photo added; the shoe is traced again from it');
    expect(retakeSaid(shirt({ trace }), false)).toBe(SHOE_RETAKEN);
    expect(retakeSaid(shirt({ trace }), true)).toBe(SHOE_RETAKEN);
  });
});
