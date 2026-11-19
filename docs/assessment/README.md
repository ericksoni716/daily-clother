# Assessment, 19 November 2026

A read-only assessment of the repo and the app, made from seven audits. Nothing in the app was
changed. The detail, with file and line references, is in the reports beside this file:

| Report | What it covers |
|---|---|
| `repo-bloat.md` | Dead code, superseded drawing approaches, repo weight, stale docs |
| `tests-audit.md` | Every test layer: counts, runtime, what to move, cut and add |
| `patterns-reachability.md` | Whether measured stripes and plaid can be removed (no), with `patterns-check.sql` |
| `frontshoe-reachability.md` | When the traced front view of shoes is shown on the figure, and what removing it takes |
| `ux-settings.md` | Settings, phone access and the QR code, Updates |
| `ux-items.md` | Adding items, progress, Fix details, the item page, taps, navigation |
| `ux-pages.md` | Today, Closet, Missing, Insights, Worn, Trips, Review, first run |
| `homestead-borrow.md` | What to borrow from Homestead, the owner's finance app |

The audits ran the app with demo data and stand-ins for Claude, weather and the cutout model.
Real Claude wording and timings, real speed over Tailscale, and iPhone Safari behavior (back
swipe, home-screen mode, the notch) were reasoned from code, not observed. Screenshots the
reports mention were not kept. The clone was shallow (234 commits, 15 to 19 November), so
history findings cover only that window.

## The short version

- The code is not full of dead files. Every module is reachable and the dependency lists are
  clean. The bloat is old approaches still wired in beside their replacements, 45 MB of
  screenshots, and experiment folders.
- The app's problems are mostly structural, not cosmetic: pages built in the order features
  were added, the same fact stored and shown in several places, every screen fetching for
  itself, and no shared model of "work in progress".
- The tests are not bloated by count. A few image tests take most of the time, and the gaps
  are exactly where the app feels worst.
- Homestead already solves most of this, and the patterns port cleanly.

## Owner decisions already made

- Shoe tracing stays.
- The item page reads a garment's look from one store: the description the drawing was made
  from, with the owner's corrections folded over it. Layout choices are left to the agent.
- Agents may edit the release workflow to add a What's new section to release notes. Starting
  a release and making tags stay with the owner.
- No history rewrite. Stop the screenshots growing instead.
- Measured stripes and plaid stay. An ordinary action on a new item still reaches that code
  (changing the Pattern chip, Claude returning no cloth description, a typed correction, and
  background jobs for older items). `patterns-reachability.md` lists what would have to change
  first.

## Causes of what the owner reported

| Complaint | Cause | Fix |
|---|---|---|
| Settings is long and unordered | 9 cards in the order they were built; about 7 phone screens, 45 controls, 1,105 words | Regroup into 7 short groups, with an Advanced screen (outline below) |
| Sections pop in | 16 requests on load, 3 of them twice; the main one runs two `tailscale` commands on the server, so the page grows from about 3,500px to 6,100px two seconds in | Take Tailscale off the request path, one payload, render once |
| Background remover card | It only downloads two models that startup already downloads | Delete the card, retry automatically |
| Backups at the top | Nested in the first card. They are local daily copies to a folder, not cloud | One status line near the bottom |
| Your style is a form | A chat exists but only on Today, about that day's outfits. Saving from it already appends to the style profile | A general style chat reusing that save; Settings shows a read-only summary |
| API key section is huge | About 1,850px with no key set | One status line and one action; the rest to Advanced |
| Updates too long, broken markdown | Notes are shown as plain text, and the release workflow writes only install steps, so there is no "what's new" | Render a safe subset; add a What's new section to releases (needs the owner, agents may not edit that workflow) |
| QR code on the phone | Shown whenever a share exists; nobody checks who is asking | Show only on `localhost`; on the phone show an Add to Home Screen line |
| Page transitions on iPhone | There are none. "‹ Closet" opens a new page instead of going back, so the closet reopens at the top and history piles up | Go back in history, remember scroll per page, add no animations |
| Unclear background progress | Status words live in four places; the tile shows only the cutout stage; describing and drawing are one step but the UI implies two; slow polling skips stages | One server-computed progress value per item, one strip, one "Working on N items" line |
| Fix details | The text box exists, at the bottom of about 24 fields, in a panel that pushes the page down | Open a sheet with only the text box; fields on their own screen |
| Scattered item text | Three stores describe the garment's look and disagree on screen; four free-text boxes | One summary from one source, one rating, one notes box, the rest folded |
| Taps resize the page and lag | Taps are fast (40 to 88 ms). The layout moves afterwards: panels inserted above content, buttons shrinking 3% on press, a blank placeholder on the item page, the whole app re-rendering on every save and every 2 second poll, edits redrawing on the server's main loop | Sheets, no press shrink, render from data already held, a query cache, redraw in a worker |

