-- A shoe in one step on Add (16 November): the owner adds all of a shoe's photos at once, in any order, and once
-- Claude has sorted them into views the outer side (else the inner side) becomes the main photo when the first one
-- was not a side view (closet/shoeviews.py, `promote`). The main photo can now change without the item being
-- described again, so Claude's words on "the first image" of its description (how many shoes it shows and from
-- where, `shoes_in_photo` and `shoe_view`) must stay with the photo it saw first, not with whichever photo is the
-- main one now (closet/tracejobs.py, `told`).
ALTER TABLE items ADD COLUMN tag_photo_id TEXT;   -- the photo the stored description saw first; NULL: none of them
-- an item described before this: its main photo, when the description is not older than it (the rule `told` used)
UPDATE items SET tag_photo_id = (
  SELECT p.id FROM photos p WHERE p.item_id = items.id AND p.kind = 'front' AND p.created_at <= items.tagged_at
  ORDER BY p.created_at LIMIT 1)
WHERE tag_answer IS NOT NULL AND tagged_at IS NOT NULL;
