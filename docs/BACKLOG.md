# Backlog

## Phase 0 (in progress)
- [ ] Run the tagging bench on the owner's 25–30 real photos with an answer key (needs an API key in the `daily-clother` environment and the photos).
- [x] Stand-in tagging run with Haiku, Sonnet and Opus subagents on the seven test photos (see `PHASE0.md`).
- [ ] Repeat that through the real API call for cost and timing.
- [ ] Striped, floral and camouflage hard cases (photos still needed).
- [ ] Take the colour word for patterned items from the measured palette instead of the model.
- [ ] Owner picks an illustration style (A flat, B outline, C soft).
- [ ] First Actions run of the packaging spike on Windows (waiting for the owner's go-ahead on Actions usage).

## Waiting on the owner
- Illustration style: A (flat), B (outline) or C (soft shaded). The demo closet uses A until decided.
- Three photos for the untested hard cases: something striped, something floral or patterned, something camouflage.
- Go-ahead to run GitHub Actions: the Windows build and smoke test (about 16 billed minutes), and whether CI should run on every push.
- 25–30 real photos with an answer key, then the API key last, once everything before it is proven.

## Phase 1 (in progress)
- [x] Backend: data model and migrations, login, one-photo capture, cutout queue, model download states, backups and restore, demo closet, launcher.
- [ ] Frontend: closet grid, item detail, capture, settings, phone and wide layouts, offline read-only cache.
- [ ] Packaged build, smoke test, CI and release workflows.
- [ ] First green packaged build in Actions (needs the owner's go-ahead).
- [ ] Try on a real Windows PC and iPhone: tray icon, start at login, Tailscale address, camera capture, home-screen install.

## Later phases
2. Illustration pipeline in the app, correction by command, visual picker, version history.
3. Bulk import, multi-item photos and video sweeps (bench first), review queue, cost estimate and cap, storage view, item rating chip.
4. Daily outfit builder, outfit rating, mannequin layering, wear log, laundry state.
5. Gap analysis and shopping, wishlist, "would this work?", scheduled price checks on the Claude plan.
6. Taste learning analytics, cost per wear, never worn.
7. Trip packing (historical weather beyond the 16-day forecast, count-only basics).
8. Extras: calendar-aware suggestions, offline edit queue. Cut: resale suggestions, seasonal storage rotation.

## Parked
- Batches API as an opt-in "economy" mode for very large imports.
- Server-side refusal fallback for the stronger model (beta); tagging currently fails clearly on a refusal.
- Sneaker side logos and other prints on shoes are not carried onto the illustration.
- Pattern direction on sleeves (the tile is not rotated to follow the sleeve).
- Slimmer ffmpeg or download-on-first-use: the bundled binary is about 105 MB of the Windows program.
