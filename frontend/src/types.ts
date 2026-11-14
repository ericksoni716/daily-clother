import type { Life } from './life';

export type CutoutState = 'none' | 'pending' | 'processing' | 'ready' | 'failed';
/** Being described by Claude: none (never asked), waiting, working, done, failed. */
export type TagState = 'none' | 'waiting' | 'working' | 'done' | 'failed';
export type Profile = 'main' | 'demo';
export type Laundry = 'clean' | 'laundry';
export type ModelState = 'missing' | 'downloading' | 'failed' | 'ready';

export interface Session {
  authenticated: boolean;
  setup_required: boolean;
  version: string;
  profile: Profile;
}

/** One colour of a measured pattern: its colour word, its shade and how much of the pattern it covers (0..1). */
export interface PatternColour {
  color: string;
  hex: string;
  share: number;
}

export interface ItemSummary {
  id: string;
  name: string | null;
  category: string | null;
  color: string | null;
  color_hex: string | null;
  pattern: string | null;
  location: string | null;
  rating: string | null;
  status: 'active' | 'archived';
  cutout_state: CutoutState;
  tag_state: TagState;
  thumb_url: string | null;
  has_illustration: boolean;
  illustration_url?: string | null;
  has_photo: boolean;
  /** Local date ("YYYY-MM-DD") of the latest wear, or null. */
  last_worn: string | null;
  wear_count: number;
  wears_since_wash: number;
  laundry: Laundry;
  created_at: string;
  updated_at: string;
}

export interface Photo {
  id: string;
  kind: string;
  url: string | null;
  thumb_url: string | null;
  cutout_url: string | null;
  cutout_thumb_url: string | null;
  width: number | null;
  height: number | null;
}

export type Silhouette = Record<string, string>;

export interface Failure {
  stage: 'cutout' | 'description';
  reason: string;
  details: string | null;
}

export interface Item extends ItemSummary {
  formality: string | null;
  season: string | null;
  brand: string | null;
  size: string | null;
  material: string | null;
  fit_notes: string | null;
  condition: string | null;
  price_cents: number | null;
  acquired_on: string | null;
  notes: string | null;
  rating_reason: string | null;
  illustration_svg: string | null;
  cutout_error: string | null;
  /** Why describing it failed, or while it waits, why it can't go yet (the API key's monthly limit), in plain words. */
  tag_error: string | null;
  /** The pattern measured from the photo: null (nothing to measure), waiting, working, done or failed. */
  pattern_state: 'waiting' | 'working' | 'done' | 'failed' | null;
  pattern_error: string | null;
  /** The colours measured from the pattern, largest first (empty when it has not been measured). */
  pattern_colors?: PatternColour[];
  /** The owner's name for its shade (from the taxonomy's shades, e.g. 'charcoal'), or null when there is none. */
  shade?: string | null;
  /** Why its cutout or its description failed: a plain sentence, and the stored reason with keys and outside paths
   * taken out (null when nothing was recorded). Null when nothing has failed. */
  failure: Failure | null;
  /** Who described it: 'plan', 'api', or 'demo' for the demo closet's descriptions made in advance. */
  tag_route: string | null;
  tag_model: string | null;
  tag_schema_version: number | null;
  tagged_at: string | null;
  /** The construction details from the stored answer (taxonomy values; null when there is none). */
  details: Record<string, unknown> | null;
  /** The details the owner set, laid over Claude's when drawn ("yes"/"no" for a feature). */
  own_details?: Record<string, unknown>;
  /** Features Claude saw that the drawing does not show yet. */
  seen_not_drawn: string[];
  /** What the drawing could not show, in plain words (e.g. a pattern drawn as its colour only). */
  drawing_notes: string[];
  /** Who set each field: 'user' for the owner, 'ai' for a suggestion. */
  source: Record<string, string>;
  confidence: Record<string, number>;
  silhouette: Silhouette;
  photos: Photo[];
  /** The latest wears, newest first. */
  recent_wears: string[];
  /** The photo of several pieces this item was cut from, and its box in it; null for a photo of its own. */
  source_photo?: { id: string; photo_url: string; box: BoxEdges | null } | null;
}

