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
  /** Why describing it failed, in plain words. */
  tag_error: string | null;
  /** Who described it: 'plan', 'api', or 'demo' for the demo closet's descriptions made in advance. */
  tag_route: string | null;
  tag_model: string | null;
  tag_schema_version: number | null;
  tagged_at: string | null;
  /** The construction details from the stored answer (taxonomy values; null when there is none). */
  details: Record<string, unknown> | null;
  /** Features Claude saw that the drawing does not show yet. */
  seen_not_drawn: string[];
  /** Who set each field: 'user' for the owner, 'ai' for a suggestion. */
  source: Record<string, string>;
  confidence: Record<string, number>;
  silhouette: Silhouette;
  photos: Photo[];
  /** The latest wears, newest first. */
  recent_wears: string[];
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
  /** Whether the API key may be used for tagging (off until there is a spend cap). */
  tagging_api_enabled: boolean;
  phone: { tailscale_installed: boolean; running: boolean; address: string | null; command: string };
  autostart: boolean | null;
  heic_supported: boolean;
  /** Where the owner is, for the weather; null until chosen. */
  place: Place | null;
}

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
