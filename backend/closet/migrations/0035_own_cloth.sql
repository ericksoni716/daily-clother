-- The owner's own words about the cloth and its lettering (DECISIONS "The cloth and its lettering, corrected in
-- the owner's words"): JSON {"surface": <a surface as the description gives it>, "lettering": [<lettering>, ...]},
-- either key absent when the owner has not changed it. Laid over Claude's answer when the item is drawn and measured,
-- and kept when the item is described again, as `own_details` are. NULL when the owner has changed neither.
ALTER TABLE items ADD COLUMN own_cloth TEXT;
