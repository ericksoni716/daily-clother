-- Stop D: what the owner decided about the gaps: the ones hidden ("Not for me") and the wishlist.
-- A gap is known by the `id` the analysis gives it (closet/gaps.py), which is the same for the same suggestion
-- each time the analysis runs, so a decision outlives the analysis and the items it was based on.

CREATE TABLE hidden_gaps (
  gap_id    TEXT PRIMARY KEY,   -- the gap's id from the analysis ("outer-rain", "trousers-business")
  name      TEXT NOT NULL,      -- its name when it was hidden, for the record
  reason    TEXT CHECK (reason IN ('have_one', 'never_wear', 'too_expensive', 'other')),  -- null: no reason given
  hidden_at TEXT NOT NULL       -- UTC
);

CREATE TABLE wishes (
  id         TEXT PRIMARY KEY,
  gap_id     TEXT,              -- the gap it came from, or null for a wish added by hand
  name       TEXT NOT NULL,
  look_for   TEXT,              -- JSON: the gap's look_for when it was wished, so it is kept if the gap goes; null by hand
  note       TEXT NOT NULL DEFAULT '',
  bought_at  TEXT,              -- UTC; set by "I bought it", which takes it off the list (the row is kept)
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
-- one wish still wanted per gap
CREATE UNIQUE INDEX wishes_open_gap ON wishes (gap_id) WHERE gap_id IS NOT NULL AND bought_at IS NULL;
