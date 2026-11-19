# Is the traced front view of a shoe ever shown on the As worn figure?

Read-only investigation of /home/user/daily-clother. Nothing was modified. Paths: the drawing modules live in
`backend/closet/drawing/` (not `backend/closet/`).

## Verdict

**It is shown, but only when a shoe has no Claude drawing.** It is never shown alongside or over a Claude
drawing, and the A/B picker cannot bring it back once a drawing exists. For a typical user with a route to
Claude who adds a new pair today, it shows only during the 4 to 10 minutes between the trace finishing and the
Claude drawing finishing. It stays on screen with no end date in these cases: shoes traced before the drawing
feature arrived (no drawing until the owner taps "Draw again"), the demo's grey runners, a drawing that failed
three times or whose photos could not be sorted, no route to Claude, and the monthly limit (until it resets).

In every one of those cases, removing it leaves the **template front view**. That fallback already exists and
works: untraced shoes, refused traces, "Use the plain drawing" and sandals all use it today, and the line-up
scored it 8/10, against 3/10 for placed traces. The one thing lost is colour fidelity on multi-coloured shoes
in those fallback cases: the template is the item's single colour plus its style details, where A/B painted the
traced panels.

**Recommendation: safe to remove. The fallback is acceptable, not worse.** Confidence is high on the code paths
(each one was traced below). I have no data on how many of the owner's real shoes sit in the "traced before
drawings, never redrawn" state. That number decides whether they would notice anything, and tapping
"Draw again" on those shoes fixes it.

## 1. What the figure draws for a shoe, in priority order

Every figure (`illustrations.outfit_figure` at illustrations.py:327-340) builds its pieces with
`illustrations.describe(row)` (illustrations.py:111-129). That function attaches:
- `drawn=drawn_of(row)` (illustrations.py:166-176): `items.drawn` as JSON, for a shoe category. It is kept
  whatever `drawn_state` says, including while a redraw is running or after a redraw failed.
- `traced=front_of(row)` (illustrations.py:179-191): a `Chosen(trace, kind, front_look)`, only when `traced(row)`
  is non-None (illustrations.py:155-163). That needs `trace` set, `trace_state == 'done'`, `trace_plain` false and
  a shoe category. `kind` is `items.shoe_front` if it is valid; otherwise FROM_PHOTO when `front_look` is set and
  FROM_SHAPE when it is not.

`figure._placed` (figure.py:570-584) then calls `_place(..., traced, made=_drawing_of(piece))`.
`_drawing_of` (figure.py:587-596) returns None, and the front view is drawn instead, when there is no drawing or
`drawn.stored()` raises (the drawing was not made safe, or its sheet has no opening).

Priority:
1. **Claude drawing** (`made is not None`). The body comes from the drawing (figure.py:1803-1810). The front-view
   body is emitted only when `shoes.drawn is None` (figure.py:1811-1818). `front_shoe(..., traced=)` still runs
   at figure.py:622 and 1089, but only for its anchors (ankle, opening, instep, toe, width) and outline, used to
   place the drawing (`_on_drawing`, `_drawn_place`, `_drawn_box`, figure.py:1122-1150). Those anchors do not
   depend on the trace. The shape is always `STYLES[style]` from the tagger's style (frontshoe.py:276-289), and
   the opening, instep and width come from `_collar_ring` (frontshoe.py:421-427). `tr` only changes paint,
   `p`'s lace words and the unused `seen`/`rim` keep (`_opening(behind=)`, frontshoe.py:412; the figure never
   reads `.seen`/`.rim`). **So when a drawing exists, the trace has no visible effect at all.**
2. **Traced front A or B**: no usable drawing, and `front_of` is non-None, and `usable_trace` passes. That needs
   `gate.ok`, a non-sandal `traced.style` and a sane profile (frontshoe.py:917-933). `front_shoe` must also not
   be drawing a sandal (frontshoe.py:273). A (FROM_SHAPE) or B (FROM_PHOTO, plus `FrontLook` when there is one)
   follows from `kind` (frontshoe.py:270-293, 327-337, 386-388, 413-417).
3. **Template front view** (`front_shoe` with `tr is None`). This covers: no trace, a refused or failed trace,
   `trace_plain`, an unreadable trace, sandals, a trace the gate turned down, and a `_spec` that failed so
   `_plainest` was used (figure.py:579 passes `traced` only when `make is _spec`).
4. The bare feet (`bare_feet`) when there are no shoes at all.

## 2. When the traced front is what the user sees

The condition is: shoe category, trace done and not plain, gate ok, not a sandal, and **no readable Claude
drawing**.

