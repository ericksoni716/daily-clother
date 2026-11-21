import type { Life } from './life';
import type { UpdateStatus } from './updates';
import type { TalkTurn } from './today';

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
  /** Why describing it failed, or while it waits, why it can't go yet (the API key's monthly limit, Claude Code's
   * sign-in), in plain words; null otherwise. */
  tag_error?: string | null;
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
  /** what it is: its kind from the owner's taxonomy (see kinds.ts), or null when nobody has said */
  kind?: string | null;
  kind_name?: string | null;
  /** the group it is shown in: its kind's, or its category's when it has no kind */
  group?: string | null;
  /** a shoe drawn by Claude for the outfit figure: how far that has got (see ShoeDrawn.state); null for anything else */
  drawn_state?: ShoeDrawn['state'];
  /** a short hash of the shoe's drawing for the outfit figure, which changes when it is drawn again; null without one */
  drawn_version?: string | null;
  /** how far the work on it has got (see Progress); null when nothing is being done to it and nothing failed */
  progress?: Progress | null;
}

/** How far the work on an item has got, worked out by the server (`backend/closet/progress.py`), in its words. */
export interface Progress {
  /** the part of the work: cutting out, describing (and drawing), measuring its pattern, tracing a shoe, sorting a
   * shoe's photos into views, or a shoe drawn by Claude */
  stage: 'cutout' | 'describing' | 'pattern' | 'trace' | 'views' | 'shoe';
  /** which of the steps (cutting out, describing and drawing, finishing the drawing) */
  step: 1 | 2 | 3;
  of: number;
  /** working: being done now; queued: next in line; waiting: held up by `waiting_for`; failed */
  state: 'working' | 'queued' | 'waiting' | 'failed';
  /** the step's name ("Cutting out") */
  title: string;
  /** what is happening now ("Claude is describing it") */
  words: string;
  /** where it runs and how long it usually takes */
  about: string;
  waiting_for: 'model' | 'download' | 'claude' | 'limit' | 'sign-in' | 'you' | null;
  /** why it waits, as a sentence */
  why: string | null;
  /** why it failed */
  error: string | null;
  can_retry: boolean;
  /** what trying again does: cut it out again, or ask Claude to describe it again */
  retry: 'cutout' | 'describe' | null;
}

/** `GET /api/progress`: the items being worked on, oldest first. */
export interface ProgressList {
  items: (Pick<ItemSummary, 'id' | 'name' | 'category' | 'color' | 'status' | 'thumb_url'> & { progress: Progress })[];
  /** how many are being worked on or next in line, and how many wait */
  going: number;
  waiting: number;
  /** why items wait, when it is something you can see to (the monthly limit, signing in, background removal) */
  why: string | null;
}

/** What a photo of a shoe shows: its outer or inner side, from above, the front (toe towards the camera), the back
 * (heel towards the camera), the sole, or something else. */
export type ShoeView = 'outer' | 'inner' | 'top' | 'front' | 'back' | 'sole' | 'other';

export interface Photo {
  id: string;
  /** 'front' is the item's main photo (whatever view it shows); a shoe's other photos are 'detail'. */
  kind: string;
  /** A shoe's photo: the view it shows (null: not sorted yet, and for any other item's photo). */
  view?: ShoeView | null;
  /** Whether that view is sure (null: not sorted). */
  view_sure?: boolean | null;
  /** Who said the view: Claude sorting the photos ('model') or the owner. */
  view_by?: 'model' | 'owner' | null;
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
  /** who said what it is ("owner" or "claude"), how sure Claude was, and the kinds Claude's answer also fits */
  kind_by?: 'owner' | 'claude' | null;
  kind_confidence?: number | null;
  kind_alternatives?: string[];
  formality: string | null;
  season: string | null;
  brand: string | null;
  size: string | null;
  material: string | null;
  fit_notes: string | null;
  /** How the owner wears it, in their own words ("How I wear it"); Claude reads it when it chooses the outfits. */
  wear_notes: string | null;
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
  /** How it sits on the outfit figure (its fit, length, sleeves or leg), each with the detail that corrects it;
   * what was not told is left out. */
  as_worn?: WornPart[];
  /** Trousers and shorts: a small drawing from behind (back pockets, yoke, label), or null when nothing on the back is known. */
  back_url?: string | null;
  /** Who set each field: 'user' for the owner, 'ai' for a suggestion. */
  source: Record<string, string>;
  confidence: Record<string, number>;
  silhouette: Silhouette;
  photos: Photo[];
  /** The latest wears, newest first. */
  recent_wears: string[];
  /** The photo of several pieces this item was cut from, and its box in it; null for a photo of its own. */
  source_photo?: { id: string; photo_url: string; box: BoxEdges | null } | null;
  /** A shoe traced from its side-on photo; null for anything that is not a shoe. */
  trace?: ShoeTrace | null;
  /** A shoe's photos sorted into views; null for anything that is not a shoe. */
  views?: ShoeViews | null;
  /** A shoe drawn by Claude from its photos for the outfit figure; null for anything that is not a shoe. */
  drawn?: ShoeDrawn | null;
}

