-- The boxes Claude found in a photo of several pieces, as it found them (closet/sources.py, DECISIONS "Several items
-- from one photo"), kept beside the boxes the owner checks so a box removed or reshaped by a slip can be put back as
-- Claude found it without asking Claude again. JSON like `boxes`; null when Claude found none, or for photos whose
-- boxes were found before this was kept (their first answer is gone).
ALTER TABLE source_photos ADD COLUMN found_boxes TEXT;
