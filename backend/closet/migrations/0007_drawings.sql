-- The drawing in the app, part 2: every item gets its drawing, kept up to date.
-- Numbered 0007, after the tagging migration 0006: a migration numbered below a closet's current version would never run.

ALTER TABLE items ADD COLUMN illustration_version INTEGER;  -- closet/drawing DRAWING_VERSION the drawing was made with (also when there is
                                                            -- nothing to draw); null: not drawn yet. Older ones are drawn again when asked for.
ALTER TABLE items ADD COLUMN illustration_notes TEXT;       -- JSON list: what the drawing leaves out or shows only roughly, in plain words

-- The only drawings so far are the demo closet's, made in advance by tools/make_demo.py with the drawing code of version 1.
UPDATE items SET illustration_version = 1 WHERE illustration_svg IS NOT NULL;
