-- Give it an outing (closet/outing.py): the days Today offered an outfit built around a piece you like and had not
-- worn in a while, so the rhythm holds (one every few days, never the same piece twice running) and a reload offers the
-- same piece. Kept in the closet, so the demo has its own and a backup takes them along.
CREATE TABLE outings (
  day         TEXT PRIMARY KEY,                -- YYYY-MM-DD, the computer's calendar: one outing a day at most
  item_id     TEXT NOT NULL,                   -- not a foreign key: a piece that leaves the closet ends its outings
  since       TEXT NOT NULL,                   -- YYYY-MM-DD: the day it was last worn before, or added when never worn
  never_worn  INTEGER NOT NULL DEFAULT 0,      -- 1 when `since` is the day it was added
  turned_down INTEGER NOT NULL DEFAULT 0,      -- 1 once "Not this piece" was used on it that day
  created_at  TEXT NOT NULL                    -- UTC
);
