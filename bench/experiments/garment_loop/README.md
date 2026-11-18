# Drawing a garment's surface by describing, rendering and correcting it: results

Run on 18 November 2026 from `PLAN.md`, as designed in `DESIGN.md` (decided before any photo was seen; every change
since is in its log). Nothing in the app changed: the code that would be app code is `closet/patterns/surface.py`,
called by nothing.

## In short

1. **The loop is not worth it.** One loop of three corrections (arm D) drew garments as well as one description
   from Sonnet (arm C), garment by garment, at three times the cost; the run stopped after the tuning half as the
   plan says. The corrector sees the faults; the measure that picks the version to keep agrees with the judge only
   two times in three.
2. **One description from Sonnet with the three gaps every arm shared fixed (arm F) is the best thing tested, and it
   held on the held-out half**, run once: picked out 88% of patterned garments (the app today: 42%), the ground colour
   right on 92% (54%), the scale within a quarter on 71% (35%), never confidently wrong (the app today: 8%), first in
   the blind ranking on 18 of 30 garments, about 2 US cents and 12 seconds an item. It meets four of the plan's
   lines and misses four, three of them narrowly (below).
3. **Recommendation: adopt F**, the owner's choice after the tuning half, with the gaps listed under "What F still
   gets wrong" as the next work.

---

# Part 1: the loop (tuning half)

## What was run

- **The set**: 60 garments: 46 of the owner's ordinary photos, 9 studio or catalogue photos the owner chose to
  include (they may import online photos of their clothes), and the demo closet's 5 garments. Split 30 and 30 by
  the balancing deal in `freeze.py` (seeded). Tables below.
- **The truth**: one reference sheet per garment, written from the photo alone before any arm ran (9 by Fable,
  51 by Opus: five Fable batches were stopped by Fable's safeguards and the owner chose Opus for the rest).
- **The arms** on the 30 tuning garments, every garment drawn by the app's own templates from the app's own
  description of its shape, the arms differing only in the cloth:

| Arm | What it is |
|---|---|
| A | The app today: the pattern measured from the photo where it passes the app's check, else plain colour |
| B | The app's describing model (Haiku), one description with the new surface form, three runs |
| C-sonnet, C-opus | The same call on the stronger models the app lists, three runs each |
| D | The loop: B's answer, drawn, shown beside the cutout to Opus at medium effort (the app's own shoe-correcting set-up), corrected three times; the version kept is the best by a measured score. Three chains |
| E | The best of D's three chains by that score |
| D-small | The loop with Haiku correcting (declared side arm) |

- **The judging**: Opus subagents, blind (random names, shuffled, never told the arm): a 0 to 3 rubric on five lines,
  every drawing twice by separate judges (agreement: 82% of line scores exactly the same, 99.5% within one; 3
  drawings judged a third time), a pairwise ranking per garment, and a "same garment?" call on each arm's three runs.
  The judges are the same model as the corrector and C-opus: see "What is uncertain".

## The tuning half, every measure

Rubric totals are of 15. "Patterned" means the sheet says the garment is not plain (24 of the 30). Costs are per
garment, through the Claude plan, priced at the API key's prices in `models.json`; tokens include Claude Code's own
context (about 35,000 a call, mostly read back from its cache), which the API key route would not send.

