# Drawing a garment's surface by describing it, rendering it, and correcting it against the photo: test plan

Written 18 November 2026 with the owner, for a separate session to run. Nothing here is app code and nothing in the
app changes during this test. Read `AGENTS.md`, then `docs/DECISIONS.md` ("Patterns drawn from the photo", including
"A plaid drawn from Claude's description") and the pattern items in `docs/BACKLOG.md`, before starting.

## The question

The app recognises a garment into a fixed vocabulary and draws each part with hand-written code. For patterns it
also measures the cloth from the photo with code written per pattern. That measuring is brittle on ordinary photos,
and fixing it photo by photo does not converge.

**Can one general loop replace per-pattern measuring: Claude describes the surface as parameters for the app's own
drawing code, the app renders it, Claude is shown the render beside the photo and corrects the parameters, a fixed
small number of times, and the best version by a measured comparison is kept?** Claude never writes the drawing;
templates, anchor points and house style stay the app's.

The owner's bar, in their words and mine:

- The drawing should be **accurate**, for a faithful picture of an outfit, because this is a fashion app that must
  look good, and because the owner wants it tuned as far as it will go.
- **Cost is a secondary concern**, one-time costs least of all. Report cost; do not optimise for it first.
- It must work for **anyone's clothes**, not the owner's six shirts. Thresholds tuned on a handful of photos are
  not acceptable evidence.
- **Never confidently wrong.** A drawing that says less (plain colour, a note) is better than one that shows the
  wrong garment.

## What is already known (so it is not learned twice)

All of this is from six of the owner's plaid shirts and two demo shirts, 17 to 18 November.

- **Measuring** (`backend/closet/patterns/measure.py`, `straighten.py`, `flatten.py`, `plaid.py`): on five plaid
  photos it had never seen, none measured at first and one crashed; after a long round, two measure well
  (agreement 0.85 and 0.86 with the photo), one is left plain, one has a cutout full of holes, one is drawn nearly
  black. The part that held up is the check at the end: the rebuilt repeat is laid back over the photo and refused
  when it does not explain it.
- **Describing, one shot** (`backend/closet/patterns/described.py`, tests in `tests/test_described_plaid.py`):
  Claude fills a short form (`plaid: {bands: [{color, width}], size}`) on the description call; the app weaves a
  tile from it. Four rounds:
  - Claude cannot judge the size of the checks, however asked (five ways tried; "medium" 11 times in 12). The size
    is read from the photo instead (`photo_repeats`: band spacing against the chest width between the landmarks'
    underarm points) and lands within about 10% of a hand count on five of six. That rule was tuned on those six.
  - Claude names cleaner, stronger colours than the cloth and twice named the wrong colour as the ground. Moving
    band widths toward the photo's colour shares helps two shirts; softening colours to 80% helps a little; full
    colour transfer from the photo harms as many shirts as it helps.
  - Two answers for the same photo differ: how much of each colour now agrees better, how the bands are arranged
    does not. Which drawing an item gets is partly luck.
  - With `tile`'s current defaults, four of six are recognisable and two are partly right.
- **Every description so far came from the app's describing model**, the smallest one, at low effort
  (`backend/closet/tagger/models.json`, role `tagging`). No stronger model has been tried on the surface. This is
  the cheapest untested explanation for the wrong ground colours.
- **Practical**:
  - There is no API key in a cloud session; the app's "Claude plan" route works (`claude -p`, see
    `backend/closet/tagger/claude_cli.py`). `starting_points/describe_cli.py` and `get_landmarks.py` are the
    scratch scripts that used it; `steady.py` measured run-to-run difference. They are starting points, not tools.
  - Thinking is counted as output: a 150-character answer cost 200 to 1,000 extra output tokens depending on how
    long the field text was.
  - The app sends the cutout, not the photo. A cutout can be wrong (holes where pale checks met a bright window).
  - Render SVG through Chromium (`starting_points/shot.js`; Playwright is pre-installed, do not install it). resvg
    draws the fuzzy edge of flannel pushed to one side.
  - The full backend suite takes six to fourteen minutes with `-n auto`.

## What to test

**H1. The loop beats one shot.** Rendering and correcting against the photo fixes what one shot gets wrong (ground
colour, colour strength, band order, scale) and makes separate runs agree.

**H2. A stronger describing model matters, with or without the loop.** If one shot from a stronger model is as good
as the loop from the small one, the simpler thing wins.

**H3. It is general.** The same loop, unchanged, works on stripes, checks of every scale, colour blocking and
placed details, and does no harm on solids and on prints the generators cannot express (where the right answer is
to say less).

### Arms

Run every test item through each arm. Keep every answer, render and token count per arm, item and run.

| Arm | What it is |
|---|---|
| A | The app today: measured where it passes its check, else plain colour |
| B | Described, one shot, the app's describing model, `described.tile` defaults |
| C | Described, one shot, the stronger models the app already lists (`models.json` roles `sorting`, `drawing`) |
| D | The loop: describe, render, show render beside photo, correct the parameters; 1, 2 and 3 corrections |
| E | D, run three times independently, keeping the version that scores best against the photo |