Also found in the parts not yet used: no error boundary (one bad response blanked the whole
app); What's missing is about 5,900px on a phone and repeats itself; Today shows a forecast
above "the weather could not be fetched"; a wear can be recorded in four places; six thumbnail
styles and five header layouts; Quit and computer-only settings are offered on the phone.

## Proposed Settings

Your style (summary, talk about it) · Everyday (weather, how you live, laundry) · Claude (one
line) · Updates (one line and Install) · Phone (computer only) · This device (look) · Your data
(backup status) · Log out.

Advanced: demo, start at login, API key, routes, limit and spending, update mode, storage,
backup folder, model address, data folder, version, Quit (computer only).

## Proposed structure

Eleven destinations become four plus Add: Today (taking in Worn and Trips), Closet (taking in
Review), one page merging Missing and Insights, and Settings.

## Repo cleanup

Low and medium risk, about 15 to 17 thousand lines and about 50 MB:

1. Stop tests and tools writing into `docs/screenshots`; delete the screenshots nothing names.
   Rewriting history to reclaim the rest is the owner's call.
2. Delete `bench/experiments/` (keep `shoe_drawn/EXAMPLES`, moved into the tests).
3. Delete `packaging/spike/` and its workflow.
4. Port `tools/make_demo.py` to the app's own pipeline, then delete the phase-0 photo fills
   and the forked cutout. Today the demo closet is drawn by different code from real items.
5. Move the backend tests out of `bench/tests`; delete the shims.
6. Unused `tools/make_*` scripts, the one dead endpoint, small frontend duplicates.
7. Fix the docs that contradict the code (listed in `repo-bloat.md`).

Open question for the owner: the traced front view of shoes on the figure (the A/B variant,
about 2.4 thousand lines and 70 tests). The decision log says the Claude drawing replaced it
and it matched 3 of 10 against 8 of 10, but it is still wired in as a fallback. This is
separate from shoe tracing for the closet picture, which stays.

## Tests

| Layer | Tests | Runtime here | In CI |
|---|---|---|---|
| Backend | 2,868 | 5m45s | 12.7 min Linux, 17.7 min Windows |
| Bench | 349 | 72 s | 86 s |
| Frontend unit | 347 | 3 s | about 1.3 min job |
| Browser | 160 | 9m45s | 11.7 min |

- 310 backend tests take 71% of the time; 1,581 take 27 seconds between them. Deleting cheap
  tests saves nothing.
- Mark about 120 image tests slow and run them nightly: Linux CI drops from about 12.7 to 7 or
  8 minutes, Windows from 17.7 to 10 or 11.
- Make fast: two window tests that wait out a 10 second timeout (and would pass even if Quit
  were broken), the demo closet rebuilt in 80 tests, fixed sleeps in the browser fakes.
- Safe to delete now: about 9 migration tests that only check columns, 4 screenshot-only
  browser tests, most of the theme and accessibility repeats.
- Add: Settings, the item page and Add have no component tests; nothing loads the app from a
  non-localhost address; nothing watches progress stage by stage; no reload or Back and
  Forward test per route.

## Suggested order of work

1. **Context for agents first**, so the rest does not repeat the mess: a `CLAUDE.md` that
   brings in `AGENTS.md`, a module map, a design document with principles and a checklist, a
   per-screen guide, a changelog, and Homestead's phone-check script. Include a rule for what
   deserves a test at which layer.
2. **Quick wins, each small:** hide the QR on the phone; Homestead's touch CSS and no press
   shrink; "‹ Closet" goes back and scroll is remembered; an error boundary; delete the
   background remover card; Fix details opens on the text box; render release notes properly.
3. **Repo cleanup and the slow-test split**, items 1 to 7 above.
4. **Data loading:** a query cache with one key file, one settings payload, Tailscale off the
   request path, `patch_item` off the main loop. This removes most pop-in and lag.
5. **One progress model** for background work, with one status endpoint.
6. **Settings regrouped**, with the Advanced screen.
7. **The item page consolidated.** Merging the three stores that describe a garment is the
   one large job and needs the owner to choose the source of truth.
8. **Style through conversation**, then the four-place structure and shared components.
