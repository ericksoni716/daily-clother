/** What's missing: the shapes the server sends, plain words for them, and the copy kept on this device. */
import { label } from './labels';
import { SAVED_PREFIX } from './today';

export interface LookFor {
  category: string;
  formality: string | null;
  season: string | null;
  weight_class: string | null;
  colors: string[];
  pattern: string | null;
  material: string | null;
}

export type GapState = 'open' | 'hidden' | 'wished';

export interface Gap {
  id: string;
  name: string;
  look_for: LookFor;
  why: string[];
  score: number;
  found_by: string[];
  evidence: { days: unknown[]; items: string[] };
  state: GapState;
  hidden_reason: HideReason | null;
  wish_id: string | null;
}

export interface GapNote {
  kind: string;
  text: string;
  items: string[];
}

export interface GapsAnswer {
  enough: boolean;
  message: string | null;
  gaps: Gap[];
  notes: GapNote[];
  checked: { items: number; wears: number; days: number };
}

export interface Wish {
  id: string;
  gap_id: string | null;
  name: string;
  look_for: LookFor | null;
  note: string;
  bought_at: string | null;
  created_at: string;
  updated_at: string;
}

// --------------------------------------------------------------------- "Not for me"

export const HIDE_REASONS = [
  { value: 'have_one', label: "I have one that isn't in the closet yet" },
  { value: 'never_wear', label: 'I never dress like that' },
  { value: 'too_expensive', label: 'Too expensive' },
  { value: 'other', label: 'Something else' },
] as const;

export type HideReason = (typeof HIDE_REASONS)[number]['value'];

export function reasonLabel(reason: string | null | undefined): string {
  return HIDE_REASONS.find((r) => r.value === reason)?.label ?? '';
}

// --------------------------------------------------------------------- how much it would help

export interface Help {
  /** 1 (a little) to 4 (a lot): the number of bars filled. */
  level: 1 | 2 | 3 | 4;
  words: string;
}

export const HELP_LEVELS = 4;
const HELP_WORDS = ['Would help a little', 'Would help some', 'Would help a fair bit', 'Would help a lot'] as const;
// Where each level starts, on the server's 0 to 100: one basic the closet lacks is about 30-45, a gap
// found on many days or by several ways is 60 and up.
const HELP_FROM = [0, 25, 45, 60] as const;

/** How much a gap would help, as a level to draw and a few words: never a number to read. */
export function helpOf(score: number): Help {
  const s = Number.isFinite(score) ? score : 0;
  let level = 1;
  for (let i = HELP_FROM.length - 1; i >= 0; i--) {
    if (s >= HELP_FROM[i]) {
      level = i + 1;
      break;
    }
  }
  return { level: level as Help['level'], words: HELP_WORDS[level - 1] };
}

// --------------------------------------------------------------------- what to look for

const PLURAL_CATEGORIES = ['jeans', 'trousers', 'shorts', 'sneakers', 'boots', 'dress_shoes', 'sandals'];
const THING: Record<string, string> = { tee: 'T-shirt', other: 'piece' };
// The occasion's own words, as the Today screen names them.
const FORMALITY_WORDS: Record<string, string> = {
  athletic: 'sport', casual: 'casual', smart_casual: 'smart casual', business: 'business', formal: 'formal',
};
const SEASON_WORDS: Record<string, string> = {
  warm: 'For warm weather', cool: 'For cool and cold weather', all: 'For any time of year',
};
const WEIGHT_WORDS: Record<string, string> = {
  lightweight: 'Light, thin cloth', midweight: 'Medium-weight cloth', heavyweight: 'Heavy, warm cloth', super_heavy: 'Very heavy, warm cloth',
};

function article(phrase: string): string {
  return /^[aeiou]/i.test(phrase) ? 'An' : 'A';
}

