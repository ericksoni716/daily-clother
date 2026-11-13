# Pattern fills: work in progress

Experiments towards drawing an item's pattern from its own photo (the owner asked for it; it was in the
original spec and fell out when the drawing moved into the app). Not used by the app yet. No photos are kept
here: run them against cutouts in `bench/private/` (git-ignored).

- `dewarp.py`, `match.py`: flatten a crumpled plaid. Measure, area by area, how far the plaid is shifted
  against a reference repeat (normalised matching, to a tenth of a pixel), join the shifts into one map,
  and put every garment pixel back into one straight repeat. `test_dewarp.py` checks it on a made-up
  crumpled plaid where the answer is known.
- `plaid_pipeline.py`: find the repeat, flatten, then (optionally) turn the straight repeat into crisp cells
  between sharp colour edges. The flattened repeat itself proved the most faithful fill on the owner's photos.
- Matching drops near-ties (soft or nearly symmetric plaids), and areas are joined all at once (least-squares
  unwrapping); a patch is only joined if it sits on the same cloth (a shirt's two fronts are separate cloth).
- `sett.py`: earlier ways of measuring the bands (averaged strips; colours from crossings).
- `repeat2d.py`: the repeat over the whole garment (2-D autocorrelation) and the best-matching square.
- `stripes.py`: stripes. Which way they run; regular stripes folded onto one sharp repeat by reading the
  stripes' local position from the photo (complex demodulation at the stripe spacing, so nothing has to be
  joined), the repeat length chosen by how sharply it folds; yarn colours without the blends at stripe edges.
  Complex repeats (many stripes) are folded by matching each area against the whole repeat (`fold_by_match`);
  yarn colours are the clusters that form real stripes (a blend at an edge is only a sliver), and
  `balance_to_words` corrects the photo's lighting when Claude's colour words say the item has white or cream.
  Stripes with no repeat (a placed chest band) use the straightened sequence across the whole garment, laid
  out as fractions of the garment so each stripe lands where it really is.
- `quilt.py`: florals and other irregular prints, by image quilting from the whole garment; `quilt_garment`
  first turns the garment upright and evens out the light.
- `cv2shim.py`: the numpy/Pillow stand-in for OpenCV used to compare the two (OpenCV is kept: the owner chose
  quality over size).

Note: OpenCV 5's `cv2.phaseCorrelate` overwrites its first argument; `match.py` uses `matchTemplate`, which
was also far more accurate here.

Found on the way: the app's default background-removal model (isnet-general-use) treats a plaid's dark
squares as background, so a plaid item's cutout is see-through in the shape of its own pattern; u2net keeps
it solid. To be fixed in the app (holes inside the garment's outline must never be removed).
