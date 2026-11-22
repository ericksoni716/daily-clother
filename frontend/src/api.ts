import type { BackgroundState, Item, ItemPatch, ItemSummary, Laundry, ModelInfo, ProgressList, Session, Settings, Storage, TaggingSpend, TaggingStatus, Vocab, BoxEdges, SourcePhoto, SourceUpload, Profile, BackupRecord, RestoreNotice, Place, WeatherLookup, ReviewField, ReviewQueue, RouteOrder, Rewear, ShoeView, TraceFix, LaundrySetting, QuestionAnswer, StyleProfile, StyleTalk } from './types';
import { forgetSaved, type DayAnswer, type RememberHow, type RememberThing, type StyleAnswer, type TodayAnswer, type TodayRequest, type WearManyAnswer } from './today';
import type { CorrectionAnswer, DetailChoices, DetailOptions, HistoryEntry } from './corrections';
import type { PlannedTrip, Trip, TripPatch, TripRequest, TripSummary, WeatherCheck } from './trips';
import type { Insights } from './insights';
import type { OutfitSent, Rating, Reason, WornOutfit, WornPage } from './worn';
import type { GapsAnswer, HideReason, Wish } from './gaps';
import type { FindsAnswer } from './shop';
import type { Life } from './life';
import type { Check, WouldPiece } from './wouldwork';
import type { FigurePieces } from './figure';
import type { KindCatalogue } from './kinds';
import type { UpdateMode, UpdateStatus } from './updates';

/** An error with a sentence the owner can read. status 0 means the server could not be reached. */
export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter?: number) {
    super(message);
  }
}

export const UNREACHABLE = "Can't reach Nines. Check that it is running on your computer.";

/**
 * Header sent on every call, so the server knows the call comes from Closet's own page: it refuses a change without
 * it (backend/closet/gate.py), which another website cannot send.
 */
export const CLIENT_HEADER = 'X-Closet-Client';

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
  if (status >= 500) return 'Something went wrong on the computer running Nines. Try again in a moment.';
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
  /** Give up after this long and treat Closet as out of reach (offline), instead of waiting for the system to. */
  timeoutMs?: number;
}

/**
 * How long the app waits for the questions it opens with (am I logged in, the closet) before showing the saved copy.
 * A computer that is asleep or switched off may never answer, and the phone would otherwise wait a minute or more.
 */
