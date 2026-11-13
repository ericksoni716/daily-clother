CREATE TABLE trips (
    id TEXT PRIMARY KEY,
    choices TEXT NOT NULL,
    plan TEXT NOT NULL,
    checked TEXT NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
