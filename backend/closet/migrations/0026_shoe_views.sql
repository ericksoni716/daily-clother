-- A shoe's photos sorted into views by Claude (shoes drawn from understanding, step B): a shoe has its main photo
-- and up to five more, in any order, and one call says which view each shows, so the owner never has to; the
-- owner is asked only when the outer and inner side cannot be told apart and it matters (closet/shoeviews.py).
-- photos.view (0024) keeps front | top and gains outer (outer side), inner (inner side), back (heel towards the
-- camera), sole and other; front is the toe towards the camera, top from above. The main photo gets a view too.
ALTER TABLE photos ADD COLUMN view_sure INTEGER;   -- 1: sure, 0: unsure, NULL: not sorted
ALTER TABLE photos ADD COLUMN view_by TEXT;        -- who said the view: model | owner; NULL: not sorted
ALTER TABLE items ADD COLUMN views_state TEXT;     -- NULL: nothing to sort | waiting | sorting | asking | sorted | failed
ALTER TABLE items ADD COLUMN views_error TEXT;     -- why the photos are not sorted, or what they wait for, in plain words
ALTER TABLE items ADD COLUMN views_attempts INTEGER NOT NULL DEFAULT 0;   -- tries that gave no usable answer (at most 3)
ALTER TABLE items ADD COLUMN sides_differ INTEGER; -- 1: the outer and inner sides look different; 0: alike; NULL: not known
-- the second photos kept before this were named by the owner
UPDATE photos SET view_by = 'owner', view_sure = 1 WHERE view IS NOT NULL;
