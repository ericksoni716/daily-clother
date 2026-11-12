# Bench

Experiments that decide how the app tags and draws clothes. Two commands:

```
cd bench
pip install -r requirements.txt

# 1. Illustration hard cases (open-licence photos in hardcases/photos)
python -m closet_bench.hardcases
#    -> out/hardcases/report.html

# 2. Tagging accuracy on your own photos (needs ANTHROPIC_API_KEY)
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

`private/`, `out/` and `models/` are git-ignored, and the bench prints item
numbers only, never file names.

## What is where

| File | Purpose |
|---|---|
| `closet_bench/cutout.py` | Background removal with ONNX models, crop, WebP cutout |
| `closet_bench/fills.py` | Colours, fabric swatches, stripes and prints taken from the photo |
| `closet_bench/templates.py` | Parametric garment shapes (tops, pants, sneakers so far) |
| `closet_bench/illustrate.py` | The four styles; shape + fill = SVG |
| `closet_bench/schema.py` | Attribute vocabulary and the shape of a tagging answer |
| `closet_bench/tagging.py` | The Claude call: schema-constrained, validated, retried |
| `closet_bench/models.json` | The one place model IDs and prices live |
| `closet_bench/hardcases.py`, `bench.py` | The two commands above |
| `tests/` | `python -m pytest tests` |