export type ItemPatch = Partial<Omit<Item, 'silhouette'>> & { silhouette?: Record<string, string | null> };

export interface Vocab {
  category: string[];
  color: string[];
  pattern: string[];
  formality: string[];
  season: string[];
  location: string[];
  condition: string[];
  rating: string[];
  silhouette: Record<string, string[]>;
}

export interface ModelInfo {
  state: ModelState;
  downloaded_bytes: number;
  total_bytes: number | null;
  error: string | null;
  url: string;
  path: string;
  sha256: string;
  name: string;
}

export interface BackupRecord {
  at: string;
  ok: boolean;
  error: string | null;
  folder: string | null;
  kind: string;
}

export interface Settings {
  version: string;
  profile: Profile;
  data_dir: string;
  port: number;
  backup_folder: string | null;
  last_backup: BackupRecord | null;
  last_good_backup: string | null;
  pending_cutouts: number;
  /** Items waiting to be described by Claude. */
  pending_tags: number;
  /** Whether the API key may be used for tagging: off by default, and only with a monthly limit. */
  tagging_api_enabled: boolean;
  /** The API key's monthly spending limit in US dollars; null until set. */
  tagging_api_cap_usd: number | null;
  /** Set when Anthropic refused the key and Closet switched it off. */
  tagging_api_off: ApiTurnedOff | null;
  /** Which route to Claude is tried first: the plan first (default), the key first, or only one of them. */
  tagging_route_order: RouteOrder;
  /** Whether an API key is set and where it comes from; never the key itself. */
  api_key: ApiKeyInfo;
  phone: { tailscale_installed: boolean; running: boolean; address: string | null; command: string };
  autostart: boolean | null;
  heic_supported: boolean;
  /** Where the owner is, for the weather: New York (`home_place`) until another place is chosen. */
  place: Place | null;
  /** The place used until one is chosen, and again when the chosen one is removed. */
  home_place?: Place;
  life: Life | null;
  life_prompt_dismissed: boolean;
  /** "Before it needs washing": wears per kind of clothing on a trip; null is the whole trip. */
  rewear?: Rewear;
}

/** The kinds of clothing the owner sets "Before it needs washing" for. */
export type RewearKind = 'tops' | 'knits' | 'bottoms' | 'outer' | 'basics';
export type Rewear = Record<RewearKind, number | null>;

/** A place to look up the weather for (saved in the program's settings, not in a closet). */
export interface Place {
  name: string;
  latitude: number;
  longitude: number;
  timezone: string;
}

/** One day's forecast, in °C. */
export interface Weather {
  date: string;
  low_c: number;
  high_c: number;
  /** Percent, or null when the forecast has none. */
  rain_chance: number | null;
  rain: boolean;
  /** One word: clear, cloudy, foggy, drizzle, rain, snow, storms or mixed. */
  summary: string;
  fetched_at: string;
}

/** Today's weather for the saved place; `message` says in plain words why there is none, or that it is old. */
export interface WeatherLookup {
  place: Place | null;
  weather: Weather | null;
  old: boolean;
  is_today: boolean;
  message: string | null;
}

/** Disk space used by the open closet (its own pictures and database; the shared model, logs and backups). */
export interface Storage {
  items: number;
  photos_bytes: number;
  cutouts_bytes: number;
  thumbnails_bytes: number;
  database_bytes: number;
  backups_bytes: number;
  model_bytes: number;
  logs_bytes: number;
  total_bytes: number;
  data_dir: string;
  free_bytes: number | null;
}

/** One way of reaching Claude: the owner's Claude plan through Claude Code, or an API key. */
export interface TaggingRoute {
  id: 'plan' | 'api';
  available: boolean;
  /** Why it can't be used right now, in plain words; empty when it can. */
  detail: string;
}

