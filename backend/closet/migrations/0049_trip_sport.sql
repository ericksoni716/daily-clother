-- Tennis or golf on a trip (closet/trips.py, `Options.sport`): a pair of the matching shoes is packed beside the days.
-- A JSON list of the sports, such as '["tennis"]'; null for none, as every trip saved before it.
ALTER TABLE trips ADD COLUMN sport TEXT;
