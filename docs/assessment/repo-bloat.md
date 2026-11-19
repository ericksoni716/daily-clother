# daily-clother: code bloat audit (read-only)

Audited at `b29309e` (2026-11-19). Nothing in the repo was modified. The clone is **shallow**
(`.git/shallow` present, 234 commits reachable, earliest 2026-11-15), so history findings cover
only that window; the full ~800-commit history is likely heavier still.

Method: static import graph from `closet.cli` (backend) and `src/main.tsx` (frontend, incl. dynamic
`import()`), every HTTP route cross-checked against frontend/e2e/test strings, vulture at 60% with
each hit re-grepped across backend, bench, tools, tests and packaging, CSS selectors grepped against
TSX, docs' backticked paths checked against `git ls-files`, git pack analysed blob by blob.
"Verified" = grep/graph confirmed; "likely" = judgement or partial evidence.

## Headline numbers

| | Files | Lines |
|---|---:|---:|
| All tracked | 844 | ~120k code (py/ts/tsx/css/js/sql) + ~6.3k markdown |
| `backend/closet` (app) | 164 | 46,689 |
| `backend/tests` | 86 | 31,018 (1,777 test functions) |
| `frontend/src` | 138 | 21,820 (323 unit tests) |
| `frontend/e2e` | 48 | 6,440 (145 Playwright tests, 1 worker, serial) |
| `bench/` | 86 | 10,351 (7,395 of it in `bench/experiments/`) |
| `tools/` | 15 | 3,523 |
| `packaging/` | 15 | 1,447 (1,014 in `packaging/spike/`) |
| `docs/` | 260 | 3,520 md + **253 screenshots, 45 MB** |

- **Classic dead code is small.** Every backend module is reachable from `closet.cli`, and every
  frontend file is reachable from `main.tsx`. Of 119 HTTP routes, one is called by nothing in the
  shipped app (`POST /api/outfits/suggest`). Functions with no references anywhere add up to about
  40 lines; functions used only by tests, about 60.
