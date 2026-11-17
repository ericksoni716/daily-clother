-- Laundry that keeps itself (17 November, the owner: "maintaining what is in the laundry seems like a huge pain").
-- A worn piece goes in the laundry by itself once worn as often as "Before it needs washing" allows, and everything
-- in the laundry comes back clean on the owner's laundry day (closet/wears.py). To know which pieces a laundry day
-- washes, and which a removed wear should take back out, each piece in the laundry keeps when it went in and why.
ALTER TABLE items ADD COLUMN laundry_at TEXT;   -- when it last went in the laundry (UTC, as updated_at)
ALTER TABLE items ADD COLUMN laundry_by TEXT;   -- 'auto' (its wears reached the count) or 'owner' (put in by hand)
-- what is in the laundry now went in when it last changed, by the owner's hand
UPDATE items SET laundry_at = updated_at, laundry_by = 'owner' WHERE laundry = 'laundry';
