/**
 * Every query key the app uses, and which keys each kind of edit makes stale. Keys are made here and nowhere else:
 * a screen asks for `queryKeys.trips()`, never writes `['trips']` itself. See docs/DEVELOPING.md, "Reading and
 * saving data".
 *
 * The rule a test holds: each key starts with its own name here (`queryKeys.trip('x')` is `['trip', 'x']`), so a
 * name in `TOUCHES` stands for every key made by that function, whatever its arguments.
 */
import type { FigurePieces } from './figure';
import type { TodayRequest } from './today';

export type ItemStatus = 'active' | 'archived';

export const queryKeys = {
  // The closet
  /** `GET /api/items?status=`: the summaries the grid, Today and the rest read. */
  items: (status: ItemStatus) => ['items', status] as const,
  /** `GET /api/progress`: the items being worked on in the background, with their progress. Polled in one place
   * (`ClosetProvider`) while there are any; an edit that can start work on an item makes it stale. */
  progress: () => ['progress'] as const,
  /** `GET /api/items/{id}`: one item in full, for its page. */
  item: (id: string) => ['item', id] as const,
  /** `GET /api/items/{id}/details` (the details that can be fixed, with their values), and, with a name, one
   * detail's choices (`.../details/{name}`). */
  itemDetails: (id: string, name?: string) => (name === undefined ? ['itemDetails', id] as const : ['itemDetails', id, name] as const),
  /** `GET /api/items/{id}/history`: the changes that can be undone. */
  history: (id: string) => ['history', id] as const,
  /** `GET /api/vocab`: the small vocabulary and the kinds' groups; it changes only with a new version of Closet. */
  vocab: () => ['vocab'] as const,
  /** `GET /api/kinds`: every kind in the taxonomy, in its groups. */
  kinds: () => ['kinds'] as const,
  /** `GET /api/review`: the review queue and its count. */
  review: () => ['review'] as const,
  /** `GET /api/sources` and `GET /api/sources/{id}`: photos of several pieces. */
  sources: () => ['sources'] as const,
  source: (id: string) => ['source', id] as const,

  // Getting dressed
  /** `POST /api/outfits/today` with the owner's choices, on a day, for the closet as it stands (`closet`: what of the
   * closet the answer depends on, see `closetKey` in today.ts). It can ask Claude, so no edit makes it stale by itself. */
  today: (choices: TodayRequest, day = '', closet = '') => ['today', choices, day, closet] as const,
  /** `GET /api/style/answers/{id}`: a question to Claude about today's outfits, while Today waits on it. */
  styleAnswer: (id: string) => ['styleAnswer', id] as const,
  /** `GET /api/day`: the note about today or the days ahead. */
  day: () => ['day'] as const,
  /** `GET /api/weather`. */
  weather: () => ['weather'] as const,
  /** `POST /api/outfits/figure`: the As worn figure for some pieces (an SVG), with the layers under it when `layered`.
   * `version` changes when any piece's drawing does (`figureVersion`), so a figure once drawn never goes stale. */
  figure: (pieces: FigurePieces, version = '', layered = false) => ['figure', pieces, version, layered] as const,
  /** `GET /api/outfits/worn`: outfits worn, a page at a time (`before` is the page's cursor, null for the first). */
  worn: (before: string | null = null) => ['worn', before] as const,

  // Trips
  trips: () => ['trips'] as const,
  trip: (id: string) => ['trip', id] as const,
  tripWeather: (id: string) => ['tripWeather', id] as const,

  // What's missing, shopping, Would this work?
  /** `GET /api/gaps`: what's missing. */
  gaps: () => ['gaps'] as const,
  wishlist: () => ['wishlist'] as const,
  /** `GET /api/wishlist/{id}/finds`: finds for a wish. */
  finds: (wishId: string) => ['finds', wishId] as const,
  /** `GET /api/would-this-work/{id}`: a check, while it is answered. */
  wouldWork: (checkId: string) => ['wouldWork', checkId] as const,
  insights: () => ['insights'] as const,

  // Settings and the program
  settings: () => ['settings'] as const,
  /** `GET /api/style/profile`: Your style. */
  styleProfile: () => ['styleProfile'] as const,
  storage: () => ['storage'] as const,
  /** `GET /api/tagging`: how Claude is reached. */
  tagging: () => ['tagging'] as const,
  /** `GET /api/tagging/spend`: what reaching Claude costs, and the monthly limit. */
  spend: () => ['spend'] as const,
  /** `GET /api/model`: the background-removal models. */
  model: () => ['model'] as const,
  updates: () => ['updates'] as const,
  restoreNotice: () => ['restoreNotice'] as const,
  /** `GET /api/places?q=` and `GET /api/places/near`: finding a town. */
  places: (q: string) => ['places', q] as const,
  placeNear: (latitude: number, longitude: number) => ['placeNear', latitude, longitude] as const,
} as const;

