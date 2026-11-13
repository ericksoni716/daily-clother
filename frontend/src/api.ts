import type { Item, ItemPatch, ItemSummary, Laundry, ModelInfo, Session, Settings, Storage, TaggingSpend, TaggingStatus, Vocab, Profile, BackupRecord, Place, WeatherLookup } from './types';
import { forgetSaved, type TodayAnswer, type TodayRequest, type WearManyAnswer } from './today';

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

interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
  /** Do not treat a 401 as "logged out" (used by login itself). */
  quiet401?: boolean;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const init: RequestInit = { method: opts.method ?? 'GET', credentials: 'same-origin', signal: opts.signal };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { 'Content-Type': 'application/json' };
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e;
    setOffline(true);
    throw new ApiError(0, UNREACHABLE);
  }
  setOffline(res.headers.get(FROM_CACHE_HEADER) === '1');
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await res.text();
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
  wearMany: (ids: string[]) => request<WearManyAnswer>('/api/wears', { method: 'POST', body: { item_ids: ids } }),
  unwearMany: (ids: string[], day: string) =>
    request<WearManyAnswer>('/api/wears/remove', { method: 'POST', body: { item_ids: ids, worn_on: day } }),
  setLaundry: (id: string, state: Laundry) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/laundry`, { method: 'POST', body: { state } }),
  retag: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/retag`, { method: 'POST' }),
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
  putSettings: (changes: { backup_folder?: string | null; autostart?: boolean; place?: Place | null; tagging_api_enabled?: boolean; tagging_api_cap_usd?: number | null }) =>
    request<Settings>('/api/settings', { method: 'PUT', body: changes }),
  storage: () => request<Storage>('/api/storage'),
  tagging: () => request<TaggingStatus>('/api/tagging'),
  tagSpend: () => request<TaggingSpend>('/api/tagging/spend'),
  places: (q: string) => request<{ places: Place[] }>(`/api/places?q=${encodeURIComponent(q)}`).then((r) => r.places),
  weather: () => request<WeatherLookup>('/api/weather'),
  today: (choices: TodayRequest, signal?: AbortSignal) =>
    request<TodayAnswer>('/api/outfits/today', { method: 'POST', body: choices, signal }),
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
