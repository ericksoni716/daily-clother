import { label } from './labels';
import type { Profile } from './types';

export interface LookFor {
  category: string;
  formality: string | null;
  season: string | null;
  weight_class: string | null;
  colors: string[];
  pattern: string | null;
  material: string | null;
}

export const HIDE_REASONS = {
  already_owned: 'I have one that is not in the closet yet',
  not_my_style: 'I never dress like that',
  too_expensive: 'Too expensive',
  other: 'Other',
} as const;
export type HideReason = keyof typeof HIDE_REASONS;

export interface Gap {
  id: string;
  name: string;
  look_for: LookFor;
  why: string[];
  score: number;
  found_by: string[];
  evidence: { items: string[]; days: { words: string }[] };
  hidden: boolean;
  hidden_reason: HideReason | null;
  wished: boolean;
}

export interface GapsAnswer {
  enough: boolean;
  message: string | null;
  gaps: Gap[];
  notes: { kind: string; text: string; items: string[] }[];
  checked: { items: number; wears: number; days: number };
}

export interface Wish {
  id: string;
  gap_id: string | null;
  name: string;
  look_for: LookFor | null;
  details: string;
  note: string;
  created_at: string;
}

export interface SavedShopping {
  saved_at: string;
  answer: GapsAnswer;
  hidden: Gap[];
  wishes: Wish[];
}

const WEIGHTS: Record<string, string> = {
  lightweight: 'Light fabric', midweight: 'Medium-weight fabric', heavyweight: 'Heavy fabric', super_heavy: 'Very heavy fabric',
};

export function lookForWords(look: LookFor | null): string[] {
  if (!look) return [];
  const category = label('category', look.category);
  const garment = look.pattern === 'solid' ? `Plain ${category === 'T-shirt' ? category : category.toLowerCase()}` : category;
  const colors = look.colors.map((c) => label('color', c).toLowerCase());
  const colorWords = colors.length < 2 ? colors.join('') : `${colors.slice(0, -1).join(', ')} or ${colors.at(-1)}`;
  return [
    garment,
    look.formality ? `For ${look.formality === 'athletic' ? 'sport' : label('formality', look.formality).toLowerCase()} days` : '',
    look.season ? (look.season === 'all' ? 'All year' : `For ${label('season', look.season).toLowerCase()}`) : '',
    look.weight_class ? (WEIGHTS[look.weight_class] ?? label('weight', look.weight_class)) : '',
    look.pattern && look.pattern !== 'solid' ? label('pattern', look.pattern) : '',
    look.material ? label('material', look.material) : '',
    colorWords ? colorWords.charAt(0).toUpperCase() + colorWords.slice(1) : '',
  ].filter(Boolean);
}

export function helpLevel(score: number): { bars: number; words: string } {
  return {
    bars: Math.max(1, Math.min(5, Math.ceil(score / 20))),
    words: score >= 70 ? 'Big difference' : score >= 40 ? 'Useful addition' : 'A little more choice',
  };
}

type KV = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const key = (profile: Profile) => `closet-shopping:${profile}`;
function local(): KV | null {
  try { return window.localStorage; } catch { return null; }
}

export function readShopping(profile: Profile, kv: KV | null = local()): SavedShopping | null {
  try {
    const raw = kv?.getItem(key(profile));
    const saved = raw ? JSON.parse(raw) as SavedShopping : null;
    return saved && typeof saved.saved_at === 'string' && Array.isArray(saved.answer?.gaps)
      && Array.isArray(saved.answer?.notes) && Array.isArray(saved.hidden) && Array.isArray(saved.wishes) ? saved : null;
  } catch { return null; }
}

export function saveShopping(profile: Profile, saved: SavedShopping, kv: KV | null = local()) {
  try { kv?.setItem(key(profile), JSON.stringify(saved)); } catch { /* full or private storage: keep working */ }
}

export function forgetShopping(kv: KV | null = local()) {
  try {
    kv?.removeItem(key('main'));
    kv?.removeItem(key('demo'));
  } catch { /* storage unavailable */ }
}
