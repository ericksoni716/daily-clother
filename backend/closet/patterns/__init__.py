"""Measuring an item's pattern from its own photo (a cutout on a transparent background).

- `flatten`: a crumpled plaid put back into one straight, sharp repeat.
- `straighten`: a plaid photographed at an angle, turned or over a slope, made regular from its own lines first.
- `plaid`:   a plaid's repeat size, where it sits on the garment (from Claude's landmarks), and plaids that do
             not repeat (madras).
- `stripes`: which way stripes run, their colours and widths, placed bands (a polo's chest stripe) and
             whether they carry on onto the sleeves.
- `prints`:  florals and other irregular prints, rebuilt by quilting squares of the garment's own cloth.
- `described`: a plaid drawn from Claude's description of its bands instead of measured from the photo; the
             app uses it through `surface`, which turns the description's surface into a kept pattern.
- `masks`:   how see-through a background-removal mask left a patterned garment, one mask from two models'
             masks (bedding left out), and a cutout of two surfaces split into the two.

These were chosen from the experiments in `bench/experiments/patterns/` (no longer in the repository; in its git history). Everything here uses OpenCV; the
drawing code (`closet.drawing`) never imports this package. The drawing code imports OpenCV itself only inside the
functions that read a photo (shoe tracing, the fills measured from a cutout), so drawing an item from its tags
needs none.
"""
