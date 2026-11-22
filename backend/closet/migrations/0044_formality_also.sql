-- Formality between two levels (22 November, the owner's request: "a penny loafer could be either"). An item keeps
-- its formality, the level it sits at most, and may also count as the level right above or below it: null for one
-- level, which is most items. Who set it is kept with the formality's own: a formality the owner set is theirs whole,
-- so describing the item again never adds a second level to it (closet/items.py, closet/tagjobs.py).
ALTER TABLE items ADD COLUMN formality_also TEXT;