- **The bloat is superseded-but-still-wired pipelines plus experiment residue.** Shoes have **four
  drawing pipelines live at once** (template, traced side view, traced front A/B, Claude-drawn). Cloth
  patterns have **two** (measured from the photo, and Claude's description, adopted 18 Nov). Phase-0
  photo-fill code survives because the **demo generator still draws demo items with it**. Experiments
  are kept in `bench/experiments`.
- **Repo weight is almost all screenshots.** `docs/screenshots` is 88.6 of the 94.6 MiB of packed
  blobs in the shallow history (364 blob versions of 253 files). `traced-front-closeup.png` alone has
  8+ versions of about 3 MB each. 211 of the 253 screenshots are not named anywhere else in the repo
  (some names are built from templates, so this count is "likely"). **Playwright specs and tools write
  screenshots into `docs/screenshots`** (15 e2e specs), so every local e2e run dirties tracked files,
  and agents commit them.
- **Realistic removal: about 15–17k lines and about 50 MB from HEAD** with low or medium risk, plus
  about 7k more lines if the owner retires shoe tracing and the legacy measured-pattern path.

## Ranked candidates

| # | Candidate | Est. lines removed | Risk | Status |
|---|---|---:|---|---|
| 1 | `docs/screenshots`: stop e2e/tools writing into the repo (write to git-ignored `docs/screenshots/out/` or `frontend/test-results`), keep the ~42 referenced images, delete the rest; optionally rewrite history (filter-repo) to drop old versions | 211 files, ~32 MB at HEAD; ~85 MiB of history | Low (HEAD), Med (history rewrite: owner decision) | Verified (refs), likely (some names templated) |
| 2 | `bench/experiments/` (garment_loop, patterns, shoe_front, shoe_solid, shoe_drawn minus EXAMPLES): not collected by CI (`pytest tests` only), not imported by app/tests/tools. Move `shoe_drawn/EXAMPLES/*.svg` (used by `test_drawn.py`, `test_figure_drawn.py`, `make_demo.py`, `make_drawn_figure_sheet.py`) into `backend/tests/data/` or compare against `closet/drawing/shoe_examples/` directly | ~7,300 (52 files) | Low | Verified |
| 3 | **Done 19 November: removed** (see "The traced front view is removed" in DECISIONS.md; the template tests moved to `test_frontshoe.py`, the columns left unread). Traced shoe **front** on the figure (A "from the shoe's shape" painted by the trace, B "from your photo"): `frontshoe.py` lines ~835–1768, `frontlook.py`, front-preview code in `illustrations.py`, `PUT trace/front` + `GET trace/front.svg`, the A/B picker in `ShoeTrace.tsx`, `test_frontshoe_traced.py`, `test_frontlook.py`, `tools/make_traced_front_sheet.py`. DECISIONS says the Claude drawing "replaces" stage 2c and the line-up test **failed** (3/10 vs 8/10 for the template); today it is only the fallback for shoes without a Claude drawing | ~2,400 | Med (shoes never drawn by Claude fall back to the plain template front) | Verified wiring; replacement decision documented |
| 4 | Phase-0 photo fills and comparison styles: `fills.dominant_colors/snap_to_named/pick_swatch(+5 helpers)/measure_stripes` (~245 lines, used only by `bench/closet_bench/hardcases.py`, `bench.py`, bench tests), `illustrate` styles `flat`/`soft`/`traced` (+`trace_outline`, `_render_traced`; the app uses only `STYLE="line"`), `trace.to_svg` (bench only), `bench/closet_bench/{bench,hardcases}.py` and their tests. **Blocker:** `tools/make_demo.py` builds demo items with `closet_bench.hardcases.build_spec` (Phase-0 fills), so first port make_demo to the app's own pipeline (`drawing.item` + `stored`/patterns) | ~900–1,100 | Med | Verified |
| 5 | `packaging/spike/` + `.github/workflows/packaging-spike.yml`. Kept "for its ffmpeg proof", but BACKLOG says "Video sweeps are out (owner's decision)", and the real build bundles no ffmpeg | ~1,140 | Low | Verified |
| 6 | Move backend tests out of bench: `bench/tests/test_taxonomy.py` (1,126 lines, tests `closet.tagger.taxonomy` + `closet.drawing` through 6-line shims) and the tagger/route tests in `test_bench.py` go to `backend/tests`; then delete the 8 shim modules (`closet_bench/{templates,illustrate,fills,taxonomy,schema,tagging,routes,claude_cli}.py`) and the second pip install in CI | 0 net for the tests; ~50 shim lines; removes a CI step | Low–Med | Verified |
| 7 | `bench/closet_bench/cutout.py`, a forked copy of `closet/cutout.py` (56 differing lines). Only `make_demo.py` uses it (`load_photo`, `predict_mask`) | ~116 | Low | Verified |
| 8 | Whole shoe-tracing pipeline, if the closet tile stops being the traced side view (BACKLOG lists "whether the closet tile stays traced" as open): `trace.py` 1,056, `traced.py` 911, `sideshoe.py` 164, `tracejobs.py` 331, trace-fix endpoints, `ShoeTrace.tsx` 206, migrations stay; tests `test_trace` 493, `test_tracejobs` 572, `test_retake` (part), bench `trace_shoes.py` 569 + test 282 | ~4,500 beyond #3 | High (owner decision; changes closet tiles for shoes) | Verified wiring |
| 9 | Legacy measured-pattern path (stripes/plaid measured from the photo), now only for answers from before 18 Nov and when the owner overrides the pattern word: `patterns/stripes.py` 918, `straighten.py` 614, `flatten.py` 400, `plaid.py` 178, part of `measure.py`, plus their tests (`test_patterns.py` 585 etc.). Prints (`prints.py`) and `described.py` stay | ~2,100 + ~1,000 tests | High (old items would need re-describing; the owner-override path needs a replacement) | Verified wiring; decision needed |
| 10 | Look-at scripts in `tools/` with no test or CI use: `make_traced_front_sheet` (with #3), `make_shoe_sheet`, `make_hem_sheet`, `make_fit_shots`, `make_figure_shots`, `make_accessory_sheet`, `make_coverage_sheet`, `make_review_gallery` (goes through bench shims). Keep `make_demo`, `time_plan_route`, `style_demo_days` (tested), `make_figure_sheet` (tested), and the two shoe-drawing runners | ~1,000–1,600 | Low (owner uses some for review) | Verified unused by CI; likely residue |
| 11 | Dead endpoint `POST /api/outfits/suggest` (app.py 1012–1035) + its tests in `test_outfits.py` + API.md row. The frontend uses `/api/outfits/today` | ~70 | Low | Verified |
| 12 | Functions with no references anywhere: `fitting.quad_map`, `fitting.affine`, `measure.see_through_mask`, `measure.combine_masks`, `straighten._delta_e`, `surfaceform.block_parts`, `taxonomy.coverage_counts`. Test-only: `figure._arm_line`, `traced.top_above_sole`, `plaid.check_placement`, `shoedrawing.draw_straight`, `wears.next_laundry_day`, `surface.scale_of` | ~40 + ~60 | Low | Verified (note `schema._older` is a pydantic validator: live, a vulture false positive) |
| 13 | Frontend small fry: `Today.tsx` `Pic`/`itemName`, byte-identical copies of `components/ItemPic.tsx`; `Trips.tsx` `itemName` variant; `ArchiveIcon` unused; CSS `.btn-on-accent`, `.shoe-photo-none`, `.today-trips`, `.add-mode` (left over from the removed Add mode switch); test-only exports `HELP_LEVELS`, `rainWords`, `tooManyPhotos` | ~40 | Low | Verified |
| 14 | Docs: stale and contradictory lines (see below), DECISIONS.md at 1,317 lines with superseded shoe sections kept in full | n/a | Low | Verified |

## Detail by area

### 1. Backend: reachability, endpoints, pipelines

- Import graph: 0 unreachable modules out of ~150 under `backend/closet`.
- Routes: 96 in `app.py`, plus routers in `shop.py`, `sources.py`, `wishlist.py`, `wouldjobs.py` (119
  in all). Every route except `/api/outfits/suggest` is referenced by the frontend, either as a literal
  or through a URL the backend builds (`illustration_url`, `back_url`, `drawn.svg`, `/media/`,
  `cutout.webp`). `/api/instance/show` is called by the second launch (`instance.py`), and
  `trace/front.svg` by `shoe.ts`.
- `app.py` is 1,661 lines: one `create_app` closure holding all 96 handlers and a 20-field
  `Services` object. This is the main tangle point.

**Background-removal methods in the tree**

| Method | Where | Status |
|---|---|---|
| ONNX `isnet-general-use` (rembg asset, called directly) | `closet/cutout.py`, `modelstore.MODEL` | **Live default** for every cutout |
| ONNX `u2net` as a second opinion | `modelstore.SECOND_MODEL`, migration 0035 | Live: downloaded after the first and used when the first mask is see-through, runs off the frame or holds two surfaces. Costs a second ~170 MB download, a `second_model_url` setting and the `second_model` service |
| OpenCV GrabCut | `drawing/trace.grabcut_mask` (+ band refinement) | Live for shoe tracing only (a fallback when the model's cut-out fails the gate). Goes away with #8 |
| Duplicate ONNX cutout | `bench/closet_bench/cutout.py` | Fork, used by `make_demo.py` only (#7) |
| `rembg` package | none | Rejected in DECISIONS; not a dependency |

No setting chooses between methods; the choice is fixed in code. The settings involved are only the
two download-URL overrides.

**Drawing pipelines in the tree**

Garments (item tile and figure):
1. Parametric templates (`templates.py` 3,680) + renderer (`illustrate.py`), style **`line`**. **Live default.**
2. Styles `flat`, `soft` (template) and `traced` (outline traced from the cutout). Bench comparison only (Phase 0 chose templates). Inline branches in `_draw` plus `trace_outline`/`_render_traced`.
3. Phase-0 fills from the photo (`fills.py` swatch, stripes, dominant colour). Bench only, **but used by `make_demo.py`**, so the demo closet is drawn by a pipeline real items never use.
4. Patterns measured from the photo (`patterns/` flatten, straighten, stripes, plaid, prints). Live for old answers, the owner's pattern override and prints.
5. Cloth described by Claude (`tagger/surfaceform.py`, `patterns/described.py`, `patterns/surface.py`). **Live default since 18 Nov.**

Shoes:
1. Side-view template (`templates.py`). Tile fallback.
2. Traced side view from the main photo (`trace.py`, `traced.py`, `sideshoe.py`, `tracejobs.py`, OpenCV, GrabCut). **Live closet tile** for traced shoes, with fixes and "Use the plain drawing".
3. Front view on the figure from the template solid (`frontshoe.front_shoe`). Figure fallback.
4. Traced front A/B (`frontshoe` traced painting, `frontlook.py`, owner picks in Fix the details). Live fallback, documented as replaced, and the line-up test failed. Removed 19 November.
5. Claude-drawn shoe (`tagger/shoedrawing.py` 1,187, `shoedraw.py` 475, `drawing/drawn.py` 582, `turned.py` 617 with svgelements, `photocheck.py`, resvg). **Live default on the figure** when a drawing exists. Supports drawing versions 1, 2 and 3 side by side.
6. Measured 3D solid (`bench/experiments/shoe_solid`). Dropped (DECISIONS), bench only.
7. Five extra tracing approaches (k-means, mean-shift; `closet_bench.trace_shoes.APPROACHES`). Bench only; small branches remain in `trace.py`.

What the extra shoe pipelines cost: about 6,900 app lines (2 to 4), the OpenCV tracing path in the
app's job queue, two per-item settings (`trace_plain`, shoe front kind), the `trace_fixes` and
`shoe_front` columns, 4 endpoints, `ShoeTrace.tsx`, and about 2,600 lines of backend tests plus 850
in bench.

Settings that select approaches: none user-wide. Per item: `trace_plain`, the front A/B choice, the
drawn version (1/2/3) and `DRAWING_VERSION`. In code: `item.STYLE`, `trace.APPROACH`, `shoedrawing.EFFORT`.

### 2. Frontend

Clean. All 138 files reachable; only the items in #13. No duplicated screens; `OutfitFigure` is
shared by Today and Trips. The largest screens are `Today.tsx` 1,199, `Settings.tsx` 929, `Trips.tsx`
883 and `ItemDetail.tsx` 837, plus `styles.css` 927.

### 3. bench / tools / packaging / e2e: load-bearing or residue

| Path | CI / tests / app use | Verdict |
|---|---|---|
| `bench/tests/*` | Run by CI (`backend` job) | Load-bearing, but mostly tests backend code (#6) |
| `bench/closet_bench/{trace_shoes,hardcases,bench,cutout}.py` | bench tests; `make_demo` uses hardcases + cutout | Partly load-bearing (demo) |
| `bench/closet_bench/` 8 shims | bench tests, `make_review_gallery` | Consolidate (#6) |
| `bench/hardcases/` (7 photos, 1.8 MB) | `make_demo` source photos | Load-bearing for the demo |
| `bench/experiments/` | none, except `shoe_drawn/EXAMPLES` | Residue (#2) |
| `tools/make_demo.py` | tests reference its output; convention | Load-bearing |
| `tools/time_plan_route.py`, `style_demo_days.py` | have tests | Keep |
| other `tools/make_*` | none | Review aids (#10) |
| `packaging/closet.spec`, `smoke_test.py` | package-check + release | Load-bearing |
| `packaging/spike/` | manual-only workflow | Residue (#5) |
| `frontend/e2e/` | CI `browser` job | Load-bearing; but writes into `docs/screenshots` (#1) |
| `docs/screenshots/` | written by e2e and tools; ~42 referenced from docs | Mostly residue (#1) |

Workflows: `ci.yml` (backend+bench lint/tests, web lint/types/unit/build, Playwright, Windows
backend), `package-check.yml`, `release.yml`, `copilot-setup-steps.yml`, `start-agent.yml`,
`packaging-spike.yml` (manual, residue).

### 4. Tests

- Tests of dead or superseded code: the traced front (`test_frontshoe_traced.py` 845,
  `test_frontlook.py` 82), the bench-only fills and traced style in `test_bench.py` (about 8 tests),
  `/api/outfits/suggest` (about 6 asserts in `test_outfits.py`), and test-only helpers (#12).
- Duplication: none significant. Name pairs that look alike are distinct (`test_wouldwork` covers the
  rule engine and `test_would_this_work` the routes; likewise `test_correcting`/`test_corrections` and
  `test_shoedraw`/`test_shoedrawing`). Misplacement is the real problem: about 1,500 lines of backend
  tests live in bench.
- Runtime (measured here, 4 cores, `-n auto`): **2,863 passed, 5 skipped in 6 min 15 s.** The slowest
  tests are concentrated in the legacy measured-pattern path (`test_patterns.py`: 47 s, 25 s, 17 s, 16 s
  setup, 13 s, 12 s, 12 s, 11 s, 11 s, 9 s; about 3 min of CPU in the top 40) and the traced shoe
  (`test_frontshoe_traced.py` 18 s and 17 s, `test_trace.py` 16 s, 6 s, 5 s, 5 s, `test_frontlook.py` 5 s).
  Candidates #3, #8 and #9 would remove most of the slow tail. Bench and frontend suites were not run.
- Risk: e2e is 145 tests serial on 1 worker with a 60 s timeout each; BACKLOG notes flakiness in
  `08-wears`. The biggest single test file is `test_figure.py` at 1,601 lines.

### 5. Dependencies

Python runtime: every direct dependency is imported by the app. Only-for-superseded-paths:
- `opencv-python-headless`: needed by `patterns/` (live) and shoe tracing. It stays unless #8 **and** #9 both happen.
- `svgelements` (`turned.py`) and `resvg-py` (`drawn.py`): the live Claude-drawn shoe path. Keep.
- `bench/requirements.txt` duplicates backend requirements unpinned (`anthropic`, `numpy`, `onnxruntime`, `opencv`, `pillow`, `pydantic`, `pytest`), against AGENTS' "pin exactly" rule. After #6 it can go.

npm: all used (`qrcode-generator` in the app; `jsqr` and `@axe-core/playwright` in tests). No unused packages found.

### 6. Docs: stale, contradictory, duplicated

- DECISIONS cites `frontend/src/screens/ShoeAdd.tsx`, which does not exist (Add is one screen now). Verified.
- DECISIONS says "the drawing code still never imports [OpenCV]", but `drawing/trace.py`, `traced.py`, `frontlook.py`, `fills.py` and `illustrate.py` import cv2 (lazily, in app paths through `tracejobs`). The `requirements.txt` comment says the same untrue thing. Verified.
- `patterns/surface.py` docstring: "AN EXPERIMENT … not called by the app", but `app.py:270` imports `kept_for_item` from it and DECISIONS says it was adopted 18 Nov. Verified.
- `packaging/spike/README.md` and the workflow keep the spike "for ffmpeg", while BACKLOG says video sweeps are out. BACKLOG's parked "slimmer ffmpeg, 105 MB of the Windows program" is stale: the real spec bundles no ffmpeg. Verified.
- BACKLOG's parked "Sneaker side logos … tracing being tried on the bench (#192)" is superseded by Claude-drawn shoes. Verified.
- README "For development": "`bench/` — tagging and illustration experiments from phase 0" undersells that CI runs backend tests from it.
- README's Shoes section documents three overlapping shoe drawings (traced side with fixes, front A/B, Claude-drawn); this follows from #3/#8.
- DECISIONS keeps every superseded shoe section in full (stage 1 → 2a → 2b → 2c → line-up → drawn steps B–E → turned). About 250 lines could become a one-paragraph history with links.
- `docs/PHASE0.md` refers to `bench/closet_bench/models.json`, which no longer exists (models.json moved into the tagger).
- README is 845 lines (54 KB) as a single user manual: long, but not duplicated.

### 7. Repo weight

- Shallow clone: 234 commits, pack 95.03 MiB, 1,958 blobs reachable.
- By path, packed: `docs/screenshots` 88.6 MiB, `backend/closet` 2.4 (mostly `demo_data`), `bench/hardcases` 1.8, everything else under 1.
- Largest at HEAD: `traced-front-closeup.png` 3.3 MB, `accessories.svg` 2.0 MB, `outfit-figures.svg` 1.4 MB, `traced-front-2x-{dark,light}.png` 1.2 MB each, `demo_data/items.json` 0.84 MB, about 15 more screenshots of 0.45–0.7 MB.
- Cause: images regenerated by e2e and tools and committed over and over (`traced-front-closeup.png` has 8+ versions of about 3 MB).

### 8. Structure

Files over ~600 lines (code and tests):

templates.py 3680 · figure.py 1932 · taxonomy.py 1801 · frontshoe.py 1768 · app.py 1661 · test_figure.py 1601 ·
outfits.py 1546 · illustrate.py 1257 · Today.tsx 1199 · shoedrawing.py 1187 · bench test_taxonomy.py 1126 ·
trace.py 1056 · bench experiments stripes.py 991 · gaps.py 936 · Settings.tsx 929 · styles.css 927 ·
patterns/stripes.py 918 · traced.py 911 · test_styletalk.py 884 · Trips.tsx 883 · test_styling.py 881 ·
test_frontshoe_traced.py 845 · make_demo.py 843 · ItemDetail.tsx 837 · updates.py 829 · test_stylejobs.py 775 ·
test_shoe_correct.py 741 · test_corrections.py 708 · wouldwork.py 707 · test_window.py 701 · Missing.tsx 698 ·
test_shoeviews.py 692 · Add.tsx 671 · test_backup.py 663 · test_shop.py 662 · test_updates.py 653 ·
test_trips.py 652 · trips.py 647 · bench test_bench.py 633 · shop.py 624 · backup.py 621 · turned.py 617 ·
straighten.py 614 · accessories.py 612

Tangles:
- `app.py`: one closure with all handlers, plus the `Services` god object.
- `frontshoe.py`: template solid and traced painting in one file, split at about line 835.
- `illustrate.py`: four styles interleaved with `if style ==` branches.
- `illustrations.py`: chooses between template, traced, A/B and drawn.
- bench to backend through `sys.modules` shims; tools to bench (`make_demo`, `make_review_gallery`).

Settings sprawl (moderate, not severe):
- `settings.json` (`State.DEFAULTS`): 38 keys. 11 are user-editable through `PUT /api/settings`; there are also the API key, update mode, model URL, profile and style profile endpoints, so about 16 user-facing settings.
- Env vars: 4 runtime (`CLOSET_DATA_DIR`, `CLOSET_HOST`, `CLOSET_PORT`, `CLOSET_NO_AUTO_DOWNLOAD`), plus `CLOSET_WEARS` and 7 `CLOSET_E2E_*` for tests, plus `CLOSET_PYTHON`.
- `models.json`: 6 roles over 3 models.
- Per-item drawing switches: 3 (`trace_plain`, front kind, drawn version), plus `DRAWING_VERSION` and `TRACING_VERSION`.
