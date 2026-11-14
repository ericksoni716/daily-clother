"""Drawing a garment from its tags: the parametric shapes, the renderer and the fills.

Moved here from the bench so the app and the bench share one copy. The bench's
`closet_bench.templates`, `illustrate` and `fills` are these same modules under
their old names. `item` is what the app calls: an item's stored tagger answer,
or just its coarse fields, in; the SVG out.

OpenCV is imported only inside the functions that read a photo (the bench's
"traced" style and the fills measured from a cutout), so the app's program
draws from tags without it.
"""

# Raised whenever a template, the renderer or the fills change what a drawing looks like. The app keeps the
# version each item was drawn with and draws an item again, the first time it is asked for, when it is older.
# Regenerate the demo closet (`tools/make_demo.py`) in the same change: it records the version it was drawn with.
DRAWING_VERSION = 4
