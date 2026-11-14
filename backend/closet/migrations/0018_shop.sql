-- Stop D: shopping for a wish. What Claude found in shops for a wish ("Find some"), each checked against the closet
-- with the "Would this work?" rules, and the price of each find every time it was looked at (closet/shop.py).
-- Nothing here is bought or opened by the program: links are only shown.

ALTER TABLE wishes ADD COLUMN price_min REAL;          -- the price range the owner set, in price_currency; null: none
ALTER TABLE wishes ADD COLUMN price_max REAL;
ALTER TABLE wishes ADD COLUMN price_currency TEXT;     -- 'USD', 'EUR'... (ISO 4217)
ALTER TABLE wishes ADD COLUMN found_at TEXT;           -- UTC; the last time Claude was asked to find some
ALTER TABLE wishes ADD COLUMN prices_checked_at TEXT;  -- UTC; the last time its finds' prices were looked at

CREATE TABLE finds (
  id          TEXT PRIMARY KEY,
  wish_id     TEXT NOT NULL REFERENCES wishes(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  shop        TEXT NOT NULL,
  url         TEXT NOT NULL,           -- the product's page (http or https only)
  image_url   TEXT,                    -- a picture of it on the shop's site, or null
  price       REAL,                    -- the latest price seen; null when the shop showed none
  currency    TEXT NOT NULL,           -- ISO 4217
  available   INTEGER NOT NULL DEFAULT 1,   -- 0: the last price check found it gone or sold out
  piece       TEXT NOT NULL,           -- JSON: its description in the closet's vocabulary (wouldwork.parse_piece)
  verdict     TEXT,                    -- JSON: {verdict, verdict_words, reasons, checked_at}: "Would this work?"
  found_at    TEXT NOT NULL,           -- UTC
  updated_at  TEXT NOT NULL,
  UNIQUE (wish_id, url)
);
CREATE INDEX finds_wish ON finds(wish_id, found_at);

CREATE TABLE find_prices (
  id        INTEGER PRIMARY KEY,
  find_id   TEXT NOT NULL REFERENCES finds(id) ON DELETE CASCADE,
  at        TEXT NOT NULL,             -- UTC
  price     REAL,                      -- null: no price shown (gone, sold out, or not found)
  currency  TEXT NOT NULL,
  available INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX find_prices_find ON find_prices(find_id, at);
