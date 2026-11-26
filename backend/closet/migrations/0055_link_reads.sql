-- A link read, described and drawn properly (closet/shop.py; the owner's report of 26 November).
-- unread_at: the time of the last check of a find's page, by Nines or by Claude, that got no price from it (turned away,
--   gone, or Claude could not read it). The last price stands; the next check that reads a price clears it. Null for
--   every find kept before this: their last check is taken to have read what they show.
-- read_asked: the fingerprint of the question that asked Claude to read a link's page whole and got no name back, so
--   the daily round does not ask the same again (a Check now by the owner does).
-- kind_asked_at: when Claude was last asked to describe the find with its kind of garment. A link described before
--   kinds were asked for (null) is described once more at its next reading.
ALTER TABLE finds ADD COLUMN unread_at TEXT;
ALTER TABLE finds ADD COLUMN read_asked TEXT;
ALTER TABLE finds ADD COLUMN kind_asked_at TEXT;
