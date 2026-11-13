/** Would this work?: the shapes the server sends for a check, and plain words for them. */
import type { LookFor, Wish } from './gaps';
import { label } from './labels';
import type { OutfitPieces } from './today';

/** The piece being checked, as typed by hand or as Claude described it from a photo. */
export interface WouldPiece {
  category: string;
  color: string;
  formality?: string | null;
  season?: string | null;
  pattern?: string | null;
  weight_class?: string | null;
  rain_proof?: boolean;
  name?: string | null;
  material?: string | null;
  silhouette?: Record<string, string>;
}

export type Verdict = 'fills_gap' | 'adds' | 'have_it' | 'hard_to_wear' | 'too_small';

export interface WouldDay {
  temperature: string;
  low_c: number;
  high_c: number;
  rain: boolean;
  occasion: string;
  words: string;
}

export interface WouldAnswer {
  enough: boolean;
  message: string | null;
  verdict: Verdict;
  verdict_words: string;
  reasons: string[];
  piece: WouldPiece;
  fills: { gap_id: string; name: string; score_before: number; score_after: number; gone: boolean; days: WouldDay[]; found_by: string[] }[];
  goes_with: {
    days: number;
    suits: number;
    of: number;
    items: string[];
    examples: { day: WouldDay; pieces: OutfitPieces; score: number; reasons: string[] }[];
    text: string | null;
  };
  repeats: { items: { id: string; worn: number; hardly_worn: boolean }[]; text: string | null };
  holds_back: string[];
  checked: { items: number; wears: number; days: number };
}

export type CheckState = 'describing' | 'checking' | 'ready' | 'failed';

export interface Check {
  id: string;
  state: CheckState;
  way: 'by_hand' | 'photo';
  piece: WouldPiece | null;
  piece_words: string | null;
  answer: WouldAnswer | null;
  message: string | null;
  /** The check failed in a way describing it by hand gets round (no route to Claude, the monthly limit). */
  by_hand: boolean;
  started_at: string;
  finished_at: string | null;
}

/** The id the piece itself has in an example outfit. */
export const CANDIDATE_ID = '~candidate';

/** How often to ask how a check is getting on. */
export const POLL_MS = 1500;

export const WEIGHTS = ['lightweight', 'midweight', 'heavyweight', 'super_heavy'] as const;
const WEIGHT_WORDS: Record<string, string> = {
  lightweight: 'Light', midweight: 'Medium', heavyweight: 'Heavy', super_heavy: 'Very heavy',
};

export function weightLabel(value: string): string {
  return WEIGHT_WORDS[value] ?? label('weight', value);
}

/** The kinds a check can try in an outfit ("other" cannot be). */
export function checkKinds(categories: string[]): string[] {
  return categories.filter((c) => c !== 'other');
}

export function isDone(state: CheckState): boolean {
  return state === 'ready' || state === 'failed';
}

/** What is happening while the owner waits. */
export function waitingWords(check: Pick<Check, 'state' | 'way'>): string {
  if (check.state === 'describing') return 'Claude is looking at the photo. This can take up to a minute…';
  return 'Trying it with your clothes on 40 kinds of day…';
}

/** The tone of the verdict: good news, a caution, or neither. */
export function verdictTone(v: Verdict): 'good' | 'caution' | 'plain' {
  if (v === 'fills_gap' || v === 'adds') return 'good';
  if (v === 'have_it' || v === 'hard_to_wear') return 'caution';
  return 'plain';
}

const RAIN_WORDS = /\b(waterproof|rain|mac|trench|waxed|shell|parka)\b/i;

/** A wish's "look for" as a starting description, so "I found one" opens with it filled in. */
export function pieceFromLook(look: LookFor | null | undefined): Partial<WouldPiece> {
  if (!look) return {};
  const out: Partial<WouldPiece> = { category: look.category };
  if (look.formality) out.formality = look.formality;
  if (look.season) out.season = look.season;
  if (look.weight_class) out.weight_class = look.weight_class;
  if (look.pattern) out.pattern = look.pattern;
  if (look.colors.length === 1) out.color = look.colors[0];
  if (look.material && RAIN_WORDS.test(look.material)) out.rain_proof = true;
  return out;
}

/** The description to send: only what was chosen, with the name trimmed. */
export function pieceToSend(p: Partial<WouldPiece>): Partial<WouldPiece> {
  const out: Partial<WouldPiece> = {};
  for (const key of ['category', 'color', 'formality', 'season', 'pattern', 'weight_class'] as const) {
    if (p[key]) out[key] = p[key] as string;
  }
  if (p.rain_proof) out.rain_proof = true;
  const name = p.name?.trim();
  if (name) out.name = name;
  return out;
}

/** What is still to choose before a description can be checked, in words; null when it can be. */
export function stillToChoose(p: Partial<WouldPiece>): string | null {
  if (!p.category && !p.color) return 'Choose what kind of piece it is and its colour.';
  if (!p.category) return 'Choose what kind of piece it is.';
  if (!p.color) return 'Choose its main colour.';
  return null;
}

/** The wish "Put it on my wishlist" adds: the piece's name, and its description and the verdict in the note. */
export function wishFrom(check: Pick<Check, 'piece' | 'piece_words' | 'answer'>): { name: string; note: string } {
  // the server's description starts with the piece's name ("Navy coat, smart casual, all year")
  const name = (check.piece?.name || check.piece_words?.split(', ')[0] || 'A piece I found').slice(0, 120);
  const verdict = check.answer && check.answer.verdict !== 'too_small' ? ` Would this work? said: ${check.answer.verdict_words.toLowerCase()}.` : '';
  const note = `${check.piece_words ?? name}.${verdict}`.slice(0, 1000);
  return { name, note };
}

/** "Worn 3 times", "Not worn yet". */
export function wornWords(n: number): string {
  if (n === 0) return 'Not worn yet';
  return n === 1 ? 'Worn once' : `Worn ${n} times`;
}

/** The check started from a wish: the wish, if it is still on the list. */
export function wishById(wishes: Wish[] | null, id: string | null): Wish | null {
  if (!id || !wishes) return null;
  return wishes.find((w) => w.id === id) ?? null;
}
