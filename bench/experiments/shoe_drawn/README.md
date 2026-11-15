# A shoe on the figure's feet, drawn from understanding: the experiment

The work this belongs to is in `docs/BACKLOG.md` (Track 1, "Shoes on the figure drawn from understanding") and what
was decided with the owner is in `docs/DECISIONS.md` ("A shoe on the figure's feet: drawn from understanding, not
traced"). Read both first. The attempt before it, a solid measured from the photos, is in `../shoe_solid/`.

This folder is the throwaway material behind that work, done with the owner on 15 November 2026. It is not app code
and nothing imports it. It holds no photos: the owner's photos and every drawing made from them stay under
`bench/private/shoe_drawn/` (git-ignored). The three drawings in `EXAMPLES/` are clip art drawn by hand or by the
model, with no photo inside them.

## The idea

Instead of tracing or measuring a shoe, a vision model (Claude) does what a person drawing clip art does:

1. **A feature sheet**, written from the photos alone: what kind of shoe it is, its silhouette, its proportions,
   its 2 to 6 true colours (one material is one colour), its parts, and what makes it recognisable from the front.
2. **A drawing from that sheet**, as bare SVG inside a fixed frame: flat fills, a bold outline, thin inner lines.
3. **Look and fix**: the model renders its drawing, looks at it beside the photos and fixes it, at most three
   times.

## Where it stands

- **Tried on five of the owner's own pairs**, five photos each (outer side, above, front, back, inner side): a
  cushioned running shoe, a German-army-trainer style sneaker, a tan cap-toe dress shoe, a boat shoe and a pull-on
  boot with elastic sides.
- **Round 1** (one run per shoe, the shoe's name not given): 5 of 5 shoes named correctly, model names included. The
  owner: "almost exactly what I want". Faults: no opening (the leg sat on top of the shoe), the running shoe's
  outline odd, laces as plain bars.
- **Round 2** (three separate runs per shoe, 15 runs; the drawing split into a part behind the leg and a part in
  front, so the leg goes into the shoe; proportions written down before drawing): 15 of 15 named; the runs agreed on
  colours and parts; the opening was fixed. But low shoes came out too tall, because the frame put the opening too
  high (10 of 15 runs said so themselves), and the boot read as a tube with no toe box. The owner picked the
  session's trainer and round 1's dress shoe and boat shoe as the best so far (now in `EXAMPLES/`); every boot had
  "zero perspective"; no runner was good (the sole's rubber over the toe wrong, the foam sole too wide and bulky).
- **Round 3** (`BRIEF3.md`: the three liked drawings as worked examples, the build order written out, a rule for
  the view, a frame that keeps a low shoe about as tall as it is wide, the sole no thicker or wider than the photos
  show; boot and runner only, three runs each): all three boots got a toe box in front with the shaft behind; the
  runners came out low and domed with a less bulky sole. Still off: the boot's toe box wide and flat, its elastic
  as slivers; the runner's toe rubber too big, its N logo unreadable and backwards on the right foot (the preview
  mirrored the left shoe).
- **Round 4**:
  - *A correction from a one-line note* (`CORRECT.md`): starting from an existing drawing and changing only what the
    note asks, the boot's elastic panels were made broad in one round, in about 35 seconds, with nothing else
    changed.
  - *Kind of shoe first* (`ARCH.md`): the model names the most specific kind (it said a max-cushion running shoe
    with a thick foam midsole), writes how that kind looks from the front, draws that, then fits it to the photos.
    The foam sole read as a thick tub with the upper sitting in it. Of the two runs the owner preferred the first
    ("looks more like a shoe"). The toe rubber got bigger and needs its own correction.
  - *Left and right drawn separately* when a mark is on one side only: the N read the right way round on both feet.
  - *Sorting unlabelled photos* with a cheaper model (Sonnet), on the 25 photos shuffled: 5 of 5 shoes grouped
    correctly; above, front and back named correctly 15 of 15; outer and inner side swapped on 3 of 5 shoes, and the
    model itself flagged all six of those photos as unsure.
- **Tried and dropped before use:** an outline measured from the photos for the model to draw over. Seen from the
  figure's real angle (24° down) the outlines were nearly twice as tall as wide and would have made the shoes tall
  again. Only the measured height and width (`guide.json`) were passed on.
- **Cost seen:** each drawing run took 70 to 170 seconds and about 80 to 95 thousand tokens on Opus, including up to
  three look-and-fix rounds; a correction about 35 seconds.

**Still open:** a correction of the runner's toe rubber was running when this was written. The method has only been
tuned and judged on these five pairs, so it must next be run unchanged on pairs it has not seen. The drawings are
straight from the front, about 15° above, tilted 7° by the preview; they are not yet at the figure's own view (24°
down, toes out 11°) and not yet placed on the app's figure. The rest is in the backlog.

## What each file does

| File | What it does |
|---|---|
| `BRIEF3.md` | The brief given to an agent for one drawing (round 3): the feature sheet, the frame, the view, the build order, the style and the look-and-fix check. |
| `ARCH.md` | Round 4's "kind of shoe first": `BRIEF3.md` with the kind of shoe named and described before drawing, and left and right shoes drawn separately when a mark is on one side. |
| `CORRECT.md` | Round 4's correction: redraw one shoe from a starting drawing and a one-line note from the owner, changing nothing else. |
| `render.js` | The preview for `BRIEF3.md`: puts one shoe on a pair of legs, mirrors it for the other foot, tilts it 7°, and renders it large and at phone size. |
| `render3.js` | The same for `ARCH.md` and `CORRECT.md`: takes `OUT.left.svg`, and `OUT.right.svg` when there is one instead of mirroring. |
| `EXAMPLES/trainer-full.svg` | The trainer drawn by the orchestrating session from the owner's photos in about ten minutes (four flat colours), with its legs. A worked example. |
| `EXAMPLES/dress-shoe.svg`, `EXAMPLES/boat-shoe.svg` | Round 1's dress shoe and boat shoe, which the owner liked. Worked examples. |

The briefs also mention `EXAMPLES/*.png`, renders of the three examples; they are not kept here. Make them again with
`node render.js EXAMPLES/dress-shoe.svg EXAMPLES/dress-shoe.png` (and the same for the boat shoe); the trainer's file
already holds its legs, so open it in a browser and save a screenshot as `trainer.png`.

## How to run a round again

1. Copy this folder's files into `bench/private/shoe_drawn/` and work there, so the photos and drawings stay out of
   the repository. The briefs use paths relative to their own folder.
2. Put each shoe's photos in `bench/private/shoe_drawn/shoe-N/` as `side.jpg` (outer side), `above.jpg`,
   `front.jpg`, `back.jpg` and `inner.jpg`, each cropped to the shoe, and a `guide.json` with `height_cm` and
   `width_cm` (measured by `../shoe_solid/guide.py`, or written by hand).
3. Make the example PNGs (above).
4. Give an agent one brief and the numbers it asks for: `BRIEF3.md` with a shoe number and a run number; or
   `ARCH.md` with a shoe number and an output name; or `CORRECT.md` with a shoe number, a starting drawing, the
   owner's note and an output name. Each agent reports back one line.
5. The preview needs Node with Playwright and Chromium (`npm install playwright` and `npx playwright install
   chromium` in that folder). `node render.js shoe-N-vR.svg shoe-N-vR.png` or `node render3.js OUT`; each also
   writes the whole picture as `.full.svg`.

## What is rough

- The frame, the view rule and the examples were tuned on these five pairs while looking at them. Nothing yet says
  the brief works as well on a shoe it was not tuned on.
- The view is a guess at "from the front and a little above", not the figure's own. The preview's legs and sock are
  a stand-in for the figure, and its 7° tilt is not the figure's turn of the toes.
- Each brief still names one-off facts about these pairs (shoe 5's side photo runs off the frame).
- How often a run comes out poor is only known from these runs (round 2's 15 and round 3's 6).
- The photos were sorted by hand for the drawings; the sorting test was separate.
- Nothing checks a drawing against the four front-shoe rules; the model's own look is the only check.
