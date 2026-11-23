import { describe, expect, it } from 'vitest';
import type { LookFor, Wish } from './gaps';
import {
  type Check, checkKinds, checkPoll, drawnFromWords, outfitStep, wornError, POLL_MS, fillNote, fillWords, isDone, noteFor, pieceFromLook, pieceFromWish, PIECE_NAME_MAX, pieceToSend, stillToChoose, verdictTone, waitingWords, WEIGHTS, weightLabel, wishById,
  wishFrom, wornWords, nextCheck, pieceLine, untoldWords, keptCheck, type KeptCheck,
} from './wouldwork';
import { forgetSaved } from './today';

const look = (over: Partial<LookFor> = {}): LookFor => ({
  category: 'coat', formality: 'smart_casual', season: 'all', weight_class: 'midweight', colors: [], pattern: 'solid',
  material: 'waterproof (a mac, trench, waxed cotton or shell)', ...over,
});

const check = (over: Partial<Check> = {}): Check => ({
  id: 'c1', state: 'ready', way: 'by_hand', piece: { category: 'coat', color: 'tan' }, piece_words: 'Tan coat, smart casual, all year',
  answer: null, message: null, by_hand: false, started_at: '', finished_at: null, ...over,
});

describe('describing the piece', () => {
  it('starts from a wish, rain-proof when the wish asks for that', () => {
    expect(pieceFromLook(look())).toEqual({
      category: 'coat', formality: 'smart_casual', season: 'all', weight_class: 'midweight', pattern: 'solid', rain_proof: true,
    });
    expect(pieceFromLook(look({ material: null, colors: ['navy'] })).color).toBe('navy');
    expect(pieceFromLook(look({ colors: ['navy', 'grey'] })).color).toBeUndefined();
    expect(pieceFromLook(null)).toEqual({});
  });

  it('starts from a page you sent for the wish with its product’s name, cut at a word to fit', () => {
    const link = (name?: string) => ({ name, shop: 'Example Shop', price: 68, currency: 'USD', available: true });
    expect(pieceFromWish({ look_for: null, link: link('Linen camp-collar shirt') })).toEqual({ name: 'Linen camp-collar shirt' });
    expect(pieceFromWish({ look_for: look(), link: link('Tan trench') })).toEqual({ ...pieceFromLook(look()), name: 'Tan trench' });
    expect(pieceFromWish({ look_for: look(), link: null })).toEqual(pieceFromLook(look()));
    expect(pieceFromWish({ look_for: null, link: link() })).toEqual({});
    expect(pieceFromWish(null)).toEqual({});
    const long = pieceFromWish({ look_for: null, link: link('Heavyweight garment-dyed linen shirt '.repeat(5)) }).name!;
    expect(long.length).toBeLessThanOrEqual(PIECE_NAME_MAX);
    expect(long).toMatch(/shirt…$/);
  });

  it('sends only what was chosen', () => {
    expect(pieceToSend({ category: 'coat', color: 'navy', formality: null, rain_proof: false, name: '  ' })).toEqual({ category: 'coat', color: 'navy' });
    expect(pieceToSend({ category: 'coat', color: 'navy', rain_proof: true, name: ' Trench ' })).toEqual({
      category: 'coat', color: 'navy', rain_proof: true, name: 'Trench',
    });
  });

  it('says what is still to choose', () => {
    expect(stillToChoose({})).toBe('Choose what kind of piece it is and its colour.');
    expect(stillToChoose({ color: 'navy' })).toBe('Choose what kind of piece it is.');
    expect(stillToChoose({ category: 'coat' })).toBe('Choose its main colour.');
    expect(stillToChoose({ category: 'coat', color: 'navy' })).toBeNull();
  });

  it('offers every kind but "other", and plain words for weights', () => {
    expect(checkKinds(['tee', 'coat', 'other'])).toEqual(['tee', 'coat']);
    expect(WEIGHTS.map(weightLabel)).toEqual(['Light', 'Medium', 'Heavy', 'Very heavy']);
  });
});

