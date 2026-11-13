import { describe, expect, it } from 'vitest';
import type { LookFor, Wish } from './gaps';
import {
  type Check, checkKinds, isDone, pieceFromLook, pieceToSend, stillToChoose, verdictTone, waitingWords, WEIGHTS, weightLabel, wishById,
  wishFrom, wornWords,
} from './wouldwork';

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
