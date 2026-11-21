-- The owner's one-line correction of a shoe's side drawing (DECISIONS "Which drawing a note is about"): the owner says
-- whether a note is about the front drawing or the side drawing, and the note waits in `drawn_note` as before. Which one
-- it is about is kept beside it while it waits or is made (closet/shoedraw.py), so neither the note shown back to the
-- owner nor the note given to Claude carries a mark of it.
ALTER TABLE items ADD COLUMN drawn_note_about TEXT;   -- 'side' while a note about the side drawing waits or is made;
                                                      -- NULL otherwise (a note about the front, or no note)
