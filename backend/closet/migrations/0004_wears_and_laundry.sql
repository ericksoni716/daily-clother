-- Stop C: what was worn when, and what is in the wash.

CREATE TABLE wears (
  item_id    TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  worn_on    TEXT NOT NULL,   -- YYYY-MM-DD, the computer's local date
  created_at TEXT NOT NULL,   -- when it was recorded (UTC)
  PRIMARY KEY (item_id, worn_on)
);
CREATE INDEX wears_worn_on ON wears (worn_on);

ALTER TABLE items ADD COLUMN laundry TEXT NOT NULL DEFAULT 'clean' CHECK (laundry IN ('clean', 'laundry'));
ALTER TABLE items ADD COLUMN wears_since_wash INTEGER NOT NULL DEFAULT 0;
ALTER TABLE items ADD COLUMN washed_at TEXT;  -- when it was last marked clean (UTC); wears recorded after it count since the wash

-- "In the laundry" is now the laundry state, not a place: location says where an item lives when it is clean.
-- Where an item in the laundry lives was never recorded, so it is left unset.
UPDATE items SET laundry = 'laundry', location = NULL WHERE location = 'laundry';
