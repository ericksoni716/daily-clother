# Bench

Experiments that decide how the app tags and draws clothes. Three commands:

```
cd bench
pip install -r requirements.txt

# 1. Illustration hard cases (open-licence photos in hardcases/photos)
python -m closet_bench.hardcases
#    -> out/hardcases/report.html

# 2. Tagging accuracy on your own photos
#    Uses your Claude plan through `claude -p` (Claude Code must be installed
#    and signed in); falls back to ANTHROPIC_API_KEY only if the plan cannot be
#    used. Force one with --route plan or --route api.
python -m closet_bench.bench --photos private/photos --key private/key.csv
#    -> out/bench/report.html and results.json

# 3. Tracing shoe photos into the flat style (#192, stages 1 and 2a)
#    Side-on photos of one shoe each in private/shoes/ (git-ignored). Uses the
#    app's cut-out model when models/ has it (command 1 downloads it),
#    otherwise OpenCV's GrabCut.
#    Sheets are also saved as PNG when Chrome or Chromium is installed.
python -m closet_bench.trace_shoes --photos private/shoes
#    -> out/trace_shoes/index.html, shoe-NN.sheet.svg/.png and results.json
```

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

To score answers produced some other way (for example by Claude subagents),
save them as `<folder>/<model name>/<photo name>.json` and add
`--recorded <folder> --models <model name> ...`. Cost and time are then not
measured. `hardcases/key.csv` is a developer-written key for the test photos.

The background-removal model (about 170 MB) downloads into `models/` on first
use and is checked against a pinned checksum.

## Your photos and answer key

Put 25–30 photos in `bench/private/photos/` and fill in `bench/private/key.csv`
using `answer_key.template.csv` as the pattern. Leave a cell blank if a field
does not apply or you are unsure; blank cells are not scored. `extra_shots` is
an optional `;`-separated list of tag or detail photos for that item.

The columns from `fit_detail` onward are the detail fields. Their allowed values
are the ones in `docs/menswear-taxonomy.json` (collar, placket, cuff, pockets,
hem, fabric, fiber and so on); `weight` is lightweight, midweight, heavyweight or
super_heavy. Fill in only the ones you care about scoring. The most useful
photos for testing details are the items that differ from the usual: a polo with
one or three buttons, a henley, corduroy, a fleece or heavy wool shirt beside a
light cotton one, a sweatshirt with a V-insert.

`private/`, `out/` and `models/` are git-ignored, and the bench prints item
numbers only, never file names.

## What is where

| File | Purpose |
|---|---|
| `closet_bench/cutout.py` | Background removal with ONNX models, crop, WebP cutout |
| `closet_bench/fills.py`, `templates.py`, `illustrate.py` | The drawing. These now live in the backend, in `backend/closet/drawing/` (colours, fabric swatches, stripes and prints taken from the photo; the parametric garment shapes; the four styles, shape + fill = SVG). The bench names are the same modules, so imports here work unchanged. OpenCV is imported only inside the parts that read a photo (the fills and the "traced" style), so the app's program draws without it |
| `closet_bench/schema.py`, `tagging.py`, `taxonomy.py`, `claude_cli.py`, `routes.py` | The tagger. These now live in the backend, in `backend/closet/tagger/` (attribute vocabulary and answer shape; the prompt and the API-key route; the owner's taxonomy as the drawing sees it; the plan route through `claude -p`; plan first, API key as fallback). The bench names are the same modules, so imports here work unchanged |
| `backend/closet/tagger/models.json` | The one place model IDs and prices live |
| `closet_bench/hardcases.py`, `bench.py`, `trace_shoes.py` | The three commands above (the shoe tracing and its gate live in `backend/closet/drawing/trace.py` and `traced.py`) |
| `tests/` | `python -m pytest tests` |