describe('by hand: the kind and the colour first, the answer at once (23 November)', () => {
  const quiet = { checked: null, busy: false, choosing: false, locked: false };

  it('asks for the answer as soon as the kind and the colour are known, with no button to press', () => {
    expect(nextCheck({}, quiet)).toBeNull();
    expect(nextCheck({ category: 'coat' }, quiet)).toBeNull();
    expect(nextCheck({ category: 'coat', color: 'tan' }, quiet)).toEqual({ category: 'coat', color: 'tan' });
  });

  it('asks again only when more has been said, never twice for the same description', () => {
    const tan = { category: 'coat', color: 'tan' };
    const checked = JSON.stringify(pieceToSend(tan));
    expect(nextCheck(tan, { ...quiet, checked })).toBeNull();
    expect(nextCheck({ ...tan, formality: 'business', name: '  ' }, { ...quiet, checked })).toEqual({ ...tan, formality: 'business' });
  });

  it('waits while a check is on its way, while a sheet of choices is open, and offline', () => {
    const tan = { category: 'coat', color: 'tan' };
    expect(nextCheck(tan, { ...quiet, busy: true })).toBeNull();
    expect(nextCheck(tan, { ...quiet, choosing: true })).toBeNull();
    expect(nextCheck(tan, { ...quiet, locked: true })).toBeNull();
  });

  it('says the piece in a few words, and what the answer took as usual until it is told', () => {
    expect(pieceLine({ category: 'coat', color: 'tan' })).toBe('Tan coat');
    expect(pieceLine({ category: 'dress_shoes', color: 'brown', name: ' Brogues ' })).toBe('Brogues, brown dress shoes');
    const levels = ['casual', 'smart_casual', 'business', 'formal'];
    const piece = { category: 'coat', color: 'tan', formality: 'smart_casual', season: 'all', pattern: 'solid' };
    // one natural sentence (23 November: "checked as business, for any time of year and plain" read oddly)
    expect(untoldWords({ category: 'coat', color: 'tan' }, piece, levels))
      .toBe('Until you say more, it is checked as a plain smart casual piece for any time of year.');
    expect(untoldWords({ category: 'coat', color: 'tan', season: 'all' }, piece, levels))
      .toBe('Until you say more, it is checked as a plain smart casual piece.');
    expect(untoldWords({ category: 'coat', color: 'tan', formality: 'smart_casual', pattern: 'solid' }, { ...piece, season: 'warm' }, levels))
      .toBe('Until you say more, it is checked as a piece for warm weather.');
    expect(untoldWords({ category: 'coat', color: 'tan', season: 'all', pattern: 'solid' }, { ...piece, formality: 'athletic' }, [...levels, 'athletic']))
      .toBe('Until you say more, it is checked as an athletic piece.');
    expect(untoldWords({ category: 'coat', color: 'tan', formality: 'smart_casual', season: 'cool', pattern: 'plaid' },
      { ...piece, season: 'cool', pattern: 'plaid' }, levels)).toBeNull();
    expect(untoldWords({ category: 'coat', color: 'tan' }, null, levels)).toBeNull();
  });
});

describe('kept on this device for the day (the review of 23 November, P12)', () => {
  const store = () => {
    const m = new Map<string, string>();
    return {
      getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k),
      get length() { return m.size; }, key: (i: number) => [...m.keys()][i] ?? null,
    };
  };
  const kept: KeptCheck = {
    day: '2026-11-23', wish_id: null, draft: { category: 'coat', color: 'tan', formality: 'business' },
    checked: '{"category":"coat","color":"tan","formality":"business"}', shown: check({ id: 'c9' }),
  };

  it('gives back what was typed and the answer after a reload, the same day, for the same closet and wish', () => {
    const kv = store();
    keptCheck('main', kv).set(kept);
    expect(keptCheck('main', kv).get('2026-11-23', null)).toEqual(kept);
    expect(keptCheck('demo', kv).get('2026-11-23', null)).toBeNull();
    expect(keptCheck('main', kv).get('2026-11-23', 'w1')).toBeNull();
    expect(keptCheck('main', kv).get('2026-11-24', null)).toBeNull();
  });

  it('forgets it when a new one is started, and with the other saved copies', () => {
    const kv = store();
    keptCheck('main', kv).set(kept);
    keptCheck('main', kv).set(null);
    expect(keptCheck('main', kv).get('2026-11-23', null)).toBeNull();
    keptCheck('main', kv).set(kept);
    forgetSaved(kv);
    expect(keptCheck('main', kv).get('2026-11-23', null)).toBeNull();
  });

  it('gives back nothing from a copy it cannot read', () => {
    const kv = store();
    kv.setItem('closet-today-saved:would:main', '{"day":"2026-11-23"');
    expect(keptCheck('main', kv).get('2026-11-23', null)).toBeNull();
    expect(keptCheck('main', null).get('2026-11-23', null)).toBeNull();
  });
});

