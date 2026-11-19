# The garment loop test: design, fixed before any photo is seen or any arm is run

Written 18 November 2026 by the session running `PLAN.md`, before the owner's photos arrived. Anything changed
after this point goes in the log at the end, with its reason; the held-out half is run once, with whatever the log
says at that moment.

## 1. The test set

**Sources.** The core is photos the owner supplies (kept in `bench/private/garment_loop/`, never committed). The
demo closet's five garment photos are tidy controls (its two shoe photos are not garments and are left out). No
open-licence photos are collected unless the owner asks for them to fill a gap; if so, each is listed with its
source and licence in `MANIFEST.md` here.

**What was asked for** (46 photos, so that at least 40 pass the bar; the bar is `PLAN.md`'s "the kind of photo a
person really takes"):

| Group | Photos | Spread over |
|---|---|---|
| Gingham and tiny checks | 3 | shirts, shorts |
| Small checks, windowpane, tattersall | 3 | shirt, jacket, trousers |
| Medium plaid, flannel | 3 | shirt, overshirt, lounge trousers |
| Buffalo and huge checks | 3 | shirt, jacket, lounge trousers |
| Tartan with thin overchecks | 2 | shirt, trousers |
| Madras | 2 | shirt, shorts |
| Fine stripes, pinstripes | 3 | shirt, trousers, tee or polo |
| Medium and wide stripes | 4 | tee, knit, rugby or polo, shirt |
| Uneven stripes | 3 | knit, shirt, shorts |
| Colour block | 4 | jacket, sweatshirt, raglan tee, shorts |
| Logo or crest on patterned cloth | 3 | rugby, plaid shirt, polo |
| Placed details (a chest band, a contrast pocket or yoke) | 2 | polo or tee, shirt |
| Solids (controls) | 5 | tee, shirt, knit, trousers, jacket |
| Prints the form cannot express (controls for "say less") | 6 | shirts, trousers or jacket, shorts |

Stripes both ways (at least three running down, three across). Photo conditions, a photo counting in several: on a
bed (about 10, some on patterned bedding), on a floor (8), on a hanger (10), a busy room around it (10), dim (8),
mixed or warm light (8), creased, unbuttoned or not laid square (most), from a standing angle (12), and 5 or 6 tidy
flat-lays from above as marked controls. The known hard cases are asked for by name: a pale check by a bright
window, a plaid with a repeat over a third of the garment on a floor, a dark plaid in dim light, a creased plaid on
a hanger, fine stripes on a small photo.

**Frozen** once the owner's photos are in and checked against the bar. Each photo gets an opaque name (`g01`...);
the table of the set by group, garment and condition (counts only) goes in `README.md`. A photo left out is
counted with the reason, never replaced by a studio shot or a made-up image.

## 2. The split

Decided now, applied once when the set is frozen, recorded in `bench/private/garment_loop/split.json`:

- The strata are the groups above (the demo's plaid flannel in "medium plaid", its madras in "madras", its jeans
  and marl sweater in "solids", its graphic tee in "placed details").
- Already tuned on, so **tuning half only**: the demo's plaid flannel and madras (rounds one to four of
  `described.py` were tuned on them), and any of the owner's six plaid shirts from 17 and 18 November if resupplied.
- In each stratum, the rest are shuffled with `random.Random(20261118)` (strata in the order of the table, items by
  their opaque name), then sorted by garment kind (top, knit, outer, bottom) with the shuffle breaking ties, and
  dealt alternately, held-out first. So an odd one goes to the held-out half, each half gets a spread of garments,
  and no one chose which photo went where.
- Reported: the counts per half by group, garment and condition. If a group has fewer than two in a half, the
  report says the group is too thin to judge on its own in that half.

## 3. The surface form

One optional field, `surface`, added to the app's description call in place of the plaid-only field. It covers
bands one way, bands both ways, blocks of colour, and "cannot be expressed":

