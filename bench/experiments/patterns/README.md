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
- Plaids that do not repeat (madras): `no_repeat` measures both band sequences whole, straightened, and redraws
  them at their true positions over the garment (one tile the garment's size). Quilting was tried and rejected
  for plaids: it breaks their lines.
- `sett.py`: earlier ways of measuring the bands (averaged strips; colours from crossings).
- `repeat2d.py`: the repeat over the whole garment (2-D autocorrelation) and the best-matching square.
- `stripes.py`: stripes. Which way they run; regular stripes folded onto one sharp repeat by reading the
  stripes' local position from the photo (complex demodulation at the stripe spacing, so nothing has to be
  joined), the repeat length chosen by how sharply it folds; yarn colours without the blends at stripe edges.
  Complex repeats (many stripes) are folded by matching each area against the whole repeat (`fold_by_match`);
  yarn colours are the clusters that form real stripes (a blend at an edge is only a sliver), and
  `balance_to_words` corrects the photo's lighting when Claude's colour words say the item has white or cream.
  Placed stripes (a polo's chest bands): `ground_stripes` measures the plain repeating ground in its own
  stretch of the garment (spacing from the fold; colours from the photo's extremes, since stripes 2 px wide
  blur together), and `compose_placed` draws every plain stretch with that crisp ground and the placed bands
  with their measured colours. The ground is also the collar's cloth (`Fill.trim_stripes` in the app's
  renderer), so a chest band never lands on the collar.
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

- `holes2.py`: background removal for patterned items. `see_through` measures how much of the garment's closed
  outline the model left out; above 20% (a plaid's checks, bold stripes), the second model (u2net) is asked
  as well and the two masks combined. On eight test shirts this turned a 22% solid plaid into 66% and a 28%
  multi-stripe into 41%, and left the other six untouched. Filling holes by size was tried and dropped: a
  plaid's checks join into one grid, and closing the mask filled the gaps between arms and body.
- Placement (`placed_from_landmarks`, and `Swatch.phase` / `Swatch.length_frac` in the app's renderer): the
  flattened repeat is lined up on the button line, PLACE_AT of the way from neck to hem, and sized against the
  neck-to-hem length; the landmarks come from Claude (`landmarks_prompt.md`).
