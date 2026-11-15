-- A shoe drawn by Claude from its sorted photos (shoes drawn from understanding, step C): a feature sheet and a
-- drawing in a fixed frame, checked against the photos at most three times, kept with the item and drawn again only
-- when the owner asks (closet/shoedraw.py, closet/tagger/shoedrawing.py). A shoe is drawn once by itself, when its
-- photos are first sorted into views; nothing is drawn for the shoes kept before this until the owner asks.
ALTER TABLE items ADD COLUMN drawn TEXT;         -- JSON, shoedrawing.Drawn.to_json: left, right, sheet, rounds, seconds,
                                                 -- calls, tokens, cost_usd, route, made_at, photo_ids; NULL: never drawn
ALTER TABLE items ADD COLUMN drawn_state TEXT;   -- NULL: not asked for | waiting | drawing | done | failed
ALTER TABLE items ADD COLUMN drawn_error TEXT;   -- why it is not drawn, or what it waits for, in plain words
ALTER TABLE items ADD COLUMN drawn_attempts INTEGER NOT NULL DEFAULT 0;   -- tries that gave no usable drawing (at most 3)
