-- How the owner dresses, kept for Claude choosing the outfits (17 November, DECISIONS "Outfits chosen by Claude",
-- step 2). Two things the stylist reads (closet/styling.py) and the owner writes in their own words:
-- the note on a piece about how they wear it (the item page, "How I wear it"), beside Notes and Fit notes because
-- the stylist is told which is which;
ALTER TABLE items ADD COLUMN wear_notes TEXT;   -- how the owner wears the piece; NULL: nothing written
-- and their style profile (Settings, "Your style"). Every save adds a row: the newest is the profile in force, the
-- older ones its history (closet/styleprofile.py). An empty text is the starting profile (styling.DEFAULT_PROFILE).
-- `source` says who wrote it: the owner, or (in a later step) Claude proposing a change the owner accepted.
CREATE TABLE style_profile (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  text       TEXT NOT NULL,
  source     TEXT NOT NULL CHECK (source IN ('owner', 'claude')),
  created_at TEXT NOT NULL      -- UTC, as items.updated_at
);
