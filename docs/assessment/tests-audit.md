# daily-clother: test suite audit (read-only)

Audited 2026-11-19 on the working tree at `/home/user/daily-clother`. Nothing in the repo was modified,
committed or pushed. The backend suite ran once in the repo (ignored `__pycache__` only; verified no other file
changed). Coverage, the bench, vitest and Playwright ran in a **copy** at `scratchpad/repo/`, because one
Playwright run rewrites tracked screenshots (see §3). Python 3.13 venv in `scratchpad/venv` from
`backend/requirements-dev.txt` + `bench/requirements.txt` + coverage. 4 cores.

**Measured** = run here, numbers from junit/coverage/Playwright output or the GitHub Actions API.
**Estimated** = reasoning from those numbers and from reading code; marked "est.".

Raw outputs in the scratchpad: `backend-junit.xml`, `backend-run.txt` (`--durations=0`), `junit-summary.txt`,
`cov/.coverage` (per-test contexts), `cov-perfile.txt`, `greedy.txt`, `demo_tests.txt`, `vitest.json`,
`e2e-run.txt`, `e2e.json`.

---

## 0. Headline

| Layer | Files | Tests | Lines | Runtime here | Runtime in CI |
|---|---:|---:|---:|---|---|
| Backend `backend/tests` | 81 test files + conftest/helpers | **2,868** collected (2,863 pass, 5 skip) | 31.0k | **5 m 45 s** wall, 1,345 s CPU, `-n 4` | 12 m 40 s (Linux), 17 m 40 s (Windows) |
| Bench `bench/tests` | 3 | 349 (128 functions) | 2.0k | 72 s serial | 86 s (serial, no `-n`) |
| Frontend unit (vitest) | 37 | 347 (323 `it` + `each`) | 3.6k | **3.1 s** | inside a 1–1.5 min job |
| Browser (Playwright) | 44 specs | 160 (1 always skipped) | 6.4k | **9 m 45 s** (159 pass, serial, 1 worker) | 11.5–13.5 min job, 702 s step |

The big picture:

- **The suite is not bloated by count. It's slow in a few places.** 1,581 backend tests (55 %) take
  27 s CPU between them. 310 tests of 1 s or more take 950 s (71 % of CPU). The 30 slowest take 25 %. Deleting
  cheap tests saves almost no time. The time is in image-processing tests (legacy measured patterns,
  shoe tracing, the traced front), in two fixed 10 s waits, and in building the demo closet again for 80 tests.
- **Coverage (measured):** 92 % of 30,340 app statements are covered. A greedy set cover over per-test line
  contexts reaches **100 % of covered lines with 733 tests (26 %) and 515 s CPU (38 %)**, and 99 % with 497 tests.
  That is the floor in line-coverage terms. Many of the other tests assert behaviour on the same lines (rules,
  geometry invariants, refusals), so this does **not** mean 2,100 tests can go. It does mean that matrices and
  per-caller repetition are common.
- **Copy-paste duplication is low.** A token-trigram similarity pass over 1,708 backend test bodies finds only
  20 pairs above 0.6, none identical. The real duplication is structural: mirrored pipelines with mirrored
  tests, and about 20 per-migration tests that `test_db.py` already covers.
- **Gaps sit in the owner's pain points.** Settings, ItemDetail and Add have **no component or unit tests**
  (vitest runs in `node` only, with no `.test.tsx`). Phone access in e2e fully fakes `/api/settings`. Nothing
  loads the app through a non-localhost origin. Add-item progress is checked only at its end states. The
  real-model e2e test never runs in CI.

---

## 1. Inventory

### 1.1 CI (`.github/workflows/ci.yml`, on every PR and push to `main`)

Jobs run side by side. "Lint and tests (Linux)" is the required check, gating `backend`, `web` and `browser`.
`windows` runs but is not required. There are no caches of any kind (the quota is exhausted).

| Job | Steps | Timeout | Measured duration (last 5 green runs, Actions API) |
|---|---|---|---|
| Backend and bench (ubuntu) | pip install both requirement files, `ruff`, `pytest -q -n auto`, `pytest -q tests` in bench (serial) | 20 min | 8 m 35 s – 14 m 31 s (pytest step 760 s, bench 86 s on run 44544182271) |
| Web page | `npm ci`, lint, typecheck, `vitest run`, build | 15 min | 1 m 0 s – 1 m 21 s |
| Browser tests | pip, `npm ci`, build, `playwright install --with-deps`, `npm run e2e` | 20 min | 11 m 32 s – 13 m 26 s (e2e step 702 s) |
| Backend tests (Windows) | pip, `pytest -q -n auto`, `PYTHONUTF8=0` | 30 min | 14 m 46 s – 18 m 46 s (pytest step 1,061 s) |