describe('waiting and the answer', () => {
  it('says what is happening', () => {
    expect(waitingWords({ state: 'describing', way: 'photo' })).toMatch(/Claude is looking at the photo/);
    expect(waitingWords({ state: 'checking', way: 'by_hand' })).toMatch(/Trying it with your clothes/);
    expect(isDone('checking')).toBe(false);
    expect(isDone('failed')).toBe(true);
  });

  it('gives each verdict a tone', () => {
    expect(verdictTone('fills_gap')).toBe('good');
    expect(verdictTone('adds')).toBe('good');
    expect(verdictTone('have_it')).toBe('caution');
    expect(verdictTone('hard_to_wear')).toBe('caution');
    expect(verdictTone('too_small')).toBe('plain');
  });

  it('puts the description and the verdict in the wish', () => {
    const answer = { verdict: 'fills_gap', verdict_words: 'Fills a gap' } as Check['answer'];
    expect(wishFrom(check({ answer }))).toEqual({ name: 'Tan coat', note: 'Tan coat, smart casual, all year. Would this work? said: fills a gap.' });
    expect(wishFrom(check({ piece: { category: 'coat', color: 'tan', name: 'Trench' }, piece_words: 'Trench, tan coat' })).name).toBe('Trench');
    const small = { verdict: 'too_small', verdict_words: 'Not enough in the closet to say' } as Check['answer'];
    expect(wishFrom(check({ answer: small })).note).toBe('Tan coat, smart casual, all year.');
  });

  it('counts wears in words and finds the wish', () => {
    expect([0, 1, 4].map(wornWords)).toEqual(['Not worn yet', 'Worn once', 'Worn 4 times']);
    const wish = { id: 'w1' } as Wish;
    expect(wishById([wish], 'w1')).toBe(wish);
    expect(wishById([wish], 'w2')).toBeNull();
    expect(wishById(null, 'w1')).toBeNull();
  });
});

describe("the answer in a wish's note", () => {
  it('keeps the note as it was, adds the answer once, and stays within the limit', () => {
    expect(noteFor({ note: '' }, 'Tan coat. Would this work? said: fills a gap.')).toBe('Tan coat. Would this work? said: fills a gap.');
    const once = noteFor({ note: 'Size 40' }, 'Tan coat.');
    expect(once).toBe('Size 40\n\nTan coat.');
    expect(noteFor({ note: once }, 'Tan coat.')).toBe(once);
    expect(noteFor({ note: 'x'.repeat(990) }, 'Tan coat, smart casual.').length).toBe(1000);
  });
});

describe('how much of a gap it fills', () => {
  it('only says "no longer missing" when the gap goes', () => {
    expect(fillWords({ gone: true, filled: true })).toBe('no longer missing');
    expect(fillWords({ gone: false, filled: true })).toBe('mostly filled');
    expect(fillWords({ gone: false, filled: false })).toBe('a little less of a gap');
  });
});

describe('who a gap it fills is for', () => {
  it('names the situations, and says when the gap is low on the list', () => {
    expect(fillNote({ situations: [], low: false })).toBeNull();
    expect(fillNote({})).toBeNull();
    expect(fillNote({ situations: ['Work'], low: false })).toBe('for work');
    expect(fillNote({ situations: ['Work', 'Everyday', 'Going out'], low: false })).toBe('for work, everyday and going out');
    expect(fillNote({ situations: ['Exercise'], low: true })).toBe('for exercise, low on your list');
    expect(fillNote({ situations: [], low: true })).toBe('low on your list');
  });
});

describe('asking how a check is getting on', () => {
  it('asks again until the check is answered or has failed', () => {
    expect(checkPoll({ state: 'describing' }, null)).toBe(POLL_MS);
    expect(checkPoll({ state: 'checking' }, null)).toBe(POLL_MS);
    expect(checkPoll({ state: 'ready' }, null)).toBe(false);
    expect(checkPoll({ state: 'failed' }, null)).toBe(false);
    expect(checkPoll(undefined, null)).toBe(false);
  });
  it('asks more slowly while Nines cannot be reached, and stops once the check is forgotten', () => {
    expect(checkPoll({ state: 'checking' }, { status: 0 })).toBe(POLL_MS * 2);
    expect(checkPoll({ state: 'checking' }, { status: 404 })).toBe(false);
  });
});

describe('a piece drawn with your clothes', () => {
  it('says once, in one sentence, where the drawing comes from and that it is rough', () => {
    expect(drawnFromWords('shop')).toBe("This piece is drawn from the shop's description, so it shows roughly its shape and colour, not how it really looks.");
    expect(drawnFromWords('photo')).toContain("Claude's description of your photo");
    expect(drawnFromWords('by_hand')).toContain('your description');
  });
  it('says the pattern is rough too when the piece is drawn striped or plaid', () => {
    expect(drawnFromWords('shop', 'stripe')).toBe("This piece is drawn from the shop's description, so it shows roughly its shape, colour and pattern, not how it really looks.");
    expect(drawnFromWords('by_hand', 'plaid')).toContain('roughly its shape, colour and pattern');
    expect(drawnFromWords('shop', 'floral')).toContain('roughly its shape and colour,');
    expect(drawnFromWords('shop', 'solid')).toContain('roughly its shape and colour,');
  });
  it('counts the outfits from one', () => {
    expect(outfitStep(0, 3)).toBe('Outfit 1 of 3');
  });
  it('says Nines is out of reach when it is, and the server\'s own sentence otherwise', () => {
    expect(wornError({ status: 0, message: 'x' })).toBe('Showing it with your clothes needs Nines running on the computer.');
    expect(wornError({ status: 409, message: 'Not yet.' })).toBe('Not yet.');
  });
});