/** The name of a key: its first element, and the name of the function that makes it. */
export type KeyName = keyof typeof queryKeys;

/**
 * Which keys each kind of edit makes stale. A save names its kind (`useEdit('trip')`), and after it succeeds every
 * query under these names is marked stale: the ones on screen are asked again at once, the rest when next shown.
 * Marking a key that nothing shows costs nothing, so a kind lists everything its edit can change.
 *
 * `today` is in none of them on purpose: asking for today's outfits can ask Claude, which costs money.
 */
export const TOUCHES = {
  /** Anything about one item: its fields, details, kind, a correction or undo, its photo, a shoe's photos and drawing,
   * describing it again, archiving it. */
  item: ['items', 'item', 'itemDetails', 'history', 'review', 'insights', 'gaps', 'progress'],
  /** An item deleted. */
  removeItem: ['items', 'item', 'review', 'insights', 'gaps', 'worn'],
  /** Photos added (an upload finished), one at a time or from a photo of several pieces. */
  upload: ['items', 'review', 'sources', 'insights', 'gaps', 'progress'],
  /** A photo of several pieces: its boxes, its pieces added, forgotten. */
  source: ['sources', 'source', 'items', 'review', 'progress'],
  /** Worn today, or a wear taken back, for one item or an outfit. */
  wear: ['items', 'item', 'history', 'worn', 'insights'],
  /** Into the laundry, or clean again. */
  laundry: ['items', 'item', 'insights'],
  /** An outfit worn: recorded, rated or removed. */
  outfit: ['worn', 'items', 'item', 'insights'],
  trip: ['trips', 'trip', 'tripWeather'],
  /** What's missing: a gap hidden or shown again. */
  gap: ['gaps'],
  /** The wishlist: a wish added, changed, bought or removed, and its finds. */
  wish: ['wishlist', 'gaps', 'finds'],
  /** The note about the day. */
  day: ['day'],
  /** Any of the settings (the place, the laundry and rewear rules, how Claude is reached, its monthly limit…). */
  settings: ['settings', 'weather', 'tagging', 'spend', 'gaps', 'progress'],
  /** The API key saved or removed. */
  apiKey: ['settings', 'tagging', 'spend', 'progress'],
  styleProfile: ['styleProfile'],
  /** The background-removal model: a download started, its address changed. */
  model: ['model', 'progress'],
  /** New versions of Closet: how they are fetched, a check, an install. */
  updates: ['updates'],
  backup: ['storage', 'settings'],
  restoreNotice: ['restoreNotice'],
} as const satisfies Record<string, readonly KeyName[]>;

export type EditKind = keyof typeof TOUCHES;

/** The key names an edit of this kind makes stale, less any it has already written itself. */
export function touched(kind: EditKind, written: readonly KeyName[] = []): KeyName[] {
  return TOUCHES[kind].filter((name) => !written.includes(name));
}
