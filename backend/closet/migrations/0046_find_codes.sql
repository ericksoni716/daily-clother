-- Checkout codes (23 November, the owner's request: "there are times where discounts are cart only, it'll say like 40%
-- off with code X, and i think we should include that kind of discount"). At most one code per find, with either a
-- percent or an amount off, where it came from and when it was last seen (closet/shop.py). The price with the code is
-- worked out, never typed. Every price point also keeps the price after the code it was seen with, and that code, so
-- a drop, price news and "within your price" count what you would pay at checkout. Null everywhere: no code.

ALTER TABLE finds ADD COLUMN code TEXT;            -- letters, digits, - and _, 3 to 30, upper-case
ALTER TABLE finds ADD COLUMN code_percent REAL;    -- 1 to 90; or null when the code takes an amount off
ALTER TABLE finds ADD COLUMN code_amount REAL;     -- in the find's currency, more than 0 and less than the price
ALTER TABLE finds ADD COLUMN code_by TEXT CHECK (code_by IN ('page', 'claude', 'you'));   -- who saw it, or typed it
ALTER TABLE finds ADD COLUMN code_seen_at TEXT;    -- UTC; the last time it was seen on the page, or saved by you
ALTER TABLE finds ADD COLUMN code_removed TEXT;    -- the last code you removed: not taken from the page or Claude again

ALTER TABLE find_prices ADD COLUMN with_code REAL; -- the price after the code then, rounded to cents; null: no code
ALTER TABLE find_prices ADD COLUMN code TEXT;      -- the code it was worked out with
