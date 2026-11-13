# Bench

Experiments that decide how the app tags and draws clothes. Two commands:

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
```

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
| `closet_bench/fills.py` | Colours, fabric swatches, stripes and prints taken from the photo |
| `closet_bench/templates.py` | Parametric garment shapes (tops, pants, sneakers so far) |
| `closet_bench/illustrate.py` | The four styles; shape + fill = SVG |
| `closet_bench/schema.py`, `tagging.py`, `taxonomy.py`, `claude_cli.py`, `routes.py` | The tagger. These now live in the backend, in `backend/closet/tagger/` (attribute vocabulary and answer shape; the prompt and the API-key route; the owner's taxonomy as the drawing sees it; the plan route through `claude -p`; plan first, API key as fallback). The bench names are the same modules, so imports here work unchanged |
| `backend/closet/tagger/models.json` | The one place model IDs and prices live |
| `closet_bench/hardcases.py`, `bench.py` | The two commands above |
| `tests/` | `python -m pytest tests` |
