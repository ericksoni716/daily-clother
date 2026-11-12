# Phase 0 results

Status: **partly done.** The illustration approach has been tested on open-licence
photos. The tagging bench has scored a first, small stand-in run (Claude
subagents answering the app's exact prompt on seven photos) and then a real
run of the same photos through the Claude plan (`claude -p`). It has not made
a call with an API key, and the owner's own photos have not been provided
yet.

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

## Tagging: stand-in run with subagents (not the API)

Haiku, Sonnet and Opus subagents each tagged the seven test cutouts blind
(neutral file names, no access to the repo) using the app's prompt and schema.
The answers were validated and scored by the same bench code
(`--recorded`), against a key written by the developer, not the owner.

| | Haiku | Sonnet | Opus |
|---|---|---|---|
| Answers that fit the schema | 7 of 7 | 7 of 7 | 7 of 7 |
| Scored fields wrong (of 39) | 4 | 2 | 1 |
| Wrong answers given confidence under 0.8 | 4 of 4 | 2 of 2 | 1 of 1 |
| Fields under 0.8 (what a review queue would show) | 31% | 36% | 31% |

- Category, pattern and every silhouette field were right for all three models on all items.
- All seven mistakes were in colour, formality or season, and at least three are arguable (cream vs white tee under warm light, tan vs grey marl, smart-casual vs casual).
- Every mistake came with a confidence of 0.7 or less, and every answer at 0.8 or above was right. That supports showing only low-confidence fields for review, with 0.8 as a first threshold.
- The models are under-confident rather than over-confident: about a third of fields would be shown for review although most of those were right.
- For the two plaid shirts the models disagreed on the main colour (multi, green, navy). The colour word for patterned items is better taken from the colours measured in the photo than asked of the model.
- With these tags, not hand-set ones, the illustrations still came out right (see `bench/out/standin/report.html` after running the command in `bench/README.md`).

What this does not show: seven items is far too few to rank the models; the
subagents are not the API call (different surrounding instructions, and one
agent saw all seven items in a row); the key is the developer's opinion; and
there are no cost or timing figures.

## Tagging: real run through the Claude plan (`claude -p`)

The same seven photos were then tagged for real through the plan route, one
`claude -p` call per photo, with the app's prompt and schema. Nothing was
billed. All 21 calls returned a valid answer on the first attempt.

| | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Time per item | 5.5 s | 5.8 s | 7.7 s |
| Estimated cost per item at API prices (includes Claude Code's own overhead) | $0.0008 | $0.016 | $0.032 |
| Scored fields wrong (of 39) | 3 | 3 | 1 |
| Wrong answers given confidence under 0.8 | 2 of 3 | 3 of 3 | 1 of 1 |
| Fields under 0.8 (what a review queue would show) | 18% | 28% | 26% |

- Category, pattern and every silhouette field were again right for all three models.
- The mistakes are the same arguable ones: cream vs white for the tee under warm light, tan vs grey for the marl knit, one formality and two season calls.
- One Haiku mistake (cream vs white) came with confidence exactly 0.8, so a review threshold of 0.8 would have let it through. A threshold just above 0.8, or always showing colour for review on pale items, would catch it; the owner's own photos will decide.
- Seven items against the developer's key is still far too few to rank the models. On this evidence Haiku is good enough for tagging and costs a twentieth of Sonnet.

## Confidence in the API call before spending anything

The paid API key is deliberately the last step. What is already checked
without it:

- The request reaches the real API and is rejected only for the missing key
  (401), so the endpoint, headers and transport are right.
- The real SDK was run against a local stand-in server: the request carries
  the model, low effort, the JSON schema and a JPEG image block, sends no
  parameters the current models reject, and the answer parses into validated
  tags with cost computed from the reported token counts.
- The schema the SDK sends is tested against the API's documented limits: no
  optional properties, no numeric or length constraints, every object closed,
  nothing recursive.
- Failure paths are tested: an incomplete answer is retried, a refusal and
  repeated invalid answers fail with a clear message.
- The prompt and schema themselves produced valid, mostly correct answers from
  three Claude models in the stand-in run above.

What only a real key can show: that the live API accepts this exact schema,
real token counts and cost per item, and response time. The plan for that day
is one single-item call first (a fraction of a cent on Haiku), then the bench
with a spend ceiling printed before it starts.

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
