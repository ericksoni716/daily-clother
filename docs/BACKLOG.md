# Backlog

The work runs on two tracks with different review rhythms (decided with the
owner; see `DECISIONS.md`, "How the work is organised").

- **Track 1, recognition and drawing:** what the tagger reports and what the
  drawing shows. Reviewed continuously from render sheets and tagging reports.
  No stops, no packaged build.
- **Track 2, the app:** what the program does. The owner tries the downloaded
  program at each stop (A, B, C, D, then smaller ones).

## In progress (Copilot agents)

Wave 1 (landed):
- [x] #20 Tagging in the app, part 1: the tagger and its two routes are in the backend; Settings shows which routes are available.
- [x] #22 Wear log and laundry state (migration 0004).
- [x] #23 Outfit engine: the rules that choose today's outfits, with an API and no screen. The same task went to two models (#23, #24); the Opus 5.5 result was merged.
- [x] #21 Bulk import of single-item photos, with duplicates caught and resume (migration 0005).

Wave 2 (landed):
- [x] #33 Tagging in the app, part 2: each item is described after its cutout and the whole answer is kept (migration 0006). The API key is only used when switched on in Settings; the demo closet is never sent to Claude.
- [x] #34 Today's outfits by themselves: the weather lookup for a saved place, and the wear log and laundry feeding the engine (`POST /api/outfits/today`).
- [x] #35 The drawing in the app, part 1: the drawing code is in the backend (`closet/drawing/`); all 203 gallery drawings came out identical.

Wave 3:
- [x] #45 and #46 The Today screen: the day, the occasion and mood, the outfits with why and warnings, "I'm wearing this", leave a piece out or start from one. Given to two models and compared from screenshots; the Opus 5.5 result was merged.
- [x] #41 and #42 What's missing: the gap analysis by rule (`GET /api/gaps`), no screen yet. Given to two models; the Opus 5.5 result was merged.
- [x] #50 The drawing in the app, part 2: every item gets its drawing (migration 0007), redrawn when it is described, when a field it shows changes, or when the drawing code is newer; a Photos / Drawings switch on the closet grid.
- [x] #51 Review queue: a Review screen with a badge shows only the fields the tagger was unsure of; confirm, change or skip.
- [x] #56 and #57 The "What's missing" screen and the wishlist (migration 0008): the gaps best first with the reasons and what to look for, "I'll look for this", "Not for me" with a reason, wishes added by hand, "I bought it". Given to two models and compared from screenshots; the Opus 5.5 result was merged.
- [x] #60 Outfits remembered and rated (migration 0010): "I'm wearing this" remembers the outfit; the Worn screen lists them, rates them (loved, fine, not again, with reasons) and wears one again; ratings move Today's scores within bounds and never let a rule-breaking outfit through. Sent back twice with faults found in review; all fixed.
- [x] #62 The packaged program is built and smoke-tested on Linux on every change to `main` and on pull requests that touch what goes into it (`package-check` workflow). It makes no release, tag or download. Windows and macOS are still built only by the release.
- [x] #63 A monthly spending limit for the API key (migration 0009): the key is only used once a limit is set, a request that could go past it is not made and the item waits and says why, every request is recorded with what it cost, and Settings shows the month, an estimate for what is waiting, and the history.
- [x] #64 Insights, reached from the Closet screen: cost per wear, pieces never worn or not worn for a long time (counted in days of their own season), worn most, how evenly each kind is worn, and what the closet is made of. Sent back once with eight faults found in review; all fixed.

