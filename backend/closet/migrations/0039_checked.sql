-- When the owner last went through an item's essentials: what it is, its name, its brand and its price (DECISIONS
-- "The item page reordered, and every new item checked once"). Set by "That's right" in the review and by changing the
-- name, the kind, the brand or the price on the item page. An item never checked is offered in the review with those
-- Claude was unsure of (closet/review.py). Items kept before this count as checked, so only items added from now on
-- are offered: a closet of a hundred pieces does not wake up to "100 to check".
ALTER TABLE items ADD COLUMN checked_at TEXT;   -- NULL: added and not checked by the owner yet
UPDATE items SET checked_at = coalesce(updated_at, created_at);
