-- "On sale now" (23 November; BACKLOG "Finding clothes you might like", step 5): things marked down across shops that
-- suit the owner, a second kind of pick ('sale') on the "You might like" card (closet/picks.py), and the shops the owner
-- likes, where a sale look starts (closet/shops.py). Numbered 0050: 0049 is kept for another piece of work.

-- Shops you like (Settings, Everyday): up to 12 shop names or sites, as the owner wrote them, read by the sale look
-- as its first places to start and by nothing else. Kept in the closet, so the demo has its own and a backup takes them.
CREATE TABLE shops (
  id        INTEGER PRIMARY KEY,
  name      TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- a shop's name or its site, cleaned (closet/shops.py)
  added_at  TEXT NOT NULL                          -- UTC
);

-- Which kind of look it was: 'taste' (every look before this one) or 'sale'. The weekly look of one kind is never
-- made on the same day as the other.
ALTER TABLE pick_looks ADD COLUMN kind TEXT NOT NULL DEFAULT 'taste';

-- A sale pick: who read its price before the markdown ('page': Nines, from the page's own data; 'claude': only Claude
-- saw it), whether the page says the owner's size is in stock (1, else null), when its page was last read again on
-- the daily round, how many of those reads in a row could not read it, and when the sale was found over (it then
-- leaves the card). Null for a taste pick.
ALTER TABLE picks ADD COLUMN before_by TEXT;
ALTER TABLE picks ADD COLUMN in_stock INTEGER;
ALTER TABLE picks ADD COLUMN checked_at TEXT;
ALTER TABLE picks ADD COLUMN misses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE picks ADD COLUMN ended_at TEXT;
