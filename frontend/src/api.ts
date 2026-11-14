import type { Item, ItemPatch, ItemSummary, Laundry, ModelInfo, Session, Settings, Storage, TaggingSpend, TaggingStatus, Vocab, Profile, BackupRecord, Place, WeatherLookup, ReviewField, ReviewQueue, RouteOrder } from './types';
import { forgetSaved, type TodayAnswer, type TodayRequest, type WearManyAnswer } from './today';
import type { CorrectionAnswer, DetailChoices, DetailOptions, HistoryEntry } from './corrections';
import type { PlannedTrip, Trip, TripPatch, TripRequest, TripSummary, WeatherCheck } from './trips';
import type { Insights } from './insights';
import type { OutfitSent, Rating, Reason, WornOutfit, WornPage } from './worn';
import type { GapsAnswer, HideReason, Wish } from './gaps';
import type { Life } from './life';
import type { Check, WouldPiece } from './wouldwork';
import type { FigurePieces } from './figure';

/** An error with a sentence the owner can read. status 0 means the server could not be reached. */
export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter?: number) {
    super(message);
  }
}

export const UNREACHABLE = "Can't reach Closet. Check that it is running on your computer.";

/** Header the service worker adds when it answers from its saved copy. */
export const FROM_CACHE_HEADER = 'x-closet-from-cache';

type Listener = (offline: boolean) => void;
const offlineListeners = new Set<Listener>();
const unauthorizedListeners = new Set<() => void>();
let offline = false;

function setOffline(value: boolean) {
  if (value === offline) return;
  offline = value;
  offlineListeners.forEach((l) => l(value));
}

export const connection = {
  get offline() {
    return offline;
  },
  subscribe(l: Listener): () => void {
    offlineListeners.add(l);
    return () => void offlineListeners.delete(l);
  },
  onUnauthorized(l: () => void): () => void {
    unauthorizedListeners.add(l);
    return () => void unauthorizedListeners.delete(l);
  },
  /** Exposed for tests and for code that learns about the network another way. */
  set: setOffline,
};

/** Pulls a readable sentence out of an error body. FastAPI validation errors carry a list. */
export function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === 'string') return detail[0].msg;
  }
  return fallback;
}

function fallbackMessage(status: number): string {
  if (status === 401) return 'Log in to continue.';
  if (status === 404) return 'That could not be found.';
  if (status === 413) return 'That file is too large.';
  if (status >= 500) return 'Something went wrong on the computer running Closet. Try again in a moment.';
  return 'That did not work. Try again.';
}

export interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
  /** Do not treat a 401 as "logged out" (used by login itself). */
  quiet401?: boolean;
  signal?: AbortSignal;
  /** The answer is text (an SVG drawing), not JSON. */
  text?: boolean;
}

/**
 * Browsers allow 64 KiB of bodies for all `keepalive` requests still on their way together, and
 * refuse one that would go over. Closet keeps its own count and stays under it, with room to spare.
 */
export const KEEPALIVE_BUDGET = 48 * 1024;
let keepaliveBytes = 0;

/**
 * Saves are sent with `keepalive` so that they reach Closet even if the page is closed or reloaded
 * a moment later. Not for photos (too large), not for questions the app can call off (they have a
 * signal), and not when earlier saves still on their way use up the browser's allowance.
 * Returns the body's size when it is sent that way, null otherwise.
 */
export function keepaliveSize(method: string, body: string | undefined, opts: Options, inFlight: number): number | null {
  if (method === 'GET' || opts.form || opts.signal) return null;
  const size = new TextEncoder().encode(body ?? '').length;
  return inFlight + size <= KEEPALIVE_BUDGET ? size : null;
}

async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? 'GET';
  const init: RequestInit = { method, credentials: 'same-origin', signal: opts.signal };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { 'Content-Type': 'application/json' };
  }
  const kept = keepaliveSize(method, init.body as string | undefined, opts, keepaliveBytes);
  if (kept !== null) {
    init.keepalive = true;
    keepaliveBytes += kept;
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    setOffline(true);
    throw new ApiError(0, UNREACHABLE);
  } finally {
    if (kept !== null) keepaliveBytes -= kept;
  }
  setOffline(res.headers.get(FROM_CACHE_HEADER) === '1');
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await res.text();
  if (opts.text && res.ok) return text as T;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    if (res.status === 401 && !opts.quiet401) unauthorizedListeners.forEach((l) => l());
    const retry = Number(res.headers.get('Retry-After')) || undefined;
    const err = new ApiError(res.status, messageFrom(data, fallbackMessage(res.status)), retry);
    (err as ApiError & { body?: unknown }).body = data;
    throw err;
  }
  return data as T;
}

