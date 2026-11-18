import { describe, expect, it } from 'vitest';
import {
  canSay, chosenBy, lookingAt, rememberWords, sameOutfits, savedLine, STYLIST_SLOW_S, stylistView, talkOf, waitingLine, withThing,
  type Outfit, type RememberThing, type StylistState, type TalkTurn, type TodayAnswer,
} from './today';

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

const style: RememberThing = { kind: 'style', item_id: null, name: null, text: 'Never shorts in town.', state: 'offered' };
const piece: RememberThing = { kind: 'piece', item_id: 'i1', name: 'Navy blazer', text: 'Fits well under a jacket.', state: 'offered' };
const turn = (over: Partial<TalkTurn> = {}): TalkTurn => ({
  id: 't1', said: 'Too dressy', state: 'ready', reply: 'Done.', message: null, remember: [style, piece], at: '2026-11-18T08:00:00', ...over,
});
const outfit = (base: string): Outfit => ({
  pieces: { base, mid: null, outer: null, bottom: 'b', shoes: 's', accessories: [] }, score: null, reasons: [], warnings: [],
});

describe('the conversation with Claude', () => {
  it('reads an older saved copy with no conversation as an empty one', () => {
    expect(talkOf(stylist('ready'))).toEqual({ talk: [], answering: null });
    expect(talkOf(null)).toEqual({ talk: [], answering: null });
    expect(talkOf(stylist('ready', { talk: [turn()], answering: 't1' }))).toEqual({ talk: [turn()], answering: 't1' });
  });

  it('sends nothing that is only spaces', () => {
    expect(canSay('')).toBe(false);
    expect(canSay('  \n ')).toBe(false);
    expect(canSay(' too dressy ')).toBe(true);
  });

  it('says which outfit is in front of the owner, kept within the outfits', () => {
    expect(lookingAt(0, 3)).toBe(0);
    expect(lookingAt(2, 3)).toBe(2);
    expect(lookingAt(5, 3)).toBe(2);
    expect(lookingAt(-1, 3)).toBe(0);
    expect(lookingAt(0, 0)).toBeNull();
  });

  it('asks about a thing for your style or for a piece in plain words', () => {
    expect(rememberWords(style)).toEqual({ question: 'Keep this for other days?', save: 'Save to Your style' });
    expect(rememberWords(piece)).toEqual({ question: 'Keep this on Navy blazer?', save: 'Save to its notes' });
    expect(savedLine(style)).toBe('Saved to Your style.');
    expect(savedLine(piece)).toBe("Saved to Navy blazer's notes.");
  });

  it('puts a thing as it now stands into its turn, and leaves everything else as it was', () => {
    const answer: TodayAnswer = {
      outfits: [], missing: [],
      context: { date: '2026-11-18', low_c: 3, high_c: 9, rain: false, source: 'given', old: false, place: null, rain_chance: null, summary: null,
        stylist: stylist('ready', { talk: [turn(), turn({ id: 't2' })], answering: null }) },
    };
    const next = withThing(answer, 't1', 1, { ...piece, state: 'saved' });
    expect(next.context.stylist!.talk![0].remember.map((r) => r.state)).toEqual(['offered', 'saved']);
    expect(next.context.stylist!.talk![1].remember.map((r) => r.state)).toEqual(['offered', 'offered']);
    expect(answer.context.stylist!.talk![0].remember[1].state).toBe('offered');
    expect(withThing(answer, 'nope', 0, style)).toBe(answer);
    expect(withThing(answer, 't1', 5, style)).toBe(answer);
  });

  it('tells whether the outfits changed after an answer', () => {
    expect(sameOutfits([outfit('a'), outfit('b')], [outfit('a'), outfit('b')])).toBe(true);
    expect(sameOutfits([outfit('a'), outfit('b')], [outfit('b'), outfit('a')])).toBe(false);
    expect(sameOutfits([outfit('a')], [outfit('a'), outfit('b')])).toBe(false);
  });
});
