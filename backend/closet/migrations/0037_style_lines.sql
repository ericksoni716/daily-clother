-- Your style as remembered lines, the style conversation and the questions the stylist cannot infer (DECISIONS
-- "Style through conversation", step 8; closet/styleprofile.py, closet/stylechat.py, closet/stylequestions.py).
--
-- Each line of the style profile is a row, with where it came from and when, so Settings can show "You said this on
-- 12 Nov" beside it and a line can be removed, put back or changed on its own. The profile text the stylist reads is
-- still the newest row of `style_profile`: every change to the lines writes a new version there, built from the lines
-- in order, so the history is kept as before and what the stylist reads is unchanged until the owner changes a line.
CREATE TABLE style_lines (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  position   INTEGER NOT NULL,           -- the order of the lines in the text
  gap        INTEGER NOT NULL DEFAULT 0, -- empty lines before this one in the text, so the text is built back exactly
  text       TEXT NOT NULL,              -- the line as written, with its "- " when it has one
  source     TEXT NOT NULL CHECK (source IN ('start', 'owner', 'talk', 'question')),
                                         -- start: one of the starting lines; owner: written by the owner; talk: offered
                                         -- by Claude in a conversation and kept by the owner; question: the owner's
                                         -- answer to one of the questions
  created_at TEXT NOT NULL,              -- UTC: when the line was written, or last changed by the owner
  removed_at TEXT                        -- UTC: when it was removed (it can be put back); NULL: in the profile
);
CREATE INDEX style_lines_position ON style_lines (removed_at, position);

-- The profile in force is carried over line by line. Each line that is not empty becomes a row; where it came from is
-- read from the history: the oldest version of the unbroken run of versions, up to the one in force, that has the
-- line in it. A line written by Claude is one the owner kept from the conversation on Today, and a line that is one of
-- the starting lines is marked as one. An empty profile (the starting one in force) has no rows: the starting lines are
-- shown from the program, as before.
WITH RECURSIVE
  newest AS (SELECT id, text FROM style_profile ORDER BY id DESC LIMIT 1),
  split (n, line, rest) AS (
    SELECT 0, NULL, (SELECT text FROM newest) || char(10) WHERE (SELECT text FROM newest) != ''
    UNION ALL
    SELECT n + 1, substr(rest, 1, instr(rest, char(10)) - 1), substr(rest, instr(rest, char(10)) + 1)
    FROM split WHERE rest != ''
  ),
  lines AS (
    SELECT n, line, (n - 1 - coalesce((SELECT max(b.n) FROM split b WHERE b.n < a.n AND b.n > 0
                                       AND trim(b.line, ' ' || char(9)) != ''), 0)) AS gap
    FROM split a WHERE n > 0 AND trim(line, ' ' || char(9)) != ''
  ),
  since AS (
    SELECT n, line, gap, (SELECT min(v.id) FROM style_profile v WHERE v.id > coalesce(
             (SELECT max(w.id) FROM style_profile w
              WHERE instr(char(10) || w.text || char(10), char(10) || line || char(10)) = 0), 0)) AS version
    FROM lines
  )
INSERT INTO style_lines (position, gap, text, source, created_at)
SELECT s.n, s.gap, s.line,
       CASE WHEN s.line IN ('- I carry an umbrella, so a rain jacket is never a must. When it really rains, favour one if it suits the outfit, and boots or shoes that can take water.',
                            '- Nothing else is written here yet: go by the guide and by what I have worn and said about it.')
            THEN 'start' WHEN v.source = 'claude' THEN 'talk' ELSE 'owner' END,
       v.created_at
FROM since s JOIN style_profile v ON v.id = s.version
ORDER BY s.n;

-- The style conversation (Settings, Your style, "Talk to Claude about your style"): the owner writes about how they
-- dress, not about a day's outfits. Each message is a row, answered in the background like a message on Today: Claude's
-- words back are `reply`, and what it offers to keep as lines of the profile is `remember`, with whether the owner kept
-- each. The day's rows, oldest first, are the conversation, told to Claude with each new message.
CREATE TABLE style_talk (
  id            TEXT PRIMARY KEY,
  day           TEXT NOT NULL,           -- YYYY-MM-DD, the computer's date
  said          TEXT NOT NULL,           -- the owner's message
  state         TEXT NOT NULL CHECK (state IN ('working', 'ready', 'failed')),
  reply         TEXT,                    -- Claude's words back to the owner
  remember      TEXT,                    -- JSON [{kind: "style", item_id: null, name: null, text, state, line_id}]
  error         TEXT,                    -- when failed: unreachable, limit, answer, error or lost
  route         TEXT,                    -- plan or api
  model         TEXT,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  seconds       REAL,                    -- how long Claude took
  asked_at      REAL NOT NULL,           -- unix seconds, to tell a message that was lost
  created_at    TEXT NOT NULL,
  finished_at   TEXT
);
CREATE INDEX style_talk_day ON style_talk (day, created_at);

-- The questions the stylist cannot infer from the clothes and the wears (closet/stylequestions.py): each answered or
-- skipped once, so it is never asked again. An answer becomes a line of the profile (`line_id`, source 'question').
CREATE TABLE style_questions (
  id      TEXT PRIMARY KEY,              -- the question's id in stylequestions.QUESTIONS
  state   TEXT NOT NULL CHECK (state IN ('answered', 'skipped')),
  answer  TEXT,                          -- the owner's words, or the choice they tapped
  line_id INTEGER,                       -- the line it became; NULL when skipped
  at      TEXT NOT NULL                  -- UTC
);
