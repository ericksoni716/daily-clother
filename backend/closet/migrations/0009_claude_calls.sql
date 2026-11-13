-- A record of every call to Claude, for the API key's monthly spending limit.
-- Only counts and money: never a photo, the prompt or an answer. Kept in the closet so it is in its backups;
-- only the real closet ever has rows (the demo closet is never sent to Claude).

CREATE TABLE claude_calls (
  id             INTEGER PRIMARY KEY,
  at             TEXT NOT NULL,                                 -- when the call came back (UTC)
  month          TEXT NOT NULL,                                 -- 'YYYY-MM', the calendar month in the computer's local time
  purpose        TEXT NOT NULL,                                 -- what for: 'tag_item' (describing an item)
  route          TEXT NOT NULL CHECK (route IN ('plan', 'api')),
  model          TEXT NOT NULL,
  input_tokens   INTEGER NOT NULL DEFAULT 0,                    -- as the API (or Claude Code) reported them
  output_tokens  INTEGER NOT NULL DEFAULT 0,
  cost_usd       REAL NOT NULL DEFAULT 0,                       -- from the price table; always 0 on the plan route
  prices_checked TEXT                                           -- the date the price table was written down
);
CREATE INDEX claude_calls_month ON claude_calls(month, route);
