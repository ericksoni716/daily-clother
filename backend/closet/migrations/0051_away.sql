-- Where a piece is (23 November; BACKLOG "Where a piece is"): in the closet, or away at the cleaner's, at the tailor's
-- or lent out (closet/away.py). Away is where it is, not its condition: a piece can need mending and be at the tailor's.
-- An away piece is left out of outfits and trips like one in the laundry, and still counted as owned.
ALTER TABLE items ADD COLUMN away TEXT CHECK (away IN ('cleaner', 'tailor', 'lent'));   -- null: in the closet
ALTER TABLE items ADD COLUMN away_since TEXT;   -- YYYY-MM-DD, the computer's local date it went
ALTER TABLE items ADD COLUMN away_until TEXT;   -- YYYY-MM-DD, the day the owner expects it back; null: not said
ALTER TABLE items ADD COLUMN away_note TEXT;    -- the owner's own few words ("for the hem"); never sent to Claude

-- When each piece went and came back, for its history, and what coming back changed, so the last return can be undone.
CREATE TABLE away_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id  TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  at       TEXT NOT NULL,                                       -- UTC
  event    TEXT NOT NULL CHECK (event IN ('went', 'back')),
  place    TEXT NOT NULL CHECK (place IN ('cleaner', 'tailor', 'lent')),
  by       TEXT NOT NULL DEFAULT 'owner' CHECK (by IN ('owner', 'wear')),   -- 'wear': it came back by being worn today
  undo     TEXT                                                 -- with 'back': JSON of the fields as they were before
);
CREATE INDEX away_log_item ON away_log (item_id, id);
