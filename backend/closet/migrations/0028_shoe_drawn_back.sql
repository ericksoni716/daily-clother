-- The owner's one-line correction of a shoe's drawing (shoes drawn from understanding, step E): the note is queued for
-- the shoe drawing worker, Claude changes only what it asks and checks the change against the photos, and the drawing
-- before is kept so the owner can go back to it in one tap (closet/shoedraw.py, closet/tagger/shoedrawing.py). A new
-- drawing ("Draw again") keeps the one before the same way. drawn_state gains `correcting` (a correction being made;
-- one waiting is `waiting` with its note).
ALTER TABLE items ADD COLUMN drawn_prev TEXT;   -- JSON, as `drawn`: the drawing before the last change (one level
                                                -- only; going back swaps the two); NULL: none
ALTER TABLE items ADD COLUMN drawn_note TEXT;   -- the owner's note while its correction waits or is made; NULL otherwise
