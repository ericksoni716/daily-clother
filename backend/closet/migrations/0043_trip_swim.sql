-- "Swimming or the beach" on a trip (closet/trips.py): swim trunks are packed, apart from the days' outfits, when it is
-- on. 1: on and 0: off, the owner's word, kept whatever the forecast; null: on by itself when a day of the trip is hot.
-- Trips saved before it follow the forecast the next time they are planned.
ALTER TABLE trips ADD COLUMN swim INTEGER;