export const OPEN_TIMEOUT_MS = 12_000;

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
  const headers: Record<string, string> = { [CLIENT_HEADER]: '1' };
  const init: RequestInit = { method, credentials: 'same-origin', signal: opts.signal, headers };
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  if (opts.timeoutMs && !opts.signal) {
    const controller = new AbortController();
    init.signal = controller.signal;
    timer = setTimeout(() => { timedOut = true; controller.abort(); }, opts.timeoutMs);
  }
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    headers['Content-Type'] = 'application/json';
  }
  const kept = keepaliveSize(method, init.body as string | undefined, opts, keepaliveBytes);
  if (kept !== null) {
    init.keepalive = true;
    keepaliveBytes += kept;
  }
  let res: Response;
  let text: string;
  try {
    res = await fetch(path, init);
    text = await res.text();
  } catch (e) {
    if ((e as Error)?.name === 'AbortError' && !timedOut) throw e;
    setOffline(true);
    throw new ApiError(0, UNREACHABLE);
  } finally {
    if (kept !== null) keepaliveBytes -= kept;
    if (timer !== undefined) clearTimeout(timer);
  }
  setOffline(res.headers.get(FROM_CACHE_HEADER) === '1');
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
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
  session: () => request<Session>('/api/session', { timeoutMs: OPEN_TIMEOUT_MS }),
  setup: (passphrase: string) => request<void>('/api/setup', { method: 'POST', body: { passphrase }, quiet401: true }),
  login: (passphrase: string) => request<void>('/api/login', { method: 'POST', body: { passphrase }, quiet401: true }),
  logout: () => request<void>('/api/logout', { method: 'POST', quiet401: true }),
  vocab: () => request<Vocab>('/api/vocab'),
  items: (status: 'active' | 'archived' = 'active') =>
    request<{ items: ItemSummary[] }>(`/api/items?status=${status}`, { timeoutMs: OPEN_TIMEOUT_MS }).then((r) => r.items),
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
  /** Every kind in the owner's taxonomy, in its groups; and saying what an item is (its category follows). */
  kinds: () => request<KindCatalogue>('/api/kinds'),
  setKind: (id: string, kind: string) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/kind`, { method: 'PUT', body: { kind } }),
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
  /** A shoe traced from its photo: a fix to its drawing, the plain drawing, tracing it again. */
  fixTrace: (id: string, fix: TraceFix) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/trace/fix`, { method: 'POST', body: fix }),
  setTracePlain: (id: string, plain: boolean) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/trace/plain`, { method: 'PUT', body: { plain } }),
  retrace: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/retrace`, { method: 'POST' }),
  /** A new photo in place of the item's main photo ("Retake the photo"): a shoe is traced again from it, clothes
   * are cut out, described and their pattern measured again. */
  replacePhoto: (id: string, photo: Blob, filename: string, sha256?: string | null) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    if (sha256) form.append('photo_sha256', sha256);
    return request<Item>(`/api/items/${encodeURIComponent(id)}/photo`, { method: 'POST', form });
  },
  /** Another photo of a shoe, besides its main one (at most 5): Closet sorts it into its view. */
  /** What each photo chosen on Add shows (one piece, several, a shoe and which shoe), up to ten small copies at once. */
  /** The note about today or the days ahead, if one holds. */
  day: () => request<DayAnswer>('/api/day'),
  /** Reads a sentence about the owner's day with Claude and keeps it; `saved` false with a `message` when it could not. */
  saveDay: (text: string) => request<DayAnswer>('/api/day', { method: 'PUT', body: { text } }),
  clearDay: () => request<DayAnswer>('/api/day', { method: 'DELETE' }),
  sortAdd: (photos: { blob: Blob; filename: string }[]) => {
    const form = new FormData();
    for (const p of photos) form.append('photos', p.blob, p.filename);
    return request<{ sorted: boolean; message: string | null; needed?: string[];
      photos: { kind: 'piece' | 'pieces' | 'shoe'; shoe: number; view?: string | null; pair?: boolean }[] }>(
      '/api/add/sort', { method: 'POST', form });
  },
  addShoePhoto: (id: string, photo: Blob, filename: string, sha256?: string | null) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    if (sha256) form.append('photo_sha256', sha256);
    return request<Item>(`/api/items/${encodeURIComponent(id)}/photos`, { method: 'POST', form });
  },
  /** Removes one of a shoe's other photos (never its main one). */
  removeShoePhoto: (id: string, photoId: string) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/photos/${encodeURIComponent(photoId)}`, { method: 'DELETE' }),
  /** The owner says which view a photo of a shoe shows (the question about the outside). */
  setPhotoView: (id: string, photoId: string, view: ShoeView) =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/photos/${encodeURIComponent(photoId)}/view`, { method: 'PUT', body: { view } }),
  /** Draws a shoe from its photos (again): the drawing it has stays until the new one is done. */
  drawShoe: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/drawn`, { method: 'POST' }),
  /** The owner's one-line note on a shoe's drawing, about its front or its side: Claude changes only what it asks;
   * the drawing stays until done. */
  correctDrawing: (id: string, note: string, about: 'front' | 'side' = 'front') =>
    request<Item>(`/api/items/${encodeURIComponent(id)}/drawn/correct`, { method: 'POST', body: { note, about } }),
  /** Swaps a shoe's drawing and the one before the last change: back in one tap, and forward again the same way. */
  drawingBack: (id: string) => request<Item>(`/api/items/${encodeURIComponent(id)}/drawn/back`, { method: 'POST' }),
  /** `duplicate` is true when the photo was already in the closet; the item returned is the one it is in. */
  upload: (photo: Blob, filename: string, clientKey: string, sha256?: string | null, signal?: AbortSignal, shoe = false) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    form.append('client_key', clientKey);
    if (sha256) form.append('photo_sha256', sha256);
    if (shoe) form.append('shoe', 'true');   // added from "A shoe": its photos are sorted into views
    return request<Item & { duplicate?: boolean }>('/api/items', { method: 'POST', form, signal });
  },
  /** A photo of several pieces, kept once; `duplicate` when it (or a single item made from it) is already kept. */
  uploadSeveral: (photo: Blob, filename: string, clientKey: string, sha256?: string | null, signal?: AbortSignal) => {
    const form = new FormData();
    form.append('photo', photo, filename);
    form.append('client_key', clientKey);
    if (sha256) form.append('photo_sha256', sha256);
    return request<SourceUpload>('/api/sources', { method: 'POST', form, signal });
  },
  sources: () => request<{ sources: SourcePhoto[] }>('/api/sources').then((r) => r.sources),
  source: (id: string) => request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}`),
  addBox: (id: string, box: BoxEdges) =>
    request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}/boxes`, { method: 'POST', body: box }),
  moveBox: (id: string, boxId: string, box: BoxEdges) =>
    request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}/boxes/${encodeURIComponent(boxId)}`, { method: 'PUT', body: box }),
  removeBox: (id: string, boxId: string) =>
    request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}/boxes/${encodeURIComponent(boxId)}`, { method: 'DELETE' }),
  mergeBoxes: (id: string, ids: string[]) =>
    request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}/boxes/merge`, { method: 'POST', body: { ids } }),
  addSourceItems: (id: string) => request<SourcePhoto>(`/api/sources/${encodeURIComponent(id)}/add`, { method: 'POST' }),
  forgetSource: (id: string) => request<void>(`/api/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  model: () => request<ModelInfo>('/api/model'),
  /** The items being worked on in the background, asked every few seconds while there are any. */
  progress: () => request<ProgressList>('/api/progress'),
  downloadModel: () => request<ModelInfo>('/api/model/download', { method: 'POST' }),
  setModelUrl: (url: string) => request<ModelInfo>('/api/model/url', { method: 'PUT', body: { url } }),
  settings: () => request<Settings>('/api/settings'),
  putSettings: (changes: { backup_folder?: string | null; autostart?: boolean; place?: Place | null; tagging_api_enabled?: boolean; tagging_api_cap_usd?: number | null; tagging_route_order?: RouteOrder; life?: Life | null; life_prompt_dismissed?: boolean; rewear?: Partial<Rewear> | null; laundry?: Partial<LaundrySetting>; stylist_on?: boolean; show_drawings?: boolean; cloudflare_team?: string; cloudflare_aud?: string; cloudflare_host?: string }) =>
    request<Settings>('/api/settings', { method: 'PUT', body: changes }),
  /** The owner's style profile: the text in force, the starting one until they write their own. */
  styleProfile: () => request<StyleProfile>('/api/style/profile'),
  /** Keep a new version of the style profile; an empty text goes back to the starting one. */
  saveStyleProfile: (text: string) => request<StyleProfile>('/api/style/profile', { method: 'PUT', body: { text } }),
  storage: () => request<Storage>('/api/storage'),
  /** Windows keeping Nines running: read from anywhere, changed only on the computer (Windows asks there). */
  background: () => request<BackgroundState>('/api/background'),
  backgroundOn: () => request<BackgroundState>('/api/background/on', { method: 'POST' }),
  backgroundOff: () => request<BackgroundState>('/api/background/off', { method: 'POST' }),
  backgroundRestart: () => request<BackgroundState>('/api/background/restart', { method: 'POST' }),
  saveApiKey: (key: string) => request<Settings>('/api/settings/api-key', { method: 'PUT', body: { key } }),
  removeApiKey: () => request<Settings>('/api/settings/api-key', { method: 'DELETE' }),
  tagging: () => request<TaggingStatus>('/api/tagging'),
  tagSpend: () => request<TaggingSpend>('/api/tagging/spend'),
  places: (q: string) => request<{ places: Place[] }>(`/api/places?q=${encodeURIComponent(q)}`).then((r) => r.places),
  /** The town at a position from the browser ("Use my location"); not saved until put in the settings. */
  placeNear: (latitude: number, longitude: number) =>
    request<{ place: Place }>(`/api/places/near?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`).then((r) => r.place),
  weather: () => request<WeatherLookup>('/api/weather'),
  today: (choices: TodayRequest, signal?: AbortSignal) =>
    request<TodayAnswer>('/api/outfits/today', { method: 'POST', body: choices, signal }),
  /** How a question to Claude about today's outfits stands, while Today waits on it (cheap to ask every few seconds). */
  styleAnswer: (id: string, signal?: AbortSignal) =>
    request<StyleAnswer>(`/api/style/answers/${encodeURIComponent(id)}`, { signal }),
  /** The owner's answer to a thing Claude offered to remember in its answer to a message: keep it or not, or take it back. */
  remember: (turnId: string, index: number, how: RememberHow) =>
    request<RememberThing>(`/api/style/answers/${encodeURIComponent(turnId)}/remember`, { method: 'POST', body: { index, ...how } }),
  /** The style conversation as it stands (Settings, Your style). */
  styleTalk: () => request<StyleTalk>('/api/style/talk'),
  /** Send a message about your style; gives the conversation, with it being answered. */
  sayStyle: (say: string) => request<StyleTalk>('/api/style/talk', { method: 'POST', body: { say } }),
  /** The owner's answer to a line Claude offered to keep in the style conversation. */
  rememberStyle: (turnId: string, index: number, how: RememberHow) =>
    request<RememberThing>(`/api/style/talk/${encodeURIComponent(turnId)}/remember`, { method: 'POST', body: { index, ...how } }),
  /** Answer a question the stylist cannot infer: one of its choices, your own words, or skip it. */
  answerQuestion: (id: string, answer: { choice: string } | { text: string } | { skip: true }) =>
    request<QuestionAnswer>(`/api/style/questions/${encodeURIComponent(id)}`, { method: 'POST', body: answer }),
  /** Take back an answer (or a skip): the question is asked again. */
  undoQuestion: (id: string) => request<QuestionAnswer>(`/api/style/questions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  /** Add a line of your own at the end of Your style. */
  addStyleLine: (text: string) => request<StyleProfile>('/api/style/lines', { method: 'POST', body: { text } }),
  editStyleLine: (id: number, text: string) => request<StyleProfile>(`/api/style/lines/${id}`, { method: 'PATCH', body: { text } }),
  /** Take a line out of Your style; `removed` is its id, to put it back. */
  removeStyleLine: (id: number) => request<StyleProfile & { removed: number }>(`/api/style/lines/${id}`, { method: 'DELETE' }),
  restoreStyleLine: (id: number) => request<StyleProfile>(`/api/style/lines/${id}/restore`, { method: 'POST' }),
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
  changeWish: (id: string, changes: { name?: string; note?: string; price_min?: number | null; price_max?: number | null; price_currency?: string | null }) =>
    request<Wish>(`/api/wishlist/${encodeURIComponent(id)}`, { method: 'PATCH', body: changes }),
  wishBought: (id: string) => request<Wish>(`/api/wishlist/${encodeURIComponent(id)}/bought`, { method: 'POST' }),
  removeWish: (id: string) => request<void>(`/api/wishlist/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  finds: (id: string) => request<FindsAnswer>(`/api/wishlist/${encodeURIComponent(id)}/finds`),
  findSome: (id: string) => request<FindsAnswer>(`/api/wishlist/${encodeURIComponent(id)}/find`, { method: 'POST' }),
  checkPrices: (id: string) => request<FindsAnswer>(`/api/wishlist/${encodeURIComponent(id)}/prices`, { method: 'POST' }),
  removeFind: (id: string, findId: string) =>
    request<void>(`/api/wishlist/${encodeURIComponent(id)}/finds/${encodeURIComponent(findId)}`, { method: 'DELETE' }),
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
  restoreNotice: () => request<{ notice: RestoreNotice | null }>('/api/restore-notice'),
  dismissRestoreNotice: () => request<void>('/api/restore-notice', { method: 'DELETE' }),
  // New versions of Closet
  updates: () => request<UpdateStatus>('/api/updates'),
  setUpdateMode: (mode: UpdateMode) => request<UpdateStatus>('/api/updates', { method: 'PUT', body: { mode } }),
  checkUpdates: () => request<UpdateStatus>('/api/updates/check', { method: 'POST' }),
  installUpdate: () => request<UpdateStatus>('/api/updates/install', { method: 'POST' }),
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