| Arm | Median total | Mean total | Picked out (2+) of patterned | Ground colour right (2+) | Scale within 25% (16 with a repeat) | Confidently wrong | Pattern on plain or print | Colour-share distance | All 3 runs judged the same garment | Run-to-run difference | Calls | Seconds | US$ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 10.25 | 9.28 | 42% | 71% | 44% (approx.) | 8% | 36% | 13.5 | n/a | n/a | 0 | 230 (measuring) | 0 |
| B | 11.75 | 10.23 | 54% | 83% | 50% | 0% | 9% | 14.4 | 57% | 9.4 | 1 | 12 | 0.002 |
| C-sonnet | 11.5 | 10.75 | 62% | **100%** | 50% | 0% | 18% | 12.7 | 87% | 5.0 | 1 | 11 | 0.026 |
| C-opus | 10.5 | 10.28 | 58% | 92% | 44% | 0% | **0%** | 13.3 | **97%** | **2.9** | 1 | 12 | 0.055 |
| D after 1 | 11.75 | 10.37 | 58% | 83% | 44% | 0% | 9% | 12.1 | | | 2 | 19 | 0.032 |
| D after 2 | 12.5 | 10.70 | 58% | 88% | 44% | 0% | 9% | 12.1 | | | 3 | 26 | 0.060 |
| D after 3 | 12.5 | 10.75 | 62% | 88% | 44% | 0% | 9% | 12.1 | 73% | 6.7 | 4 | 33 | 0.084 |
| E | 12.5 | **11.35** | **75%** | 88% | **56%** | 0% | 9% | **10.4** | (not run) | | 12 | 96 | 0.250 |
| D-small | 12.25 | 10.70 | 71% | 88% | 50% | 0% | 9% | 12.8 | 63% | 7.7 | 4 | 33 | 0.005 |
| **The plan's line** | 2 above B | | 80% | 90% | 80% | 5%, not above A | 0% | | 90% | a third below B (6.3) | | | |

Garment by garment (mean difference in rubric total, with the range a resampling of the 30 garments gives 95% of the
time): D minus C-sonnet **0.00** (-0.57 to +0.58; better on 10, worse on 14); E minus C-sonnet +0.60 (-0.22 to +1.55);
D minus B +0.52 (-0.03 to +1.12); E minus B +1.12 (+0.30 to +2.10); C-sonnet minus B +0.52 (+0.03 to +1.00).

Pairwise ranking (average place, 0 best and 1 worst; times ranked first of 30): E 0.34 (11), D 0.47 (5), C-sonnet
0.48 (5), D-small 0.53 (5), A 0.55 (11), C-opus 0.59 (2), B 0.68 (2). A is often first and often last: it pieces a
print from the photo itself, which the judges liked, and draws a plaid it could not measure as plain colour.

By family (mean rubric total) and by kind of garment:

| | A | B | C-sonnet | C-opus | D | E | D-small |
|---|---|---|---|---|---|---|---|
| Plaid and check (10) | 8.3 | 10.4 | 10.8 | 10.0 | 11.2 | 12.3 | 11.4 |
| Stripes (5) | 6.0 | 11.0 | 11.7 | 11.8 | 11.9 | 11.2 | 11.5 |
| Colour block (3) | 6.2 | 5.8 | 6.5 | 5.3 | 7.8 | 11.2 | 6.0 |
| Logo on pattern (2) | 11.2 | 14.0 | 13.2 | 12.8 | 13.0 | 13.5 | 14.5 |
| Placed detail (3) | 11.5 | 10.5 | 11.3 | 10.3 | **10.0** | 10.8 | 10.5 |
| Solid (4) | 13.0 | 14.1 | 14.4 | 14.2 | 14.1 | 13.5 | 14.0 |
| Print (3) | 12.2 | 4.7 | 6.2 | 6.2 | **5.0** | 4.7 | 4.8 |
| Home photos (25) | 9.7 | 9.8 | 10.5 | 10.1 | 10.5 | 11.2 | 10.4 |
| Studio photos (5) | 7.0 | 12.3 | 12.1 | 11.1 | 12.1 | 12.2 | 12.3 |

The loop is worse than the app today on prints and on placed details: "no family worse than A" fails on the tuning
half. On prints that is the design (the form draws a print as its main colour), and the app's own way, piecing the
print from the photo, is better; see the recommendation.

## The loop itself

- **It converges.** The loop's own score, kept version: 0.440 at the start, 0.487 after one correction, 0.500 after
  two, 0.506 after three; the third gains an eighth of the first. Judged, D after 1, 2 and 3: 10.37, 10.70, 10.75.