Wall time per run is about **15–19 min**, set by Windows, or by Linux backend when it is the slowest. The Linux backend job
is at 73 % of its timeout on a bad day and the browser job at 67 %. Both are at risk as tests are added.
`packaging-spike.yml`, `package-check.yml` and `release.yml` are not test gates.

### 1.2 Backend per file (measured, sorted by CPU; junit `time` = setup+call+teardown)

| CPU s | Tests | File | Lines |
|---:|---:|---|---:|
| 151.3 | 26 | test_patterns.py (legacy measured stripes/plaid) | 585 |
| 134.4 | 61 | test_trace.py (shoe tracing) | 493 |
| 90.0 | 95 | test_styletalk.py | 884 |
| 69.3 | 25 | test_wouldwork.py | 310 |
| 66.5 | 63 | test_frontshoe_traced.py (traced front, prior audit #3) | 845 |
| 60.6 | 16 | test_shoedrawing_turned.py | 355 |
| 52.4 | 49 | test_stylelook.py | 606 |
| 44.9 | 60 | test_trips.py | 652 |
| 43.0 | 28 | test_shop.py | 662 |
| 42.6 | 18 | test_gaps.py | 265 |
| 41.9 | 22 | test_wishlist.py | 237 |
| 37.3 | 44 | test_styleahead.py | 552 |
| 37.0 | 49 | test_stylejobs.py | 775 |
| 28.0 | 33 | test_shoe_correct.py | 741 |
| 27.1 | 55 | test_corrections.py | 708 |
| 25.6 | 335 | test_figure.py | 1,601 |
| 22.9 | 34 | test_window.py | 701 |
| 20.7 | 40 | test_tracejobs.py | 572 |
| ≤15 each | 1,750 | the other 63 files | ~19k |

The full table is in `scratchpad/junit-summary.txt`. Setup is 178 s of the 1,345 s. The largest single setup
is `test_patterns::test_rectify_recovers_the_repeat` at 14.6 s.

Largest parametrize matrices (collected cases per function): `test_kinds::test_every_kind_sets_a_category_of_its_own_sort`
142; `test_figure::test_a_leg_narrower_than_the_shoe_rests_on_it…` 60, `…back_of_a_low_shoes_collar…` 36,
`…cropped_trousers_leave_a_gap…` 30, `…slim_leg_never_drops_over_a_boots_shaft` 27, `…top_hangs_over_the_waistband` 21;
`test_drawing::test_the_footwear_fields_choose_the_shoe_drawing` 32; `test_collar_rounding` 32;
`test_figure_drawn::…drawn_exactly_as_today` 28; `test_db` 27 + 26 (every migration version).
All of these are cheap. `test_figure.py` is 335 cases in 25.6 s and `test_kinds.py` 156 cases in 2.8 s.

### 1.3 Bench (measured)

349 tests in 72 s serial. `test_trace_shoes.py` (16 functions) takes about 60 s of that: one 15 s setup
(cut-out of a photo), and several 3–11 s calls to the bench's `trace_shoes` command and its gate.
`test_taxonomy.py` (74 functions, 1,126 lines) and `test_bench.py` (38) are fast. Most of them test
`closet.tagger`/`closet.drawing` through the 8 shim modules (prior audit #6).

### 1.4 Frontend unit (measured)

347 tests, 37 files, 3.1 s wall (748 ms in test files). Slowest: `qr.test.ts` 124 ms, `api.test.ts` 76 ms. All of them are
pure-logic `.ts` modules in a `node` environment. There is **no** test of any `.tsx` screen or component, and
no testing-library in devDependencies.

### 1.5 Playwright (measured locally, `CLOSET_PYTHON` = the venv)

160 tests in 44 specs (the `for` loops over layouts and themes produce more than the 147 `test(` call sites). 159 passed and
1 was skipped: `06-model` needs `CLOSET_E2E_MODEL`, which **CI never sets**, so that test never runs anywhere.
Test time is 554 s, plus about 30 s for the build and startup. Slowest specs:

| s | Tests | Spec |
|---:|---:|---|
| 75.4 | 9 | 17-accessibility (4 × ~18 s axe sweeps of the main screens: phone/computer × light/dark) |
| 70.7 | 7 | 25-conversation (one test 27.7 s: fixed 5 s/1.5 s sleeps in the stand-in) |
| 56.6 | 2 | 20-shoe (one test 48 s: Add → sort photos → draw) |
| 29.6 | 4 | 08-import |
| 27.7 | 6 | 12-would-work |
| 23.0 | 1 | 14-shop |
| 16–17 | — | 12-missing-life (15 tests), 19-core, 10-today (16 tests), 14-failed-item |

The fakes in `backend/tests/e2e_backend.py` sleep a fixed 1 s per stage (describe, look, sort, draw, search),
1.5 s for the stylist and 5 s for a "slow" message.

---

## 2. Redundancy

### 2.1 Same behaviour at several layers

| Behaviour | Where it's asserted | Comment |
|---|---|---|
| What's missing / life questions / wishlist | backend `test_gaps`, `test_life`, `test_life_review`, `test_wishlist`; vitest `gaps.test.ts` (16), `life.test.ts`; e2e `11-missing` (9 tests) + `12-missing-life` (15 tests, several titled "review 1/5/10:", i.e. regression tests from one design review) | The heaviest stack in the repo for one screen. Backend rules are tested properly. The e2e repeats rule cases (all-never answers, zero-week vacation, held-back hides) that belong in backend/vitest. est. 6–8 e2e tests could fold into 2–3. |
| Theme | vitest `design.test.ts` checks forced dark = device dark tokens; `theme.test.ts`; e2e `14-theme` = 3 modes × 2 layouts + 1 | 6 matrix tests take screenshots of the same background check. 2 would do (dark device on phone, forced light on computer) plus "Look wins and is remembered". |
| Accessibility | e2e `17-accessibility` runs a full axe sweep 4 times (phone/computer × light/dark); `25-conversation` and `18-phone-qr` call axe again | Two of the four sweeps (phone-light, computer-dark) catch the same rule classes. Saves about 35 s. |
| Migrations | `test_db.py` upgrades a closet from **every** shipped version, checks integrity and FKs, and kills a migration mid-way for every version. About 20 more per-feature tests ("the migration adds the columns", "…runs on a closet made by the previous version") in `test_corrections`, `test_tagjobs`, `test_wears`, `test_wishlist`, `test_worn`, `test_shoedraw`, `test_shoe_correct`, `test_shoeviews`, `test_tracejobs` ×2, `test_sources`, `test_styleprofile`, `test_illustrations`, `test_items`, `test_shop`, `test_trips` ×2, `test_import`, `test_shoe_main_photo` | Keep the ones that check **data transformation**: 0005 hash carry-over, 0023 laundry, 30 laundry place, the shoe main-photo word, the illustrations kept, items copy per closet. The roughly 9 that only check columns exist or that "the previous version" upgrades are covered by `test_db`, and their "previous" goes stale as migrations are added. |
| Shoe drawing / correcting jobs | `test_shoedraw.py` and `test_shoe_correct.py` have mirrored tests (deleted mid-job, Claude out of reach, missing photo, through the API key): similarity 0.64–0.73 | Two queues on the same job framework. One parametrized test over both queues would halve about 6 tests. Low value either way. |
| Would-this-work rules | `test_wouldwork` (rules, 69 s), `test_would_this_work` (routes, 15 s), `test_shop` re-runs the would-work rules on finds (two tests, 32 s), e2e `12-would-work` | `test_shop::test_finds_are_judged_on_the_same_weighed_list…` and `…checked_against_the_closet_with_the_would_this_work_rules` re-test the rules through shopping on the full demo closet. One test that asserts shop **calls** the same scorer (same inputs give the same verdict) on a 6-item closet would protect the same thing in under 1 s. |

### 2.2 Near-duplicates and copy-paste

Measured: 20 pairs above 0.6 token-trigram Jaccard out of 1,708 non-trivial test bodies, and nothing identical.
This agrees with the prior audit: there are no copy-pasted files. The pairs that matter are listed in 2.1.

### 2.3 Matrices

They are all cheap (2.8 s for 142 kinds). Trimming them would remove cases without saving time. The only matrices
worth trimming are in `test_figure.py` (four shoe × leg × break products: 153 cases, about 5 s est.) and `test_db`'s
kill-mid-migration (26 subprocesses, 6.5 s total). Both are low priority. Keep `test_kinds`: it is table-driven
over the taxonomy and catches a new kind with no category.

### 2.4 Same helper through many callers

The demo closet is **built from scratch in 80 tests** (measured: tests whose coverage context executed
`demo._add_items`). That costs about 1.3 s each (measured standalone), or about 100 s CPU (est.), concentrated in
`test_wishlist` (11), `test_trips` (9), `test_demo` (7), `test_shop`, `test_corrections` (4 each). Gap analysis
on the demo closet then costs another ~1.7 s the first time per test. This is a fixture problem, not a test
problem: build the demo closet once per session and copy the folder per test.

---

## 3. Low-value tests

| Group | Files / count | Why low value | Action |
|---|---|---|---|
| Screenshot-only e2e | `11-missing` "screenshot of What's missing on a phone/computer", `10-today` "screenshot of Today on a phone/computer" (4 tests) | Log in, wait for images, screenshot. They assert nothing new. `10-today`'s copy writes into `docs/screenshots`. | Delete, or move into a `tools/make_*_shots` script. Low risk. |
| E2e writing tracked files | **Measured:** one local `npm run e2e` rewrote **58 files** in `docs/screenshots/` (19 specs call `screenshot(` 44 times; theme alone writes 18) | Every agent's local run dirties tracked PNGs, which then get committed (the prior audit's 88 MiB of history) | Point `SHOTS` at `testInfo.outputPath()` (git-ignored `test-results/`). The specs do assert things (e.g. `15-closet-design` 27 expects, `20-shoe` 114), so keep the tests. |
| Real-model test that never runs | `06-model.spec.ts` (38 lines) | Skipped unless `CLOSET_E2E_MODEL` is set. CI doesn't set it. | Owner: wire it into a nightly job with the model downloaded, or delete it. |
| Golden digests | `bench/tests/test_taxonomy.py::test_non_jacket_drawings_are_unchanged` (≈45 SHA digests of SVGs) | Break on any intended drawing change and say nothing about what's wrong. They encode a deliberate "drawings must not change by accident" rule (ruff ignores in pyproject say the same). | Owner decision. If kept, move them to backend with a one-command re-record and a rendered diff. |
| Lint-like tests | vitest `design.test.ts` (10: tokens only, no colour outside tokens, motion tokens); backend tests reading source (`test_auth`, `test_backup`, `test_trips`) | Cheap (52 ms) and useful. They are really stylelint/ruff rules. | Keep. Don't add more per screen. |
| Exact long strings | 18 backend asserts compare strings of 50+ chars (7 in `test_insights`); 6 e2e `toHaveText` of 50+ chars | Break on copy edits | Low count. Turn them into `in`/regex on the key phrase when touched. Not worth a sweep. |
| Superseded/dead | `/api/outfits/suggest` asserts in `test_outfits.py` (prior #11, about 6); bench-only fills/`traced` style in `test_bench.py` (about 8, prior #4); `test_frontshoe_traced.py` + `test_frontlook.py` (prior #3) | Test code the app no longer uses (or only as a fallback) | Delete with the feature (see §7). |
| Mostly mocks | `test_window.py` (fake toolkit, fake tray), `test_windows.py` | Fakes stand in only at the OS boundary, and the real launcher and server run. **Not** low value. | Keep. Fix the two waits (§4). |
| Tests of constants | `test_kinds` group titles; `design.test` type scale `[12,14,16,20,25,31,39]` | Pin decided values. They are cheap and documented in DECISIONS. | Keep. |

Coverage evidence (measured, §6): seven backend files add **zero** unique covered lines: `test_db`,
`test_hem_stitch`, `test_collar_rounding`, `test_leg_depth`, `test_import`, `test_archive`, `test_time_plan_route`.
Every one of them is an invariant or regression test whose value is in its assertions. For example, `test_db` is the only
test of upgrading every version, and hem/collar/leg-depth pin drawing bugs that were fixed. Together they take
about 9 s. **Coverage doesn't justify deleting them.** That is why this audit doesn't use "zero unique lines" as a deletion criterion.

---

## 4. Slow tests: the slowest 30 (measured, CPU seconds incl. setup)

| s | Test | Protects | Proposal |
|---:|---|---|---|
| 34.2 | test_patterns::a_plaid_from_a_dark_photo_is_lightened… | legacy measured plaid: colour from a dark photo | `slow` (nightly). Shrink the synthetic photo (est. 4–10× faster). |
| 18.9 | test_frontshoe_traced::collar_back_and_lining_painted_before_the_leg | traced front paint order | delete with #3, else `slow` |
| 18.0 | test_shop::finds_are_judged_on_the_same_weighed_list… | shop uses would-work scoring | rewrite on a tiny closet (<1 s) |
| 18.0 | test_frontshoe_traced::b_outline_equals_a_outline_for_every_synthetic_shoe | A/B front outlines agree | delete with #3, else `slow` |
| 17.6 | test_patterns::a_plaid_photographed_at_an_angle… | legacy straightening | `slow` |
| 15.4 | test_trace::a_shoe_that_does_not_stand_out_is_turned_down | tracing gate rejects low contrast | `slow`, or smaller image |
| 14.7 | test_patterns::rectify_recovers_the_repeat (14.6 s is setup) | legacy rectify | `slow`. Make its fixture module-scoped. |
| 14.5 | test_patterns::an_overcheck_over_every_other_check… | legacy plaid | `slow` |
| 13.6 | test_shop::finds_are_checked_against_the_closet… | as above | rewrite small |
| 12.3 | test_shoedrawing_turned::a_drawing_with_a_measured_fault… | Claude-drawn shoe judge | `slow`, or stub the renderer |
| 11.5 | test_patterns::a_plaid_with_no_regular_repeat… | legacy | `slow` |
| 10.7 | test_patterns::a_large_repeat_on_creased_cloth… | legacy | `slow` |
| 10.4 | test_patterns::placed_band_survives… | legacy | `slow` |
| 10.2 | test_patterns::placed_stripes_keep_the_band | legacy | `slow` |
| 10.2 | test_window::by_default_there_is_no_tray_icon… | close hides, Quit stops | **make fast**: it waits out `stop_running(timeout=10)` |
| 10.2 | test_window::without_a_tray_or_a_window… | second launch opens browser | **make fast**, same cause |
| 9.7 | test_patterns::a_plaid_seen_straight_on… | legacy | `slow` |
| 9.2 | test_patterns::measure4_vertical_stripes | legacy stripes | `slow` |
| 8.4 | test_shoedrawing_turned::failures_keep_what_was_made | drawn shoe failure path | stub the renderer |
| 7.4 | test_wouldwork::unanswered_questions_give_the_plain_check | would-work default | demo-closet fixture copy |
| 7.3 | test_shoe_correct::through_the_api_key_and_its_monthly_limit | spend limit on corrections | keep |
| 6.9 | test_gaps::gaps_answers_for_the_open_closet | gaps on demo | demo fixture copy |
| 6.7 | test_cloth::the_gaps_use_the_stored_answer… | cache invalidation | demo fixture copy |
| 6.6 | test_wouldwork::the_days_it_would_cover… | would-work | keep |
| 6.4 | test_trace::clean_single_shoes…[high-collar-boot] | tracing accepts good photos | keep 1–2 params on PR, the rest `slow` |
| 6.1 | test_shoedrawing_turned::a_running_shoe_is_drawn_with_its_midsole… | drawn shoe | `slow` |
| 6.0 | test_gaps::same_inputs_give_the_same_answer_in_any_order | determinism | keep, smaller closet |
| 5.7 | test_shoedrawing_turned::photos_are_cut_to_the_shoe… | cut-out before drawing | stub the model |
| 5.7 | test_would_this_work::by_hand_in_the_demo_closet… | route | demo fixture copy |
| 5.7 | test_life_review::legacy_hide_needs_explicit_confirmation… | hides | demo fixture copy |

**The `test_window` cause (verified by reading):** `instance.stop_running()` waits until the copy's PID is
gone, but in these tests the launcher runs **in the test process**, so `_pid_alive(os.getpid())` stays true
until the 10 s deadline. The tests don't check the return value (`False`), so they pass after 10 s each. Fix:
pass a short timeout, or assert `running_instance(cfg) is None` instead. This saves 20 s and closes a hole
where the tests would also pass if Quit did not work.

Groups: `test_patterns` 151 s, traced front 73 s, `test_trace` 134 s (about 100 s of it in roughly 15 image tests),
`test_shoedrawing_turned` 61 s. Together that is about **420 s, or 31 % of backend CPU, in about 120 tests**, all pure image
algorithms with no platform dependence. They are the obvious `@pytest.mark.slow` group. Run them nightly
and on PRs that touch `closet/patterns/**`, `closet/drawing/{trace,traced,frontshoe,frontlook,drawn,turned}.py`
or `closet/tagger/shoedrawing.py` (a path filter in a second workflow job). The Windows job can skip them
outright: they don't touch the Windows code it exists for.

E2e: replace the fixed sleeps in `e2e_backend.py` with gates the test releases, or with 0.2 s. est. 30–60 s off e2e,
plus less flake. Cut `17-accessibility` from 4 sweeps to 2 (−35 s) and `14-theme` from 6 to 2 (−5 s).

---

## 5. Gaps

| Pain point | What exists | What's missing | Proposal (layer) |
|---|---|---|---|
| **Settings** (`Settings.tsx` 929 lines) | e2e: layout and group order (`07-storage`), storage numbers, model download address visible, Look, API key, route order, spend limit, laundry/re-wear (`12-trips`), place, life, style, updates, phone QR | No unit or component test at all. In e2e, **nobody presses** *Back up now* or chooses a backup folder, flips *Start Closet when I log in*, saves or resets the model download address (*Save address*, *Use default*), confirms *Quit Closet*, or toggles the demo switch from Settings (specs switch through `/api/profile`). No test that a failed save in one group leaves the others intact. | One e2e spec, "every Settings control once": press each, then check `/api/settings` (or the toast) and that a reload shows it. About 1 test per control, ~8 tests, ~15 s. Add vitest + `@testing-library/react` (jsdom) for the Settings sub-forms' validation states. That is a new dependency, so it's the owner's call. |
| **Phone / Tailscale** | `phone.py` 94 % covered, but by tests in **`test_backup.py`** (misplaced). e2e `18-phone-qr` fakes the whole `phone` object in `/api/settings` and checks the QR decodes. `test_auth` checks the Secure cookie with `x-forwarded-proto`. | Nothing exercises the app **as the phone reaches it**: a non-localhost https origin through a proxy (`Host: <name>.ts.net`, forwarded proto). That would cover login, the Secure + SameSite=Strict cookie, the service worker scope, upload with `capture`, and the offline cache. BACKLOG: "Not yet exercised: the Tailscale address, camera capture, home-screen install, HEIC from the phone". `net.py` 53 %, `instance.py` 76 %. | Backend: move the phone tests to `test_phone.py`, and add one TestClient test with `base_url="https://closet-pc.example.ts.net"` + forwarded headers covering login → upload → list. E2e: one phone-viewport spec through a tiny local reverse proxy (or Chromium `--host-resolver-rules` + TLS-ignoring proxy) covering login, add a photo and reload. Keep a short manual checklist for real Tailscale. |
| **Add-item progress** | Unit: `added.ts` state mapping, `uploadQueue.test.ts` (24). E2e: queue status `Added` (11 asserts), `Uploading` once, `Already in your closet`, `Failed`, the waiting badge without a model, import resumed after close, describe/draw end states | Intermediate stages (*Removing the background* → *Claude is describing it…* → named) are never observed live in order. Fakes finish in fixed 1 s sleeps, so tests assert end states only. The model download progress bar is never exercised (`06-model` never runs). There's no test that progress keeps updating after navigating away from Add and back. | Gate the fakes (e.g. `/__e2e/release?stage=describe`) and add one e2e test that asserts each row state appears in order without reload, then navigates to Closet and back mid-way. Add a backend test for model download progress events with a fake HTTP server. |
| **Item detail** (`ItemDetail.tsx` 837) | e2e: `02-demo` (switch pictures, change a chip, persists, rejected change undone, archive/delete), `15-closet-design` (phone layout, opens at top), `19-core` (save races, Back saves), `11-corrections`, `26-retake`, `20-shoe` | Reasonably covered, but only through e2e. No component tests of field editing, error and undo states. Nothing for an item deleted or changed in another tab while the detail is open, or for offline edit attempts on the detail page specifically. | Component tests for the field editors (if testing-library is approved). One e2e test for "item gone under you" (404 → back to closet with a message). |
| **Navigation** | vitest `nav.test.ts` (route → tab table), `router.test.ts` (3); e2e tab bar contents (`04-layout`), search kept on Back (`15-closet-design`), Today swipe → piece → back (`10-today`), landing on Today (`10-today`) | No deep link + reload for every route (`/item/:id`, `/settings`, `/trips/…`, `/missing`, `/worn`, `/review`). No Back/Forward across 3+ screens on the phone, and no check that scroll is restored. The landing redirect is fragile enough that `fixtures.login` carries a long workaround comment. | One table-driven e2e test over all routes: deep-link, reload, Back returns to the previous screen with its scroll. Unit-test `landing.ts` (it has no test file). |

Other gaps found on the way:
- Settings → Updates: `updates.py` is 82 % covered and has no frontend unit test beyond `updates.test.ts` (9).
- `window_mac.py` 0 %, `cli.py` 71 %: platform launch code. This is acceptable (the Windows job covers Windows), but nothing covers the Mac.
- The `windows` job isn't required, so its 17–19 min run can fail without blocking.

---

## 6. Coverage evidence (measured)

Run: `pytest -n 4 --cov=closet --cov-context=test` in the copy, 10 m 15 s (1.8× the plain run). 8,551 contexts.
**Total line coverage is 92 %** (30,340 statements, 2,554 missed). The biggest misses are `drawing/fills.py`
(34 %, phase-0 fills covered only by bench), `patterns/stripes.py` 150 lines, `cli.py` 116, `updates.py` 111,
`accessories.py` 89 and `patterns/measure.py` 83.

**Unique lines per test file** (lines covered by no other backend test file; `scratchpad/cov-perfile.txt`):

- 0 unique: `test_hem_stitch`, `test_db`, `test_archive`, `test_collar_rounding`, `test_import`, `test_time_plan_route`, `test_leg_depth`.
- Under 15: `test_failures` 2, `test_cloth` 3, `test_state` 3, `test_taste_review` 4, `test_frontlook` 5, `test_tagging` 5,
  `test_retake` 5, `test_gaps` 8, `test_styleprofile` 8, `test_palette` 9, `test_shoedrawing` 10, `test_shoe_main_photo` 11,
  `test_spend` 11, `test_turned` 11, `test_shoedraw` 12, `test_learning` 13, `test_stylejobs` 14, `test_uploads` 14,
  `test_life` 14, `test_auth` 14, `test_figure_drawn` 14.
- Most unique: `test_patterns` 1,462 (stripes/straighten/flatten: **only this file covers the legacy
  measured-pattern code**, so marking it slow is safer than deleting it), `test_corrections` 409, `test_updates` 397,
  `test_shop` 368, `test_figure` 345, `test_window` 335, `test_outfit_rules` 237, `test_insights` 247, `test_backup` 219
  (incl. 60 lines of `phone.py`), `test_trips` 201.

**Greedy set cover over individual tests** (`scratchpad/greedy.txt`): 90 % of covered lines with 108 tests
(197 s); 95 % with 217 (281 s); 99 % with 497 (432 s); 100 % with 733 (515 s). Files that contribute almost
nothing to the cover relative to their size: `test_figure` 21/335, `test_kinds` 20/156, `test_drawing` 17/120,
`test_styling` 18/127, `test_climate` 14/79, `test_trace` 8/61, `test_frontshoe_traced` 8/63.

How to read it: these files are mostly table-driven assertions over the same code paths. Their cases differ in
**inputs and expected outputs**, which line coverage can't see. They're cheap except `test_trace` and
`test_frontshoe_traced`, which is where the slow-marking and deletion proposals already point. Line coverage
backs the slow/delete groups below. It doesn't support mass pruning of cheap tests.

Not measured: frontend coverage (`vitest --coverage` needs `@vitest/coverage-v8`, not installed) and e2e coverage.

---

## 7. Proposed target suite

Totals are relative to today: backend 2,868 tests / 31.0k lines / 1,345 s CPU / 5 m 45 s wall (CI 12.7 min Linux,
17.7 min Windows); bench 349 / 2.0k / 72 s; vitest 347 / 3.6k / 3 s; e2e 160 / 6.4k / 9 m 45 s (CI 11.7 min).

### 7.1 Safe to do now (no feature change)

| # | Change | Files | Tests | Lines | Time saved | Risk |
|---|---|---|---:|---:|---|---|
| S1 | Fix the two 10 s waits in `test_window.py` (short timeout, and assert that Quit worked) | `backend/tests/test_window.py` | 0 | ~0 | −20 s CPU; removes a long pole | Low |
| S2 | Build the demo closet once per session and copy the folder per test (`conftest.py` fixture used by the `demo`/profile switches) | `backend/tests/conftest.py`, the `demo` fixtures in `test_wishlist`, `test_wouldwork`, `test_trips`… | 0 | +30 | −~100 s CPU (est., 80 tests × ~1.3 s) | Low–Med (tests must not mutate the shared template) |
| S3 | Add a `slow` marker. PR runs `-m "not slow"`; nightly and path-filtered jobs run everything; the **Windows job always skips slow** | `pyproject.toml`, `ci.yml`, a new nightly workflow (owner edits workflows), and markers on `test_patterns.py` (all 26), about 15 image tests in `test_trace.py`, `test_shoedrawing_turned.py` (16), `test_frontshoe_traced.py` (63) | ~120 move to nightly | 0 | −~420 s CPU on PR (31 %); Windows job est. −5 min | Med (an image regression is found next morning, not on the PR) |
| S4 | Rewrite the two `test_shop` would-work-on-finds tests on a 6-item closet asserting shop calls the same scorer | `backend/tests/test_shop.py` | 0 (2 rewritten) | −20 | −30 s | Low |
| S5 | Drop column-only migration tests covered by `test_db` (keep the data-transforming ones listed in §2.1) | `test_tagjobs`, `test_corrections`, `test_wishlist`, `test_worn`, `test_wears` (previous-version ones), `test_shoedraw`, `test_tracejobs` ×2, `test_sources` | ~9 | ~250 | ~3 s | Low |
| S6 | Move the phone tests out of `test_backup.py` into `test_phone.py`; move bench's backend tests (`test_taxonomy.py`, tagger/route parts of `test_bench.py`) into `backend/tests` and drop the shims (prior #6); run bench with `-n auto` | `backend/tests/test_backup.py`, `bench/tests/*` | 0 | 0 net (−~50 shim lines) | bench −~40 s wall in CI | Low |
| S7 | E2e: stop writing into `docs/screenshots` (use `testInfo.outputPath`) | 19 specs (`SHOTS` constants) | 0 | ~0 | — | Low |
| S8 | E2e: delete the 4 screenshot-only tests; `14-theme` from 6 matrix tests to 2; `17-accessibility` sweeps from 4 to 2 | `10-today`, `11-missing`, `14-theme`, `17-accessibility` | −10 | −~120 | −~60 s | Low |
| S9 | E2e fakes: replace fixed sleeps with test-released gates (or 0.2 s) | `backend/tests/e2e_backend.py`, `24/25-*.spec.ts`, `09`, `16`, `20` | 0 | ~+40 | −30–60 s (est.); less flake | Low–Med |
| S10 | Fold the rule-level cases in `12-missing-life` ("review 1/5" etc.) into backend/vitest tests and keep the screen journeys | `frontend/e2e/12-missing-life.spec.ts` (+ `test_life_review`, `gaps.test.ts`) | −5 e2e, +5 unit | −~100 | −~5 s | Med |

### 7.2 Delete together with the feature

| # | Feature (prior audit) | Tests | Tests removed | Lines | Time | Risk |
|---|---|---|---:|---:|---|---|
| F1 | Traced shoe **front** A/B (#3) | `test_frontshoe_traced.py`, `test_frontlook.py`, the front-choice steps and `shoe-front-choice.png` in `e2e/20-shoe.spec.ts` | 70 | ~950 | −73 s CPU | Med (as #3) |
| F2 | Dead `/api/outfits/suggest` (#11) | its asserts in `test_outfits.py` | ~3 | ~70 | ~0 | Low |
| F3 | Phase-0 fills and bench comparison styles (#4) | the fills/`traced` style tests in `bench/tests/test_bench.py` (~8), `fills` digests if any | ~8 | ~200 | ~2 s | Med (blocked by `make_demo`) |

### 7.3 Owner decisions

| # | Question | Tests concerned | If removed |
|---|---|---|---|
| O1 | Legacy measured-pattern path (#9). Another agent is checking reachability. **Keep the tests while the code stays**: `test_patterns` is the only coverage of 1,462 lines. | `test_patterns.py` (26, 585 lines, 151 s) | −26 tests, −585 lines, −151 s. Until then, S3 (slow) gets the same CI time. |
| O2 | Bench `trace_shoes` command (the bench runner, not the app pipeline, which stays) | `bench/tests/test_trace_shoes.py` (16, 282 lines, ~60 s) | −60 s of the bench step. Otherwise mark it slow. |
| O3 | SVG golden digests | ~45 cases in `bench/tests/test_taxonomy.py` | Replace with "re-record + rendered diff", or keep as is |
| O4 | `06-model` real-model e2e | `frontend/e2e/06-model.spec.ts` | Wire a nightly with the model, or delete (it never runs today) |
| O5 | Component tests for screens (adds `@testing-library/react` + `jsdom`, which needs saying why in the PR) | new `*.test.tsx` for Settings, ItemDetail, Add | Without them, the gaps in §5 need e2e tests instead (slower) |

### 7.4 Additions (gaps, §5)

About **+20 e2e tests** (Settings controls ~8, phone-through-proxy 1–2, add progress live 1–2, navigation table
~6, item-gone 1) for est. +60–90 s, which the S8/S9 savings cover. About +6 backend (proxy-origin login/upload,
model download progress, `landing.ts` unit). Optionally about +30 component tests if O5 is approved.

### 7.5 Resulting suite (est.)

| Layer | Tests | Lines | PR runtime |
|---|---:|---:|---|
| Backend (PR, `not slow`) | ~2,665 on PR + ~120 nightly. Total ~2,790, or ~2,720 after F1 | ~30.0k (−1.0–1.3k) | ~850 s CPU → **~3.6 min local, ~7–8 min CI** (from 12.7); Windows ~10–11 min (from 17.7) |
| Bench | 349 now; ~230 after S6 moves its backend tests | ~0.9k after S6 | <30 s with `-n auto` and O2 |
| Vitest | 347 (+ optional ~30 component) | 3.6k | ~3–5 s |
| E2e | ~165 (−15 +20) | ~6.5k | **~8 min local, ~10 min CI** (from 11.7) |

Net count changes are small on purpose: the money is in CI minutes (est. −5 min per PR on the required path,
−7 min on Windows), in no longer dirtying tracked screenshots, and in the gap tests.

---

## 8. A rule for future agents: what deserves a test, and where

1. **Rules and calculations** (taxonomy, outfits, gaps, trips, spend, geometry): unit tests at the module,
   table-driven, no HTTP, no demo closet, a handful of cases per rule plus the edge that broke. Fast (<0.1 s each).
2. **Each endpoint**: through `TestClient`, one success and one test per distinct refusal or permission rule.
   Don't re-test the rule's cases through the API. Give the route test a tiny closet, not the demo, unless the
   demo itself is what's being tested.
3. **Browser (Playwright)**: one test per thing the owner does on a screen (a journey or a visible state), asserting
   what the owner sees. Never re-check backend rules there. No fixed sleeps. Screenshots only to
   `testInfo.outputPath()`, never into `docs/`.
4. **Bug fixes**: a regression test at the **lowest** layer that reproduces the bug.
5. **Over 1 s**: shrink the input or mark it `slow`, and say so in the PR. Image tests use the smallest image that shows the case.
6. **Migrations**: `test_db.py` already upgrades every version. Add a migration test only when the migration
   transforms existing data.
7. **Design and lint rules**: write them once as a rule over all files (as `design.test.ts` does), not per screen.
8. **Platform code**: fakes at the OS boundary only. Assert the outcome (e.g. that Quit stopped the server), not just that the call returned.
