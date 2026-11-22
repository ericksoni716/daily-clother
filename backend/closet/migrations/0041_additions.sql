-- What Claude drew onto a garment's drawing at the owner's word (closet/additions.py, DECISIONS "Claude adds to a
-- garment's drawing"): parts laid over the template's own, kept with the item as JSON, with the additions before the
-- last change (one level, to go back to) and the owner's line while Claude draws it.
ALTER TABLE items ADD COLUMN additions TEXT;         -- {"parts": [...], "notes": [...], "said", "at", ...}; NULL: none
ALTER TABLE items ADD COLUMN additions_prev TEXT;    -- the additions before the last change, the same shape
                                                     -- ({"parts": []} when there were none); NULL: nothing to go back to
ALTER TABLE items ADD COLUMN additions_state TEXT;   -- 'drawing' while Claude draws the owner's line; 'failed' when it
                                                     -- could not; 'said' when Claude answered without drawing; NULL: idle
ALTER TABLE items ADD COLUMN additions_job TEXT;     -- {"note", "message", "at"}: the line and what became of it