- **The corrector sees the faults.** Of the 28 starting drawings the judge faulted, the first correction changed the
  field the judge's fault names on 24 (86%); its notes read like the judge's ("photo's repeat is about half the drawn
  size, the green is darker"; "photo is wavy colour-blocked: navy top, dusty rose middle, cream bottom"). 95 of 270
  corrections said the drawing matched.
- **The measure that keeps the best version is the weak part.** In 36 of 90 chains it kept the starting drawing.
  Across pairs of different drawings of one garment, it agreed with the judge on which was better 164 times and
  disagreed 83 times (two in three); within a garment, its score and the judge's total correlate at a median 0.47.
- **Scale does not improve.** The corrector moved the scale often (with the bands, the field it changed most), but within 25%
  of the count went from 50% (B) to 44% (D). Relative size beside the photo is no easier for it than absolute size.
  Six garments have more than 16 repeats across (fine stripes and tiny checks, 22 to 117); the drawing caps a repeat
  at 16 across (`described.REPEATS`), so no described arm can reach them. Without them: B, C-sonnet and D-small 8 of
  12, D 7 of 12, E 9 of 12.
- **The small model corrects nearly as well.** D-small 10.70 against D 10.75, at about a seventeenth of the cost; less steady.

## What every arm shares

The worst drawings were the same garments for every arm:

1. **Colour blocks the drawing has no part for**: a panel across the chest, wavy bands, a stripe at the join. The
   form can name only a yoke, sleeves, collar or pocket; Claude names them right and has nowhere to put them.
2. **Prints**, drawn as their main colour by design. The app today pieces a print from the photo and judges score
   it 12.2 of 15 against about 5 for every described arm. (Its piecing is not clean either: on one print shirt on
   a hanger it pieced the hanger into the collar, which the judges did not mark down; the final look at the sheets
   caught it.)
3. **Fine patterns** past the 16-repeat cap (above).

## Changes along the way

All before any arm ran; see `DESIGN.md`, "Log of changes": the split's deal (it had sent every jacket to the tuning
half), one photo regrouped, the bottoms' tile size per kind, one colour strength for every described colour, the
owner's decisions on the set and on Opus for the visual jobs. No prompt or rule was tuned after seeing a drawing: the
run stopped first.

## Recommendation after the tuning half (the owner then chose F: Part 2)

Adopt **neither** the loop nor a one-shot description yet. The loop as built is not worth its cost: one chain matches
one call to Sonnet. If the owner wants one direction taken further:

- **One description from Sonnet** (the app's `sorting` model) on the description call, with the surface form
  (`closet/patterns/surface.py`): the ground colour right on every patterned garment, all three runs the same garment
  87% of the time, about 2.6 US cents and 11 seconds an item, no render step, nothing new for the owner to wait for.
- With it, the three shared gaps: keep the app's own piecing for prints (kind "other" when the app's print measure
  passes its check), give the form a few more parts for blocks (a chest panel, upper and lower body), and lift the
  16-repeat cap for fine patterns.
- Then run the held-out half on that, once.

The best of three loops (E) is the most accurate thing tried (first or tied first in the ranking on 11 of 30), and
the owner said cost is secondary. If accuracy is worth about 25 US cents and twelve calls an item, it is the one to
try next, with a better measure for picking the version (two in three is too weak) before anything else.

## What is uncertain

- **The judge is the same model** as the corrector and C-opus (the owner chose Opus over a stronger-vision model for
  cost). A fault Opus cannot see is missed by both the loop and its judge. The measured lines do not share that blind
  spot, and they agree with the ranking.
- **30 garments**: three colour-block garments, three prints, two logos on pattern, one shorts. Medians move in half
  points; the garment-by-garment differences above are the better guide.
- **Arm A's scale** for measured stripes is read off its band sequence and is only approximate.
- **The sheets** were written by two models (9 Fable, 51 Opus); counts above 30 are rough.
- **Studio photos** (5 in the tuning half) look easier for described arms (12 against 10) and harder for the app's
  measuring (7 against 10); too few to say more.

## The three garments each arm did worst on (rubric total, the judge's fault)

