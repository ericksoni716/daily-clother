CREATE TABLE gap_choices (
    gap_id TEXT PRIMARY KEY,
    snapshot TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    hidden_reason TEXT CHECK (hidden_reason IN ('already_owned', 'not_my_style', 'too_expensive', 'other')),
    CHECK (hidden = 1 OR hidden_reason IS NULL)
);

CREATE TABLE wishes (
    id TEXT PRIMARY KEY,
    gap_id TEXT REFERENCES gap_choices(gap_id),
    name TEXT NOT NULL,
    look_for TEXT,
    details TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    bought_at TEXT
);

CREATE UNIQUE INDEX wishes_active_gap ON wishes(gap_id)
    WHERE gap_id IS NOT NULL AND bought_at IS NULL;
