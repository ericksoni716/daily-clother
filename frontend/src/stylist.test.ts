import { describe, expect, it } from 'vitest';
import { chosenBy, STYLIST_SLOW_S, stylistView, waitingLine, type StylistState } from './today';

const stylist = (state: StylistState['state'], over: Partial<StylistState> = {}): StylistState => ({
  state, id: 'a1', read: null, message: null, ...over,
});

describe('what Today shows about Claude choosing', () => {
  it('shows nothing when Claude does not choose here', () => {
    expect(stylistView(undefined, false)).toBe('none');
    expect(stylistView(null, false)).toBe('none');
  });

  it('waits while Claude is choosing, but never on a saved copy', () => {
    expect(stylistView(stylist('working'), false)).toBe('waiting');
    expect(stylistView(stylist('working'), true)).toBe('none');
  });

  it("shows Claude's sentence once ready and why when it could not choose, saved or not", () => {
    expect(stylistView(stylist('ready', { read: 'A cold morning.' }), false)).toBe('read');
    expect(stylistView(stylist('ready'), true)).toBe('read');
    // "Ask Claude again" refused by the daily limit: still Claude's outfits, with a note, and no waiting card
    expect(stylistView(stylist('ready', { message: 'Claude has chosen outfits 12 times today, the most in one day, so these are still the ones it chose last.' }), false)).toBe('read');
    expect(stylistView(stylist('failed', { id: null, message: 'No.' }), false)).toBe('failed');
    expect(stylistView(stylist('failed'), true)).toBe('failed');
  });
});

describe('who chose an outfit', () => {
  it("says Claude for Claude's outfits", () => {
    expect(chosenBy({ by: 'claude' }, stylist('ready'))).toBe('Chosen by Claude');
  });

  it("says Closet's rules for the others once Claude has answered or could not", () => {
    expect(chosenBy({}, stylist('ready'))).toBe("From Closet's rules");
    expect(chosenBy({}, stylist('failed'))).toBe("From Closet's rules");
  });

  it('says nothing while Claude is choosing or when Claude does not choose here', () => {
    expect(chosenBy({}, stylist('working'))).toBeNull();
    expect(chosenBy({}, null)).toBeNull();
    expect(chosenBy({}, undefined)).toBeNull();
  });
});

describe('the line on the waiting card', () => {
  it('says how long it usually takes, then that it is taking longer', () => {
    expect(waitingLine(0)).toBe('This usually takes about 20 seconds. They are kept for the rest of the day.');
    expect(waitingLine(STYLIST_SLOW_S - 1)).toMatch(/about 20 seconds/);
    expect(waitingLine(STYLIST_SLOW_S)).toBe('This is taking longer than usual.');
  });
});