| Arm | Worst three |
|---|---|
| A | multicolour stripes drawn as plain dark knit (0.5); a small lavender check drawn plain (3.0); a tiny navy check drawn plain grey (3.0) |
| B | a two-tone tee with a chest stripe drawn all olive (1.5); a pastel tropical print drawn plain grey (2.5); wavy colour blocks drawn plain navy (3.0) |
| C-sonnet | wavy colour blocks drawn all cream (3.5); the two-tone tee drawn plain khaki (4.0); the tropical print drawn plain blue (5.0) |
| C-opus | the two-tone tee drawn one sage grey (4.0); patchwork madras drawn as one tan plaid (4.5); wavy colour blocks drawn all cream (4.5) |
| D | the tropical print drawn plain grey (2.5); wavy colour blocks drawn plain navy (3.0); a bold floral drawn plain blue (5.5) |
| E | the tropical print drawn plain grey (2.5); the bold floral drawn plain blue (5.5); fine grey stripes drawn near plain (6.0) |
| D-small | the two-tone tee drawn plain sage (2.0); the tropical print drawn plain grey (2.5); wavy colour blocks drawn plain navy (3.0) |

The result sheets (photo, every arm's drawing, scores) are private, one per garment, in
`bench/private/garment_loop/results/tuning/`.

---

# Part 2: one description from Sonnet with the three gaps fixed (arm F)

After Part 1 the owner chose to take one Sonnet description, with the three gaps every arm shared fixed, to the
held-out half (`DESIGN.md`, log 7 and 8). F is the description call on Sonnet with the **second surface form**
(`surface.Surface2`): colour blocks may also be bands across the body (where each starts and ends from collar to
hem, drawn as one garment-sized picture); a print ("other") is drawn with the app's own piecing from the photo, as
arm A draws a print; fine patterns get a "micro" size word, a cap of 150 repeats across instead of 16, and a reading
of the repeat at the photo's own detail when Sonnet calls the pattern micro or tiny. A, B and C-sonnet run exactly as
in Part 1. F was checked on the tuning half, judged there together with A, B and C-sonnet, and frozen unchanged (one
rule was considered and not adopted: a threshold that would have been tuned on four garments). Then the held-out half
was run once: A, B, C-sonnet and F, three runs each, judged blind in one shuffled round (two passes, 77% of line
scores exactly the same and 98% within one; 8 drawings judged a third time), ranked pairwise, and checked for
steadiness.

## The held-out half, every measure

30 garments; 24 patterned by the reference sheets, 17 with a repeat, 4 studio photos.

| Arm | Median total | Mean total | Picked out (2+) of patterned | Ground colour right (2+) | Scale within 25% (17) | Confidently wrong | Pattern on a solid | Print pieced from the photo | Colour-share distance | All 3 runs the same garment | Run-to-run difference | Calls | Seconds | US$ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 9.0 | 7.88 | 42% | 54% | 35% (approx.) | 8% | 0% | 3 of 3 | 16.7 | n/a | n/a | 0 | 326 (measuring) | 0 |
| B | 10.75 | 10.05 | 62% | 92% | 41% | 0% | 0%* | 0 of 3 | 15.3 | 60% | 8.0 | 1 | 11 | 0.002 |
| C-sonnet | 11.5 | 10.77 | 75% | 88% | 41% | 0% | 0%* | 0 of 3 | 12.2 | 80% | 5.4 | 1 | 10 | 0.025 |
| **F** | **12.25** | **11.68** | **88%** | **92%** | **71%** | **0%** | 0%* | 3 of 3 | **11.8** | **83%** | **4.2** | 1 | 12 | 0.022 |

\* One solid polo has a pocket in contrasting cloth; B, C and F all drew the grey pocket (judged right). It counts
as a pattern on a solid in `results/held-out.json`; it is not one.

Garment by garment (mean difference in rubric total, 95% resampling range): F minus C-sonnet +0.92 (-0.07 to +2.15;
better on 14, worse on 12); F minus B +1.63 (+0.42 to +3.02); F minus A +3.80 (+2.23 to +5.48). On the tuning half
F minus C-sonnet was +0.88 (+0.03 to +1.88): the same lead in both halves, just inside chance on the held-out one.

Pairwise (average place, 0 best; times first of 30): F 0.30 (18), C-sonnet 0.44 (10), B 0.52 (9), A 0.74 (7).

By family and kind of garment (mean rubric total, held-out):

| | A | B | C-sonnet | F |
|---|---|---|---|---|
| Plaid and check (9) | 6.4 | 9.8 | 10.8 | 11.4 |
| Stripes (7) | 5.1 | 12.2 | 12.4 | 11.6 |
| Colour block (4) | 6.0 | 7.5 | 9.5 | 8.9 |
| Print (3) | 14.3 | 5.3 | 4.7 | 13.8 |
| Solid (4) | 10.0 | 10.6 | 11.9 | 12.6 |
| Placed detail (2) | 12.2 | 13.8 | 14.0 | 14.0 |
| Logo on pattern (1) | 11.5 | 11.5 | 11.5 | 10.5 |
| Shirts (8) | 9.3 | 9.4 | 9.6 | 11.7 |
| Tees and polos (10) | 9.4 | 11.8 | 11.8 | 12.6 |
| Knits (4) | 5.1 | 9.4 | 11.8 | 11.1 |
| Jackets (3) | 4.8 | 10.5 | 9.3 | 10.5 |
| Trousers (3) | 7.7 | 7.7 | 12.3 | 13.2 |
| Shorts (2) | 4.8 | 8.2 | 8.5 | 8.0 |
| Home photos (26) | 8.0 | 10.5 | 10.9 | 11.7 |
| Studio photos (4) | 6.9 | 7.0 | 9.9 | 11.5 |

On the tuning half, judged in the same way (round `r2`): mean totals A 8.95, B 9.92, C-sonnet 10.55, F 11.43; F
picked out 88% and had the ground colour right on 100%; first in the ranking on 19 of 30.

## The plan's lines, for F on the held-out half

| Line | Needed | F | |
|---|---|---|---|
| Picked out, patterned | 80% | 88% | met |
| Median total above B | 2 points | 1.5 (mean 1.6) | missed narrowly |
| Ground colour right | 90% | 92% | met |
| Scale within 25% | 80% | 71% (C-sonnet 41%) | missed |
| Confidently wrong | at most 5%, not above A's 8% | 0% | met |
| No pattern on solids | 100% | 100% (the pocket above is right) | met |
| Prints | draw no pattern | pieced from the photo, by the owner's choice | changed by design |
| All 3 runs judged the same garment | 90% | 83% | missed |
| Run-to-run difference a third below B | 5.3 or less | 4.2 | met |
| No family or garment worse than A | none | prints 13.8 against 14.3 (the same piecing; within the judges' noise), one logo-on-stripes 10.5 against 11.5 | missed narrowly |
| Simpler wins ties | C within 1 point and meeting the lines | C-sonnet is 0.9 behind but meets fewer lines (picked out 75%, scale 41%) | F |

## What F still gets wrong (the three worst, and the pattern behind them)

| | Rubric total | The judge's fault |
|---|---|---|
| Studio shorts in two colours | 6.0 | the yellow leg panel missing; drawn in one blue (one leg in another colour has no band or part) |
| Small windowpane shirt | 7.5 | the check drawn about twice too fine and too faint (the fine reading's one overshoot) |
| Colour-block windbreaker | 7.5 | chevron yoke and sleeve panels left out (diagonal blocks are neither bands nor parts) |

Across both halves: a block that runs down one side or diagonally; a thin stripe band at a seam; a logo on
patterned cloth (the app lifts a graphic only on plain cloth); fine pinstripes the fine reading misses (one at 2 for
38 across); and three runs agreeing 83% of the time, not 90%.

## What the app would need to adopt F

- **The form**: the `surface` field (`surface.Surface2`, `FIELD_TEXT_2`, `GUIDANCE`) added to the description
  call, and the description call moved to the `sorting` model (Sonnet). That makes every description about
  2 US cents and 12 seconds at the API key's prices (about 11 times what the describing model costs now) through the
  same routes and monthly limit; one call, no render step, nothing new for the owner to wait for.
- **Drawing it**: `surface.drawn(..., second=True)` turns the answer into the kept pattern the drawing already reads
  (`closet.drawing.stored`); bands across the body need the drawn garment's proportions (a plain drawing, as the
  harness does); a print needs the app's print piecing, which `patjobs` already runs in the background; a plaid's
  and a stripe's scale need the landmarks the app already asks for on a patterned top.
- **The data**: the answer kept with the item's description (it is part of the tagger's answer); a migration only if
  the kept pattern's format changes (it does not: a described tile is a kept tile).
- **What the owner sees**: patterns drawn from the description straight away, a print a little later (as today).

## What is uncertain (Part 2)

- The judges are Opus; F is described by Sonnet. The judge is not the describer, but the caveat of Part 1 (one
  family of models judging another's drawings) stands.
- 30 held-out garments, one logo on pattern, two shorts, four studio photos: the family rows are thin.
- F's lead over C-sonnet is the same in both halves (+0.9) but within chance on each; its lead over the app today and
  over the describing model is clear in both.
- From the final look at the result sheets: the garment's shape comes from the app's own description and is the
  same for every arm, so when that description is wrong every arm suffers alike (a long-sleeved plain jumper drawn
  short-sleeved with cables, which the judges partly marked against the cloth; a pullover rugby shirt drawn as an
  open jacket). A striped body's stripes run into the collar and the inside of the neckband, where the real collar is
  plain. A print drawn with the app's piecing is the photo's own cloth, so A's and F's scores on prints measure the
  piecing, not a description (and the piecing can carry the photo's creases and, once in Part 1, a hanger).
- A full score beside a small named fault on the sheets is expected: the score is two judges averaged, the fault
  line is the first judge's.

The result sheets (photo, every arm's drawing, scores) are private: `bench/private/garment_loop/results/held-out/`
and, for the check on the tuning half, `bench/private/garment_loop/results/tuning-r2/`.

## The set

60 garments: tuning and held-out halves.

| Group | Tuning | Held-out |
|---|---|---|
| Gingham, tiny check | 2 | 2 |
| Small check, windowpane, tattersall | 1 | 1 |
| Medium plaid | 3 | 2 |
| Buffalo, huge check | 1 | 1 |
| Tartan with overchecks | 1 | 1 |
| Madras | 2 | 2 |
| Fine stripes | 1 | 2 |
| Medium and wide stripes | 2 | 3 |
| Uneven stripes | 2 | 2 |
| Colour block | 3 | 4 |
| Logo on patterned cloth | 2 | 1 |
| Placed detail | 3 | 2 |
| Solid | 4 | 4 |
| Print | 3 | 3 |

| Garment | Tuning | Held-out |
|---|---|---|
| Shirt | 11 | 8 |
| Tee or polo | 7 | 10 |
| Knit or sweatshirt | 3 | 4 |
| Jacket | 3 | 3 |
| Trousers | 5 | 3 |
| Shorts | 1 | 2 |

| Photo condition (a photo can have several) | Tuning | Held-out |
|---|---|---|
| Creased, unbuttoned or not laid square | 11 | 19 |
| Plain backdrop | 11 | 12 |
| On a hanger | 13 | 8 |
| On a floor | 7 | 11 |
| Tidy flat-lay from above | 7 | 7 |
| Warm or mixed light | 6 | 5 |
| Studio or catalogue | 5 | 4 |
| Standing angle | 2 | 7 |
| Demo closet (tidy) | 4 | 1 |
| Busy room | 1 | 2 |
| On a bed | 0 | 2 |
| Dim | 1 | 0 |

Gaps, accepted by the owner: no pale check by a bright window, no dark plaid in dim light, no big plaid on a floor,
no fine stripes on a small photo; five groups have one photo a half. **Open-licence photos**: none were used; the
demo closet's are credited in `backend/closet/demo_data/CREDITS.md`.

## How to run it again

From this folder, with the backend's requirements installed and Claude Code signed in: `python freeze.py` (once),
`python run.py prep --half tuning`, `bash run_half.sh tuning D-small`, `python judge.py packs`, the judges (briefs
in this conversation's record), `python judge.py collect`, `python analyse.py`, `python sheets.py`. Part 2:
`python run.py describe F --half <half> --runs 1,2,3` (and `arm-a`, `describe B`, `describe C-sonnet` on the
held-out half), then `python judge.py packs --half <half> [--round r2] --rubric A,B,C-sonnet,F --pair A,B,C-sonnet,F
--steady B,C-sonnet,F`, `collect`, `analyse.py` and `sheets.py` with the same `--half` and `--round`. Everything
private stays under `bench/private/garment_loop/`.
