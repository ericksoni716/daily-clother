-- Who said a sale pick's "Your size is in stock" (closet/picks.py, `check_sale`): 'page' when the page Nines read listed
-- the owner's size in stock, 'claude' when only Claude said so; null when nobody said, and for a pick kept before this
-- (taken as Claude's word, as it was read before). When the page stops saying it on the daily round, a word that was
-- only the page's is no longer said; Claude's still stands (the second logic review, 24 November).
ALTER TABLE picks ADD COLUMN in_stock_by TEXT;
