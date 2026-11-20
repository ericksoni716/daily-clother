# Bench

The shoe tracing bench: it tries other ways of tracing a shoe photo beside the
app's own, to decide how the app traces shoes. Also here, in `hardcases/`, the
seven open-licence photos the demo closet is made from (`tools/make_demo.py`;
credits in `hardcases/ATTRIBUTION.md`), which the browser tests use too.

```
cd bench
pip install -r requirements.txt

# Tracing shoe photos into the flat style (#192, stages 1 and 2a)
#    Side-on photos of one shoe each in private/shoes/ (git-ignored). Uses the
#    app's cut-out model when models/ has it (isnet-general-use.onnx; it is
#    never downloaded here), otherwise OpenCV's GrabCut.
#    Sheets are also saved as PNG when Chrome or Chromium is installed.
python -m closet_bench.trace_shoes --photos private/shoes
#    -> out/trace_shoes/index.html, shoe-NN.sheet.svg/.png and results.json
```

The phase 0 commands that once lived here (the illustration hard cases and the
tagging accuracy bench) are in the git history; `docs/PHASE0.md` has what they
found.

The shoe tracing bench tries six ways of tracing (k-means colours, mean-shift
then k-means, bilateral filter then k-means; two settings each) and puts them
side by side with the photo, the cut-out and today's template drawing, at item
size and at grid-tile size. Each trace is scored (outline overlap with the
cut-out, colour error, how many colours and paths, whether logos and stripes
survived) and the best approach overall is named. A quality gate says which
photos are too poor to trace and why (blurred, low contrast, not side-on, cut
off, more than one thing in the photo). To have the template drawn from the
shoe's tags, save its tagger answer beside the photo as `<photo name>.json`.
The gate also takes that answer's word on the photo: when its `details` say
`shoes_in_photo` is `pair` or `more`, or `shoe_view` is anything but `side`, the
photo is turned down for that reason (answers from before schema version 5 say
nothing about it).

The tracing itself is the app's (`backend/closet/drawing/trace.py`), so the
gate the sheets show is the app's gate. When the model's cut-out fails the gate,
GrabCut is tried before the photo is turned down; the sheet says which cut-outs
were tried. Each sheet also shows the traced shoe as the app stores it
(`backend/closet/drawing/traced.py`): each traced colour piece edged in the
colour of the part it is labelled with, the parts that have a piece of their own
outlined (dashed when inferred; the key says "in upper" for a part that is just
the shoe's base colour), the profile lines, laces, eyelets and stitching dotted, and the
marks numbered; and a "Pairs" column with the turned cut-out, a second sole
ringed where it shows beyond one end, and a second top edge drawn where it
runs inside the outline. These two pair checks only advise: they are listed
under the reasons as "advice" and never turn a photo down. At the end the command prints how many
photos passed and how many were turned down for each reason (also in
`index.html`), and `results.json` holds each shoe's traced data.

`private/`, `out/` and `models/` are git-ignored, and the bench prints item
numbers only, never file names.

## What is where

| File | Purpose |
|---|---|
| `closet_bench/trace_shoes.py` | The command above (the shoe tracing and its gate live in `backend/closet/drawing/trace.py` and `traced.py`) |
| `closet_bench/cutout.py` | Background removal with ONNX models, crop, WebP cutout, for the command above (the app's own is `backend/closet/cutout.py`) |
| `closet_bench/fills.py`, `illustrate.py` | The drawing's modules (`backend/closet/drawing/`) under their old names, so the command's imports work unchanged |
| `hardcases/` | The demo closet's photos (`photos/`), their credits, and the drawing attributes `tools/make_demo.py` reads for each (`cases.json`) |
| `tests/` | `python -m pytest tests`: the shoe tracing bench. The tests of the tagger and the drawing are in `backend/tests/` (`test_taxonomy.py`, `test_templates_and_tagger.py`) |
