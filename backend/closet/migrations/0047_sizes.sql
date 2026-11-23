-- Your sizes (23 November; BACKLOG "Finding clothes you might like", step 3): the owner's usual size for each kind of
-- piece, as they would say it ("M", "32x32", "10.5 US", "40R"), and a brand's own where it fits differently. Read by
-- "Find some" (closet/aboutyou.py) and kept in Settings, Everyday (closet/sizes.py says the kinds and the limits).
-- One row per kind and brand; `brand` is '' for the usual size. Kept in the closet, so the demo has its own and a
-- backup takes it along. Number 0046 is kept for another piece of work.
CREATE TABLE sizes (
  kind       TEXT NOT NULL,                          -- closet/sizes.py, KINDS: tops, knitwear, trousers, jackets, shoes
  brand      TEXT NOT NULL DEFAULT '' COLLATE NOCASE, -- '' for the usual size; else the brand, as the owner wrote it
  size       TEXT NOT NULL,
  updated_at TEXT NOT NULL,                          -- UTC
  PRIMARY KEY (kind, brand)
);