Wave 4:
- [x] #70 Correct an item by picking (choices shown as small drawings) or by saying it ("it has three buttons"), with a history that can be undone (migration 0011). The owner's details are kept apart from Claude's answer and laid over it when the item, or an outfit figure, is drawn. A typed correction goes through the same routes and the same monthly spending limit as describing an item, and nothing is applied until confirmed. Sent back once with eleven faults found in review; all fixed.
- [x] #71 and #72 The outfit drawn as worn: every piece in one scale, each layer over the one beneath, open layers drawn open. On Today each outfit can be switched between its pieces and the figure (`POST /api/outfits/figure`). Given to two models and compared from the drawings; the Opus 5.5 result was merged. Known: a coat is drawn at jacket length (the coat template, not the figure).
- [x] #77 The outfit engine and the gap analysis use what the tagger saw: the cloth's weight, then the knit gauge, and the sleeve length. What the owner typed wins over the tagger; the tagger wins over a guess from the name.
- [x] #78 and #79 Trip packing (migration 0012): the weather for each day of a trip (the forecast, or what those dates are usually like from the last five years), the fewest pieces that dress every day with an outfit for each, basics by count, "Not this one" and "Take something else", and a saved trip that can be ticked off on the phone. Given to two models and compared from screenshots; the Opus 5.5 result was merged after one round of faults found in review. The re-wear numbers (a shirt two days, jeans five) still want the owner's word.
- [x] #85 "Would this work?": check a piece against the closet before buying it, from a photo (described by Claude through the same routes and the same monthly limit as an item; the photo is kept in memory only and never saved) or described by hand. The answer is by rule: fills a gap, works and adds something, works but you have it already, or hard to wear, with the gap it would fill, the pieces it goes with, the ones it repeats and what holds it back. Sent back once with ten faults found in review; all fixed. Known: the check compares the plain analysis with and without the piece and does not yet know how the owner lives, so it can name a gap that the weighed list ranks differently.
- [x] #88 and #89 What's missing informed by how the owner lives: a one-minute set of questions (work, everyday, going out, lounging at home, exercise, vacation, and how often), the climate of the saved place from four past years, and taste from what is worn and rated, per kind of clothing. Each suggestion says which situations it is for and the list can be narrowed to one. Until the questions are answered the analysis is exactly as before. Given to two models; the GPT 6 Astra run was the one that finished the screen and was merged after one round of ten faults found in review. Known: lounging is told from everyday by relaxed kinds and soft-cloth words, and exercise cannot tell one sport from another; the closet has no kinds for sportswear or loungewear. Trips and this each have their own lookup of Open-Meteo's archive; they could share one.

Next (not started; the owner asked for a pause after this wave and a release): shop searches for a wish with each find checked against the closet, price checks, "Would this work?" taking how the owner lives into account, kinds of clothing for sportswear and loungewear.

