-- A shoe traced from its photo (#206, shoe tracing stage 2b): the traced shoe kept with the item, so its drawing is
-- the owner's shoe and not a template; why it fell back to the template when the photo could not be traced; and
-- the owner's fixes to it, kept apart so a new trace keeps them where they still fit (closet/tracejobs.py).
ALTER TABLE items ADD COLUMN trace TEXT;              -- JSON, closet/drawing/traced.py TracedShoe; NULL: not traced
ALTER TABLE items ADD COLUMN trace_version INTEGER;   -- tracejobs.TRACING_VERSION it was traced with; older ones are traced again
ALTER TABLE items ADD COLUMN trace_state TEXT;        -- NULL (not a shoe) | waiting | working | done | refused | failed
ALTER TABLE items ADD COLUMN trace_error TEXT;        -- why the drawing is not traced, in plain words
ALTER TABLE items ADD COLUMN trace_fixes TEXT;        -- JSON: the owner's colours for parts, marks removed or moved
ALTER TABLE items ADD COLUMN trace_plain INTEGER NOT NULL DEFAULT 0;   -- 1: the owner chose the plain drawing
ALTER TABLE photos ADD COLUMN view TEXT;              -- a shoe's second photo: front | top (kept for the front view)
