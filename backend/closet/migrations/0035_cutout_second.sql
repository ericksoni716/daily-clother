-- Whether the second background model (u2net) was there to be asked when a photo's cutout was made (closet/jobs.py,
-- DECISIONS "Background removal"). 1: it was, or the cutout has been looked at since it came and it would not
-- change it; 0: it was not (still downloading, or its download failed); NULL: made before this was recorded.
-- Once the second model is ready, a front photo's cutout that is not 1 is looked at, and made again when the
-- second model would change it: see-through in the shape of its own pattern, or keeping what the garment lies on.
ALTER TABLE photos ADD COLUMN cutout_second INTEGER;