## Waiting on the owner
- **Garment review**: the owner called the drawings good enough for now (after round 7). Marks and notes in the review gallery are still read when they appear; drawing work is parked until asked for.
- **On the Mac**: confirm with 0.2.0 that the background-removal model downloads (it failed in 0.1.0 and was fixed in 0.1.1, never confirmed), and that the closet made by the older version opens: it is brought up to date by itself, with a backup made first.
- **0.2.0 is released** (13 November, Windows and Mac, built from `main` at the owner's request after wave 4): https://github.com/ericksoni716/daily-clother/releases/tag/v0.2.0. Both programs passed the smoke test and the real background-removal check on GitHub's machines. This is the first Windows build; nobody has run it on a real Windows PC yet. No new tasks are started until the owner asks.
- **The app's top UI complaints**, as the brief for UI tasks. A full interface-design pass comes after more features exist.
- **25–30 photos of the owner's own clothes** with an answer key (`bench/answer_key.template.csv`). Most useful: items that differ from the usual (a polo with one or three buttons, a henley, corduroy, fleece or heavy wool beside light cotton, a sweatshirt with a V-insert). The bench runs them through the Claude plan by default; an API key is optional.
- Three photos for the untested hard cases: something striped, something floral or patterned, something camouflage.
- Whether to drop the Google Drive hand-off for price checks now that the app can run them itself through the plan route while the PC is on (recommended: drop it).
- Whether multi-item photos and video sweeps stay after the outfit builder (as planned below) or move into stop B.

## Track 1: recognition and drawing (continuous)

Checkpoints, not stops:
- [ ] **Coverage of the taxonomy.** Every visible value in `docs/menswear-taxonomy.json` is listed in `bench/closet_bench/taxonomy.py` (`COVERAGE`) as drawn, approximate or not drawn. The owner looks over the render sheets; the approximate and not-drawn values are worked down, most common garments first.
- [ ] **Accuracy on the owner's photos.** Tagging accuracy, confidence calibration, time and cost per model, on the coarse fields and the detail fields. Decides which model tags, the review threshold, and which fields need an extra shot.

Done:
- [x] Illustration approach tested on open-licence photos; templates chosen over tracing (see `PHASE0.md`).
- [x] Owner picked style B (bold outline, thin inner lines).
- [x] Top, pants and shoe templates rebuilt from reference drawings and real garment measurements after independent reviews.
- [x] Tagger reports each garment's details in the owner's taxonomy vocabulary, plus fibre, weight class, knit gauge and corduroy wale; anything it sees that no field covers is kept as "seen but not drawn".
- [x] Tagging works through the Claude plan (`claude -p`) with the API key as fallback; seven test photos tagged with valid answers on both the coarse and the detail fields.
- [x] Hip patch pockets added to the taxonomy.
- [x] The top template draws the taxonomy's fit, sleeve, neckline, collar, placket, cuff, pocket and hem values, and shows weight, fuzzy cloth, knit gauge and corduroy wale.

In progress (owner's corrections to the first taxonomy sheets):
- [x] Fits recalibrated from real garment measurements: everything was drawn slim.
- [x] Tailored jackets (blazer, sport coat, suit jacket, coats with lapels) rebuilt as their own construction (by a Copilot agent, #12; drawn at the same 84% body width as every top). Waiting for the owner's verdict in the gallery (round 5).
- [ ] Jacket faults left from that work: sleeves splay wide and the strokes merge into a dark wedge under the arm; a double-breasted jacket that is told "2 buttons" shows one row of two instead of the usual six; lapels do not grow with an oversized fit; cuff buttons are tiny; three-roll-two draws as two-button; low-contrast buttons on some cloths; the jacket's inside barely shows on black or navy.
- [ ] Weight shown much more strongly, as thickness and bulk and not only a heavier line. Done, waiting for the owner's verdict in the gallery (round 4): a heavy cloth is drawn with depth (shade inside its edges, sunken seams, a collar and pockets that stand proud). Still to do: a sign of its own for light cloth (drape wrinkles), and more depth on plain knits, which have few seams to show it.
- [x] A worn-open state for jackets, cardigans, overshirts and zip hoodies, with a proof that an open layer lines up over a shirt (`state="open"` on a top; `layer(under, over)` in the renderer; gallery section "Worn open"). Rebuilt as layers after the owner rejected the first version: two equal fronts, buttons on one and buttonholes on the other, the garment underneath drawn whole. Waiting for the owner's verdict (round 7).

To do:
- [ ] Drawing faults its own author listed: the tab and wing collars barely read, lapels on black and plaid read only by their edges, the puffer has channels but no puffed outline, the trucker jacket has a rib band where a waistband belongs, the vest's armhole rib thins at the underarm, linen texture is busy at full size.
- [ ] Accessories (bag, belt, hat, scarf) have categories but no drawing; today they would be drawn as a crew-neck top. They need simple shapes of their own or a neutral placeholder.
- [ ] Shoes: the loafer strap, lacing on dress shoes, a sandal shape.
- [ ] Trousers: the taxonomy's bottoms are a signature line each; rise, fit names and jeans washes are not tagged yet.
- [ ] Re-run the tagging test with the tightened prompt (snaps, hip pockets and feature flags were wrong in the first run).
- [ ] Striped, floral and camouflage hard cases on real photos.
- [ ] Take the colour word for patterned items from the measured palette instead of the model.
- [ ] One real call through the API-key route for cost and timing (deliberately last; it costs money).

Rules that keep the two tracks independent:
- The templates keep the same anchor points (neck, shoulders, waist, hem, ground) whatever else changes, so the mannequin view can rely on them.
- Category, formality, season and weight class are what outfit and gap logic read. Their vocabularies are settled before stop C; the finer details can keep growing after it.

## Track 2: the app

### Stop A: the program on the owner's PC and iPhone (built; waiting for its first real build)
Original phase 1.
- [x] Backend: data model and migrations, login, one-photo capture, cutout queue, model download states, backups and restore, demo closet, launcher. 42 tests.
- [x] Frontend: closet grid, item detail, capture, settings, phone and wide layouts, offline read-only cache. 22 unit tests, 15 browser tests (one runs a real cutout).
- [x] Packaged build, smoke test (plus a real-cutout mode), CI and release workflows. Passes on Linux, including a browser run against the packaged program.
- [x] First packaged build on macOS (0.1.0). The owner tried it: passphrase, browser, demo closet and uploads (including AVIF) work; the model download failed and is fixed in 0.1.1.
- [ ] First packaged build on Windows.
- [ ] Owner tries it on a real Windows PC and iPhone. Not yet exercised: tray icon, start at login, the Tailscale address, camera capture, home-screen install, HEIC from the phone, the model download progress bar, dropping a folder of photos.
- [ ] Pin the macOS-only tray dependencies after the first Mac build.

### Stop B: the owner's real wardrobe in
Original phase 2 and the single-photo parts of phase 3.
- [x] Storage view in Settings: total, photos, cutouts, thumbnails, backups, the model, items and free space (`GET /api/storage`).
- Tagging in the app through the two routes (move `bench/closet_bench/routes.py`, `claude_cli.py`, `tagging.py` into the backend); Settings shows which routes are available and their order.
- Store the tagger's full answer (coarse fields, details, schema version) and the cutout with each item, so better drawings need no data change and a taxonomy edit only means re-tagging.
- The drawing in the app, with "seen but not drawn" beside it.
- Correction by command, including details ("it has three buttons", "the collar is white"); visual picker; version history.
- Review queue showing only uncertain fields.
- Bulk import of single-item photos, with dedupe and resume.
- Cost estimate and spend cap (API route only), item rating chip.
- The app's stored vocabulary (`backend/closet/vocab.py`, the frontend labels) moves to the taxonomy.
- README: installing Claude Code on Windows and checking it is signed in.
- The bench as a `bench` command in the packaged program, so the owner's photos never leave the PC.

### Stop C: today's outfit
Original phase 4 and the rating parts of phase 6. The first stop the owner uses every day.
- Daily outfit builder (weather, event, mood, build-around-item) on the rule-based outfit engine.
- Layering rules from the weight class (what can be worn under or over what), not only from category.
- Mannequin layering, outfit rating with reasons, wear log, laundry state.

### Stop D: what's missing, and shopping
Original phase 5.
- Gap analysis (counts by code, explanations by the model), shopping by web search, wishlist, "would this work?", computer layout first.
- Price checks.

### After D, each its own smaller stop
- Multi-item photos and video sweeps (bench first; decides ffmpeg bundled or downloaded on first use).
- Taste learning analytics, cost per wear, never worn (rest of original phase 6).
- Trip packing (historical weather beyond the 16-day forecast, count-only basics).
- Extras: calendar-aware suggestions, offline edit queue. Cut: resale suggestions, seasonal storage rotation.

### Definition of done for a stop
Tests pass, the packaged build is green in CI, demo mode works, docs are updated, and the owner is told exactly what to try from the downloaded program and what is uncertain.

## Parked
- Browser tests in `08-wears` timed out twice in local full runs (once each test in the file), both times while reviewers were also running on the machine: the demo closet's tiles were missing or kept being replaced for a minute. Not reproduced in five further runs, three of them under deliberate heavy load, and never on GitHub. Cause not found. If it comes back: run with `--trace retain-on-failure` and look at what keeps re-rendering the grid after a profile switch.
- A change made a moment before the page is reloaded or closed can be lost, because the save is still on its way. Sending saves so that they outlive the page (a keep-alive request) would close that gap. Found when a browser test raced it.
- Batches API as an opt-in "economy" mode for very large imports.
- Server-side refusal fallback for the stronger model (beta); tagging currently fails clearly on a refusal.
- Sneaker side logos and other prints on shoes are not carried onto the illustration.
- Slimmer ffmpeg or download-on-first-use: the bundled binary is about 105 MB of the Windows program.
