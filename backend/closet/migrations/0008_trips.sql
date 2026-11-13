-- Trip packing: a trip, its weather, the packing plan chosen for it and what has been packed.
-- Numbered 0008, the next free number after 0007: a migration numbered below a closet's current version would never run.

CREATE TABLE trips (
  id            TEXT PRIMARY KEY,
  place         TEXT NOT NULL,               -- JSON {name, latitude, longitude, timezone}
  first_day     TEXT NOT NULL,               -- YYYY-MM-DD
  last_day      TEXT NOT NULL,               -- YYYY-MM-DD
  occasion      TEXT NOT NULL DEFAULT 'casual',
  day_occasions TEXT NOT NULL DEFAULT '{}',  -- JSON {date: occasion} for the days that differ
  can_wash      INTEGER NOT NULL DEFAULT 0,  -- "I can wash there"
  leave_out     TEXT NOT NULL DEFAULT '[]',  -- JSON list of item ids swapped out ("not this one")
  pinned        TEXT NOT NULL DEFAULT '[]',  -- JSON list of item ids pinned in ("I want to take this")
  weather       TEXT NOT NULL DEFAULT '[]',  -- JSON list of days the plan was made for (closet/tripweather.py)
  weather_message TEXT,                      -- why some days had no weather, when they did not
  plan          TEXT NOT NULL,               -- JSON: the plan as closet/trips.py made it
  packed        TEXT NOT NULL DEFAULT '[]',  -- JSON list of lines ticked as packed ("item:<id>", "basic:<key>")
  planned_at    TEXT NOT NULL,               -- when the plan was last worked out (UTC)
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX trips_first_day ON trips (first_day);
