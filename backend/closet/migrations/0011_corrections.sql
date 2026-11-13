-- Corrections: the owner's own details, kept apart from Claude's answer, and the history of every change to a description.
-- Numbered 0011: 0010 went to the worn outfits, which merged first.
-- A migration numbered below a closet's current version would never run.

ALTER TABLE items ADD COLUMN own_details TEXT;   -- JSON object: detail -> the owner's value, laid over the answer's details when
                                                 -- drawn (a feature flag such as v_insert is "yes" or "no"). Never touched by tagging.

CREATE TABLE changes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  at         TEXT NOT NULL,                              -- when (UTC)
  by         TEXT NOT NULL CHECK (by IN ('owner', 'claude')),
  kind       TEXT NOT NULL CHECK (kind IN ('answer', 'field', 'detail', 'sentence', 'undo')),
  parts      TEXT NOT NULL,                              -- JSON list: {target: field | detail | answer, name, before, after}
  sentence   TEXT,                                       -- the owner's words, for a correction by sentence
  drawing    TEXT,                                       -- JSON: the drawing before the change {svg, version, notes}, put back by an undo
  undoes     INTEGER REFERENCES changes (id) ON DELETE SET NULL,
  undone_by  INTEGER REFERENCES changes (id) ON DELETE SET NULL
);
CREATE INDEX changes_item ON changes (item_id, id);