| Situation | Does the traced front show? | How common for a normal user with a route, adding a pair today |
|---|---|---|
| Before the Claude drawing finishes | Yes, from the moment the trace is done until the drawing is done. Order of events: Add with "A shoe" (`items.add` calls `shoeviews.changed`, items.py:237-238), then the cutout and the description. The trace waits for sorting (`SORTING_FIRST`, tracejobs.py:42), and sorting runs about 10 s after the last photo plus one Claude call. Then `first_sorted` (shoeviews.py:133) puts the shoe in the drawing queue while the trace runs in the cutout queue, usually in under a minute. The drawing takes 4 to 10 minutes (shoedraw.py:66), one shoe at a time. | **Every new pair, for about 4 to 10 minutes**, longer with several new pairs queued. It is seen only if the owner opens a figure in that window. |
| No route to Claude (no API key and no plan, or the key switched off) | Yes, for as long as that lasts. Sorting sets `views_error` (NO_ROUTE, shoeviews.py:251-256), which lifts `SORTING_FIRST`, so the trace runs. The drawing waits (shoedraw.py:461-463). Note that without Claude the shoe is not described either, so it is a shoe only if the owner set its category. | Rare for this user. |
| Monthly limit reached | Yes, until the limit resets or is raised (LIMIT note). | Occasional, and temporary. |
| Drawing failed three times (`drawn_state` failed, `drawn` NULL) | Yes, until "Draw again" succeeds. | Uncommon. No failure rate was measured. |
| Drawing exists but `drawn.stored` raises | Yes (figure.py:592-596). | Very rare: a defensive path. |
| Photos could not be sorted (`views_state` failed: WAIT_UNSORTED) | Yes: `due()` needs `views_state = 'sorted'` (shoedraw.py:279-284). | Rare. |
| A shoe that is a shoe but has `views_state` NULL (added as a plain piece and then tagged or set to a shoe category, or added when Add's own sort fell back to "piece", app.py:1232) | Yes, with no end date. Tagging marks it for tracing (items.py:346; `tracejobs.answered`), but nothing ever sorts it or draws it until the owner adds or removes a photo or taps "Draw again". | Uncommon. Add normally classifies shoe photos as "shoe". |
| **Shoes traced before the drawing feature** (migration 0027: "nothing is drawn for the shoes kept before this until the owner asks"; shoeviews.py:24-25) | Yes, with no end date. | Does not apply to a new pair, but it is the main real-world case for an existing closet. The feature is about 3 days old (decisions dated 15 to 17 Nov 2026). |
| Demo closet | Yes, for **Grey runners** (trace, no drawing, no `front_look`, so view A). The demo's Brown boots have a demo drawing, so the drawing shows. The other demo shoes have no trace and get the template. | Always, in the demo. |
| Owner picks A or B in Fix the details | Only changes which traced view shows **when there is no drawing**. With a drawing, the picker is still shown (ShoeTrace.tsx:96-121, rendered at line 183 whenever the shoe is traced and not plain) but changes nothing on the figure: a misleading no-op today. | Picking does not force the traced front over a drawing. |
| "Use the plain drawing" (`trace_plain`) | No: template. | n/a |
| Sandals, or a trace the gate refused | No: template. | n/a |

## 3. If it were removed

**What shows instead:** in every row above, the template front view. That is the same code path untraced
shoes use today, covered by `test_an_untraced_shoe_is_drawn_exactly_as_before` (a digest) and the template
rules. DECISIONS.md:886 already says "a shoe with no photos, or whose drawing fails, is drawn from today's
template". Placement of Claude drawings is unchanged, because the anchors never depended on the trace. Hems and
socks are unchanged too: DECISIONS.md:980 already treats template and traced alike.

**Orphaned if removed:**
- DB columns `items.shoe_front` and `items.front_look` (migration 0025). Leave them in place and stop reading
  and writing them. No migration is needed (a new migration would only be to drop them, which isn't
  recommended).
- `photos.view` 'front'/'top' **stays**: sorting and the Claude drawing use it.
- Endpoints `PUT /api/items/{id}/trace/front` (app.py:739-744) and `GET /api/items/{id}/trace/front.svg`
  (app.py:746-751).
- Item payload `trace.front` (tracejobs.py:118-122; frontend types.ts:221-232 `ShoeFront`).
- UI: the `FrontChoice` A/B picker and `FrontPhotoButton` "Add a front photo" (ShoeTrace.tsx:67-121, used at
  line 183); `FRONT_VIEWS`, `frontPreviewUrl` and `FrontKind` (shoe.ts:29-39); `api.setShoeFront` and
  `api.addShoeView` (api.ts:225-244; `addShoeView` has no other caller, and `ShoePhotos.tsx` uses
  `addShoePhoto` for extra photos); the `.shoe-front*` CSS (Shoe.css:41-49).
- No settings keys involved: `shoe_front` and `front_look` appear only in the files listed.

**Shared versus exclusive code:**
- *Shared, and it stays.* All of frontshoe.py from line 1 to 821: `front_shoe`, `STYLES`, `_interp`,
  `_half_width`, `_hull`, `_collar_ring`, `_View`, `_opening`, `_details`, `bare_feet`, the sandal code and the
  constants. These are used by `traced.py` (side view: `LENGTH`, `STYLES`, `_interp`, traced.py:18-22, 203-220),
  `turned.py` (the Claude drawing's 3D turn: `BALL`, `LENGTH`, `STYLES`, `_half_width`, `_interp`, `_hull`,
  `ANKLE_*`, `INSTEP_U`, `_collar_ring`, `SHAFT_RIM`), `trace.py` (`LENGTH`) and `figure.py`. Nothing below line
  822 is used by the side view, `sideshoe.py`, `traced.py`, `trace.py` or `turned.py`.
- *Exclusive to the traced front.* frontshoe.py:822-1768 (the section header "a traced shoe (#192, stage 2c)",
  `PAINT_STEP_CM` through `MARK_ROOM`, `FROM_SHAPE`/`FROM_PHOTO`, `Chosen`, `FrontLook`, `_see`/`SEE`,
  `usable_trace`, helpers `_lerp` through `_area`, `_Raster`, `_merge_small`, `_sole_bands`, `_Traced`); the
  `traced`/`kind` branches inside `front_shoe` (lines 256, 261-265, 270-273, 290-294, 297, 300, 327-337,
  386-388, 412, 413-415, plus `tr is None and` guards at 338, 342, 347, 400); `_details(traced=)` (line 594);
  `_opening(behind=)` (lines 516-517). All of frontlook.py (164 lines). `_View.warp` (lines 191-205) is already
  dead: nothing passes `warp`.
- **The traced side view (closet picture) does not depend on any of this.** `illustrations.make` draws it via
  `sideshoe.drawing(TracedShoe...)` (illustrations.py:225-228). The trace record (`items.trace`), `trace_fixes`,
  `trace_plain`, Re-trace and the Fix-the-details colour and mark controls all stay.

## 4. Cost at add time when it is never shown

- **No Claude call.** `frontlook` and the traced painting are local.
- **Extra CPU per trace.** Once the side photo passes the gate, `tracejobs._look` (tracejobs.py:248, 276-289)
  reads the front or top photo with `frontlook.measure`. That runs a second segmentation (the cutout model,
  then GrabCut) on that photo, at most 900 px. It happens for every shoe with a front or top photo, which is
  typical now that Add takes up to six photos. Seconds of CPU, not measured.
- **Extra full retraces.** `shoeviews.look_moved` (shoeviews.py:90-95), called after sorting (line 194), after
  an owner's view answer (line 213) and on photo add or remove (shoes.py:206, 236), clears `front_look` and
  **re-runs the whole side trace** whenever the photo read for the front view changes. At first add the trace is
  usually still waiting, so it costs nothing extra. Later, answering a view question or adding or removing a
  front or top photo re-traces the side view only to re-read the front look.
- **Every figure render with a traced, drawn shoe.** `front_shoe(traced=)` runs at least twice (figure.py:622,
  1089). Each run does `_Traced.of`, `on_template` and the painting (72x16 sampling cells), and the result is
  thrown away except for anchors the trace doesn't affect. Not measured: the sandbox has no backend venv.

## 5. Removal boundary

Backend:
- `drawing/frontshoe.py`: delete lines 822-1768 (about 947 lines). In `front_shoe`, drop the `traced`/`kind`
  parameters and every `tr` branch (about 30 lines); drop `_details(traced=)` and `_opening(behind=)`; optionally
  drop the dead `_View.warp`. Keep the "no trace" behaviour byte for byte, so `UNTRACED_DIGEST` must not change.
  About 990 lines removed.
- `drawing/frontlook.py`: delete (164 lines).
- `drawing/figure.py`: remove `Piece.traced` (line 384) and `Placed.traced` (line 404), plus the `traced=`
  plumbing at lines 579, 599, 622, 629, 1090 and 1818 (about 10 lines). Update the module docstring if it
  mentions the trace.
- `illustrations.py`: delete `front_of` and `front_preview` (lines 179-214); drop `traced=shoe`/`front_of` from
  `describe` (lines 119, 123, 129); drop the frontshoe imports of `FROM_*` and `Chosen`; trim the docstrings at
  lines 15-19 and 115-116 (about 45 lines).
- `tracejobs.py`: delete `look_photo` (lines 80-85 in the 130+ block, that is file lines ~209-215), `_look`
  (lines 276-289), the `look` call (line 248), `front_look` in the UPDATE (lines 265-267: write NULL or leave the
  column alone), `run.look` (lines 197-201 of the block, file lines 326-330), `front` in `shown()` (lines 118-122)
  and the docstring (about 35 lines).
- `shoeviews.py`: delete `look_id` and `look_moved` (lines 85-95), the `before = look_id(...)` captures and the
  calls (lines 186, 194, 202, 213), and the docstring paragraph at lines 18-21 (about 20 lines).
- `shoes.py`: delete `FRONTS` (line 19) and `set_front` (lines 123-130); drop the `look_moved` and `before` lines
  around 206 and 236 (about 15 lines).
- `app.py`: delete the two endpoints (lines 739-751); keep `views_soon`, but fix its docstring (line 761) and the
  comment at line 798 (about 15 lines).
- Migrations: **none**. Leave `shoe_front` and `front_look` unread. A future migration could drop them, but
  that isn't recommended.
- Demo: no change needed. Grey runners keep their trace (side view) and get the template front. Optionally give
  them a demo drawing.

Frontend:
- `ShoeTrace.tsx`: delete `FrontPhotoButton` and `FrontChoice` and the line 183 usage (about 57 lines), plus the
  imports `FRONT_VIEWS` and `frontPreviewUrl`. `shoe.ts`: lines 29-39. `api.ts`: `setShoeFront` and
  `addShoeView` (about 14 lines). `types.ts`: `ShoeFront` and `front?` (about 12 lines). `Shoe.css`: lines 41-49.
  `shoe.test.ts`: lines 4-5 imports and 62-69. `e2e/20-shoe.spec.ts`: the front-view block at lines 308-327
  (about 20 lines).

Tests:
- `test_frontshoe_traced.py` (845 lines): delete the traced cases. **First move the template tests** into, say,
  `test_frontshoe.py` (about 150 lines): `UNTRACED` and `UNTRACED_DIGEST` with
  `test_an_untraced_shoe_is_drawn_exactly_as_before` (lines 69-87); the four rules (collar back before the leg,
  nothing hides the leg, details on the shoe, no horns) restricted to the template and no-show shoes in
  `every_front_shoe` (lines 402-516 and 810-815, keeping `after_the_leg` and `turns`);
  `test_a_no_show_cut_lowers_the_collar_and_the_opening` (lines 786-807); and
  `test_no_point_of_a_low_collar_sticks_up_beside_the_bare_ankle` (lines 818-845). DECISIONS.md:859 requires
  these rules to keep a test, so this is not deleting tests to make a change pass: those tests would cover only
  removed code. About 690 lines net.
- `test_frontlook.py`: delete (82 lines).
- `test_tracejobs.py`: line 386 (`describe().traced == Chosen(...)`): rewrite to assert the figure does not get
  the trace, or delete; lines 477-560 (the migration columns, choosing the front view, the front photo read, the
  reader that can't read, the real reader): delete, and keep the column check only if wanted (about 85 lines).
- `test_shoeviews.py`: lines 528-586 (the front-view photo is read, newest of two): delete (about 58 lines).
- `test_shoe_main_photo.py` line 216: drop the `look_photo` assertion.

Tools, bench and docs:
- `tools/make_traced_front_sheet.py` (240 lines): delete. `bench/experiments/shoe_front/` imports
  `closet.drawing.frontlook`/`frontshoe` (`common.py`, `drape.py`, `page_assets.py`): delete it, or mark it
  frozen (it is not run by `bench/tests`). `docs/screenshots/traced-front-*.png`, `shoe-front-choice.png` and
  `traced-marks-*.png`: delete or leave as the record.
- `docs/DECISIONS.md`: add a row: the traced front view is removed; a shoe without a usable Claude drawing gets
  the template front; the stage 2c rows (lines 842-859) and lines 839, 913 stay as the record. `docs/API.md`
  lines 47, 69, 70, 74: remove the endpoints and `trace.front`. `README.md` lines 395-400: remove the two-ways
  paragraph. `AGENTS.md` line 39 ("the front view on the figure"): still true for the template. The backlog
  belongs to the orchestrator (AGENTS.md:74). Update `docs/assessment/repo-bloat.md` item 3.

**Estimated total:** about 2,500 lines removed (about 1,190 production backend, about 130 frontend, about 900
tests, 240 tools, plus the bench experiment and the screenshots).

### Optional follow-up the owner may want

To avoid the "old shoes stay on the template" step, a one-off queue could draw shoes that have photos but no
drawing. That costs about $2 each on the API key (`shoedraw.ABOUT_USD`), so it is the owner's call; tapping
"Draw again" per shoe does the same.
