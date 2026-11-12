export type CutoutState = 'none' | 'pending' | 'processing' | 'ready' | 'failed';
export type Profile = 'main' | 'demo';
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
  thumb_url: string | null;
  has_illustration: boolean;
  illustration_url?: string | null;
  has_photo: boolean;
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
  silhouette: Silhouette;
  photos: Photo[];
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
  phone: { tailscale_installed: boolean; running: boolean; address: string | null; command: string };
  autostart: boolean | null;
  heic_supported: boolean;
}

export interface StorageInfo {
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
  free_bytes: number;
}
