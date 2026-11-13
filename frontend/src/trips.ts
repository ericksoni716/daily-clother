import type { Outfit } from './today';
import type { Place, Profile } from './types';

export interface TripChoices {
  place: Place;
  first_day: string;
  last_day: string;
  occasion: string;
  overrides: { date: string; occasion: string }[];
  can_wash: boolean;
  leave_out: string[];
  pins: string[];
}

export interface TripWeather {
  date: string;
  source: 'forecast' | 'usual';
  low_c: number | null;
  high_c: number | null;
  rain: boolean | null;
  message: string | null;
}

export interface PackingPiece { id: string; name: string; days_worn: number; pinned: boolean }
export interface TripPlan {
  packing: Record<string, PackingPiece[]>;
  basics: { id: string; name: string; count: number }[];
  days: { date: string; occasion: string; weather: TripWeather; outfit: Outfit | null; missing: string[] }[];
  uncovered: { date: string; reasons: string[] }[];
  piece_count: number;
  notes: string[];
}
export interface TripPreview { choices: TripChoices; plan: TripPlan }
export interface Trip extends TripPreview {
  id: string;
  checked: Record<string, boolean>;
  revision: number;
  created_at: string;
  weather_changed?: boolean;
  latest_weather?: TripWeather[];
}
export type TripPatch = Partial<TripChoices> & { checked?: Record<string, boolean>; replan?: boolean; revision?: number };

const PREFIX = 'closet-trips:';

/** Successful server answers only; kept per closet and cleared on logout. */
export function readTrips(profile: Profile): Trip[] {
  try { return JSON.parse(localStorage.getItem(PREFIX + profile) || '[]') as Trip[]; }
  catch { return []; }
}
export function keepTrips(profile: Profile, trips: Trip[]) {
  try { localStorage.setItem(PREFIX + profile, JSON.stringify(trips)); }
  catch { /* full or private storage: the server still has the trip */ }
}
export function forgetTrips() {
  try { for (const p of ['main', 'demo']) localStorage.removeItem(PREFIX + p); }
  catch { /* no saved copy */ }
}
export function packingProgress(trip: TripPreview & { checked?: Record<string, boolean> }) {
  const keys = [...Object.values(trip.plan.packing).flat().map((p) => `item:${p.id}`),
    ...trip.plan.basics.map((b) => `basic:${b.id}`)];
  return { total: keys.length, packed: keys.filter((k) => trip.checked?.[k]).length };
}
