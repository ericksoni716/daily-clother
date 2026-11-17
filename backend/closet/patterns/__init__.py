"""Measuring an item's pattern from its own photo (a cutout on a transparent background).

- `flatten`: a crumpled plaid put back into one straight, sharp repeat.
- `straighten`: a plaid photographed at an angle, turned or over a slope, made regular from its own lines first.
- `plaid`:   a plaid's repeat size, where it sits on the garment (from Claude's landmarks), and plaids that do
             not repeat (madras).
- `stripes`: which way stripes run, their colours and widths, placed bands (a polo's chest stripe) and
             whether they carry on onto the sleeves.
- `prints`:  florals and other irregular prints, rebuilt by quilting squares of the garment's own cloth.
- `masks`:   how see-through a background-removal mask left a patterned garment, one mask from two models'
             masks (bedding left out), and a cutout of two surfaces split into the two.

These were chosen from the experiments in `bench/experiments/patterns/`. Everything here uses OpenCV; the
drawing code (`closet.drawing`) never imports this package, so drawing an item stays free of OpenCV.
"""
