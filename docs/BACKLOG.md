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

Wave 2:
- [ ] #33 Tagging in the app, part 2: tag each item after its cutout and keep the full answer (migration 0006).
- [ ] #34 Today's outfits by themselves: the weather lookup, and the wear log and laundry feeding the engine.
- [x] #35 The drawing in the app, part 1: the drawing code is in the backend (`closet/drawing/`); all 203 gallery drawings came out identical.

Next: the outfit screen (two models, since it is judged by looking), the drawing shown on the item and corrections, the review queue, mannequin layering and outfit rating; then gap analysis and shopping.

## Waiting on the owner
- **Garment review**: the owner called the drawings good enough for now (after round 7). Marks and notes in the review gallery are still read when they appear; drawing work is parked until asked for.
- **Mac 0.1.1**: confirm the background-removal model now downloads on the owner's Mac.
- **The Windows build** for stop A has still not been made or tried.
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
- A change made a moment before the page is reloaded or closed can be lost, because the save is still on its way. Sending saves so that they outlive the page (a keep-alive request) would close that gap. Found when a browser test raced it.
- Batches API as an opt-in "economy" mode for very large imports.
- Server-side refusal fallback for the stronger model (beta); tagging currently fails clearly on a refusal.
- Sneaker side logos and other prints on shoes are not carried onto the illustration.
- Slimmer ffmpeg or download-on-first-use: the bundled binary is about 105 MB of the Windows program.