```
surface:
  kind:      plain | stripes | plaid | blocks | other
  bands:     [{color: "#rrggbb", width: int}]   stripes and plaid: one repeat, ground first (described.py's form)
  direction: horizontal | vertical              stripes only: the way the stripes run
  size:      tiny | small | medium | large | huge   repeats across the ruler (below); used only when the photo
                                                  cannot settle the scale
  blocks:    [{part: yoke | sleeves | collar | pocket, color}]   blocks only: parts in another colour than the body
  colors:    [{color, share: int}]               plain, blocks and other: the main colours, largest first
```

How each kind is drawn, with the app's own templates, anchor points and house style:

- `plain`: the cloth in `colors[0]`.
- `plaid`: `described.tile` with its defaults (scale from the photo, widths from the photo, strength 0.8).
- `stripes`: the app's kept `stripes` kind (`drawing/stored.py`), the described repeat laid over the garment as
  many times as the scale says; the scale from the photo the same way as a plaid's, along the one direction the
  stripes repeat; widths as described (there is no photo-widths rule for stripes, and writing one would be
  tuning).
- `blocks`: the template's `colorblock` parts in the block colour, the body in `colors[0]`. A block the drawing
  has no part for (a panel across the chest) cannot be drawn: Claude is told to use `other` then.
- `other`: no pattern; the cloth in `colors[0]`, and the item page's "not in the drawing" note. Saying less.

**The ruler** for every count: the chest from underarm to underarm on a top (the app's landmarks call), the
waistband's width on trousers and shorts (read from the cutout's outline). A count is "how many repeats fit in one
ruler's length", measured the way the pattern repeats: across for vertical stripes and plaids, down the body for
horizontal stripes.

## 4. What every arm shares

For each garment, once, before the arms: the app's cutout (`closet/cutout.py`, both models as the app uses them),
the app's own description (the app's describing model, its unchanged form), and, for tops, the app's landmarks
call. **Every arm's drawing uses that one description for the garment's shape** (its template, collar, sleeves and
so on); the arms differ only in the surface. A drawing is the app's item drawing (`drawing/item.py`) with the
arm's surface as its fill, rendered through Chromium (`starting_points/shot.js`).

| Arm | Surface from | Runs |
|---|---|---|
| A | the app today: `measure` on the cutout for the pattern the description gives, kept where it passes its own check, else plain colour | 1 |
| B | the app's description call with `surface` added, the describing model (`tagging`, effort as `models.json`) | 3 |
| C-sonnet, C-opus | the same call on the `sorting` and `drawing` models, effort as `models.json` | 3 each |
| D | the loop below, starting from B's answer | 3 chains |
| E | the best of D's three chains by the loop's score | no calls of its own |
| D-small (declared side arm) | the loop with the describing model correcting, tuning half only; run on the held-out half only if within one rubric point of D | 3 chains |

Arm B, C and every round of D see the cutout only, as the app sends it.

## 5. The loop (D and E)

- **Start**: B's answer from the same run (chain k starts from B's run k), so D is paired with B and its three
  chains are independent.
