-- A traced shoe's front view on the outfit figure (#205, shoe tracing stage 2c): which of its two front drawings
-- the owner chose, and what its second photo, from the front, showed (closet/drawing/frontlook.py).
ALTER TABLE items ADD COLUMN shoe_front TEXT;   -- NULL: the default (photo with a front photo, else shape) | shape | photo
ALTER TABLE items ADD COLUMN front_look TEXT;   -- JSON, frontshoe.FrontLook: the front photo's colours, laces and marks