/** Why Closet switched the API key off by itself: no credit left, or the key was not accepted. */
export interface ApiKeyInfo {
  set: boolean;
  /** "keychain": saved from Settings; "environment": ANTHROPIC_API_KEY on the computer. */
  source: 'keychain' | 'environment' | null;
  /** Whether this computer has a keychain Closet can keep a key in. */
  can_save: boolean;
  /** Where a saved key is kept, in plain words ("this Mac's keychain"), or null. */
  where: string | null;
  /** Only on the answer to saving a key: false when Anthropic couldn't be reached to check it. */
  checked?: boolean;
}

export interface ApiTurnedOff {
  at: string;
  reason: 'credit' | 'key';
}

/** One calendar month of calls to Claude (the computer's local time). */
export interface SpendMonth {
  month: string;
  api_calls: number;
  plan_calls: number;
  spent_usd: number;
  input_tokens: number;
  output_tokens: number;
}

/** GET /api/tagging/spend: what the API key has cost, its limit, and what waiting items would cost. */
export interface TaggingSpend {
  allowed: boolean;
  cap_usd: number | null;
  suggested_cap_usd: number;
  max_cap_usd: number;
  /** "2026-11" */
  month: string;
  spent_usd: number;
  api_calls: number;
  plan_calls: number;
  input_tokens: number;
  output_tokens: number;
  left_usd: number | null;
  /** Less is left than one more photo could cost. */
  reached: boolean;
  /** The most one photo should cost through the API key. */
  per_photo_usd: number;
  /** The most finding the pieces in one photo of several should cost through the API key. */
  per_find_usd: number;
  waiting: { items: number; photos: number; at_most_usd: number };
  model: string;
  /** The date the price table was written down, "2026-11-03". */
  prices_checked: string;
  turned_off: ApiTurnedOff | null;
  /** Newest first, this month included once anything was sent. */
  history: SpendMonth[];
}

/** The order the routes to Claude are tried in, as chosen in Settings. */
export type RouteOrder = 'auto' | 'api-first' | 'plan' | 'api';

/** Which routes to Claude can be used right now, and the order they are tried in. */
export interface TaggingStatus {
  order: TaggingRoute['id'][];
  routes: TaggingRoute[];
}

/** One field the tagger was unsure of: its value (an object of parts for the silhouette) and the allowed values. */
export interface ReviewField {
  field: 'category' | 'color' | 'pattern' | 'formality' | 'season' | 'silhouette';
  value: string | Record<string, string>;
  confidence: number;
  allowed: string[] | Record<string, string[]>;
}

export interface ReviewItem extends ItemSummary {
  /** The biggest picture to judge from: the cutout, else the photo, else the drawing. */
  picture_url: string | null;
  picture_kind: 'cutout' | 'photo' | 'illustration' | null;
  fields: ReviewField[];
}

/** The review queue, most doubtful first, and the items not in it because they are not described yet. */
export interface ReviewQueue {
  count: number;
  items: ReviewItem[];
  waiting: number;
  failed: number;
  waiting_items: { id: string; name: string | null; category: string | null }[];
  failed_items: { id: string; name: string | null; category: string | null }[];
}

/** A box in a photo, as fractions of its width and height (0 left/top, 1 right/bottom). */
export interface BoxEdges {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** A box around one piece in a photo of several. */
export interface SourceBox extends BoxEdges {
  id: string;
  /** Its number on the photo, from 1. */
  n: number;
  /** What Claude called the piece; null for a box the owner drew. */
  label: string | null;
  /** The piece cut out of its background; answers 409 until the background model is ready. */
  cutout_url: string;
}

/** A photo of several pieces: waiting for Claude to find them, ready to check, or added. */
export interface SourcePhoto {
  id: string;
  state: 'finding' | 'review' | 'added';
  /** Why finding waits or did not work (or that the demo never asks Claude); null otherwise. */
  note: string | null;
  found_by: 'claude' | null;
  photo_url: string;
  thumb_url: string;
  width: number;
  height: number;
  boxes: SourceBox[];
  /** The items made from it, once added. */
  items: ItemSummary[];
  created_at: string;
  updated_at: string;
}

/** What sending a photo of several pieces answers: the photo kept, or what an earlier copy of it became. */
export interface SourceUpload {
  duplicate: boolean;
  source: SourcePhoto | null;
  item: Item | null;
}