/** A shoe drawn by Claude from its photos for the outfit figure: drawn once by itself after its photos are sorted,
 * after that only when the owner asks. */
export interface ShoeDrawn {
  /** null: not drawn, nor waiting to be; waiting: for its photos to be sorted, the answer about the outside, or Claude
   * (also a correction from the owner's note waiting: see `correcting`); correcting: the drawing is being changed from
   * the owner's note; failed: three tries gave no drawing (the one it had, if any, stays). */
  state: 'waiting' | 'drawing' | 'correcting' | 'done' | 'failed' | null;
  /** What is happening, or why it is not drawn, in plain words. */
  message: string | null;
  /** The drawing on two legs, while the shoe has one (the old one stays until a new one is done). */
  url: string | null;
  /** How many times the drawing was checked against the photos. */
  rounds: number | null;
  seconds: number | null;
  /** What the API key would charge for it, whichever way it was drawn. */
  cost_usd: number | null;
  route: 'plan' | 'api' | '' | null;
  made_at: string | null;
  /** Photos were added or removed since it was drawn. */
  photos_changed: boolean;
  /** Roughly what drawing it again costs on the API key. */
  about_usd: number;
  /** A correction from the owner's note waits or is being made (`note` is that note). */
  correcting: boolean;
  /** While correcting, the note being drawn; otherwise the note this drawing was changed from (null when it was not). */
  note: string | null;
  /** This drawing is the one before, changed from the owner's note (`note`, `changed`, `against_photos`). */
  corrected: boolean;
  /** What Claude says it changed, in one plain sentence. */
  changed: string | null;
  /** When the note asks for something the photos do not show, one plain sentence saying so (drawn as asked). */
  against_photos: string | null;
  /** The drawing before the last change is kept: the owner can go back to it in one tap. */
  has_previous: boolean;
  /** That kept drawing is the newer one (the owner went back): the same button goes forward again. */
  previous_newer: boolean;
  /** The shoe drawn by Claude from its side with this drawing, on its card, and what makes the shoe itself from the
   * side; null when it has none (yet). */
  side: ShoeSide | null;
  /** The item's own drawing (the closet tile, the item page's drawing) is that side: the trace's colours and marks do
   * not show. False when the owner chose the plain drawing. */
  side_shown: boolean;
  /** The note waiting or being made (`correcting`, `note`) is about the side drawing, not the front. */
  correcting_side: boolean;
  /** The last change to this drawing was its side, changed from the owner's note (`side_note`, `side_changed`,
   * `side_against_photos`); the front is as it was. The front's `corrected`, `note`, `changed` and `against_photos`
   * stay about the front's last correction. */
  side_corrected: boolean;
  side_note: string | null;
  /** What Claude says it changed in the side, in one plain sentence. */
  side_changed: string | null;
  /** When the note on the side asks for something the photos do not show, one plain sentence saying so. */
  side_against_photos: string | null;
}

/** The shoe drawn by Claude from its side: its picture on its card, what makes the shoe itself from the side, and how
 * long it took, how often it was checked and what it cost (for a side changed from a note, that change's). */
export interface ShoeSide {
  url: string;
  features: string[];
  rounds?: number | null;
  seconds?: number | null;
  cost_usd?: number | null;
  route?: 'plan' | 'api' | '' | null;
}

/** A shoe's photos sorted into views by Claude, so the owner never has to say which is which. */
export interface ShoeViews {
  /** null: nothing to sort (a shoe kept from before, or the demo closet); asking: the owner is asked which photo
   * shows the outside. */
  state: 'waiting' | 'sorting' | 'asking' | 'sorted' | 'failed' | null;
  /** What is happening, or why the photos are not sorted, in plain words. */
  message: string | null;
  /** While asking: the photos to choose the outside from (ids, the main photo first). */
  asking: string[] | null;
}

/** A shoe's trace from its photo, and what "Fix the details" can change on the traced drawing. */
export interface ShoeTrace {
  /** null: not traced (yet); refused: the photo would not trace well; failed: it could not be traced. */
  state: 'waiting' | 'working' | 'done' | 'refused' | 'failed' | null;
  /** What is happening, or why it is drawn from its details, in plain words. */
  message: string | null;
  /** The item's drawing is the traced one. */
  drawn: boolean;
  /** The owner chose the plain drawing for this shoe. */
  plain: boolean;
  /** The owner has fixed something on the traced drawing. */
  fixed: boolean;
  parts: TracePart[];
  marks: TraceMark[];
}

export interface TracePart {
  name: string;
  title: string;
  /** The colour drawn: the owner's, else the traced one. */
  color: string;
  traced: string;
  own: boolean;
}