For D and E decide and write down before running: which model corrects (one the app can call through its routes),
what it is shown (the garment's cutout and the render at the same size and crop, side by side, nothing else), what
it may change (the parameters only, as a small patch), and how "best" is measured (start from the existing
comparison ideas: `flatten.agreement`, colour shares, `described`'s fit measure; a judge's score is for evaluation,
not for picking inside the loop).

For anything beyond plaid, the description needs a general surface form, not one form per pattern. Design the
smallest one that covers bands one way (stripes), bands both ways (plaid, check, gingham), blocks of colour, and
"cannot be expressed: main colours only". Reuse `described.py`'s weaving for the first two.

### The test set

At least 40 garments, more if they come cheaply, chosen before any run and not changed after:

- **Patterns**: plaids and checks from tiny (gingham) to huge (buffalo), tartans with thin overchecks, madras;
  stripes fine to wide, both directions, uneven; colour block; solids (controls); florals and other prints
  (controls for "say less"); a few with a logo or crest on patterned cloth.
- **Garments**: shirts, tees, knits, jackets, trousers, shorts; not only tops.
- **Photo conditions**: flat on a plain surface, on a bed, on a hanger, creased, dim, backlit, at an angle. Mostly
  ordinary phone photos, not catalogue shots.
- **Sources**: open-licence photos (the demo closet's photos in `backend/closet/demo_data/` and their
  `CREDITS.md` show the standard); record each one's source and licence in a manifest committed here, and keep the
  photos themselves under `bench/private/garment_loop/` (git-ignored). If the session's network cannot reach a
  source, say so and ask the owner; do not substitute made-up images for real photos.
- **The owner's own photos** (the six plaid shirts) join the set only if the owner uploads them to that session.
  They stay in `bench/private/` and never enter a commit, a log or a fixture.

Split the set in two before any run: a **tuning half** that prompts and rules may be adjusted on, and a **held-out
half** that is run once at the end. Report the two separately. A result that holds only on the tuning half is a
failure of H3.

### The truth each drawing is judged against

Before any arm is run, write a reference sheet per garment from a careful look at the photo: the ground colour and
each other colour with its rough share of the cloth, the order of bands in one repeat each way, the number of
repeats across the chest (counted, with the count written out), anything placed (a logo, a pocket in contrast
cloth), and what is uncertain. The sheets are the yardstick: they are never shown to a model inside an arm.

### Scoring

1. **Blind rubric.** A judge sees the photo and one drawing, not knowing the arm, in shuffled order, and scores
   0 to 3 on each of: ground colour; the other colours and their shares; scale; structure (band order, direction,
   crossings); and "would a person who owns this pick it out of a closet of forty". Every pair is judged twice;
   report agreement between the two passes, and re-judge where they differ by 2 or more.
2. **Pairwise.** For each garment, the judge ranks the arms' drawings against the photo, blind.
3. **Measured.** Scale error against the reference count; colour-share distance; run-to-run difference over three
   independent runs (`steady.py`'s two numbers); the loop's own score per correction round.
4. **Confidently wrong.** The share of drawings scoring 0 on ground colour or on "pick it out" while showing a
   pattern. This is the number that must not go up.
5. **Cost.** Calls, input and output tokens, and seconds per garment, per arm.

### Where a stronger vision model is used as a helper

The session running this plan may hand a small number of narrow, purely visual jobs to a subagent on a model with
better vision than its own, each as a self-contained brief with the images' paths:

- writing the reference sheets (including the counts);
- the blind judging and the pairwise ranking;
- a final close look at the result sheets before they are shown to the owner.

It is not used inside any arm unless that is declared as its own arm, because the app can only ship what its routes
can call. The judge is never told which arm made a drawing and never judges with the reference sheet's author's
notes about arms in view.

## What counts as success

On the **held-out half**, for arm D or E against arms A, B and C:

- **Recognisable**: at least 80% of patterned garments score 2 or more on "pick it out", and the median rubric
  total is at least 2 points (of 15) above arm B's.
- **Ground colour**: right (2 or more) on at least 90% of patterned garments.
- **Scale**: within 25% of the reference count on at least 80% of garments that have a repeat.
- **Never confidently wrong**: no more than 5% of patterned garments, and not above arm A's rate. On solids and on
  prints the form cannot express, the loop draws no pattern: 100%.
- **Steady**: of three independent runs per garment, the judge calls all three "the same garment" for at least
  90%; the measured run-to-run difference is at least a third below arm B's.
- **General**: no pattern family and no garment type scores worse under the loop than under arm A.
- **It converges**: the gain from the third correction is small beside the first; if drawings are still changing
  materially at three, say so.
- **Simpler wins ties**: if arm C is within 1 rubric point of D and E and meets the lines above, recommend C.

Cost is reported, not gated. Flag it for the owner's decision if a garment costs more than a few US cents or takes
more than about two minutes.

**Stop early and report** if after the tuning half the loop is not clearly ahead of one shot from a stronger
model, or if the correcting model cannot see the faults the judge sees (show the evidence: its corrections beside
the judge's notes).

## Rules for the session running this

- The hard rules in `AGENTS.md` hold: no real photos, personal data or secrets in commits, logs, fixtures or pull
  request text; nothing private leaves `bench/private/`; no new dependency without saying why.
- An experiment only: no change to the form the app sends, to `measure.py` or `patjobs.py`, to migrations or the
  frontend. New code lives here or, where it would be app code if adopted, in `backend/closet/patterns/` behind
  functions nothing calls, with tests on made-up cloth.
- One answer per call, kept as given. Never adjust an answer, a reference sheet or a score after seeing a drawing.
- Prompts and rules are tuned on the tuning half only, and every change to them is logged with its reason.
- Do not edit `docs/BACKLOG.md`. Do not open a pull request unless the owner asks.

## What to hand back

- `README.md` in this folder: what was run, the table of every measure per arm on the tuning half and on the
  held-out half, what was changed along the way and why, and a plain recommendation: adopt the loop, adopt a
  stronger one-shot description, or neither, with what the app would need (form fields, calls per item, where the
  render-and-correct step would run, what the owner would see while it runs).
- The manifest of test photos with sources and licences.
- Result sheets (photo, each arm's drawing, scores) under `bench/private/garment_loop/`, and their paths.
- What is uncertain, and the three garments each arm did worst on, shown.
