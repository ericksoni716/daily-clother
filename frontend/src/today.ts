import { label } from './labels';
import type { ItemSummary, Profile, WeatherLookup } from './types';
import { localDay } from './wears';

export interface Outfit {
  pieces: { outer: string | null; mid: string | null; base: string; bottom: string; shoes: string; accessories: string[] };
  score: number;
  reasons: string[];
  warnings: string[];
}

export interface TodayChoices {
  occasion: string;
  mood: 'usual' | 'sharp' | 'relaxed';
  build_around?: string;
  leave_out: string[];
  low_c?: number;
  high_c?: number;
  rain?: boolean;
}

export interface TodayResult {
  outfits: Outfit[];
  missing: string[];
  context: {
    date: string; low_c: number; high_c: number; rain: boolean;
    source: string; old: boolean; place: string | null;
    rain_chance: number | null; summary: string | null;
  };
}

export interface WearReceipt {
  worn_on: string;
  created_ids: string[];
  item_ids: string[];
}

export interface SavedToday {
  day: string;
  choices: TodayChoices;
  result: TodayResult;
  weather: WeatherLookup | null;
  items: ItemSummary[];
  selected: number;
}

export function outfitPieces(outfit: Outfit): { id: string; place: string }[] {
  const { outer, mid, base, bottom, shoes, accessories } = outfit.pieces;
  return [
    { id: outer, place: 'Outer layer' }, { id: mid, place: 'Mid layer' },
    { id: base, place: 'Base top' }, { id: bottom, place: 'Bottom' },
    { id: shoes, place: 'Shoes' }, ...accessories.map((id) => ({ id, place: 'Accessory' })),
  ].filter((piece): piece is { id: string; place: string } => !!piece.id);
}

export function pieceName(item: ItemSummary | undefined): string {
  return item?.name || label('category', item?.category) || 'Item';
}

export function canDress(items: ItemSummary[]): boolean {
  return missingBasics(items).length === 0;
}

export function missingBasics(items: ItemSummary[]): string[] {
  const categories = new Set(items.filter((i) => i.status === 'active' && i.laundry === 'clean' && i.rating !== 'dislike').map((i) => i.category));
  const missing = [];
  if (!['tee', 'shirt', 'polo'].some((c) => categories.has(c))) missing.push('Start with a clean shirt, T-shirt or polo.');
  if (!['trousers', 'jeans', 'shorts'].some((c) => categories.has(c))) missing.push('Add a clean pair of trousers, jeans or shorts.');
  if (!['boots', 'sneakers', 'dress_shoes', 'sandals'].some((c) => categories.has(c))) missing.push('Add a clean pair of shoes.');
  return missing;
}

export function dayWeather(context: Pick<TodayResult['context'], 'low_c' | 'high_c' | 'rain'>): string {
  return `Low ${Math.round(context.low_c)}°C · High ${Math.round(context.high_c)}°C · ${context.rain ? 'Rain expected' : 'No rain expected'}`;
}

export function swipeDirection(x: number, y: number): number {
  return Math.abs(x) > 50 && Math.abs(x) > Math.abs(y) * 1.5 ? (x < 0 ? 1 : -1) : 0;
}

const PREFIX = 'closet-today-';
let dataVersion = 0;

export function todayDataVersion(): number {
  return dataVersion;
}

export function readTodayValue<T>(key: string): T | null {
  try { return JSON.parse(localStorage.getItem(PREFIX + key) || 'null') as T | null; }
  catch { return null; }
}

export function writeTodayValue(key: string, value: unknown): void {
  try {
    if (value === null) localStorage.removeItem(PREFIX + key);
    else localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch { /* The screen still works when browser storage is full or unavailable. */ }
}

export function savedToday(profile: Profile, day = localDay()): SavedToday | null {
  const saved = readTodayValue<SavedToday>(profile);
  return saved?.day === day && Array.isArray(saved.result?.outfits) && Array.isArray(saved.items) ? saved : null;
}

export function lastChoices(): TodayChoices {
  const saved = readTodayValue<{ occasion: string; mood: string }>('choices');
  const occasion = ['athletic', 'casual', 'smart_casual', 'business', 'formal'].includes(saved?.occasion ?? '') ? saved!.occasion : 'casual';
  const mood = saved?.mood === 'sharp' || saved?.mood === 'relaxed' ? saved.mood : 'usual';
  return { occasion, mood, leave_out: [] };
}

export function clearTodayData(): void {
  dataVersion++;
  for (const profile of ['main', 'demo']) {
    writeTodayValue(profile, null);
    writeTodayValue(`${profile}-wear`, null);
  }
}