export interface TraceMark {
  index: number;
  kind: string;
  title: string;
  color: string;
  hidden: boolean;
  /** cm towards the toe, cm up, from where it was traced */
  moved: [number, number];
}

export type TraceFix =
  | { part: string; color: string | null }
  | { mark: number; hide: boolean }
  | { mark: number; nudge: [number, number] }
  | { reset: true };

export interface WornPart {
  part: 'fit' | 'length' | 'sleeve' | 'leg';
  value: string;
  /** The detail that corrects it in "Fix the details". */
  field: string;
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
  /** the groups kinds are shown in, for the Closet filter */
  kind_groups?: { id: string; title: string }[];
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
  /** The second model, asked as well for striped and checked clothes; null when there is none (tests). */
  second?: ModelInfo | null;
}

export interface BackupRecord {
  at: string;
  ok: boolean;
  error: string | null;
  folder: string | null;
  kind: string;
}

/** What Closet did at start-up about a restore that was cut short: shown once, until the owner says OK. */
export interface RestoreNotice {
  at: string;
  outcome: 'finished' | 'undone' | 'unreadable';
  message: string;
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
  /** How the phone reaches Closet, looked up in the background; null until the first lookup is in. */
  phone: PhoneInfo | null;
  /** How this device came in. */
  came_in: CameIn;
  /** The door through Cloudflare, changed on the computer (or through Tailscale), never through Cloudflare itself. */
  cloudflare: CloudflareDoor;
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
  /** Laundry that keeps itself: worn clothes go in by themselves after their count, and come out on the laundry day. */
  laundry?: LaundrySetting;
  /** Whether Claude may choose the outfits on Today (Settings, Your style); otherwise Closet's own rules do. */
  stylist_on?: boolean;
  // Each exactly what its own endpoint answers, so Settings is drawn from this one answer.
  /** As `GET /api/model`. */
  model: ModelInfo;
  /** As `GET /api/updates`; null when the program has no updater. */
  updates: UpdateStatus | null;
  /** As `GET /api/style/profile`. */
  style_profile: StyleProfile;
  /** As `GET /api/tagging/spend`. */
  tagging_spend: TaggingSpend;
}

/** Phone access through Tailscale: the address that reaches Closet (null when no share does), and the commands. */
export interface PhoneInfo {
  tailscale_installed: boolean; running: boolean; address: string | null; command: string;
  stop_command: string | null; others_share: boolean;
}

/** How the device asking came in (`gate.came_in`): on this computer, through Tailscale, or through Cloudflare's sign-in.
 * `login` is who Tailscale or Cloudflare said it is; null when no one was named. */
export interface CameIn {
  via: 'computer' | 'tailscale' | 'cloudflare';
  login: string | null;
  name: string | null;
}

/** The door through Cloudflare (`access.py`): off (`on` false) until all three are set. */
export interface CloudflareDoor {
  team: string | null;
  aud: string | null;
  host: string | null;
  on: boolean;
}

/** Laundry that keeps itself. `day`: Monday 0 to Sunday 6, or null for no set laundry day. */
export interface LaundrySetting {
  auto: boolean;
  day: number | null;
}

/** The owner's style profile (Settings, "Your style"): how they like to dress, in their own words. `text` is the one in
 * force, the starting text (`default_text`) while `is_default`; `updated_at` is when it was last saved (null: never). */
export interface StyleProfile {
  text: string;
  is_default: boolean;
  updated_at: string | null;
  default_text: string;
  max_length: number;
  /** The profile's lines in order, each with where it came from. Absent in a copy saved before lines existed. */
  lines?: StyleLine[];
}

/** Where a line of Your style came from: a starting line, written by you, kept from a conversation, or an answer. */
export type StyleLineSource = 'start' | 'owner' | 'talk' | 'question';

/** One line of Your style. While the starting profile is in force its lines have ids -1, -2… and no date. */
export interface StyleLine {
  id: number;
  /** The line as written, with its "- " when it has one. */
  text: string;
  source: StyleLineSource;
  /** UTC, when the line was written or last changed by you; null for a starting line not yet changed. */
  created_at: string | null;
}

/** A question the stylist cannot learn from your clothes, asked one at a time in the style conversation. */
export interface StyleQuestion {
  id: string;
  ask: string;
  why: string;
  /** What each answer button says. */
  choices: string[];
}

/** The style conversation as it stands: the day's turns, the one being answered, the next question while nothing has
 * been said today, and why a message can't be sent now (or null). */
export interface StyleTalk {
  turns: TalkTurn[];
  answering: string | null;
  question: StyleQuestion | null;
  refused: string | null;
}

/** After answering or skipping a question: the line kept (null for a skip) and the next question. */
export interface QuestionAnswer {
  line: StyleLine | null;
  question: StyleQuestion | null;
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
