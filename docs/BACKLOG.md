# Backlog

## Phase 0 (in progress)
- [ ] Run the tagging bench on the owner's 25–30 real photos with an answer key (needs an API key in the `daily-clother` environment and the photos).
- [ ] Run the hard cases through the app's real tagging call instead of hand-set attributes.
- [ ] Owner picks an illustration style (A flat, B outline, C soft).
- [ ] First Actions run of the packaging spike on Windows (waiting for the owner's go-ahead on Actions usage).

## Phase 1
- Project skeleton (`backend/`, `frontend/`), data model and migrations, demo mode with about 30 sample items.
- Closet grid, item detail, one-photo capture, cutout job queue, model download states.
- Passphrase login, `tailscale serve` instructions, PWA shell with read-only offline cache (thumbnails).
- Packaged build and release workflow; tray icon, single instance, start at login.
- Backup before migration, nightly backup with catch-up, one-command restore.

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
