-- Several items from one photo (closet/sources.py). The photo is kept once, at most 1600px like any photo, with a
-- box around each garment Claude found in it (or the owner drew). Once the owner has checked the boxes, each becomes
-- an ordinary item with its own photo (the box cut out of this one) and remembers which photo and box it came from.

CREATE TABLE source_photos (
  id            TEXT PRIMARY KEY,
  client_key    TEXT UNIQUE,         -- set by the uploader so a retried upload never keeps the photo twice
  original_path TEXT NOT NULL,       -- relative to the images folder: sources/<id>/photo.webp
  thumb_path    TEXT NOT NULL,
  width         INTEGER NOT NULL,
  height        INTEGER NOT NULL,
  bytes         INTEGER,
  sha256        TEXT,
  source_sha256 TEXT NOT NULL,       -- the file the owner picked, as photos.source_sha256: the same photo is not kept twice
  state         TEXT NOT NULL DEFAULT 'finding' CHECK (state IN ('finding', 'review', 'added')),
  boxes         TEXT NOT NULL DEFAULT '[]',   -- JSON: [{id, x0, y0, x1, y1, label}], fractions of the photo, in order
  found_by      TEXT,                -- 'claude' when Claude found the boxes; null when the owner drew them all
  note          TEXT,                -- why finding waits or did not work, in plain words; null otherwise
  attempts      INTEGER NOT NULL DEFAULT 0,   -- tries at finding the boxes that gave no usable answer
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX source_photos_sha256 ON source_photos (source_sha256);
CREATE INDEX source_photos_state ON source_photos (state, created_at);

ALTER TABLE items ADD COLUMN source_photo_id TEXT REFERENCES source_photos (id) ON DELETE SET NULL;
ALTER TABLE items ADD COLUMN source_box TEXT;   -- JSON {x0, y0, x1, y1}: the box in that photo, fractions of its size
