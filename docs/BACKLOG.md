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

- [x] #150 Outfits follow the owner's outfit rules: the engine reads them from `docs/menswear-taxonomy.json`; watch, eyewear, gloves and tucking are not used yet.

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
- [x] #175 The outfit as worn by a drawn person in the garments' flat style (head with a simple face, neck, arms, hands, legs and feet; skin only where clothes leave it bare). The body sets the proportions (an average build: shoulders 2.7 head widths, hips 2, a neck half the head's width, arms that hang with a bend at the elbow and the wrists at the crotch) and each garment is fitted to it in the figure only (shoulder seams on the shoulders, sleeves to the wrist, hems at the hip, trousers to the shoe, fit and length tags kept); the item drawings are unchanged. Shoes drawn from the front on the feet, each ankle centred under its trouser leg with a small break over the instep, for every kind of shoe. Before and after pictures in `docs/screenshots/figure-*.png`.
- [ ] The demo closet's "Black overcoat" is drawn at blazer length, in its own drawing and on the figure: the template takes the coat shape only for a knee length (`templates._block_for`). To be filed as its own issue.
- [ ] A skin tone choice in Settings for the As worn figure (the drawing reads it from `SKIN` in `drawing/figure.py`).
- [x] #77 The outfit engine and the gap analysis use what the tagger saw: the cloth's weight, then the knit gauge, and the sleeve length. What the owner typed wins over the tagger; the tagger wins over a guess from the name.
- [x] #78 and #79 Trip packing (migration 0012): the weather for each day of a trip (the forecast, or what those dates are usually like from the last five years), the fewest pieces that dress every day with an outfit for each, basics by count, "Not this one" and "Take something else", and a saved trip that can be ticked off on the phone. Given to two models and compared from screenshots; the Opus 5.5 result was merged after one round of faults found in review.
- [x] #155 Trip packing with the owner's re-wear (migration 0023): "Before it needs washing" per kind of clothing in Settings (tops 1, knitwear 3, trousers and shorts 3, jackets and coats the whole trip, basics 1), hot or humid days wear what is next to the skin once, laundry on the trip on one day or every few days, and counts explained in plain words.
- [x] #85 "Would this work?": check a piece against the closet before buying it, from a photo (described by Claude through the same routes and the same monthly limit as an item; the photo is kept in memory only and never saved) or described by hand. The answer is by rule: fills a gap, works and adds something, works but you have it already, or hard to wear, with the gap it would fill, the pieces it goes with, the ones it repeats and what holds it back. Sent back once with ten faults found in review; all fixed. Known: the check compares the plain analysis with and without the piece and does not yet know how the owner lives, so it can name a gap that the weighed list ranks differently.
- [x] #88 and #89 What's missing informed by how the owner lives: a one-minute set of questions (work, everyday, going out, lounging at home, exercise, vacation, and how often), the climate of the saved place from four past years, and taste from what is worn and rated, per kind of clothing. Each suggestion says which situations it is for and the list can be narrowed to one. Until the questions are answered the analysis is exactly as before. Given to two models; the GPT 6 Astra run was the one that finished the screen and was merged after one round of ten faults found in review. Known: lounging is told from everyday by relaxed kinds and soft-cloth words, and exercise cannot tell one sport from another; the closet has no kinds for sportswear or loungewear. Trips and this each have their own lookup of Open-Meteo's archive; they could share one.

Wave 5:
- [x] #112 Shopping for a wish (migration 0018): "Find some" asks Claude, through the same routes and monthly limit as describing an item (with web search allowed), for up to 8 products on sale now that match the wish and its price range. Each is checked against the closet with the "Would this work?" rules and kept with the wish; links open in a new tab and nothing is bought or opened by itself. "Check prices" looks again on demand, and while Closet runs each wish with finds is checked at most once a day (never in the demo closet), with the price history kept and a drop shown. Known: the API route's answer tool together with web search has only been run against a stand-in, never against Anthropic.
- [x] #111 Kinds of clothing from the owner's taxonomy: the tagger reports the kind (schema version 2), the item page lets the owner set it, the fleece pullover is a warm mid layer, and lounging and exercise in What's missing go by the kind when it is known. Drawn: the fleece pullover (stand collar, snap placket, flap pocket, contrast binding, colour-blocking), training tee, technical half-zip, track jacket and twelve sportswear and loungewear trousers and shorts. Open: values for colour-blocking and binding in the owner's taxonomy (asked in the pull request); robes, pyjama sets and jerseys are drawn only from their details.

