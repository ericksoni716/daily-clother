# Pattern fills: work in progress

Experiments towards drawing an item's pattern from its own photo (the owner asked for it; it was in the
original spec and fell out when the drawing moved into the app). Not used by the app yet. No photos are kept
here: run them against cutouts in `bench/private/` (git-ignored).

- `dewarp.py`, `match.py`: flatten a crumpled plaid. Measure, area by area, how far the plaid is shifted
  against a reference repeat (normalised matching, to a tenth of a pixel), join the shifts into one map,
  and put every garment pixel back into one straight repeat. `test_dewarp.py` checks it on a made-up
  crumpled plaid where the answer is known.
- `plaid_pipeline.py`: find the repeat, flatten, then turn the straight repeat into crisp cells between sharp
  colour edges.
- `sett.py`: earlier ways of measuring the bands (averaged strips; colours from crossings).
- `repeat2d.py`: the repeat over the whole garment (2-D autocorrelation) and the best-matching square.
- `quilt.py`: florals and other irregular prints, by image quilting from the whole garment.
- `cv2shim.py`: the numpy/Pillow stand-in for OpenCV used to compare the two (OpenCV is kept: the owner chose
  quality over size).

Note: OpenCV 5's `cv2.phaseCorrelate` overwrites its first argument; `match.py` uses `matchTemplate`, which
was also far more accurate here.