- **Who corrects**: the `drawing` model at medium effort, through the plan route: the model and effort of the app's
  own render-and-correct loop for shoes (`tagger/shoedrawing.py`, the owner's choice on 16 November).
- **What it is shown**: one image: the cutout on the left and the drawing on the right, each cropped to its
  garment and scaled to the same height, on mid-grey; and the current `surface` as JSON. Nothing else: no score, no
  earlier rounds, no photo beyond the cutout.
- **What it may change**: a patch, as a structured answer: any of the surface's fields, each replacing the current
  value whole, plus `scale`, a factor of 0.5 to 2 on the size of the repeat as drawn now (so a relative "the checks
  are too big" can be acted on even where the photo set the scale). Not the garment's shape or description. An
  empty patch means "it matches". One answer per call, kept as given; the patch is made safe by the same rules as
  a description (`described.read`).
- **How many**: three corrections. D1, D2, D3 are what the loop would keep after one, two and three; each round's
  own version is kept too, to see convergence.
- **Which version is kept**: the one with the best score below among round 0 and the corrections so far, so the
  loop can never keep something its own measure finds worse than its start.
- **E**: the best by the same score over D's three chains. Its own steadiness needs six more chains a garment; they
  are run on the held-out half only if E is the arm to recommend and D misses the steadiness line.

## 6. The loop's score (how "best" is measured)

Code only; a judge's score is never used inside the loop. Two parts, each 0 to 1, averaged:

- **Colour**: the colours of the garment's pixels in the cutout (smoothed over 2 px, its edge eroded) against the
  drawing's cloth (its rendered garment, outline eroded away), as `steady.py`'s make-up measure: per CIE Lab
  channel, the mean gap between the two sorted pixel lists, added up with lightness counted half (photos differ in
  exposure). The part is 1 minus that over 30, not below 0.
- **Structure**, for stripes and plaid: does the drawn repeat explain the photo where it is? The garment is cut
  into windows about 1.5 repeats a side (at most 24, each at least 80% garment); in each, the drawn repeat at the
  scale the drawing uses is matched against the photo at every offset and at turns of up to 15° (normalised
  correlation of the light-evened signal, `common.soft_signal`), and the part is the median of the windows' best
  matches. For plain, blocks and other, the part is a fixed 0.35, the app's own bar for a whole-garment measure:
  so a drawn pattern beats saying less only when it explains the photo better than that.

These are starting values. They may be tuned on the tuning half only, and every change is logged below.

## 7. The truth, the judge and the measures

- **Reference sheets**: written before any arm runs, by a subagent on a model with better vision, from the
  original photo only, one sheet a garment, in a fixed form: kind; ground colour and each other colour with a
  hex and rough share; one repeat's band order each way; the count of repeats across the ruler, with the counting
  written out; anything placed; what is uncertain. Never shown to a model inside an arm, nor to the judge.
- **Blind rubric**: the same kind of subagent sees the original photo and one drawing side by side, under a random
  name, and scores 0 to 3 on ground colour, other colours and shares, scale, structure, and "would the owner pick
  it out of a closet of forty", with one line naming the main fault. Judged: A, B, C-sonnet, C-opus, D1, D2, D3 and
  E (run and chain 1), and D-small on the tuning half. Every pair twice, by separate subagents, each pass in its
  own shuffled order; a pair whose two passes differ by 2 or more on any line is judged a third time and the median
  kept. Agreement between passes reported.
- **Pairwise**: per garment, all judged drawings under random letters beside the photo, ranked best to worst.
- **Steady (judge)**: per garment and arm, the three runs' drawings beside the photo: are all three the same
  garment?
- **Measured**: scale error against the sheet's count; colour-share distance against the sheet; `steady.py`'s two
  numbers over three runs; the loop's own score per round.
- **Confidently wrong**: the share of drawings scoring 0 on ground colour or on "pick it out" while showing a
  pattern; and on solids and prints, the share drawn with any pattern.
- **Does the corrector see the faults**: for each round-0 drawing the judge faulted, whether the first correction
  changed the field the judge's fault names.
- **Cost**: calls, input, cache and output tokens, and seconds, per garment and arm; dollars at `models.json`'s
  prices.

**After the tuning half, stop and report** if D and E are not clearly ahead of the better C arm (clearly: a median
rubric total at least one point higher, and no more confidently wrong), or if the first correction changes the
field the judge faulted on fewer than half the faulted drawings.

## 8. Expected size and cost

About 50 garments: 50 base descriptions and 50 landmarks calls; B 150, C 300, D 450 corrections; D-small about
225 on the tuning half; any extra E chains on the held-out half up to 450. Some 1,200 to 1,700 calls through the
plan route, run three at a time: about five to eight hours, longer if the plan's usage limit pauses it. A
correction call on the `drawing` model is likely to cost 5 to 10 US cents at the API key's prices, so the loop as
the app would run it (one chain of three) is likely to pass the plan's flag of a few cents and about two minutes a
garment; the measured numbers will say.

## Log of changes

All before any arm was run and before any drawing of a test photo existed.

1. **The split's deal** (section 2). The owner's 55 photos came in (46 pass the bar; the 9 left out are all
   studio or catalogue shots). Dealt alternately within each group after sorting by garment kind, as written, all
   five jackets went to the tuning half: in a group of two, the later kind always fell to the second place. With
   none held out, "no garment type scores worse" could not be checked for jackets. Replaced by a balancing deal
   (`freeze.py`): each photo, in its group's seeded shuffle (same seed), goes to the half with fewer of its group
   so far, then fewer of its garment kind, then (for a known hard case) fewer hard cases, then fewer overall, then
   the held-out half. The hard-case key changed nothing (group and kind settle every choice first): the four photos
   marked "creased plaid on a hanger" are all in the tuning half; the held-out plaids are creased on floors, a bed
   and at an angle. Accepted as it came out.
2. **One photo moved group** from the contact sheet before freezing: three wavy bands with no repeat (filed as
   uneven stripes) are colour blocking.
3. **Bottoms' tile size**: `surface.WAIST_PER_OUTLINE` is per kind (trousers and jeans 0.885, shorts 0.73),
   measured on the demo closet's drawings; one value of 0.86 was a guess.
4. **Strength 0.8 on every described colour**, not only a plaid's (plain, blocks and other too): one rule for
   described colours, written into `surface.py` before any run.
5. **The owner's decisions on the set, 18 November** (before any arm ran): the gaps are accepted (no pale check
   by a window, no dark plaid in dim light, no big plaid on a floor, no fine stripes on a small photo; five groups
   have one photo a half). The 9 studio and catalogue photos are **in** the set, because the owner may import
   online photos of their own garments; every table also reports them as their own row beside the home photos.
   The split was dealt again with them (60 garments, 30 and 30), with "fewer studio photos" as a key after garment
   kind so they spread over both halves (5 and 4).
6. **Opus, not a stronger-vision model, for the visual helper jobs** (the owner's decision: Fable was too costly
   here). One Fable batch had already written 9 reference sheets; they are kept. The other five Fable batches were
   stopped by Fable's safeguards (`reasoning_extraction`) before writing anything; their brief had asked for the
   counting written out step by step, and the Opus brief asks for the pixel positions of the counted line instead.
   **Caveat:** the judges and most sheet writers are the same model as the loop's corrector (`drawing` role) and
   C-opus, so a fault that model cannot see will be missed by both the loop and its judge; the measured lines
   (scale against the sheet's count, colour shares, run-to-run) do not share that blind spot.
7. **After the tuning half (the run stopped there; `README.md`), the owner chose to take one description from
   Sonnet with the three gaps every arm shared fixed to the held-out half.** This is a new arm, **F**: Sonnet
   (`sorting` role, its effort in `models.json`), one call per run, three runs, with the **second surface form**
   (`surface.Surface2`, drawn with `drawn(..., second=True)`). The first form and arms A, B and C are unchanged, so
   they draw as they did. The three fixes:
   - **Bands across the body** for blocks (`panels`: where each starts and ends from collar to hem, at most six),
     drawn as one garment-sized picture laid over the template, the drawn garment's proportions measured from a
     plain drawing of it; the yoke, sleeves, collar and pocket parts stay.
   - **Prints pieced by the app**: kind "other" is drawn with the app's own print piecing from the photo
     (`measure`'s print path, as arm A draws a print); with no piece, the main colour as before.
   - **Fine patterns**: a size word "micro" (more than 20 across; "tiny" now 9 to 20), a cap of 150 repeats
     across instead of 16, and for a pattern Claude calls micro or tiny, the repeat read first from a 400 px square
     of cloth at the photo's own detail (`fine_repeats`, used only when it finds at least 12 across).
   Checked on the tuning half first (prompts and rules may be tuned there only, every change logged here). Then the
   held-out half is run once: A, B, C-sonnet and F, judged by Opus in one shuffled round so the four are compared
   on the same footing.
8. **F checked on the tuning half and frozen unchanged** (judged with A, B and C-sonnet in a second round, `r2`).
   One rule was considered and not adopted: letting the size word override the photo's whole-garment reading when
   the two disagree (a gingham and a windowpane read at 1.9 and 1.4 repeats against counts of 25 and 30.5, where
   Sonnet said "small"). The fine reading found nothing on either photo (one dim, one at an angle). The override
   would have helped those two and a third partly and harmed a broad-striped sweater where the photo is right: a
   threshold tuned on four garments, which the plan does not accept. F runs on the held-out half as it stands.
