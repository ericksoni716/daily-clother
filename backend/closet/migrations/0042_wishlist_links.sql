-- Wishlist links (22 November, the owner's request): a product's page the owner sends is kept as a find of a wish, and
-- its price is read from the page itself before Claude is asked (closet/shop.py, closet/productpage.py). The finds
-- Claude found keep 0 and null here and are checked as before.

ALTER TABLE finds ADD COLUMN link INTEGER NOT NULL DEFAULT 0;   -- 1: sent by the owner as a link; 0: found by Claude
ALTER TABLE finds ADD COLUMN read_at TEXT;    -- UTC; the last time Nines read the page itself (a link only), whatever it found
ALTER TABLE finds ADD COLUMN read_by TEXT CHECK (read_by IN ('page', 'claude'));   -- how the latest price was read; null: as found