/** "a, b or c" */
export function orWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} or ${words[words.length - 1]}`;
}

/** The kind of piece in a few words: "A smart casual coat", "Business dress shoes". */
export function whatWords(look: Pick<LookFor, 'category' | 'formality'>): string {
  const thing = THING[look.category] ?? (label('category', look.category).toLowerCase() || 'piece');
  const style = look.formality ? FORMALITY_WORDS[look.formality] ?? label('formality', look.formality).toLowerCase() : '';
  const phrase = style ? `${style} ${thing}` : thing;
  if (PLURAL_CATEGORIES.includes(look.category)) return phrase.charAt(0).toUpperCase() + phrase.slice(1);
  return `${article(phrase)} ${phrase}`;
}

/** The colours to look for, in words: "Navy, grey or tan". Empty when none are given. */
export function colorWords(colors: string[] | null | undefined): string {
  const words = (colors ?? []).map((c) => label('color', c).toLowerCase()).filter(Boolean);
  const text = orWords(words);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * What to look for in plain words, one short line each: the kind of piece, then season, weight, pattern and
 * material where they matter. Colours are given separately (`colorWords`), since they are shown as swatches.
 */
export function lookForLines(look: LookFor | null | undefined): string[] {
  if (!look || !look.category) return [];
  const lines = [whatWords(look)];
  if (look.season && SEASON_WORDS[look.season]) lines.push(SEASON_WORDS[look.season]);
  if (look.weight_class && WEIGHT_WORDS[look.weight_class]) lines.push(WEIGHT_WORDS[look.weight_class]);
  if (look.pattern === 'solid') lines.push('Plain, no pattern');
  else if (look.pattern) lines.push(`${label('pattern', look.pattern)} pattern`);
  if (look.material) lines.push(look.material.charAt(0).toUpperCase() + look.material.slice(1));
  return lines;
}

// --------------------------------------------------------------------- the quieter findings

export interface OtherFinding {
  kind: string;
  title: string;
  text: string;
  items: string[];
}

const NOTE_TITLES: Record<string, string> = { never_worn: 'Not worn yet' };

/**
 * What the analysis says besides the gaps: its notes (pieces never worn), and the pieces worn far more than the
 * rest, taken from the gaps the wear log found (the gap itself stays in the list above).
 */
export function otherFindings(answer: Pick<GapsAnswer, 'gaps' | 'notes'> | null | undefined): OtherFinding[] {
  if (!answer) return [];
  const out: OtherFinding[] = (answer.notes ?? []).map((n) => ({
    kind: n.kind, title: NOTE_TITLES[n.kind] ?? 'Also worth knowing', text: n.text, items: n.items ?? [],
  }));
  for (const g of answer.gaps ?? []) {
    if (!g.found_by.includes('worn_most')) continue;
    const text = g.why.find((w) => w.startsWith('You wore'));
    if (!text) continue;
    const alone = g.found_by.length === 1;
    out.push({ kind: 'worn_most', title: 'Worn far more than the rest', text, items: alone ? g.evidence.items.slice(0, 1) : [] });
  }
  return out;
}

// --------------------------------------------------------------------- kept on this device

/** The last answer fetched, kept per closet so the screen can show it offline. Removed on logout with the rest. */
export interface SavedGaps {
  saved_at: string;
  gaps: GapsAnswer | null;
  wishes: Wish[] | null;
}

type KV = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const savedKey = (profile: string) => `${SAVED_PREFIX}:gaps:${profile}`;

export function loadSavedGaps(profile: string, kv: KV | null = local()): SavedGaps | null {
  try {
    const raw = kv?.getItem(savedKey(profile));
    const value = raw ? (JSON.parse(raw) as SavedGaps) : null;
    return value && typeof value.saved_at === 'string' ? value : null;
  } catch {
    return null;
  }
}

/** Keeps the parts given, leaving the others as they were. */
export function saveGaps(profile: string, part: Partial<Omit<SavedGaps, 'saved_at'>>, kv: KV | null = local(), now = new Date()) {
  const before = loadSavedGaps(profile, kv);
  const value: SavedGaps = { saved_at: now.toISOString(), gaps: before?.gaps ?? null, wishes: before?.wishes ?? null, ...part };
  try {
    kv?.setItem(savedKey(profile), JSON.stringify(value));
  } catch {
    /* private mode or full: not kept, nothing else breaks */
  }
}