Next (not started): "Would this work?" taking how the owner lives into account.

Design (from the design review; each builds on the first):
- [x] #127 Design 1, a design system: one set of tokens in `frontend/src/styles.css` (four text levels, surfaces, see-through borders, a 1.25 type scale from 16px, 4px spacing, four radii, one depth for cards), no colour outside them, a Light / Dark / Same as this device choice in Settings → Look, and shared pieces in `frontend/src/components/ui/` used where the swap was mechanical. Layouts unchanged; `src/design.test.ts` keeps CSS on the scale. Known: the spacing tokens are not yet used by existing paddings, the model banner is still its own component, and a forced choice is applied once the script runs.
- [x] #128 Design 2, navigation: five places in the phone's bar with Add in the middle as a round button; Review reached from a note on the closet and a dot on Closet (and under Closet in the computer's menu); the computer's menu starts with Add clothes and keeps Settings at the foot; Archived only from the closet's switch; a 32px demo strip with Leave. The place search on Today (#130) and How you live on What's missing (#131) are separate issues.
- [x] #129 Design 3, the Closet grid and the item page: a page header with the count and Insights, one sticky toolbar (search, a Filter button opening a sheet on the phone and a popover on a computer with category, laundry and In use / Archived, and the Photos / Drawings switch) with the filters that are on shown as chips to remove; the model banner is a notice shown only while it needs something done and can be hidden for the session; smaller tile text. The item page reads first: the picture with its switch and "Fix the details", the name as heading with kind and colour, wearing and washing, then a Details card of label / value rows, each opening its choices in place (computer) or in a sheet (phone). On a computer the grid takes the width and a 420px panel opens only for a chosen item, scrolling with the page. New shared piece: `Sheet` in `components/ui/`. Known: the phone's search box is narrow (its placeholder can be cut), the category chips still list all nineteen kinds (#136), and the Archived link in the sidebar stays until #128.
- [x] #130 Design 4, Today and Worn, the outfit leads: the place is New York until the owner chooses one (so Today has real weather from the first open), **Use my location** on a tap, a mild-day outfit with a notice when the weather cannot be fetched, a one-line weather summary with **Change**, occasion and mood in one row, the outfit card first with **I'm wearing this** on a phone's first screen, yesterday's question above it, an empty state for a closet that cannot dress the owner yet; on Worn, the rating as a chip and the other actions under **⋯**. Known: "Use my location" needs https or the computer itself, so on the phone over Tailscale (plain http) it only explains; the place OpenStreetMap names is a town, not a street.
- [x] #131 Design 5, What's missing, Would this work? and Trips: each gap card has a labelled pill for how much it helps, one sentence for why and the rest behind "Why, day by day (N)", where a reason given for several kinds of day is said once with the days under it (on the demo closet the computer page went from about 6,250px to 4,800px tall); "I'll look for this" and "Not for me" as the shared buttons. The "Based on" line is a row that opens How you live, where the rest of what the suggestions are based on now sits. Would this work? is its own page on a computer too, the piece on the left and the answer on the right, with the wishlist kept in the side panel of What's missing. Trips use the shared page header and a card per trip and per day. Known: the "Look for" box is now the tallest part of a card; the four help levels were kept (the issue named three).
- [x] #132 Design 6, Insights, Settings, Add and the login screens: each Insights card leads with a short label, one figure and one sentence, the not-worn pieces are listed once and their Archive / Keep buttons line up; Settings is one column in groups (Your closet, Where you are, How you live, Look, Describing clothes with the plan and the key once each and the limit folded away, Phone access, Advanced folded away, then Log out / Quit as a row); one-column pages are at most 720px beside the sidebar and two-pane pages use the full width; Login and Setup use the shared card and button. Known: the route-order choice (#104) and the update settings (#137) had not landed; they go in Describing clothes and Your closet when they do.
- [x] Designs 2 to 6 landed together in one pull request (#144), as they all change `styles.css` and the same screens. Where they met: the colours measured from a pattern (#118) show beside the pattern word in the item page's Pattern row and in its choices; the In use / Archived switch Design 2 points to is the one under Design 3's Filter; the browser tests' backend keeps the shop stand-in and demo seed (#124) with Design 4's "never reach the weather service". Known: `e2e/14-leave.spec.ts` sometimes fails on a slow machine (also on `main`): the page reloads and reads the item before the save sent on leaving has arrived.
- [x] #162 The redesign checked against Designs 1 to 6 and for accessibility, on a phone and a computer in light and dark. An automated check (axe-core, `e2e/17-accessibility.spec.ts`) now runs over the main screens. Fixed: words in the faintest ink ("Not set", disabled buttons, chips, tabs and menu items) made darker; 44px touch targets on the phone; Tab kept inside sheets, popovers, the ⋯ menu and the "are you sure?" boxes, with focus back on the opener; reduced motion respected; long item names, Settings values and update notes wrap; spoken names that match what is shown; Today's yesterday question shows its pieces without making them tiny links; shopping finds use the shared card, buttons and notices. Known: tile names in the grid still end in "…".
- [x] #136 Design 3b, "What is it?": the item page's Details card starts with the item's kind from the owner's taxonomy, with its small drawing and how sure Claude was; a tap opens a picker (a sheet on the phone, a popover on a computer) with a search, the ten groups from the taxonomy, a drawn tile per kind and "Claude also thought" first. Choosing a kind sets the category that follows from it, is the owner's word in the history (undo, kept by "Describe it again"), redraws the item and hides the details the kind does not have. The Closet filters by group and by kind. No migration.

Fixes after 0.2.0:
- [x] A newer program that finds an older copy running says so and offers to close it and use the new one (it used to open the old one without a word). The owner's first test of 0.2.0 found it.
- [x] The owner's first item in 0.2.0 failed to be described after three tries. The cause: Claude Code on the owner's Mac was still signed in to a work account that had been turned off, so Anthropic refused its key ("Not a valid API key for this workspace"), and Closet took that for a bad answer. Now a refused sign-in keeps items waiting with a note saying what to do, and they go ahead by themselves once Claude Code is signed in with the plan.
- [x] A box in Settings to paste the API key, kept in the computer's keychain (Mac keychain, Windows Credential Manager) and checked with Anthropic first; replace and remove. Run against Windows Credential Manager in the CI's Windows job (#164); not yet on a real Mac keychain or the owner's PC.
- [x] #104 A choice in Settings of which route to Claude is tried first: the plan first (as before), the API key first, only the plan, or only the key. The key-first choices need a saved key; the key is still only used once allowed with a monthly limit.
- [x] A failed item shows why: the plain sentence, and a "Details" fold with the reason the job recorded (keys, tokens, e-mail addresses and paths outside Closet's folder taken out), written once to the log as well; "Try again" never queues a second job (`failure` in the item, no migration).
- [x] #114 A change made just before the page is reloaded or closed is no longer lost: saves are sent so that they outlive the page, and an edit still being typed (or trip ticks waiting their turn) is sent as the page goes away. It had been parked since a browser test raced it.
- [x] #147 A note typed just before a reload was still lost now and then (the browser test `14-leave` failed 10 times in 30): the browser dropped a save on its way through the service worker as the page went away. Saves now skip the service worker where the browser allows it.
- [x] #159 "Find some" now and then kept nothing: saving the finds read the closet before taking the write lock, so when a worker was writing at the same moment SQLite refused at once ("database is locked") instead of waiting. Every write transaction now takes the lock first and waits for it; if it still cannot save, the wish says so instead of looking as if nothing was found. A search that ended just as its finds were being read could also be shown as done with none; the run is now read before the finds.
- [x] #161 Review of the backend after the fast wave. The monthly limit could be passed when several things asked Claude at once (describing, landmarks, the pieces in a photo, "Would this work?", shopping): each looked at the month's spending alone. What a request on its way may cost is now held against the limit until it comes back. A pattern measurement that could not be kept (its drawing failed) left the item "working" and was measured again every minute ahead of every other item; it now says why and the next item goes on. The reason a failed cutout or description keeps in the database (and so in backups) is now cleaned of keys, e-mail addresses and outside paths before it is written, as it already was before it was shown. An item deleted while its background was being removed no longer leaves its cut-out pictures behind on the disk.

Patterns from the photo (owner's request; it had fallen out of the app):
- [x] Plaids flattened and placed per front, madras measured whole, stripes (regular and placed bands, sleeves checked), prints quilted; OpenCV and the second background model in the app; migration 0013.
- [ ] Florals placed motif by motif on a good photo (now pieced from the whole garment).
- [ ] Very fine stripes on small photos (a 285 px polo loses its 1–2 px pink lines).
- [x] #105 Graphic prints on tops: a top Claude calls graphic (or a novelty print) has its print lifted from the cutout in the background and drawn at its place, on its own drawing and in the outfit figure; a print that cannot be lifted leaves it plain with a note. Known: the tagging schema does not yet ask for the taxonomy's `graphic_technique` and `graphic_placement`, so a back print or a sleeve print is not told apart, and only the front photo is read.
- [ ] Graphic prints on the back or sleeves (needs `graphic_placement` in the tagging schema and a photo of the back).

## Waiting on the owner
- **Garment review**: the owner called the drawings good enough for now (after round 7). Marks and notes in the review gallery are still read when they appear; drawing work is parked until asked for.
- **Mac 0.1.1**: confirm the background-removal model now downloads on the owner's Mac.
- **The Windows build** for stop A has still not been made or tried.
- **The app's top UI complaints**, as the brief for UI tasks. A full interface-design pass comes after more features exist.
- **25–30 photos of the owner's own clothes** with an answer key (`bench/answer_key.template.csv`). Most useful: items that differ from the usual (a polo with one or three buttons, a henley, corduroy, fleece or heavy wool beside light cotton, a sweatshirt with a V-insert). The bench runs them through the Claude plan by default; an API key is optional.
- Three photos for the untested hard cases: something striped, something floral or patterned, something camouflage.
- Whether to drop the Google Drive hand-off for price checks now that the app runs them itself (#112, through the plan route while the PC is on; see DECISIONS, "Shopping for a wish"). Recommended: drop it.
- Whether multi-item photos and video sweeps stay after the outfit builder (as planned below) or move into stop B.

## Track 1: recognition and drawing (continuous)

Checkpoints, not stops:
- [ ] **Coverage of the taxonomy.** Every visible value in `docs/menswear-taxonomy.json` is listed in `bench/closet_bench/taxonomy.py` (`COVERAGE`) as drawn, approximate or not drawn. The owner looks over the render sheets; the approximate and not-drawn values are worked down, most common garments first. #163 took the first pass (470 drawn, 109 approximate, 118 not drawn before; 496, 87 and 114 after): knit textures, the hidden button-down, each trouser kind's look, notched hems, rivets and roping, the trench, parka, varsity and waxed jacket, patent shine, flip-flops, D-rings, toggle laces, the robe's sash and velvet's sheen. Before/after sheets are `docs/screenshots/coverage-*.png`, written by `tools/make_coverage_sheet.py`. Still open, most common first: plain weaves and jerseys that read as plain cloth at item size, colourwork knits (Fair Isle, Nordic, argyle), reverse and forward pleats (one pleat at grid size), back pockets and back details (the drawing is front-on), shoe uppers and laces, sportswear and lounge sets, and ties, gloves, eyewear, watches and socks.
- [ ] **Accuracy on the owner's photos.** Tagging accuracy, confidence calibration, time and cost per model, on the coarse fields and the detail fields. Decides which model tags, the review threshold, and which fields need an extra shot.

Done:
- [x] Illustration approach tested on open-licence photos; templates chosen over tracing (see `PHASE0.md`).
- [x] Owner picked style B (bold outline, thin inner lines).
- [x] Top, pants and shoe templates rebuilt from reference drawings and real garment measurements after independent reviews.
- [x] Tagger reports each garment's details in the owner's taxonomy vocabulary, plus fibre, weight class, knit gauge and corduroy wale; anything it sees that no field covers is kept as "seen but not drawn".
- [x] Tagging works through the Claude plan (`claude -p`) with the API key as fallback; seven test photos tagged with valid answers on both the coarse and the detail fields.
- [x] Hip patch pockets added to the taxonomy.
- [x] The top template draws the taxonomy's fit, sleeve, neckline, collar, placket, cuff, pocket and hem values, and shows weight, fuzzy cloth, knit gauge and corduroy wale.
- [x] #108 Shoes: loafer straps (penny, tassel, horsebit, venetian), oxford closed and derby open lacing, the number of eyelets, toe caps and brogue punching (quarter, semi, full), wholecut, and a sandal shape (slide, two-strap, strap sandal) on a footbed. Chosen from the taxonomy's footwear ids and words the tagger names; every footwear id is in `COVERAGE`.

In progress (owner's corrections to the first taxonomy sheets):
- [x] Fits recalibrated from real garment measurements: everything was drawn slim.
- [x] Tailored jackets (blazer, sport coat, suit jacket, coats with lapels) rebuilt as their own construction (by a Copilot agent, #12; drawn at the same 84% body width as every top). Waiting for the owner's verdict in the gallery (round 5).
- [x] Jacket faults left from that work (#109): sleeves splay wide and the strokes merge into a dark wedge under the arm; a double-breasted jacket that is told "2 buttons" shows one row of two instead of the usual six; lapels do not grow with an oversized fit; cuff buttons are tiny; three-roll-two draws as two-button; low-contrast buttons on some cloths; the jacket's inside barely shows on black or navy. All seven fixed, each with a test (before/after: `docs/screenshots/jacket-faults-before.png`, `jacket-faults-after.png`); waiting for the owner's verdict in the gallery.
- [ ] Weight shown much more strongly, as thickness and bulk and not only a heavier line. Done, waiting for the owner's verdict in the gallery (round 4): a heavy cloth is drawn with depth (shade inside its edges, sunken seams, a collar and pockets that stand proud). Light cloth now shows faint drape folds from the underarms and at the elbows, and a heavy knit a soft shade where the body meets its rib bands (#110). Still to do: midweight plain knits (t-shirt, cardigan, quarter zip) are still flat inside.
- [x] A worn-open state for jackets, cardigans, overshirts and zip hoodies, with a proof that an open layer lines up over a shirt (`state="open"` on a top; `layer(under, over)` in the renderer; gallery section "Worn open"). Rebuilt as layers after the owner rejected the first version: two equal fronts, buttons on one and buttonholes on the other, the garment underneath drawn whole. Waiting for the owner's verdict (round 7).

To do:
- [x] Drawing faults its own author listed (#110): the tab collar has close-set points and a buttoned strap, the wing collar larger tips; lapels on dark or patterned cloth carry a facing shade; the puffer's sides and sleeves swell between its channels; the trucker jacket has a buttoned waistband with side adjusters; the vest's armhole band keeps its width to the side seam; linen texture is sparser and fainter. Before/after sheets: `docs/screenshots/drawing-faults-*.png`. Still open: at item size the tab strap and wing tips are only specks, and tab and point collars are hard to tell apart.
- [x] Accessories drawn from the taxonomy's accessory ids and kinds: bags, belts, caps, beanies, brimmed hats and scarves have shapes of their own; ties, pocket squares, gloves, glasses, watches and socks a plain tag. The outfit figure wears a belt, scarf, hat and bag. Sheet: `docs/screenshots/accessories.png` (`tools/make_accessory_sheet.py`). Waiting for the owner's verdict.
- [ ] Shapes of their own for ties, pocket squares, gloves, glasses, watches and socks (a plain tag stands in for them today), and accessories in the demo closet.
- [ ] Shoes left after #108: a monk strap's buckles, a flip-flop's thong, apron and split toes, speed hooks and D-rings, boot kinds (chukka, western, rain), a cork footbed's grain, patent shine.
- [ ] Trousers: the taxonomy's bottoms are a signature line each; rise, fit names and jeans washes are not tagged yet.
- [ ] Re-run the tagging test with the tightened prompt (snaps, hip pockets and feature flags were wrong in the first run).
- [ ] Striped, floral and camouflage hard cases on real photos.
- [x] Take the colour word for patterned items from the measured palette instead of the model (#106).
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
- [x] #164 Ready for the Windows hub: a step-by-step Windows setup guide in the README; the Windows-only code reviewed (the plan route could not have started on Windows: describing an item made a command line longer than Windows allows; now the prompt goes on standard input, in UTF-8, and `claude.exe` is found before an npm `claude.cmd`; `taskkill` no longer flashes a console; typed Windows calls for "is it still running" and the message box); the backend tests run on Windows in CI, with real Credential Manager, start-at-login, tray and rename-while-running tests.
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
- README: installing Claude Code on Windows and checking it is signed in (done in #164, "Setting up Closet on a Windows PC").
- The bench as a `bench` command in the packaged program, so the owner's photos never leave the PC.

### Stop C: today's outfit
Original phase 4 and the rating parts of phase 6. The first stop the owner uses every day.
- Daily outfit builder (weather, event, mood, build-around-item) on the rule-based outfit engine.
- Layering rules from the weight class (what can be worn under or over what), not only from category.
- Mannequin layering, outfit rating with reasons, wear log, laundry state.

### Stop D: what's missing, and shopping
Original phase 5.
- Gap analysis (counts by code, explanations by the model), shopping by web search, wishlist, "would this work?", computer layout first.
- Price checks (#112: run by the app itself while it runs).

### After D, each its own smaller stop
- Multi-item photos: done in #151 (Claude finds the pieces, the owner checks the boxes; see DECISIONS, "Several items from one photo"). Video sweeps are out (owner's decision). Still to learn: how well Claude boxes a cluttered bed.
- Taste learning analytics, cost per wear, never worn (rest of original phase 6).
- Trip packing (historical weather beyond the 16-day forecast, count-only basics).
- Extras: calendar-aware suggestions, offline edit queue. Cut: resale suggestions, seasonal storage rotation.

### Definition of done for a stop
Tests pass, the packaged build is green in CI, demo mode works, docs are updated, and the owner is told exactly what to try from the downloaded program and what is uncertain.

## Parked
- Browser tests in `08-wears` timed out twice in local full runs (once each test in the file), both times while reviewers were also running on the machine: the demo closet's tiles were missing or kept being replaced for a minute. Not reproduced in five further runs, three of them under deliberate heavy load, and never on GitHub. Cause not found. If it comes back: run with `--trace retain-on-failure` and look at what keeps re-rendering the grid after a profile switch.
- Batches API as an opt-in "economy" mode for very large imports.
- Server-side refusal fallback for the stronger model (beta); tagging currently fails clearly on a refusal.
- Sneaker side logos and other prints on shoes are not carried onto the illustration.
- Slimmer ffmpeg or download-on-first-use: the bundled binary is about 105 MB of the Windows program.
