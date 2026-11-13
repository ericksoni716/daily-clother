-- Stop C: outfits remembered as worn together, and how they went.
-- The wear log stays the record of wears; an outfit only says which wears belonged together.

CREATE TABLE worn_outfits (
  id             TEXT PRIMARY KEY,
  worn_on        TEXT NOT NULL,   -- YYYY-MM-DD, the computer's local date
  recorded_by    TEXT NOT NULL CHECK (recorded_by IN ('today', 'hand')),
  low_c          REAL,            -- the day it was offered for (null when recorded by hand)
  high_c         REAL,
  rain           INTEGER,         -- 0 or 1
  occasion       TEXT,
  mood           TEXT,
  score          INTEGER,         -- what it was offered with (null when recorded by hand)
  reasons        TEXT NOT NULL DEFAULT '[]',   -- JSON list of sentences
  warnings       TEXT NOT NULL DEFAULT '[]',   -- JSON list of sentences
  rating         TEXT CHECK (rating IN ('loved', 'fine', 'not_again')),
  rating_reasons TEXT NOT NULL DEFAULT '[]',   -- JSON list from worn.REASONS
  rating_note    TEXT,            -- only with the reason 'other'
  rated_at       TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX worn_outfits_newest ON worn_outfits (worn_on, created_at, id);

CREATE TABLE worn_outfit_pieces (
  outfit_id  TEXT NOT NULL REFERENCES worn_outfits (id) ON DELETE CASCADE,
  item_id    TEXT NOT NULL,              -- no cascade: a deleted item stays part of the outfit as it was worn
  place      TEXT NOT NULL CHECK (place IN ('base', 'mid', 'outer', 'bottom', 'shoes', 'accessory')),
  position   INTEGER NOT NULL,          -- order among the accessories (0 for the others)
  added_wear INTEGER NOT NULL DEFAULT 0, -- 1 when recording this outfit made the item's wear for that day
  PRIMARY KEY (outfit_id, item_id)
);
CREATE INDEX worn_outfit_pieces_item ON worn_outfit_pieces (item_id);

-- An outfit none of whose pieces is left in the closet goes with the last one deleted.
CREATE TRIGGER worn_outfits_last_piece_deleted AFTER DELETE ON items
BEGIN
  DELETE FROM worn_outfits
   WHERE id IN (SELECT outfit_id FROM worn_outfit_pieces WHERE item_id = OLD.id)
     AND NOT EXISTS (SELECT 1 FROM worn_outfit_pieces p JOIN items i ON i.id = p.item_id
                      WHERE p.outfit_id = worn_outfits.id);
END;
