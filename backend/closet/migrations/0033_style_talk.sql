-- The conversation about the day's outfits (DECISIONS "Outfits chosen by Claude", step 3; closet/stylejobs.py).
-- A message the owner writes to Claude about the outfits on Today is a question of its own: a row of
-- `style_answers` with `said`. Claude's words back are `reply`, and what it offers to remember for other days is
-- `remember`, with whether the owner kept each. The day's rows with `said`, oldest first, are the conversation.
ALTER TABLE style_answers ADD COLUMN said TEXT;       -- the owner's message this row answers; NULL: a plain question
ALTER TABLE style_answers ADD COLUMN reply TEXT;      -- Claude's words back to the owner
ALTER TABLE style_answers ADD COLUMN remember TEXT;   -- JSON [{kind, item_id, name, text, state}]
