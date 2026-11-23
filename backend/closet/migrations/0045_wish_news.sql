-- The wish page and price news (23 November, the owner's request: "how do i tell it to flag to me when the price
-- drops?"). When the owner last saw a wish's price news: set when they open the wish's page or dismiss the banner, so
-- the phone and the computer agree. A price that came down after this is news (closet/shop.py, `news`); null: never
-- seen, so a price that is down already is told once.
ALTER TABLE wishes ADD COLUMN news_seen_at TEXT;   -- UTC
