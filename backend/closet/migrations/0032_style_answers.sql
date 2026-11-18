-- Claude's outfits for a day (DECISIONS "Outfits chosen by Claude", step 2; closet/stylejobs.py). One row for each
-- question asked: while Claude is choosing it is 'working', then 'ready' with the outfits that can be worn, or
-- 'failed' with why. Today reads the newest row for the day and the owner's choices (`key`), so the same choices
-- are answered at once for the rest of the day, and a row is also the record of what Claude was asked and gave.
CREATE TABLE style_answers (
  id            TEXT PRIMARY KEY,
  day           TEXT NOT NULL,                 -- YYYY-MM-DD, the computer's date
  key           TEXT NOT NULL,                 -- a hash of the choices and the owner's words the answer is for
  state         TEXT NOT NULL CHECK (state IN ('working', 'ready', 'failed')),
  dressed       TEXT NOT NULL,                 -- JSON {low_c, high_c, rain}: the day it was asked for
  outfits       TEXT,                          -- JSON: the outfits kept, in the engine's shape, with by "claude"
  read          TEXT,                          -- Claude's line on what about the day shaped the choices
  problems      TEXT,                          -- JSON: a sentence for each outfit left out
  error         TEXT,                          -- when failed: unreachable, limit, answer, error or lost
  route         TEXT,                          -- plan or api
  model         TEXT,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  seconds       REAL,                          -- how long Claude took
  asked_at      REAL NOT NULL,                 -- unix seconds, to tell a question that was lost or may be retried
  created_at    TEXT NOT NULL,
  finished_at   TEXT
);
CREATE INDEX style_answers_day_key ON style_answers (day, key, created_at);
