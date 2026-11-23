-- "You might like" (23 November; BACKLOG "Finding clothes you might like", step 4): things the owner might like,
-- found by Claude from their taste rather than from a gap, three at a time on the Wardrobe (closet/picks.py).
-- Kept in the closet, so the demo has its own (it never searches) and a backup takes them along.

-- Every product ever shown, and what became of it. A product's page is kept once whatever became of it, so the same
-- address is never shown twice, and what was turned down is told to the next search.
CREATE TABLE picks (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL DEFAULT 'taste',   -- 'taste': chosen from what the owner wears and loves; step 5 adds 'sale'
  source     TEXT NOT NULL,                   -- how the look was started: 'look' (Look now), 'weekly', 'more' (More like this)
  seed_id    TEXT,                            -- with 'more': the pick it was asked from
  look_id    TEXT NOT NULL,                   -- the look it was found in (pick_looks)
  rank       INTEGER NOT NULL DEFAULT 0,      -- its place among the look's picks, best first
  name       TEXT NOT NULL,
  shop       TEXT NOT NULL,
  url        TEXT NOT NULL UNIQUE,
  image_url  TEXT,
  price      REAL,                            -- as the shop showed it when found; null when it showed none
  price_before REAL,                          -- the price before a markdown, when the shop shows one (step 5); null here
  currency   TEXT NOT NULL,
  piece      TEXT NOT NULL,                   -- JSON: its description in the closet's words (wouldwork.parse_piece)
  verdict    TEXT NOT NULL,                   -- JSON: what the closet said of it when found (shop.judge)
  found_at   TEXT NOT NULL,                   -- UTC
  state      TEXT NOT NULL DEFAULT 'shown' CHECK (state IN ('shown', 'saved', 'refused')),
  state_at   TEXT,                            -- UTC: when it was saved or turned down
  wish_id    TEXT                             -- with 'saved': the wish made from it (not a foreign key: the wish may go)
);
CREATE INDEX picks_found ON picks (found_at DESC, rank);

-- Every look that asked Claude, with what came of it: when the next weekly look is due, and "nothing this week".
CREATE TABLE pick_looks (
  id        TEXT PRIMARY KEY,
  source    TEXT NOT NULL,                    -- 'look', 'weekly' or 'more'
  at        TEXT NOT NULL,                    -- UTC, when it finished
  found     INTEGER NOT NULL DEFAULT 0        -- picks kept from it
);

-- The one switch, and a line offered for Your style after a few "Not for me" alike.
CREATE TABLE pick_settings (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  weekly    INTEGER                           -- 1 on, 0 off; null: the default, on once the owner has tapped Look now
);
CREATE TABLE pick_offers (
  id        TEXT PRIMARY KEY,
  text      TEXT NOT NULL UNIQUE,             -- the line offered, in the owner's voice ("Nothing bright."); offered once
  said      TEXT NOT NULL,                    -- why, in a sentence ("You passed on three bright colours.")
  state     TEXT NOT NULL DEFAULT 'offered' CHECK (state IN ('offered', 'saved', 'dismissed')),
  line_id   INTEGER,                          -- with 'saved': the line of Your style it became (style_lines)
  at        TEXT NOT NULL
);
