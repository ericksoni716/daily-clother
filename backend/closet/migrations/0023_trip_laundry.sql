-- Laundry on a trip: on one day of the trip, or every so many days (closet/trips.py). Replaces "I can wash there":
-- a trip saved with it keeps laundry every 3 days, which packs what four days need as before. `can_wash` stays
-- in the table but is no longer read.
ALTER TABLE trips ADD COLUMN laundry TEXT;   -- JSON {"day": 4} or {"every": 3}; null: no laundry on the trip
UPDATE trips SET laundry = '{"every": 3}' WHERE can_wash = 1;
