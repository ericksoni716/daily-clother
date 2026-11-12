# Phase 0 results

Status: **partly done.** The illustration approach has been tested on open-licence
photos. The tagging accuracy bench is built and unit-tested but has not made a
single real API call, because no API key is available in the build environment
yet, and the owner's own photos have not been provided yet.

## What was tested

`python -m closet_bench.hardcases` (in `bench/`) runs each photo through
background removal, takes colour, fabric and prints from the photo, draws the
item from a parametric template, and writes `bench/out/hardcases/report.html`
with the photo, the cutout and four styles side by side.

The attributes for these items (category, sleeve, neck, pattern type, colour
word) were set by hand while developing. They stand in for the tagging call
until it can be run.

| Hard case from the brief | Photo used | Result |
|---|---|---|
| Plaid shirt | Flannel shirt on a dress form | Works. The repeat is detected and tiled at the right scale. |
| Plaid shirt (second) | Small, angled madras shirt | Partly. Reads as blue madras but duller, with two colours missing. Photo quality is the cause. |
| Graphic tee with a logo | White tee with a printed design | Works. The real print is lifted and placed; nothing is redrawn. |
| White sneakers | Two photos: a pair, and one held in a hand | Partly. Correct colour only with the attribute word "white"; the drawing is a generic sneaker and a side logo is lost. |
| Jeans | Jeans flat on a rug | Works. |
| Striped sweater | none yet | **Not tested on a real photo.** The stripe measurement is only unit-tested on a synthetic image. |
| Floral (a floral shirt, since the wardrobe is menswear) | none yet | **Not tested.** Uses the same fabric-tile path as the knit sweater below, with the irregular-pattern tile. |
| Camo jacket | none yet | **Not tested.** Same path as floral. |
| (extra) Textured knit sweater | Marl turtleneck | Works. |

The three untested cases are missing only because Wikimedia Commons rate-limited
the build environment before those photos could be downloaded.

## Findings

1. **Templates beat tracing.** Style D traces the real outline from the cutout.
   It fails on most items: the outline depends on how the item hung or lay, and
   includes mannequins, hands and laces. The template styles (A, B, C) are
   consistent and are the recommendation.
2. **Colour needs the attribute word as well as the photo.** White shoes in
   shade measure grey and a white tee under warm light measures cream. The
   photo gives the exact shade; the word (white, black, cream) corrects what
   lighting did. Colours that differ only by brightness are merged into one
   family and the lit end is used.
3. **Fabric tiles work when the photo is decent.** A patch is chosen that is
   evenly lit, has the garment's overall colour mix, and avoids the button
   placket. Plaids use one detected repeat, or a mirrored tile when no repeat
   is found. Irregular patterns use a tile blended with a half-shifted copy of
   itself so it wraps without a seam.
4. **Prints are told from shadows by their edges.** A soft shadow was first
   lifted as part of the tee's print. Crisp-edged regions are now kept and
   soft-edged ones dropped.
5. **Shoes are the weakest template.** One generic side view per height and
   sole. Model-specific details and side logos are not shown.
6. **The shape vocabulary will grow.** The first sweater photo needed a
   turtleneck option. Each addition is a few lines and a test.
7. **Background removal.** `isnet-general-use` and `u2net` both gave usable
   cutouts on all seven photos in about a second each on CPU.
   `isnet-general-use` was slightly cleaner on laces and removed more of a
   hand, so it is the default. Cutouts at 1600px as WebP were 32–197 KB.
8. **Packaging.** A minimal program with FastAPI, onnxruntime, Pillow,
   pillow-heif and ffmpeg builds into one file with PyInstaller and passes its
   smoke test on Linux (about 117 MB, of which ffmpeg is about 65 MB). It has
   not been built on Windows or macOS; the workflow exists but has never run.

## Still open

- Tagging accuracy, confidence calibration, cost per item and time, per model,
  with and without an extra shot: needs an API key and real photos.
- Which fields stay, which become optional, which need a prompted extra shot,
  and which model tags what: decided from that run, not before.
- Striped, floral and camouflage items on real photos.
- A style choice from the owner.
- The first Windows build of the packaging spike.

## Cost estimate for tagging (not measured)

From token arithmetic only: one cutout at 1024px is roughly 1,400 input
tokens, the prompt about 350, and the answer about 300–500 output tokens. At
the prices in `bench/closet_bench/models.json` that is about $0.0004 per item
on Haiku 5.5, $0.008 on Sonnet 5.5 and $0.017 on Opus 5.5, so 300 items cost
roughly $0.15, $2.50 or $5. The bench reports the real figures.
