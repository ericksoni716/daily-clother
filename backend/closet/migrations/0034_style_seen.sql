-- Claude's look at the day's outfits as drawn (DECISIONS "Outfits chosen by Claude", step 2, the look at the drawn
-- figure; closet/stylejobs.py). After choosing, Claude is shown each outfit drawn on the figure and keeps or
-- changes it. `seen` records that look for a row: JSON {saw, changed, seconds}, `saw` being Claude's sentence on
-- what the pictures showed and `changed` how many outfits it changed; NULL when no look was taken.
ALTER TABLE style_answers ADD COLUMN seen TEXT;
