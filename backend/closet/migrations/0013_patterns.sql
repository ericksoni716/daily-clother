-- An item's pattern measured from its photo (closet/patterns), so the drawing can show its stripes, plaid or
-- print; and the garment's landmarks (buttons, neck, hem, shoulders, underarms) Claude gave for placing it.
ALTER TABLE items ADD COLUMN pattern_fill TEXT;      -- JSON, see closet/drawing/stored.py; NULL: drawn in its colour
ALTER TABLE items ADD COLUMN pattern_state TEXT;     -- NULL (nothing to measure) | waiting | working | done | failed
ALTER TABLE items ADD COLUMN pattern_error TEXT;     -- why it failed, in plain words
ALTER TABLE items ADD COLUMN landmarks TEXT;         -- JSON as Claude gave them, in cutout pixels
