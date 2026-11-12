-- Phase 1: items, their photos, and the background job queue.

CREATE TABLE items (
  id               TEXT PRIMARY KEY,
  client_key       TEXT UNIQUE,              -- set by the uploader so a retried upload never makes a duplicate
  status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  name             TEXT,
  category         TEXT,
  color            TEXT,
  color_hex        TEXT,
  pattern          TEXT,
  formality        TEXT,
  season           TEXT,
  silhouette       TEXT NOT NULL DEFAULT '{}',   -- JSON: sleeve, neck, leg, ...
  confidence       TEXT NOT NULL DEFAULT '{}',   -- JSON: field -> 0..1
  source           TEXT NOT NULL DEFAULT '{}',   -- JSON: field -> 'ai' | 'user' | 'demo'
  brand            TEXT,
  size             TEXT,
  material         TEXT,
  fit_notes        TEXT,
  condition        TEXT,
  price_cents      INTEGER,
  acquired_on      TEXT,
  location         TEXT,
  notes            TEXT,
  rating           TEXT CHECK (rating IN ('love', 'like', 'meh', 'dislike')),
  rating_reason    TEXT,
  illustration_svg TEXT,
  cutout_state     TEXT NOT NULL DEFAULT 'none'
                   CHECK (cutout_state IN ('none', 'pending', 'processing', 'ready', 'failed')),
  cutout_error     TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE INDEX items_status_created ON items (status, created_at DESC);

CREATE TABLE photos (
  id            TEXT PRIMARY KEY,
  item_id       TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  kind          TEXT NOT NULL DEFAULT 'front' CHECK (kind IN ('front', 'tag', 'detail', 'back')),
  original_path TEXT NOT NULL,   -- the uncut photo, at most 1600px, relative to the images folder
  thumb_path    TEXT NOT NULL,
  cutout_path   TEXT,
  cutout_thumb_path TEXT,
  width         INTEGER,
  height        INTEGER,
  bytes         INTEGER,
  sha256        TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX photos_item ON photos (item_id);

CREATE TABLE jobs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  kind       TEXT NOT NULL,
  item_id    TEXT REFERENCES items (id) ON DELETE CASCADE,
  photo_id   TEXT REFERENCES photos (id) ON DELETE CASCADE,
  state      TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'done', 'failed')),
  attempts   INTEGER NOT NULL DEFAULT 0,
  error      TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX jobs_state ON jobs (state, id);