export const api = {
  session: () => request<Session>('/api/session'),
  setup: (passphrase: string) => request<void>('/api/setup', { method: 'POST', body: { passphrase }, quiet401: true }),
  login: (passphrase: string) => request<void>('/api/login', { method: 'POST', body: { passphrase }, quiet401: true }),
  logout: () => request<void>('/api/logout', { method: 'POST', quiet401: true }),
  vocab: () => request<Vocab>('/api/vocab'),
  items: (status: 'active' | 'archived' = 'active') =>
    request<{ items: ItemSummary[] }>(`/api/items?status=${status}`).then((r) => r.items),
  item: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}`),
  patch: (id: string, changes: ItemPatch) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}`, { method: 'PATCH', body: changes }),
  remove: (id: string) => request<void>(`/api/items/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  wear: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/wears`, { method: 'POST' }),
  unwear: (id: string, day: string) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/wears/${encodeURIComponent(day)}`, { method: 'DELETE' }),
  /** Records a wear for several items at once (an outfit), on one day. */
  wearMany: (ids: string[], outfit?: OutfitSent) =>
    request<WearManyAnswer>('/api/wears', { method: 'POST', body: outfit ? { item_ids: ids, outfit } : { item_ids: ids } }),
  /** With `outfitId`, the outfit remembered with the wears is removed too (`ids` may then be empty). */
  unwearMany: (ids: string[], day: string, outfitId?: string) =>
    request<WearManyAnswer>('/api/wears/remove', {
      method: 'POST', body: outfitId ? { item_ids: ids, worn_on: day, outfit_id: outfitId } : { item_ids: ids, worn_on: day },
    }),
  wornOutfits: (before?: string | null, limit = 20) =>
    request<WornPage>(`/api/outfits/worn?limit=${limit}${before ? `&before=${encodeURIComponent(before)}` : ''}`),
  recordOutfit: (ids: string[], day?: string) =>
    request<WornOutfit>('/api/outfits/worn', { method: 'POST', body: day ? { item_ids: ids, worn_on: day } : { item_ids: ids } }),
  rateOutfit: (id: string, rating: Rating | null, reasons: Reason[] = [], note?: string | null) =>
    request<WornOutfit>(`/api/outfits/worn/${encodeURIComponent(id)}/rating`, { method: 'PUT', body: { rating, reasons, note: note || null } }),
  removeOutfit: (id: string) => request<void>(`/api/outfits/worn/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  setLaundry: (id: string, state: Laundry) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/laundry`, { method: 'POST', body: { state } }),
  retag: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/retag`, { method: 'POST' }),
  /** The details that can be fixed for this kind of garment, and the choices for one of them. */
  detailOptions: (id: string) => request<DetailOptions>(`/api/items/${encodeURIComponent(id)}/details`),
  detailChoices: (id: string, name: string) =>
    request<DetailChoices>(`/api/items/${encodeURIComponent(id)}/details/${encodeURIComponent(name)}`),
  /** Sets details; null gives one back to Claude's description. */
  setDetails: (id: string, details: Record<string, unknown>) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/details`, { method: 'PUT', body: { details } }),
  correct: (id: string, sentence: string) =>
    request<CorrectionAnswer>(`/api/items/${encodeURIComponent(id)}/correct`, { method: 'POST', body: { sentence } }),
  confirmCorrection: (id: string, sentence: string, changes: { name: string; value: unknown; before?: unknown }[]) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/correct/confirm`, { method: 'POST', body: { sentence, changes } }),
  history: (id: string) => request<HistoryEntry[]>(`/api/items/${encodeURIComponent(id)}/history`),
  undo: (id: string, changeId: number) =>
    request<{ item: Item; history: HistoryEntry[] }>(`/api/items/${encodeURIComponent(id)}/history/${changeId}/undo`, { method: 'POST' }),
  review: () => request<ReviewQueue>('/api/review'),
  /** Marks fields as the owner's without changing them. */
  confirm: (id: string, fields: ReviewField['field'][]) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/confirm`, { method: 'POST', body: { fields } }),
  retryCutout: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/retry-cutout`, { method: 'POST' }),
  /** `duplicate` is true when the photo was already in the closet; the item returned is the one it is in. */
  upload: (photo: Blob, filename: string, clientKey: string, sha256?: string | null, signal?: AbortSignal) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    form.append('client_key', clientKey);
    if (sha256) form.append('photo_sha256', sha256);
    return request<Item & { duplicate?: boolean }>('/api/items', { method: 'POST', form, signal });
  },
  model: () => request<ModelInfo>('/api/model'),
  downloadModel: () => request<ModelInfo>('/api/model/download', { method: 'POST' }),
  setModelUrl: (url: string) => request<ModelInfo>('/api/model/url', { method: 'PUT', body: { url } }),
  settings: () => request<Settings>('/api/settings'),
  putSettings: (changes: { backup_folder?: string | null; autostart?: boolean; place?: Place | null; tagging_api_enabled?: boolean; tagging_api_cap_usd?: number | null; tagging_route_order?: RouteOrder; life?: Life | null; life_prompt_dismissed?: boolean }) =>
    request<Settings>('/api/settings', { method: 'PUT', body: changes }),
  storage: () => request<Storage>('/api/storage'),
  saveApiKey: (key: string) => request<Settings>('/api/settings/api-key', { method: 'PUT', body: { key } }),
  removeApiKey: () => request<Settings>('/api/settings/api-key', { method: 'DELETE' }),
  tagging: () => request<TaggingStatus>('/api/tagging'),
  tagSpend: () => request<TaggingSpend>('/api/tagging/spend'),
  places: (q: string) => request<{ places: Place[] }>(`/api/places?q=${encodeURIComponent(q)}`).then((r) => r.places),
  weather: () => request<WeatherLookup>('/api/weather'),
  today: (choices: TodayRequest, signal?: AbortSignal) =>
    request<TodayAnswer>('/api/outfits/today', { method: 'POST', body: choices, signal }),
  planTrip: (trip: TripRequest, signal?: AbortSignal) =>
    request<PlannedTrip>('/api/trips/plan', { method: 'POST', body: trip, signal }),
  saveTrip: (trip: TripRequest) => request<Trip>('/api/trips', { method: 'POST', body: trip }),
  trips: () => request<{ trips: TripSummary[] }>('/api/trips').then((r) => r.trips),
  trip: (id: string) => request<Trip>(`/api/trips/${encodeURIComponent(id)}`),
  /** Looks the weather up again for a saved trip; the trip itself is not changed. */
  tripWeather: (id: string) => request<WeatherCheck>(`/api/trips/${encodeURIComponent(id)}/weather`),
  patchTrip: (id: string, changes: TripPatch) =>
    request<Trip>(`/api/trips/${encodeURIComponent(id)}`, { method: 'PATCH', body: changes }),
  removeTrip: (id: string) => request<void>(`/api/trips/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  insights: () => request<Insights>('/api/insights'),
  // What's missing and the wishlist
  gaps: () => request<GapsAnswer>('/api/gaps'),
  hideGap: (id: string, reason: HideReason | null) =>
    request<unknown>(`/api/gaps/${encodeURIComponent(id)}/hide`, { method: 'POST', body: { reason } }),
  unhideGap: (id: string) => request<void>(`/api/gaps/${encodeURIComponent(id)}/hide`, { method: 'DELETE' }),
  wishlist: () => request<{ wishes: Wish[] }>('/api/wishlist').then((r) => r.wishes),
  addWish: (wish: { gap_id: string } | { name: string; note?: string }) => request<Wish>('/api/wishlist', { method: 'POST', body: wish }),
  changeWish: (id: string, changes: { name?: string; note?: string }) =>
    request<Wish>(`/api/wishlist/${encodeURIComponent(id)}`, { method: 'PATCH', body: changes }),
  wishBought: (id: string) => request<Wish>(`/api/wishlist/${encodeURIComponent(id)}/bought`, { method: 'POST' }),
  removeWish: (id: string) => request<void>(`/api/wishlist/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  // Would this work?: a check starts and answers later; the photo is not kept
  checkByHand: (piece: Partial<WouldPiece>) => request<Check>('/api/would-this-work', { method: 'POST', body: { piece } }),
  checkPhoto: (photo: Blob, filename: string) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    return request<Check>('/api/would-this-work', { method: 'POST', form });
  },
  check: (id: string, signal?: AbortSignal) => request<Check>(`/api/would-this-work/${encodeURIComponent(id)}`, { signal }),
  outfitFigure: (pieces: FigurePieces, signal?: AbortSignal) =>
    request<string>('/api/outfits/figure', { method: 'POST', body: pieces, signal, text: true }),
  backup: () => request<BackupRecord>('/api/backup', { method: 'POST' }),
  setProfile: (profile: Profile) => request<{ profile: Profile }>('/api/profile', { method: 'POST', body: { profile } }),
  quit: () => request<void>('/api/quit', { method: 'POST' }),
};

/** Removes the saved copies of closet data (kept: the app's own files). */
export async function clearSavedData(): Promise<void> {
  forgetSaved();
  if (!('caches' in window)) return;
  const names = await caches.keys();
  await Promise.all(names.filter((n) => n.startsWith('closet-data') || n.startsWith('closet-media')).map((n) => caches.delete(n)));
}
