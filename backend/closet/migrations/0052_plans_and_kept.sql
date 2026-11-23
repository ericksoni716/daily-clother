-- Dress for another day, and outfits you keep (closet/plans.py, closet/kept.py). Kept in the closet, so the demo has
-- its own and a backup takes them along.

-- An outfit kept for a day ahead: a plan, not a wear. One a day; a plan for a day that has passed unworn lapses.
CREATE TABLE day_plans (
  day        TEXT PRIMARY KEY,                -- YYYY-MM-DD, the computer's calendar
  pieces     TEXT NOT NULL,                   -- JSON: {base, mid, outer, bottom, shoes, accessories}, as a worn outfit's
  occasion   TEXT,                            -- what it was chosen for, when it was chosen on Today
  mood       TEXT,
  created_at TEXT NOT NULL,                   -- UTC
  updated_at TEXT NOT NULL
);

-- An outfit kept without wearing it, found under Worn. No piece is a foreign key: a piece that leaves the closet
-- stays part of the outfit, which says so.
CREATE TABLE kept_outfits (
  id         TEXT PRIMARY KEY,
  name       TEXT,                            -- given later, in place; null until then
  pieces     TEXT NOT NULL,                   -- JSON, as day_plans.pieces
  same       TEXT NOT NULL UNIQUE,            -- the pieces' ids, sorted and joined: the same pieces kept twice are one
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  removed_at TEXT                             -- set aside by Remove, so Undo can bring it back; null while kept
);
CREATE INDEX kept_outfits_created ON kept_outfits (created_at DESC);
