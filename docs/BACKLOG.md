# Backlog

The work runs on two tracks with different review rhythms (decided with the
owner; see `DECISIONS.md`, "How the work is organised").

- **Track 1, recognition and drawing:** what the tagger reports and what the
  drawing shows. Reviewed continuously from render sheets and tagging reports.
  No stops, no packaged build.
- **Track 2, the app:** what the program does. The owner tries the downloaded
  program at each stop (A, B, C, D, then smaller ones).

## Left over from finished work

What a finished piece of work left undone, newest first. Any agent may add a line here (and
only here); take a line out when it is done.

- **Telling the search who you are** (23 November; DECISIONS, "What the search is told about you").
  Not tried with the real Claude: whether the block changes what it finds, and how much longer the
  prompt makes a search through the API key. The style conversation does not ask for sizes, and an
  item's own size is not checked against the saved one. Belts and hats have no size kept. The
  Google Shopping button of step 1 can now add the size and brands.
- **The wish page and price news** (23 November; DECISIONS, "The wish page and price news"). Telling
  the owner on their phone when Nines is not open (a push notification or an email) is not built and
  awaits the owner: it needs Nines reachable from outside, or a service holding the phone's address
  or an email password. "See them" on the banner opens the Wardrobe at its top; on a phone the
  wishlist is below Worth buying.
- **A link judged against the closet, and Google Shopping** (23 November; DECISIONS, the section of
  that name). Built and tested with Claude and the web stood in for; not yet tried with real calls on
  real shops' pages, so how well a page's words alone give the colour and pattern is not known. Left
  undone: the product's picture is not sent to Claude (text only, on purpose, for now); a link that
  waited is described only when its page is read again (Check now, or the daily round the day after),
  not as soon as Claude can be reached; "Would it go with my clothes?" on a described link still
  starts from the name alone rather than from Claude's description; the Google Shopping search has no
  size or brands (step 3) and is always "men's".
- **The wishlist's own page** (23 November; DECISIONS, "The wishlist's own page"). Would this work?
  opened from a wish ("Would it go with my clothes?") still goes back to the Wardrobe, not to the wish
  or the wishlist. The toast after "I'll look for this" cannot open the list: toasts take no action.
- **Checkout codes** (23 November; DECISIONS, "Checkout codes"). Nines reads a code only from a
  page's text: text a page hides with its styles (`display: none`, `hidden`) is still read, a
  code's end date is not, and a banner put in by a script is never seen. Claude's finds get a
  code only from Claude's price checks. On the wishlist's row a long code can cut the shop's name
  off with "…".
- **The gap list worked out once at a time** (23 November; DECISIONS, of that name). What is left of a
  search's wait is "Would this work?" itself: each find runs the outfit engine over the 40 kinds of day
  with the piece (about 3 s of one core on the demo's closet, nearly all in `outfits._search`), so the
  browser tests' search for two finds is still about 7 s of work, each price check the same. On a runner
  much slower than the slowest seen so far it could reach its 30 s wait again; making the engine's search
  quicker is the way, not a longer wait.
- **Choosing a shade** (22 November; DECISIONS, "Choosing a shade"). The review's question about
  a doubtful colour and Would this work?'s colour still offer the colour words only, and the
  closet's search does not find a piece by its shade's name.
- **Formality between two levels** (22 November; DECISIONS, "Formality between two levels"). The review
  queue shows a doubtful formality's main level only: "That's right" keeps a second level Claude gave,
  but choosing another level there makes it one level, and the second is not shown. A gap's "look for"
  is always one level, even for "another like your loafers". Not yet tried with Claude's real answers:
  how often it gives a second level, and for which pieces.
- **Tennis and golf shoes** (22 November; DECISIONS, "Tennis and golf shoes"). The demo closet has
  none, so the demo and the phone check show them only once a shoe is said to be one. A trip has
  no "Tennis" or "Golf" choice to pack them by itself (only "I want to take this"). The rules build
  an outfit around a pair when asked (`build_around`), but Today's screen offers building around
  only a piece already in one of its outfits, so a pair it leaves out (like swim trunks or
  loungewear) cannot be built around from the page; a "Build today's outfit around it" on the
  item page would open that. Choosing a
  golf shoe by hand draws its usual nubs even over spikes Claude saw, as every kind's pick draws its
  usual look; nubs are faint on the dark sole they default to when no sole colour is known.

- **Wishlist links and their prices** (22 November; DECISIONS, "Wishlist links and their prices").
  Built and tested with the web and Claude stood in for; not yet tried on real shops' pages, nor
  the iPhone Shortcut (README) on a real iPhone, nor the share sheet on a real Android phone.
  A link is now judged against the closet once Claude has described it from its page's words
  (DECISIONS, "A link judged against the closet, and Google Shopping"). Left undone: a page that
  turns programs away (bot protection) goes to Claude every day it is checked;
  only microdata given as `content` is read, not a price written as the element's text; a wish's
  name cannot be changed on its page (the API takes it); a link shared while the computer cannot
  be reached is not kept for later.

- **Swim trunks** (22 November; DECISIONS, "Swim trunks"). The demo closet has no swim trunks, so
  the demo and the phone check show a trip packing them only when a piece is said to be swim trunks
  (a demo item needs a full `tools/make_demo.py` run with the cutout model). Once the owner has
  turned "Swimming or the beach" on or off, the screen offers no way back to following the weather
  (the API takes `swim: null`). Board shorts and other swimwear are not kinds; the picker's search
  finds swim trunks for them.

- **Claude adds to a garment's drawing** (22 November; DECISIONS, "Claude adds to a garment's
  drawing"). Built and tried with real calls on two of the demo's photos; waiting for the owner
  to try it on their own pieces. Left undone: only the front is drawn on (a pair of trousers'
  small back drawing, `back_from_answer`, gets none, and Claude says so of anything on the back);
  Claude adds parts but cannot reshape or remove the template's own (it points to the details);
  the parts are in the template's coordinates, so a detail that changes the garment's shape can
  leave them out of place (the sheet says so, and the owner asks Claude to move them); a line
  being drawn when Nines closes is not started again by itself, nor is one sent while Claude
  could not be reached.

- **Ribbing and the trim colour** (22 November; DECISIONS, "A top's ribbing, a collar in the trim
  colour, and plain weave on a knit"). Only tops draw their ribbing in their own colour with ribs:
  joggers' ribbed cuffs (drawn with their ribs since 22 November) and a sock's or beanie's cuff
  still take the lighter or darker tint. A garment with edges bound in a contrast colour but a
  collar of its own cloth (an overshirt) is drawn with a contrast collar, since one trim colour
  covers both; the owner fixes it with collar and cuff colour, "same as the body".

- **Windows keeping Nines running** (21 November; DECISIONS, "Kept running by Windows"). Built and
  tested only with Windows stood in for, plus one test that registers a real task on the CI's
  Windows runner (an administrator, without the prompt). To try on the owner's own PC after the
  release, in this order: the administrator prompt and a declined one; which way it starts (turned
  on, then restart the PC without signing in and open Nines from the phone); the window closing and
  opening again onto the copy Windows runs; Nines killed in Task Manager coming back within five
  minutes; the API key and the Claude plan used by a copy started before sign-in (Claude Code's
  sign-in has not been tried there at all); opening Nines just after boot; an update through the
  task, and a newer `Nines.exe` opened by hand; Turn this off, which brings back an ordinary copy
  and Start Nines when I log in if it was on. Whether the account may stop the task with `schtasks
  /End` (only read and run are granted) is not known; nothing relies on it.
- Also left by it, to settle once tried on a real computer (21 November, from the review):
  - `SetSecurityDescriptor(..., 0)` lets Task Scheduler add its own entry for the task's principal, which may give the
    owner's account more than read and run. Flag 0x10 stops that, but whether the task then still runs for its
    principal is not known, so it stays as it is until tried.
  - The one-file program unpacks its pages into %TEMP%, which a clean-up tool may empty under a copy that runs for
    weeks while its health check still answers. A fixed unpack folder, or a health check that sees the page is
    there, would settle it.
  - If Credential Manager can be read but not written before sign-in, a key saved from the page goes only into the
    sealed file while the old one in Credential Manager keeps winning.
  - A missing or damaged marker (`background.json`) while the task still exists leaves Settings unable to turn it off.
  - The elevated script writes its result into Nines' folder, which the owner's programs can write.
- Left by it for a later rename of the program: the copy Windows runs is `Nines.exe` in
  `%LOCALAPPDATA%\Nines`, under the task `Nines` (`EXE_NAME`, `TASK_NAME` in
  `closet/background.py`), whatever the release file is called. A rename of the task or of that
  folder needs code that removes the old task and folder, since the task is changed only behind the
  administrator prompt.

- **Today's first outfit sometimes takes over 20 seconds in the browser tests in CI** (21 November). `e2e/32-places.spec.ts:42` failed on that wait in #288 and passed when run again; #286 met the same wait and lengthened it from 10 to 20 seconds. The cause is not known: on a loaded machine outside CI the outfit appears in about a second, in that spec and by itself. To find: what Today waits on in the demo closet just after the closet is switched while other spec files run.
- **A shoe's side drawn by Claude** (20 November; DECISIONS, "A shoe's side drawn by Claude").
  Left:
  - Worked examples for the side: once the owner has side drawings they like, show them as
    examples (as the front's three liked drawings are), instead of only the plain templates.
  - Not yet tried on the owner's own pairs; one trial on the open-licence held sneaker only,
    whose photo does not trace (the shoe runs off the photo), so the measured path has not been
    tried on a real photo.
  - Time and cost per shoe not measured beyond that one trial (the side by itself through the
    plan, `tools/draw_shoe_photos.py --side-only`: 120 s, three calls, said good at the second
    check, about $0.33 at the API key's prices), nor how often the side, beside the turns, ends
    up the longest part of a drawing.
  - Correcting the side with a note (21 November; DECISIONS, "Which drawing a note is about"):
    tried only with stand-ins for Claude, never with a real call; `tools/correct_shoe_drawing.py
    --side` has no trace to read, so it runs without the measured proportions.
- The program file and the data folder renamed to Nines (21 November; DECISIONS, "The program file: Nines"): the folder's move and the carrying over of start at login were tried only on Linux and with a stand-in registry; the first run on Windows is the owner's own, from `Closet.exe` 0.11.0. The release notes' first-run steps still say the program opens in the browser and shows a coat-hanger icon.
- The word sweep (22 November; DECISIONS, "The word sweep: Closet to Nines"): moving the API key in the keychain from the entry named Closet to Nines was tried only with stand-ins and, on Windows, in the CI's own Credential Manager; the first run on the owner's PC and a Mac is the real one. Renaming the backup folder's `Closet backup` was tried only on Linux, never inside a synced OneDrive or iCloud folder. Past CHANGELOG entries, DECISIONS entries before the sweep and the assessment keep the old name on purpose.
- **The doors decide who comes in** (the three pull requests to the other app's access model,
  20 to 22 November; DECISIONS, "The doors decide who comes in"): the passphrase is gone, and a
  Tailscale request that names no one is refused. Still to try on real devices after the
  release: the phone through Tailscale opening straight onto the closet with no passphrase and
  This device naming the owner; the Windows hub, where the Tailscale service check runs,
  including a copy Windows keeps running before sign-in (the check may not be allowed to ask
  for the service there, which is meant to be believed, not refused; only reasoned, never run);
  a device on the tailnet that Tailscale does not name (a tagged device) showing "Nines could not
  tell who you are"; a page from 0.12.0 left open on the phone across the update (it should open
  the closet, or say to reload); Forget saved copies on the phone; and, if wanted, a real
  Cloudflare tunnel, including Cloudflare's sign-in running out on an open page (only tested at
  the unit level). `packaging/smoke_test.py` was changed for the missing passphrase and has not
  been run against a packaged build yet; the release workflow runs it.
- **Shoe drawing made faster** (20 November): two shoes at once, and a check that says good
  stops being read there. Left: the plan route still reads every check's whole answer; nobody
  has yet timed a real shoe with either change, so "four to ten minutes" in the app is
  unchanged; and a check cut short is counted from its time at 200 tokens a second
  (`correcting.CUT_TOKENS_PER_SECOND`), an estimate nobody has yet checked against a real
  run's billed output.
- **Four places and shared components** (step 8 of the order of work, second part, 20 November).
  Left:
  - Reading load (the phone check's count at 393px, demo closet): Today about 500 words on the
    page (its first screen is within budget; the reasons in "Why this works" and the
    conversation make most of it), the Wardrobe about 470 (from about 720 for What's missing
    plus 470 for Insights), a saved trip about 370. Settings, Add and the rest are within it.
    The check warns but does not fail yet.
  - Occasion and mood are still two rows of chips above the outfit; the assessment's one
    compact control ("Casual · As usual ▾") is not done. "Tell Claude" is still a box under the
    outfits, not a sheet over them.
  - Item thumbnails: Today, Worn, Recent outfits, the Wardrobe and Would this work? use
    `ItemThumb`, but at their own sizes (several classes); the closet's tiles and a trip's
    pieces have their own markup. One size scale for thumbnails is not decided.
  - Headers: Worn, Trips, Review, a wish and the Wardrobe use `PageHeader` with its back link;
    the item pages under Today, the closet and the Wardrobe still have their own "‹ Place" row
    (the item page was being rewritten at the same time, so it was left alone).
  - `SaveStatus` is used for ratings and a wish's note only; the item page, Settings and the
    trip's checklist still say saves in toasts. `Fold` could shorten Settings' groups (see
    Settings regrouped, below) and Advanced.
  - The "describe by hand" form of Would this work? is still the 67-control wall (assessment,
    Would this work? 1); cost per wear and the price checks are parked one level down, not
    removed, as asked.
  - Trips is not in the sidebar on a computer either; if the owner misses it there, it is one
    line in `NAV` in `Shell.tsx` and a decision to change.
  - The wishlist never had an address of its own; `/wishlist` leads to the Wardrobe.
- **Style through conversation** (first part of step 8 of the order of work, 20 November).
  Left:
  - Today does not ask the questions the stylist cannot infer yet (the assessment: at most one
    a day, inside Today's conversation, when it bears on the outfit); only the style
    conversation in Settings asks them.
  - Ratings of worn outfits do not offer lines for Your style, and How you live is still a form
    rather than asked one question at a time.
  - A line kept from the style conversation makes Today ask Claude again on its next open (as a
    change by hand does); it could move the day's answer instead, as a line kept on Today does.
  - Lines cannot be reordered except by Edit the text.
  - The second half of step 8 (the four-place structure and shared components) is separate.
- **The item page consolidated** (step 7 of the order of work, done 20 November). Left:
  - The failure notices (the pattern could not be measured, the cutout or the description
    failed) are now together under the picture, but still come into the page above the name
    when a step fails while you look. Laying them over the picture as the strip is would need
    room for their longer text and Try again.
  - The `silhouette` column still holds a copy of Claude's shape for an item Claude described.
    Nothing reads it for the look any more (only the history and `drawn_answer`, which ignores
    it unless the shape is the owner's); dropping the copy would need a migration and a change
    to how the history records a new description.
  - The details one by one are still a view in the sheet, not a route (`/item/<id>/details`),
    and the old notes boxes are only emptied once you edit the one box; a closet keeps them
    until then.
  - "What is it?" still says "Kind not said yet" and shows the group in place of a kind the
    assessment called jargon; the Details rows for formality and season are rarely changed and
    could go further down.
  - The phone check shows the item page with its folds closed; there is no picture of them
    open except from a browser test run by hand.
- **Settings regrouped** (step 6 of the order of work, done 20 November). Left:
  - The main page is about 1,820px and 201 words on a 390px phone with the demo closet and
    no phone share (about 2.2 screens), down from about 6,100px and 1,105 words, not the 1.5
    screens the outline hoped for; the Phone group's setup steps take the most room until
    the share works. A Homestead-style `Fold` per group would shorten it further.
  - Not done, because they change what Nines does on the computer without being asked: start
    at login turned on at first run, and a backup folder proposed by itself (iCloud Drive or
    OneDrive). A folder picker for the backup folder in Nines' own window is not done
    either; the path is still typed.
  - The route order still has its four choices; the assessment suggested two ("plan first,
    key as backup" and "key only"), which changes a setting's meaning and is the owner's call.
  - Allow the API key and the monthly limit are still two steps, not one.
  - The items waiting to be described are counted on Advanced only; step 5's progress line
    should say it on the closet.
  - A key put in the keychain by hand still shows only after a restart (from step 4).
- **One progress model** (step 5 of the order of work, done 20 November). Left:
  - Why the work waits is known on the server only for the monthly limit, Claude Code's
    sign-in, background removal and "Claude could not be reached on the last try" (kept in
    memory by the describing queue). A description waiting because no way to reach Claude is
    set up at all says "Waiting until Claude can be reached"; it could say what to set up.
  - Measuring a pattern and tracing a shoe have no job row, so "next in line" for them is a
    guess from the state alone; an item whose measuring is stuck behind a slow one looks the
    same as one being measured.
  - The item page's strip says the short reason a piece waits; the long sentence (the monthly
    limit's) is only on Add and in the "Working on N items" list.
  - The demo closet never has work under way, so the phone check shows none of this; the
    browser test `30-progress` takes the pictures instead (in its own output folder).
- **Data loading** (step 4 of the order of work, done 20 November). Left:
  - The cache is not saved on the device. Doing that (Homestead's `offline.ts`) would replace
    `saveTrips`, `saveGaps` and the other hand-made offline copies.
  - The updates status lives in the `updates.ts` store and under the `updates` key; the store
    could become the query.
  - `TOUCHES.source` covers both moving a box in a photo of several pieces and adding the
    pieces, so Several marks keys stale by hand for a box change. Consider two kinds.
  - The Wardrobe (was What's missing) still asks for its lists again when you come back from a check, because a
    browser test adds a wish behind the page's back and expects to see it.
  - The browser test `12-would-work` expects one wish, but the demo closet starts with two; it
    passes only because an earlier spec in the run removes them.
  - A key put in the keychain by hand, or `ANTHROPIC_API_KEY` set, while Nines runs shows in
    Settings only after a restart (the key's line is now read once and kept).
  - Some rows on Advanced settings can still change height when a slow answer lands: a long
    Claude Code detail, a failed check, a disk whose free space cannot be read. (The main
    page's Claude line keeps one line's height while it checks.)
- **Repo clean-up and the slow-test split** (step 3 of the order of work, done 20 November). Left:
  - `docs/screenshots/` still holds about 150 pictures (25 MB) that DECISIONS or this file
    name, most of them only by a pattern in a finished item (`figure-*.png`, `fit-*.png`,
    `*-depth-*.png`, `drawing-faults-*.png`). Deleting those, and rewriting history to
    reclaim the rest, are the owner's call.
  - The bench is now only `trace_shoes` with its fork of the cut-out (`bench/closet_bench/cutout.py`)
    and two stand-in modules. Whether it stays is the owner's call (the tests audit, O2).
  - The slowest test (`test_patterns`, a plaid from a dark photo) sets how long the slow job
    takes; a smaller made-up photo would cut it most.
  - Not done from the tests audit: the demo closet built once per test session (S2), the two
    shop tests on a small closet (S4), column-only migration tests (S5), fewer theme and
    accessibility repeats (S8), gates instead of sleeps in the browser fakes (S9), and the
    missing tests it lists (Settings controls, a non-localhost address, progress stage by stage).
  - `06-model.spec.ts` still never runs anywhere; the nightly workflow could download the
    model and run it.
  - The leather sneakers in the demo closet lost their thick sole: no answer value gives a
    court sneaker one.
- **Quick wins** (step 2 of the order of work, done 20 November). Left:
  - After the next release, the first pull request that touches `CHANGELOG.md` moves the
    released lines from *Unreleased* under a `## <version>` heading (`docs/DEVELOPING.md`,
    "Releasing").
  - Fix the details: the details one by one are a view inside the sheet, not a route of
    their own (`/item/<id>/details`), and "Changed as you said" has no Undo, because a toast
    cannot carry a button yet. Undo is still in History.
- **Context for agents** (step 1 of the order of work in `assessment/README.md`, done 19 November):
  `CLAUDE.md`, `docs/DEVELOPING.md`, `docs/DESIGN.md`, `docs/USING.md`, `CHANGELOG.md` and
  `frontend/scripts/phone-check.mjs` exist. Left:
  - `docs/DESIGN.md` states where the app is headed; some screens do not meet it yet.
  - Not ported from Homestead: a sweep that counts each screen's words against the budget in
    `DESIGN.md`, a `/design-review` skill, and a README for `components/ui/`. Worth doing
    with step 6 or 8, when screens are reshaped.
  - `README.md` still mixes the owner's guide with notes that are now in `USING.md`
    (a trip, shoes, several pieces). Shorten it when those screens next change, not before.
  - The phone check is run by hand. Whether CI or the release should run it is the owner's
    call (it adds a few minutes).

## In progress (Copilot agents)

- [x] #218 Backups: a restore cut short (a power cut, a forced quit) is finished or undone at the next start, from a journal of its moves, and the owner is told once. Backup images are kept by content, so restoring an older snapshot gives back its own cutouts; old backups still restore.
- [x] #217 The login is checked before an upload is read, and every request is cut off with 413 as soon as it goes past its size limit (`closet/gate.py`, limits in `closet/limits.py`); found by the stack review (#210)
- [x] #202 Adversarial review of frontend core: fixed interrupted-response handling, stale list and item reads, lost drafts on Back or refresh, reconnect recovery, overlapping item edits, and save-queue error/lifetime handling. Each fix has a regression that failed first. Follow-ups left for an owner decision or cross-stack work: shared profile switches across tabs and queued uploads, failed/offline logout, and ordering of saves forced out when a page closes.

- [x] #199 Adversarial review of planning: fixed hot-day packing with unlimited re-wear, missed feels-like forecast changes, malformed trip weather, removal during price checks, partial rejected wishlist edits, API-disable races, and situation claims using unsuitable partners or requiring shoes indoors. Each fix has a regression that failed first.

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
- [x] #71 and #72 The outfit drawn as worn: every piece in one scale, each layer over the one beneath, open layers drawn open. On Today each outfit can be switched between its pieces and the figure (`POST /api/outfits/figure`). Given to two models and compared from the drawings; the Opus 5.5 result was merged. Known: a coat is drawn at jacket length (the coat template, not the figure); fixed for the overcoat in #181.
- [x] #175 The outfit as worn by a drawn person in the garments' flat style (head with a simple face, neck, arms, hands, legs and feet; skin only where clothes leave it bare). The body sets the proportions (an average build: shoulders 2.7 head widths, hips 2, a neck six tenths of the head's width, arms that hang close to the body with a bend at the elbow and the wrists at the crotch; bare feet in sandals are one shape with the legs) and each garment is fitted to it in the figure only (shoulder seams on the shoulders, sleeves to the wrist, hems at the hip, trousers to the shoe, fit and length tags kept); the item drawings are unchanged. Shoes drawn from the front on the feet, each ankle centred under its trouser leg with a small break over the instep, for every kind of shoe. Before and after pictures in `docs/screenshots/figure-*.png`.
- [x] #179 As worn shows how each garment sits: ease by fit (slim and tailored shaped at the waist, regular a little room, relaxed and boxy straight from the shoulder, oversized with dropped shoulders and a longer body), trouser legs by leg shape, hems at body landmarks (waist, hip, below the hip, thigh, knee), sleeves ending by their length, cropped trousers showing the ankle; rounder sleeve tops, no sliver at a slim shirt's waist and a smooth hood under a jacket. The item page has a line of fit words, each opening "Fix the details" at its field. Pictures in `docs/screenshots/fit-*.png` (`tools/make_fit_shots.py`, since removed; in the git history). No fold or drape lines yet, by the owner's choice.
- [x] #193 As worn draws garments as 3D shells around the body, flattened: depth layers back to front, the arms over a loose top's sides and under its sleeves, sleeves as tubes the arms come out of (an oversized tee shows the forearm below a wide sleeve near the elbow), an open coat showing the trousers and the layers under it between its fronts instead of a flat strip. Slim and regular tees read apart; a long coat reaches just above the knee. The scarf on the figure is a wrap round the neck at its depths (back of the loop, band, crossed ends), with a bag's chest strap under its ends. The rain shell's hood lies down on its shoulders in its own drawing (`DRAWING_VERSION` 13). Before and after pictures in `docs/screenshots/*-depth-*.png`. Known, not done: a slim tee's shoulder corners and waist are still a little angular; a few 1 px slivers at hems.
- [x] #223 As worn places the trouser hem on the shoe in 3D: a leg narrower than the shoe rests on it (on top of a boot's shaft, bunching), a wide or bootcut leg drops over it but never past the vamp, the break sets how far, cropped lengths leave a gap with the ankle or sock. Sheets: `tools/make_hem_sheet.py` (since removed; in the git history).
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
- [x] #181 The **Pieces / As worn** choice is remembered on the device (it already was, since #71/#72, and its tests pass: choose As worn, reload, still As worn; an older program or a cached page would still reset it) and is now the same choice on a trip's days: one switch beside "Day by day" draws every day as worn, with Today's figure.
- [x] #181 The demo's overcoat drew as a blazer (jacket length, a breast welt like a pocket square): an overcoat was cut from the jacket at the tagger's "long", and the demo item never said it was an overcoat. It is now drawn at knee length from the coat's own measurements with no breast pocket, the demo item says it is an overcoat, and the demo was made again (`DRAWING_VERSION` 10). Before and after: `docs/screenshots/overcoat-before-after.png`.
- [ ] A trench coat and a peacoat are still cut from the jacket at the tagger's "long" (the trench coat's taxonomy length is the knee); look at both drawn before changing them (the review gallery they were to be checked in is gone).

Patterns from the photo (owner's request; it had fallen out of the app):
- [x] Plaids flattened and placed per front, madras measured whole, stripes (regular and placed bands, sleeves checked), prints quilted; OpenCV and the second background model in the app; migration 0013.
- [x] Plaids photographed at an angle, turned, over a slope, in soft dark cloth or on bedding (17 November, the owner's navy flannel jacket drawn as a pale smear): the cloth is straightened from its own lines before it is flattened, an overcheck over every other check is kept, the two background models no longer keep the bedding between them, every result must explain the photo before it is kept, and a plaid that cannot be measured says so. Plaids the older code could not measure are cut out and measured again once. See DECISIONS, "A plaid is measured three ways".
- [x] Plaids with a repeat up to about a third of the garment, on hanging or creased cloth (18 November, the owner's five more shirts): read from the garment's whole band sequences and kept when the rebuilt repeat explains the photo. Two of the five now measure (purple check, rust plaid).
- [ ] A plaid whose repeat is more than about a third of the garment (the owner's green and burgundy flannel on the floor: 341 x 314 px on a 1,100 px shirt) is found but cannot be checked, because fewer than two repeats fit on the body, so it is not drawn. It needs its own way of rebuilding and checking a repeat seen less than twice.
- [ ] A pale check photographed against a bright window is cut out as a lattice of holes (its white squares go with the background), and nothing can be measured. The cutout should fill holes enclosed by the garment.
- [ ] A plaid in a dim photo (the owner's dark burgundy and green shirt) finds no repeat and falls back to the whole-garment measure, which draws it nearly black with the hanger's bar as a white line.
- [ ] A repeat rebuilt from creased cloth carries the creases' shadows as dark streaks (the owner's rust plaid).
- [ ] A logo or crest on patterned cloth is not drawn (the owner, 18 November). An item has one pattern word, and only "graphic" lifts a logo from the photo, over plain cloth: a striped rugby shirt with a crest or a plaid shirt with a chest logo gets its stripes or plaid and the logo is only listed under Not in the drawing. A logo would have to be kept as its own thing beside the pattern. Not looked into; try the logo lift on a few of the owner's patterned clothes first.
- [x] **Retake the photo** for clothes (shoes have it): the note on a plaid that could not be measured, and the notice that the background couldn't be removed, each have the button now. The item keeps its wears, rating and everything the owner set; the new photo is cut out, described again and its pattern measured again.
- [ ] A shoe's retake does not refuse a photo that is waiting on Add as several pieces (clothes do).
- [ ] If a description of the old photo is still running when the photo is retaken, its answer is dated after the new photo, so the new photo is taken as already described (shoes and clothes alike).
- [x] A plaid measured from a photo too dark or too light is brought to the colour the item is called (17 November: the navy jacket came out near black). See DECISIONS, "A plaid's repeat is made lighter or darker".
- [x] On cloth Claude calls flannel, the drawing laid its cloudy "brushed" surface over a measured plaid, which blotched the checks; on plain flannel it read as a grid of ovals. The owner called it "way too much" (17 November). The surface is now a faint, scattered nap with no grid; a measured plaid reads cleanly through it.
- [ ] Plaids with a repeat larger than about a quarter of the garment's body, seen at an angle: too few areas show the repeat to even it out, so only the tilt is undone.
- [ ] Florals placed motif by motif on a good photo (now pieced from the whole garment).
- [ ] Very fine stripes on small photos (a 285 px polo loses its 1–2 px pink lines).
- [x] #105 Graphic prints on tops: a top Claude calls graphic (or a novelty print) has its print lifted from the cutout in the background and drawn at its place, on its own drawing and in the outfit figure; a print that cannot be lifted leaves it plain with a note. Known: the tagging schema does not yet ask for the taxonomy's `graphic_technique` and `graphic_placement`, so a back print or a sleeve print is not told apart, and only the front photo is read.
- [ ] Graphic prints on the back or sleeves (needs `graphic_placement` in the tagging schema and a photo of the back).

## The closet app to have (the owner, 23 November: "be unreasonably ambitious")

The owner asked this session to work by itself: bring the discovery steps in, review the app for bugs and UI errors, and build what would make Nines the closet app to have, "without sacrificing the core functionality". Each line is its own pull request. The order is by how often the owner would feel it (DESIGN, "The jobs"). Nothing here adds a place to the tab bar, a door, or a phone notification (the owner said no to those). What a line left undone goes under "Left over from finished work" as always.

**First, what is already there made right**
- [ ] **The review's findings** (`docs/assessment/` gets a short report of the two reviews of 23 November, the screens and the rules; the fixes go in small batches, each fault shown with a failing test first).
- [ ] **Words and dates**: one date format everywhere, no "engine" in the owner's text, no raw dates in Worth buying.
- [ ] **Today's first screen**: "I'm wearing this" in view with five pieces; the weather notice as one line with Try again.
- [ ] **What you wear at home is not a reason to buy**: loungewear, sleepwear, swim trunks and sport shoes never make a "another like your…" suggestion.
- [ ] **The closet at a glance**: three across as a choice, a search box that takes the row, the Photos or Drawings switch in words, and search that finds a shade, a brand, a material or a note.
- [ ] **Would this work? by hand**: kind and colour first, the rest behind "More about it".
- [ ] **The figure: an open layer under an open jacket** shows its fronts, not a thin strip (changes "The outfit as worn" in DECISIONS; say so).

**Every day**
- [ ] **Dress for another day**: on Today, tomorrow or a date you choose, with that day's forecast and a word about the day ("dinner at eight"). "Wear this on Saturday" keeps the outfit; that morning Today opens on it, and its pieces are kept out of the laundry's way.
- [ ] **Outfits you keep**: save an outfit you like without wearing it; find them under Worn; wear one again in a tap.
- [ ] **From a piece to an outfit**: on a piece's page, "Build an outfit around it" and the outfits you have worn it in.
- [ ] **Give it an outing**: Today may offer one outfit built around a piece you like and have not worn in a while, and says so.

**The closet**
- [ ] **Where a piece is**: at the cleaner's, at the tailor's, lent out, needs mending. Left out of outfits and trips like the laundry, with one line on the closet and a tap to bring it back.
- [ ] **Wearing while the computer is off**: "I'm wearing this", a rating and a tick on a packing list are kept on the phone and sent when Nines answers again (the backlog's offline edit queue).

**The wardrobe**
- [ ] **On sale now** (step 5 of "Finding clothes you might like").
- [ ] **Your nines** (the owner's idea): the nine pieces worn most, three by three.
- [ ] **What your clothes cost you**: what you spent by year from prices and dates, what the wishlist would cost, and the pieces that have earned their price.
- [ ] **Worth buying, folded**: each card a title, how much it helps and one line, opening on a tap.
- [ ] **A find's pattern is drawn**, so a striped shirt in "See it with your clothes" is striped.

**Trips**
- [ ] **A trip for tennis or golf**, and a way back to "follow the weather" for swimming.
- [ ] **A trip covers today**: Today dresses for where you are without a note.

**Later, and only if the owner wants it** (each needs a decision that is theirs): reading a calendar for the day's events (what would be sent to Claude); the colours reworked; a year in clothes.

## Finding clothes you might like (asked for by the owner, 23 November)

The owner: "is there some way to ideate/find clothes I might like", "rather than using things like google shopping which seems to target me well"; then "I also would love to discover sale items across the internet to find gems that I otherwise might never see". Today Nines shops only for a need it already has a name for (a gap or a wish, then "Find some", up to 8 products), and the search is told only the wish's kind, colours, price range and note (`find_prompt` in `backend/closet/tagger/shopping.py`): not Your style, the pieces loved or worn most, the brands owned or a size. Nines will not beat a shop search at browsing, since Claude's web search is slow and is no catalogue; what it has that a shop search lacks is the closet, the wears and the ratings. So the order below starts with judging what the owner finds elsewhere and ends with Nines looking by itself. Each step is its own pull request, in this order; all go in the Wardrobe (no new place in the tab bar).

- [x] **1. A shared link is judged against the closet.** A link sent to the wishlist (Add a link, the share sheet, the iPhone Shortcut) becomes a wish but is not checked ("Wishlist links and their prices" under Left over). Its page should answer at once, as Would this work? does: what it goes with, what it repeats, which gap it would fill, with the product's picture. The page's name and description are read by `productpage.py`; what the check needs beyond them (kind, colour, formality) is asked of Claude once, as a find's is. Also a "Search Google Shopping" button on each gap and each wish, opening the owner's browser on a search made from what to look for (kind, colour, and size and brands once step 3 keeps them). Nothing about the closet is in that address beyond those words; say so in DECISIONS.
- [ ] **2. See it with your clothes.** A find, or a judged link, drawn into an outfit with pieces the owner has: the find's described values go through `drawing/item.py` as a new item's do, and the example outfits Would this work? already builds are shown as worn. A drawing from words is approximate; the card says so and keeps the shop's picture beside it.
- [x] **3. Tell the search who you are.** Done (migration 0047; DECISIONS, "What the search is told about you"): sizes went in a row in Settings → Everyday, not the style conversation. `find_prompt` also gets the lines of Your style, the pieces loved and worn most in that kind (`taste.py`), the brands on the owner's items, and sizes. Sizes need a home: kept once, per kind of piece, with a brand's own where it differs (a migration; a row in Settings → Everyday or asked in the style conversation, to decide then). What is sent to Claude for a search grows, so the privacy sentence beside "Find some" and DECISIONS ("Shopping for a wish") change with it.
- [ ] **4. "You might like" in the Wardrobe.** A small card, not a feed: three picks a week chosen from taste rather than from a gap, each with its picture, price and what it goes with, and Save (onto the wishlist), Not for me and More like this. A reaction may offer a line for Your style, kept only on a tap as everywhere else. Run in the background on the daily round `shop.py` already has for prices, inside the monthly limit, and never in the demo closet. Needs step 3. To measure first: what one such search costs and how long it takes through the plan and the API key.
- [ ] **5. On sale now.** Things marked down across shops that suit the owner and that they would not have gone looking for: each with the price before and now, the size in stock where the page says, and the same check against the closet. An honest limit to design around: Claude's web search cannot read every shop's sale, so the search needs somewhere to start. Starting points, to settle with the owner: the brands they own and rate well, shops they name (a short list kept in Settings), shops that have sold them a find before, and Claude's own searches for sales in the kinds the closet's taste favours. Weekly in the background, inside the limit; a pick shown once and not again after Not for me. A sale price is read again by `productpage.py` before it is shown, so a sale that ended is not offered. Needs steps 3 and 4 (it is the same card with a second row, or a second card: decide when 4 exists).

## From the review of 17 November (asked for by the owner)

The review's fixes are merged (#244 to #248). Left for later, in the owner's words where they gave them:

- [x] **Laundry with much less upkeep** (#249, migration 0030; approved by the owner 17 November: "Yes keep going"). Done as proposed below; the laundry day is Sunday until the owner chooses another. The owner: "maintaining what is in the laundry seems like a huge pain, but I realize it affects what outfits can be put together". A proposal to decide first:
  - Clothes go in the laundry by themselves once worn as often as **Before it needs washing** allows. That setting exists already for trips: tops after one wear, knitwear and trousers after three, jackets and coats rarely.
  - They come back clean by themselves on the owner's laundry rhythm (for example "every Sunday", or "three days after"). **Laundry's done** marks everything clean in one tap.
  - Today and Trips trust that. The owner only corrects the exceptions: a shirt worn twice, a sweater washed early. **Put these in the laundry** on Worn and **All clean** on the closet (#246) stay as the manual way.
  - Needs a migration, and a Settings group (how often you do laundry).
- [x] **One Add for clothes and shoes, sorted by Closet** (#250, approved by the owner 17 November). Done as below; shoes are grouped within each set of ten photos; Take photos opens the camera on Add itself, and each shoe gets a checklist of its three photos (outer side, front, inner side), with a photo showing the pair held back (DECISIONS, "One Add for clothes and shoes"). The owner: "clothes/shoes import could all be combined and classified to the category it is". Today Add has three switches: one item per photo, several in one photo, a shoe.
  - Instead, drop or take any mix of photos. Claude says for each photo whether it shows one piece, several pieces, or a shoe (and which view).
  - Photos of the same shoe are grouped into one shoe, as "A shoe" does now. Several pieces go through the boxes step, as now. The switch goes.
  - Open: what to ask the owner when Claude is unsure whether two shoe photos are the same pair, and the cost of the extra sorting call on large imports.
- [ ] **Outfits chosen by Claude** (decided by the owner, 17 November; DECISIONS, "Outfits chosen by Claude"). The owner: "we could make this so much better by inserting real intelligence into it"; "not sure what menswear rules I care about"; "scores probably shouldn't be fixed"; "learning should be very deep"; "outfit should be considered in totality". Opus through the API key; rules become preferences; today's engine stays as the fallback. In steps, each its own pull request:
  - [x] **Step 1, the day.** The forecast hour by hour (what it feels like, when rain falls and how hard, wind, sun, humidity), read for the hours the owner is out; and the day in the owner's words on Today ("In Lisbon until Friday", "at a match, outside from noon to six"), read by Claude, with the place's weather looked up by Closet. Not tried on a real phone or with the real Claude yet (the tests stand in for it).
  - [ ] **Step 2, the stylist.** Done so far: what Claude is told and what is kept from its answer (`closet/styling.py`, `tagger/stylist.py`), and the measuring tool `python tools/style_demo_days.py` (the demo closet, four made-up days, through the plan or the API key). Measured through the plan on Opus at medium effort: 12 of 12 outfits wearable, 16 to 23 seconds a call, about 5 cents a call through the API key for the demo's 38 wearable pieces (low effort: 14 seconds, 4 cents); a closet three times the size would be about 6 to 7 cents, since the pieces are a small part of what is read. Also done: the style profile, kept in the closet and edited in **Settings → Your style**, and **How I wear it** on each piece's page (migration 0031); both are read whenever Claude chooses. And Today asks Claude in the background, keeps its answer for the day and falls back to the rules (migration 0032; DECISIONS, "Step 2, the stylist on Today"). Also done: Claude is asked ahead, once a day from five in the morning while the program runs, for the hours from when the owner usually first opens Today, so the first open has its outfits at once (DECISIONS, "Step 2, asked ahead"; not seen on the owner's computer yet, where it depends on the computer being awake). And Claude looks at each outfit it chose, drawn on the figure, and keeps or changes it before Today shows them (migration 0034; DECISIONS, "Step 2, the look"): about 3 cents and 13 to 30 seconds more for each of the day's plain questions, none for replies in the conversation. Still to do: trying all of it on the owner's own closet through the API key (so far only the demo closet with the real Claude, and stand-ins in the tests); and after some weeks, reading what the look changed there (`style_answers.seen`) to judge whether it earns its place. A small one for the screen: the outfit cards are all as tall as the tallest, so when the rules' outfits (many reasons) follow Claude's (one or two sentences), Claude's cards have empty space under them; the track should take the height of the card in view. The plan as decided: One call a day (and when the closet, the weather or the day note changes), made in the background so Today still opens at once: Claude is given the day (the hour-by-hour reading and the note), what can be worn, recent wears, the style profile and a shortlist from the engine, and returns three whole outfits with its reasons. It also looks at the drawn figure of each before offering it. The engine stops choosing: it only removes what cannot be worn and proposes the shortlist; it is the answer when Claude cannot be reached. Rain is a preference in the profile, never a rule (the owner: "I have an umbrella… it could favor one, and waterproof boots").
    - **The style profile:** how the owner dresses, in plain words, readable and editable in Settings. It starts from the taxonomy's outfit rules as preferences. It is the whole of Claude's memory between calls, with the wear history.
    - **What to know about a piece** (the owner: "a way to tag specific items with context that help Claude use the garment effectively, more than just like/love/meh/dislike"): a box on the item page for how the owner wears it ("only with the navy suit", "runs warm", "too short to wear untucked", "dinners out"), given to the stylist with the item's Notes and Fit notes; Claude may offer to add a line to it from a conversation.
    - Measure first: what one stylist call costs and how long it takes on a closet of the owner's size (estimated at 5 to 10 cents on Opus, not measured).
  - [x] **Step 3, the conversation.** On Today, under Claude's outfits, the owner writes what they think ("too dressy", "swap the boots", "why not the navy blazer?"); Claude answers, picks again when asked, and may offer to keep a lasting preference, which is saved only when the owner taps Save: to **Your style**, or to the piece's **How I wear it** (migration 0033; DECISIONS, "Step 3, the conversation"). Tried once with the real Claude on the demo closet (three messages, 6 to 18 seconds each). Left for later: ratings of worn outfits offering lines for the profile the same way; trying it on the owner's own closet; a long day's conversation folded to its last few messages. Found while building it (older than it): tapping an outfit's dot and then scrolling the page while the outfits slide can leave the carousel on another outfit than the one tapped.
  - [ ] **Step 4, the interview: on hold** (the owner, 18 November: "not sure I understand the point of the interview. Can that information be gleaned through the conversation?"). It was a one-time set of questions to fill Your style on the first day (which menswear rules the owner cares about, how many layers at which temperatures). The conversation now does this a line at a time, for things that actually come up, so it is not built unless the first weeks show Claude learning too slowly; a lighter form then is "ask me three things" in the conversation's own box.
  - Later: a trip in Trips that covers today moves Today to its place by itself, as a day note does.
- [ ] **Bigger redesigns found in the review** (with phone screenshots), each its own issue:
  - **Settings** as a short list of groups that open (Your closet and backups, Where you are, Look, Describing clothes, Updates, Phone access, Advanced), with Look near the top. It is one 4,850 px column now.
  - **What's missing** with folded cards (title, how much it helps, one line, thumbnails) that open on a tap. Merge "Also worth knowing" lines that repeat a card. The first suggestion starts about 440 px down.
  - **The item page** with one Details card and "Show all details" opening in place below the wearing box, with What Claude saw folded inside it. Now four places overlap: the line under the name, Details, Fix the details and What Claude saw. Fix the details pushes the name a screen down.
  - **The closet grid:** a denser choice (three across, one-line names). The Review and background-removal notes folded into one slim line. The first phone screen shows two tiles.
  - **The Filter sheet:** group first with its kinds under it, Laundry and In use / Archived at the top, Clear all, and **Show N** on Done. Category, group and kind overlap now.
  - **Would this work? by hand:** kind and colour first, the rest under "More about it". A button that stays in view, a busy state while it checks, and the wishlist buttons under the verdict.
  - **Today:** yesterday's rating card (above the outfit by the owner's earlier choice) as one slim row or below the outfit, so I'm wearing this and See another idea stay on the first screen. The piece ⋯ menu as a sheet, not a panel below the grid. The weather failure as one line with Try again.
  - **Record an outfit** grouped by top, bottom, shoes and extras, recent first, with a search.
  - **Review:** the picture at about a third of the screen, Undo on "Confirmed", and Back to closet when done.
  - **Smaller:**
    - one date format everywhere;
    - engine words out of the owner's text ("the engine can only say…", "40 kinds of day the closet is tried on", 3.2°C to 9.8°C);
    - Add's switch reading "One piece / Several / A shoe";
    - the tab bar's Add label on the same line as the others, and the bar opaque;
    - one empty state on Insights;
    - Photo | Drawing in words on the phone;
    - the privacy paragraph behind "What is sent?".
- [ ] **Technical, left over:**
  - The words Claude Code prints when it cannot reach Anthropic (#244) were never seen from a real offline Claude Code. Check them once on the owner's computer.
  - Shopping searches are not marked for the prompt cache.
  - Tray-less running (#247) not yet tried on a real PC or Mac.
  - **A faster plan route** (asked for by the owner). The timing tool is built: `python tools/time_plan_route.py` on the owner's PC times one description four ways, five runs each, through the plan (nothing billed): `today` (the app's call, the photos opened with the Read tool), `inline` (the photos inside the message, `--input-format stream-json`, no tools), `lean` (as inline, loading none of the computer's settings or slash commands) and `ready` (as lean, with Claude Code started ahead and waiting; a fresh one for each call, so one item's photos never reach another item's answer). For each way it splits the time into Claude's (what Claude Code says it waited on Anthropic) and Claude Code's own. A process kept open for many items was ruled out: each message carries the conversation before it (seen: about 2,000 tokens read again on the second message). On a Linux test machine (one demo photo, four runs): today 6.9 s (Claude Code's own part 1.3 s), inline 8.0 s, lean 6.1 s, ready 4.0 s, the steadiest; Claude's own time swings by several seconds between calls. Next: the owner runs it on the PC (Windows may start Claude Code more slowly), then the way that wins is built into the app.

## Which model for which work (suggested 17 November; the owner to confirm)

The owner finds the most capable model (Fable) better at drawing and at judging what matters to a person. Its weekly allowance is small, so it goes where a wrong call costs the most:

- **For the most capable model:**
  - the bigger screen redesigns above (each starts from phone screenshots and ends with looking at the result);
  - all drawing work (shoes, garments, the As worn figure) and judging a drawing against its photos;
  - changes to what the outfit engine, trips, gaps and laundry decide for the owner, and the DECISIONS that go with them;
  - reviews that look for faults (the review of 17 November was one), and anything where processes, timing or the owner's data could go wrong, such as building the ready Claude Code into the app.
- **For a cheaper model, with the tests as the guard:** the smaller wording fixes, one date format, the prompt-cache mark on shopping searches, new tests for behaviour already decided, docs, renumbering a migration, redoing screenshots.
- **Inside the app** (`tagger/models.json`): describing an item and shopping searches use Haiku; sorting photos Sonnet; several pieces in one photo, landmarks and drawing a shoe Opus. Worth one trial on the bench, not a switch: drawing a shoe with the most capable model on the five pairs already drawn (`tools/draw_shoe_photos.py`), judged by the owner side by side. A shoe reads 53,000 to 106,000 tokens, so through the plan it would use a good share of that model's weekly allowance; it belongs to the shoe-drawing work to decide.

## Waiting on the owner
- **Garment review**: the owner called the drawings good enough for now (after round 7). The review gallery's tool was removed on 20 November (it is in the git history); drawing work is parked until asked for.
- **Mac 0.1.1**: confirm the background-removal model now downloads on the owner's Mac.
- **The Windows build** for stop A has still not been made or tried.
- **The app's top UI complaints**, as the brief for UI tasks. A full interface-design pass comes after more features exist.
- **25–30 photos of the owner's own clothes** with an answer key. Most useful: items that differ from the usual (a polo with one or three buttons, a henley, corduroy, fleece or heavy wool beside light cotton, a sweatshirt with a V-insert). The tagging bench that ran them was removed on 20 November with the rest of phase 0 (it is in the git history: `bench/closet_bench/bench.py` and `bench/answer_key.template.csv`); bring it back, or run them through the app, if this is still wanted.
- Three photos for the untested hard cases: something striped, something floral or patterned, something camouflage.
- **Shoes drawn from understanding**: five photos each (outer side, above, front, back, inner side) of three to five more pairs, of kinds not tried yet (not a runner, army trainer, cap-toe dress shoe, boat shoe or elastic-sided boot), for the check on unseen pairs. They stay out of the repository.
- **Time the plan route on the PC** (when the owner is home; about 3 minutes, nothing billed): `python tools/time_plan_route.py` in the Closet folder, and paste the table it prints. It decides whether a Claude Code started ahead of each call is built into the app (see "A faster plan route" above).
- Whether to drop the Google Drive hand-off for price checks now that the app runs them itself (#112, through the plan route while the PC is on; see DECISIONS, "Shopping for a wish"). Recommended: drop it.
- Whether multi-item photos and video sweeps stay after the outfit builder (as planned below) or move into stop B.

## Track 1: recognition and drawing (continuous)


Checkpoints, not stops:
- [ ] **A question to assess, not yet work: do garment drawings need more than a feature each to show what is particular to an item? (the owner, 21 November)** Shoes are now drawn by Claude from their photos; shirts, trousers, jackets and the rest are drawn from templates filled in from tags, one feature at a time, so two similar pieces can look much the same. The owner's aim is that the drawing steps capture each item's own characteristics (DECISIONS, "A shoe's side drawn by Claude"), and their view is that the features already built may do this more cheaply than having Claude draw everything: a feature costs nothing per item and nothing to redraw. So assess before building: go through the owner's real items (the owner can say which ones do not look like themselves), list which particulars the drawing misses, and sort them into those a feature would cover for many items and those only that one item has. Only for what is left ask whether a drawing by Claude is worth its wait and cost. No plan and no code until that list exists.
- [ ] **A shoe's drawing takes four to ten minutes (the owner, 20 November: "really long").** Reviewed by reading `tagger/shoedrawing.py` `draw`: 6 to 14 calls one after another (two straight-on drawings each checked, a judge, two turns each checked, a judge, then a fix with its checks and a judge), each writing a whole drawing. Two of the ideas below are done (20 November), not yet timed on a real shoe; the others have not been tried. The order is from the least risk to the drawings:
  - Done (20 November): `shoedraw` draws two shoes at once (`AT_ONCE`); before, one at a time, so ten new shoes took over an hour. See DECISIONS, "Two shoes drawn at once".
  - A small tool that reads the kept drawings' `calls` (each call's kind and seconds are stored) and says where the time went and how often the fix after the second judge was kept. If it is rarely kept, dropping it takes the longest chain from 14 calls to 10.
  - Done on the API route (20 November): a check that says good with no automatic problem stops being read there (`correcting.CutShort`, `shoedrawing._good_as_is`); the request is unchanged. See DECISIONS, "A check that says good stops being read there". The plan route still reads the whole answer.
  - The plan route starts Claude Code for every call and opens each image as a step of its own; not measured against the API route.
- [ ] **Coverage of the taxonomy.** Every visible value in `docs/menswear-taxonomy.json` is listed in `backend/closet/tagger/taxonomy.py` (`COVERAGE`) as drawn, approximate or not drawn. The owner looks over the render sheets; the approximate and not-drawn values are worked down, most common garments first. #163 took the first pass (470 drawn, 109 approximate, 118 not drawn before; 496, 87 and 114 after): knit textures, the hidden button-down, each trouser kind's look, notched hems, rivets and roping, the trench, parka, varsity and waxed jacket, patent shine, flip-flops, D-rings, toggle laces, the robe's sash and velvet's sheen. Before/after sheets are `docs/screenshots/coverage-*.png`, written by `tools/make_coverage_sheet.py` (since removed; in the git history). #182 took tops and knits (496 drawn, 87 approximate, 114 not drawn before; 573, 42 and 82 after): a faint surface of its own for each plain weave, shirting, smooth cloth and jersey; colourwork knits placed where the garment carries them (a Fair Isle or Nordic yoke, all-over argyle, an intarsia motif on the chest) in the other colours seen; leather, suede, worsted, lambswool and merino on tops; the convertible cuff and cargo pockets on a top; every kind of top (sportswear, jerseys, rain, leather and softshell jackets, pyjama and lounge tops, the kimono robe and smoking jacket); a marl surface for heathered and marled tops. Stripes knitted into a sweater come from the photo's stripe fill. Left on tops, honestly: acrylic (drawn like wool), where a sun fade falls, and black cotton's and garment-dyed cloth's colour shifts (the measured colour carries them). #183 took trousers and shorts (573 drawn, 42 approximate, 82 not drawn before; 584, 41 and 72 after): double pleats set apart, reverse and forward pleats shaded on the side they open to, a small drawing from the back on the item page (back pockets, the jeans yoke, a leather label, darts, a V belt loop, honeycombs), a set's trousers and shorts drawn as the lounge or sweat bottoms they are cut like, an overdye drawn in its measured colour. Left on trousers, honestly: fatigues' back-sateen cloth (drawn as a twill) and an overdye's cast over the blue. #184 drew footwear (its axes 110 drawn, 34 approximate, 24 not drawn before; 165, 3 and 0 after; overall 584, 41 and 72 before, 639, 10 and 48 after): the upper's surface for every upper material, the five kinds of lace, ghillie lacing, split and chisel toes, city, studded and foam soles, a moulded slide, a cork footbed's grain, each construction round the sole, a no-show cut, the trainer, camp moc, moccasin and velvet slippers, and the colourways; the front-on shoes on the figure follow. Left approximate: a knee boot (it would not fit the card at the shoes' common scale), synthetic leather (it looks like calf) and a multi colourway. Before/after sheets are `docs/screenshots/coverage-shoes-*.png` and `figure-shoes-front-*.png`. #185 drew the accessories (ties, pocket squares, gloves, glasses, watches and socks, with each one's own details), wore them on the figure (hats on the head, bags carried) and listed the accessory values not yet in `COVERAGE` (tie patterns, lenses, watch straps, buckle finishes, jewellery, braces and umbrellas): with #182, #183 and #184, 695 drawn, 14 approximate and 21 not drawn now. Of the accessories, jewellery, braces and umbrellas are still not drawn.
- [ ] **Shoes traced from the owner's photo (#192).** Stage 1 is the bench command `python -m closet_bench.trace_shoes` (see `bench/README.md`). Stage 2a (#204) moved the tracing into the app's code (`closet/drawing/trace.py`), fixed the quality gate (padding no longer counts as running off the edge; toe spring and curved soles pass; a pair or a view other than the side is turned down on the tagger's word (new answer fields `shoes_in_photo` and `shoe_view`, schema version 5) or when two pieces stand apart, while the outline's own pair checks only advise; white on white is refined and tries the other cut-out before giving up) and turned the trace into data (`closet/drawing/traced.py`, `TracedShoe`: profile, parts taken from the traced colour pieces with every piece labelled, marks, laces counted along the lacing, eyelets, stitching, a style hint that decides shaft or no shaft first, confidence). Stage 2b (#206) traces a shoe in the cut-out queue and keeps the trace with the item (versioned, traced again when the photo changes), draws the traced side view as its drawing, says in plain words why a turned-down photo is drawn from its details instead (with Retake), lets the owner fix the traced drawing in Fix the details (part colours, remove or move a mark, Re-trace, the plain drawing; fixes kept apart and carried over a re-trace) and adds "A shoe" to Add (a side-on outline guide, an instant check, an optional second photo from the front or above, kept for 2c); two demo shoes have made-up traces. Next: the orchestrating session runs the bench on the owner's photos and the owner picks the one tracing approach from the sheets (`trace.APPROACH` is provisional); stage 2c (#205) draws a traced shoe's front view on the As worn figure from its trace (on the template's shape: colour panels sampled at the upper's top surface, the sole's colour bands, marks and laces; a boot template's shaft, collar and tongue when the tagger says boot; `figure.Piece.traced`, set from the item's stored trace by `illustrations.describe`), with untraced shoes unchanged (sheets: `docs/screenshots/traced-front-*.png`, written by `tools/make_traced_front_sheet.py`). Stage 2c also gives each traced shoe two front views, "From the shoe's shape" (the template in the trace's colours) and "From your photo" (the template's shape painted by sampling the trace), chosen per shoe in Fix the details from two previews, with "Add a front photo": a front photo is read (`closet/drawing/frontlook.py`) for its toe-box and vamp colours, laces and front marks, and makes "From your photo" the default. **Removed 19 November** (see DECISIONS, "The traced front view is removed"): the figure wears the template until Claude's drawing arrives, and the sheets and their tool are gone. #224 drew a traced shoe's side marks (stripes, a curve, a panel) in both front views as bands wide enough to see, and lowered a no-show cut's collar on the front low sneaker, runner and slip-on (shorts also draw their rule pocket now). The trace now finds thin, tapered stripe sets before the laces, so their colour is never taken for the laces'. Not tried on a real phone yet: the live camera needs a secure address, so over the home network the phone's camera app is used.
- [ ] **A traced shoe's front, from a front photo.** The aim, the pass mark and what was ruled out are in DECISIONS, "A traced shoe's front on the figure". Each step has a result that stops or changes the next one.
  1. *What shops show.* Done, on 18 real pairs from one shop that labels each photo's view. A side view: 17 of 18. A view from above: 16 usable of 18 (half a single shoe seen a little from the side, half a pair from straight above). A true front view, toe towards the camera: 6 of 18; the photo the shop calls "front" was the back of a pair for 8 and a three-quarter view for 3. So the second photo the plan can count on is the one from above, the owner's own included (standing over the shoe is the easy shot); a front view is a bonus. Also found: the app's tracer passed 15 of 16 of the side photos; today's reader of the second photo got nothing from any photo from above, and from the six front views only two colours each, once the wrong one (white laces read as the vamp's colour); the tracer's joining of a colour with its shade turned grey suede white and a navy shoe into one colour on the photos from above, so they need their own flattening; a penny loafer whose trace was taken for a derby is drawn with laces in "From your photo".
  2. *The line-up* (decides everything below). Built and with the owner (see "Waiting on the owner"): ten of those pairs, each drawn on the feet three ways (today's drawing; the photo from above flattened to its colours and laid over the front of the template's shape, inside its outline; the same with the toes turned out 20°), shuffled, matched to the side drawings at phone size. Pass: 8 of 10 from the photo laid on and 3 more than today's. The laid-on drawing is a rough stand-in made by hand, not app code: no drawn laces, a boot's shaft left as today. The code that drew it, how to run it again and what to do with the owner's result were in `bench/experiments/shoe_front/` (no photos there; now in the git history). Already read from the sheets: cutting the limits on small colour pieces to a quarter changed one shoe of ten, so that alone is not worth doing; at 20° the figure still stands naturally and the inner side shows the side stripes, at 30° the feet splay.
  **Result of the line-up: failed.** The owner matched 8 of 10 from today's drawing, 3 of 10 from the photo laid on and 2 of 10 with the toes turned 20° (every miss was "can't tell"); the 20° stance looked natural. So steps 3, 4 and 6 are not taken up: the photo laid on as paint is harder to read at phone size than today's clean drawing, and today's drawing is already matched to its shoe most of the time. What the test could not show: the stand-in drew no lines and was blotchy, so it is not proof that a well-drawn front trace would fail; and with today's at 8 the mark (3 more) was out of reach. The owner's complaint after seeing the sheets is the shoes' outlines ("the silhouettes of most shoes are off in every example"), which this test held fixed: every variant used the template's outline. That is step 5's subject and is the open question now. The owner says it is the feet on the figure (the template's outline), not the side drawings. Next, before anything is built: for the ten pairs, set the template's front outline beside the real shoe (its plan from the photo from above, its sole thickness, collar height and toe from the side trace), find which few measures are off most often and by how much, and show the owner the feet redrawn by hand with those measures corrected, each kept within limits, never a traced outline (`bench/experiments/shoe_front/`, now in the git history, had the photos' fetcher and the sheets).
  3. *The second photo as a capture.* From above first (step 1), from the front when there is one: an outline guide for it in Add, a check of which view it is and that it is one shoe, a pair photo split into one shoe, and a stored trace of it. Risks: a second photo for every pair is a chore; a white shoe on a pale floor, and the shadow under the toe, cut out badly.
  4. *The trace painted inside the template's outline.* Laid over the upper's top surface from the toe to the top of the tongue (a photo from above), or lined up on the toe tip, the ball's width and the top of the tongue (a front view); everything above the template's throat left out; its colours matched to the side trace's; the sole's bands and the side marks still from the side trace. The four front-shoe rules and their tests stay as they are. Risks: a toe-cap line in the wrong place, lining showing in front, two photos in different light giving two shades of one colour.
  5. *Measured numbers move the template*, one at a time, each within limits: sole thickness and collar height from the side profile, ball width from the front photo. Risks: square toes and horns come back if an outline is ever taken from the photo; the trouser hem's place depends on these widths.
  6. *The turn of the toes*, only if step 2 says so. Risk: it changes the whole figure, and the inner side it shows was never photographed.
  With no front photo a traced shoe keeps today's default ("From the shoe's shape") and the item page asks for one.
  **Result (15 November 2026): the outline work moved to a new item.** The owner's notes on the ten pairs said the feet were off in shape on all ten, missing detail on eight and badly traced on four. A first hand redraw from those notes was rejected ("more detailed, not better", and based on the notes, not the image). A 3D solid measured from five photos of each of the owner's own pairs was tried and dropped (blobs, colours like camouflage). Steps 3 to 6 above are not taken up; the front is now drawn by a model from the photos, in "Shoes on the figure drawn from understanding" below (DECISIONS, "A shoe on the figure's feet: drawn from understanding, not traced").
- [ ] **Shoes on the figure drawn from understanding.** A vision model writes a feature sheet from a shoe's photos (kind, silhouette, proportions, 2 to 6 true colours, parts, what makes it recognisable from the front), draws the shoe from it as flat clip art in a fixed frame, then looks at its render beside the photos and fixes it, at most three times. The briefs, the preview and how to run it again were in `bench/experiments/shoe_drawn/`, the dropped measured solid in `bench/experiments/shoe_solid/` (no photos in either; both now in the git history); the liked drawings are kept in `backend/tests/data/shoe_drawn/`. Done so far, on five photos (outer side, above, front, back, inner side) of each of five of the owner's pairs (a cushioned runner, a German-army-trainer style sneaker, a tan cap-toe dress shoe, a boat shoe, a pull-on elastic-sided boot): round 1 named 5 of 5 shoes correctly, model names included, and the owner called it "almost exactly what I want" (faults: no opening, the runner's outline, laces as bars). Round 2, 15 runs: 15 of 15 named, the runs agreed on colours and parts, the leg now goes into the shoe; but low shoes too tall (10 of 15 runs said so themselves), every boot a tube with "zero perspective", no runner good. Round 3, with the three liked drawings as examples, a written build order, a view rule and a lower frame: all three boots got a toe box with the shaft behind, the runners came out low with a less bulky sole; still off, the boot's toe box wide and flat, the runner's toe rubber too big and its N backwards on the mirrored foot. Round 4: a one-line correction made the boot's elastic panels broad in one round (about 35 seconds) with nothing else changed; naming the kind of shoe first gave the runner a thick foam sole the owner preferred ("looks more like a shoe"), though its toe rubber grew; left and right drawn separately put the N the right way on both feet; a cheaper model sorted the 25 shuffled photos into 5 of 5 shoes and named above, front and back 15 of 15, but swapped outer and inner side on 3 of 5 shoes (all six photos flagged as unsure by the model). Each drawing run took 70 to 170 seconds and about 80 to 95 thousand tokens on Opus, a correction about 35 seconds. An outline measured from the photos to draw over was dropped before use (at the figure's 24° it was nearly twice as tall as wide); only measured height and width are passed on. Next, in order:
  1. *The owner's verdicts (15 November):* the corrected boot is good. On the runner the owner prefers the drawing BEFORE the toe correction: on the real shoe the sole's rubber comes up higher at the toe and is not centred, so the correction made it less true. Both drawings are kept in `backend/tests/data/shoe_drawn/` (`boot.svg`, `runner-left.svg`, `runner-right.svg`). Lesson: a correction note can be wrong about the shoe; the redraw should be checked against the photos, not only against the note.
  2. *The check on unseen pairs (put off by the owner on 15 November: build it into the app first):* run the method unchanged on three to five pairs of other kinds (see "Waiting on the owner"), and count how often a run comes out poor. Only these five pairs have been seen so far.
  3. *The figure's own view and placing on the figure:* the drawings are straight from the front, about 15° above, tilted 7° by the preview; the figure looks 24° down with the toes out 11°. Draw at that view and place the shoes on the app's figure. First look (15 November, `bench/experiments/shoe_drawn/on_figure.py`, in the git history, sheets `docs/screenshots/shoe-drawn-on-figure-*.png`): the saved examples laid on the figure as they are; the leg goes in at the opening, but beside today's shoes they are about a quarter wider and a little lower, and their outline half as thick. With the owner to say whether the view fits or the brief must draw at the figure's own view. **The owner's verdict (15 November):** the view from the front and a little above stays, and so does the size; the app turns the toes out and matches the line weight itself; the boat shoe example was made lower (DECISIONS, "A shoe drawn by Claude in the app"). Placing the drawing on the app's figure is step D (done, below).
  4. *How it enters the app* (undecided): a Claude call per shoe through the plan route or the API key, as tagging does, and its cost and time; the drawing and its feature sheet stored with the item and not redrawn unless asked; the four front-shoe rules as checks on a model-made drawing; with no photos or a failed drawing, today's template; where the owner types a correction note; a photo check that says when a photo is not good enough (the toe end of the photo from above was guessed wrong on 1 of 5, one side photo ran off the frame); the app sorts the photos itself, so the owner never says which photo is which view; and whether the closet tile (the side view) stays traced.
     **Step B done (15 November): the photos are sorted by the app.** A shoe takes up to five more photos besides its guided side photo, in any order, on Add and on the item page; one call to Claude with all of them says which view each shows (outer or inner side, from above, front, back, sole, other) and whether it is sure; the item page asks which photo shows the outside only when the sides look different and Claude was unsure (DECISIONS, "A shoe's photos sorted into views by the app"). Tried with the real call on the owner's five pairs (photo 1 the side, the other four shuffled): 25 of 25 views right, about 10 to 14 seconds a shoe; outer and inner were marked unsure on all five, and the sides were said to differ only on the runner, so only the runner would ask.
     **Step C done (15 November): Claude draws the shoe in the app.** Once a shoe's photos are first sorted (after the owner's answer about the outside, when asked), one call writes the feature sheet and draws the shoe as flat clip art in the experiment's frame, with the three liked drawings as worked examples, then up to three calls check it against the photos with a render on two legs and what the automatic checks found (the shoe on the ground, in the frame, not too tall, the leg in the shoe and not hidden above its opening; they stand in for the four front-shoe rules); through the same routes and monthly limit as describing (purpose `draw_shoe`), on Opus at a high effort. The drawing, its sheet, rounds, seconds, tokens and what the API key would charge are kept with the item and shown under **Drawn for the outfit figure** on the shoe's page, with **Draw again**; it is never drawn again unless the owner asks, and the page says when the photos changed since. A developer tool, `tools/draw_shoe_photos.py`, runs the same drawing on folders of photos (DECISIONS, "A shoe drawn by Claude in the app"). Tried with the real calls through the plan on the owner's five pairs (photos named by their views, so not sorted first; at most two shoes at a time): all five drawn and named (a max-cushion road running shoe, a German army trainer, a cap-toe oxford, a two-eye boat shoe, a pull-on Chelsea boot); four were said good after one check, the trainer used all three checks without being said good; no automatic problem was left on any. 75 to 231 seconds a shoe, 124 on average; 53,000 to 106,000 tokens read (about 40,000 of them Claude Code reading its context again) and 7,000 to 23,000 written; at the API key's prices $0.23 to $0.70 a shoe, $0.37 on average. The drawings are with the owner to judge.
     **Step D done (15 November): the drawing on the As worn figure.** A shoe with a drawing is drawn from it on the figure, placed as `on_figure.py` showed (the frame's leg as wide as the figure's ankle, its ground on the figure's, the lines thickened, the toes turned out by sliding the part below a hinge, the right drawing used when there is one), the hem resting on the drawing's opening, full-length trousers just meeting an ordinary sneaker so the sock shows over a boat shoe; a shoe with no drawing, or one that cannot be read, keeps today's drawing exactly. Claude now draws each shoe in two parts, behind the leg and in front of it, drawn on either side of the leg on the figure, the item page and the check image, and the automatic check holds every kind of shoe to nothing in front of the leg above its opening (so a boot's back pull tab goes behind the leg); drawings kept before stay as they are until **Draw again**. The figure on Today and Trips is drawn again when a shoe's drawing changes. The demo's brown boots carry the liked boot, split, made in advance. Sheets: `docs/screenshots/drawn-figure-closeup.png` and `drawn-figure-phone.png` (`tools/make_drawn_figure_sheet.py`, which now writes into the git-ignored `tools/out/`) (DECISIONS, "A shoe drawn by Claude on the As worn figure"). Waiting for the owner's verdict in the app.
     **Step E done (15 November): the owner's one-line correction.** Under the drawing on the shoe's page, **What's wrong with the drawing?** takes one line (at most 200 characters) and **Send**. Claude is shown the photos, the drawing as it is, the owner's earlier notes and the note, and changes only what the note asks; then at most two checks compare the change with the photos and with the drawing before it, fix anything else it broke without undoing the owner's change, and say in one line when the note asks for something the photos do not show (drawn as asked all the same). The page shows what changed, the change's time and cost, and **Go back to the drawing before**, which swaps back in one tap and then offers the newer one again (one level; **Draw again** keeps the drawing before it too). The notes stay with the drawing they made and are given to a later **Draw again**. Recorded with purpose `correct_drawing`; never in the demo closet. A developer tool, `tools/correct_shoe_drawing.py`, runs one correction on a drawing `tools/draw_shoe_photos.py` wrote (DECISIONS, "The owner's correction of a shoe's drawing"). Tried with the real calls through the plan on step C's drawing of the pull-on boot (kept as version 1, its back pull tab drawn over the sock), with the note "The pull tab is at the back of the boot, so from the front it should be hidden behind the leg.": the tab moved behind the leg and every other shape stayed exactly as it was (the sheet's words about the tab changed with it); it came back as version 2; one check said good, with no automatic problem left; 48 seconds, 53,000 tokens read (20,000 of them Claude Code reading its context again) and 5,600 written, $0.25 at the API key's prices. The check did not say the note went against the photos, though the photo from the front shows a tab at the front of the collar as well. Waiting for the owner to try it in the app. The note was wrong about the shoe: the side photo shows that these boots have a pull tab at the front and another at the back, so the tab step C drew over the leg was most likely the front one, rightly in front. The correction instructions now tell Claude to check, in every photo, each thing the note says or takes for granted about the shoe (where a part is, how many there are), and the check to do the same. Run again with the same note: drawn as asked, and the page said "The photos show two pull tabs, one at the back and one at the front of the opening; the back one is hidden behind the leg as you asked." (two checks, 80 seconds, $0.34 at the API key's prices). The owner then decided that a pull tab at the front shows, in front of the leg (DECISIONS): the sheet's `front_pull_tab` lets it rise above the opening in the middle of the leg, and the demo's boot has its tab in front again.
     **A shoe in one step on Add (16 November), approved by the owner.** "A shoe" takes all of a shoe's photos at once, 1 to 6 in any order (several chosen at once, or taken one after another; where the page can show the camera it stays open between photos), in a row the owner can remove photos from, sent together by **Add this shoe**. The outline and the "will it trace well" check are gone (`POST /api/shoes/check` with them). Once the photos are sorted, the outer side (else the inner side) becomes the main photo when the first one was not a side view: the closet picture, cut out, and the photo traced for the side drawing; Claude's words on the photo it described first stay with that photo (`items.tag_photo_id`, migration 0029) and it is not described again. The shoe's page says when no photo shows a side; the pair in the main photo is said by the trace's message, as before. The switch at the top of Add reads "Clothes, one per photo / Several in one photo / A shoe" (DECISIONS, "A shoe in one step on Add"). Open question: a photo that becomes the main one is traced without Claude's word on how many shoes it shows, so if it shows the pair only the photo's own check can say so.
     Next, in order: the check on unseen pairs (still put off by the owner); a photo check that says when a photo is not good enough, whether the closet tile stays traced, lowering the effort once the time and cost per shoe are known, and trying the brief on sandals (the figure draws a drawn sandal like a shoe, with no bare foot).
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
- [x] Accessories drawn from the taxonomy's accessory ids and kinds: bags, belts, caps, beanies, brimmed hats and scarves have shapes of their own; ties, pocket squares, gloves, glasses, watches and socks a plain tag. The outfit figure wears a belt, scarf, hat and bag. Sheet: `docs/screenshots/accessories.png` (`tools/make_accessory_sheet.py`, since removed; in the git history). Waiting for the owner's verdict.
- [x] Shapes of their own for ties, pocket squares, gloves, glasses, watches and socks (`closet/drawing/accessories.py`), with each one's details: a tie's width, knit or silk and pattern; a watch's dial, strap and colours; glasses' frame and lenses; socks' length and pattern. The figure wears a tie under the collar, a pocket square in a tailored jacket's breast pocket, a watch on the wrist, glasses, and socks above low shoes with shorts or cropped trousers (`closet/drawing/worn.py`); hats sit on the head and bags are carried (in the hand, on the shoulder, across the body, round the waist or on the back). The demo closet has a tie, a pocket square, a watch, glasses, socks and gloves. Sheets: `docs/screenshots/coverage-accessories-*.png` and `accessories.png`. Waiting for the owner's verdict.
- [x] An armhole seam only where it marks something (16 November, #240): a dropped, raglan or saddle shoulder, or a sleeve or yoke in a second colour; none on an ordinary set-in sleeve (`templates.seam_shows`, DRAWING_VERSION 17).
- [ ] Ringer and raglan baseball tees (the t-shirt's `ringer` and `raglan_baseball` variants in the taxonomy) are drawn in one colour: nothing maps their contrast sleeves (or a ringer's contrast neck and cuffs) to the drawing yet. A raglan's seams are already kept.
- [ ] Accessories still drawn simply: a fingerless glove's thumb is hidden by its palm; the watch on the figure is only drawn when no sleeve covers the wrist; jewellery, braces and umbrellas have no drawing.
- [x] Shoes left after #108: a monk strap's buckles, a flip-flop's thong, apron and split toes, speed hooks and D-rings, boot kinds (chukka, western, rain), a cork footbed's grain, patent shine. All drawn by #184, with the shoe uppers and laces.
- [x] Trousers: the taxonomy's bottoms are a signature line each; rise, fit names (leg shapes) and jeans washes are tagged and drawn; what is on the back shows in a small drawing from behind on the item page.
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
- [x] #177 Phone access when the PC already shares another app with Tailscale Serve: Settings shows only the address `tailscale serve status --json` says reaches Closet (with `:8443` and so on when not on 443), says plainly when none does, suggests a port no other app uses, and stops only Closet's share (`tailscale serve --https=<port> off`, never `reset`). A QR code of that address in Phone access, for the iPhone's camera.
- [ ] Owner tries it on a real Windows PC and iPhone. Not yet exercised: tray icon, start at login, the Tailscale address, camera capture, home-screen install, HEIC from the phone, the model download progress bar, dropping a folder of photos.
- [x] Pin the macOS-only tray dependencies: pinned (PyObjC 12.2.2) with Closet's own window, which needs more of them.
- [x] Closet opens in its own window (pywebview; approved by the owner 16 November): closing it leaves Closet in the tray, Open Closet and opening the program again bring it back, a copy started at login opens none, and the browser is used when the window cannot open. Tested with the window and the tray faked, and on Linux only otherwise.
- [ ] Try Nines' own window on the owner's Windows PC and on a Mac: closing and reopening it, Open Nines, double-clicking the program while it runs, start at login, the login remembered after a restart, Open in shop opening the browser, choosing photos and a folder on Add, dropping photos and a folder on Add, Use my location, shutting down Windows with Nines running (it must not hold up the shutdown), and on the Mac ⌘Q and the Dock icon. On the Mac, Add's "choose a folder" is expected to offer files only (pywebview's file chooser cannot pick a folder for the page); dropping a folder still works.

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
- [x] Add shows what each photo became (approved by the owner 16 November, #239): each row of the import list shows the item's picture and what Claude called it, links to the item, and says once above the list why photos wait when that is something the owner can change; the shoe's done screen shows the shoe the same way.
- [ ] The closet's item list is re-checked every 2 to 10 seconds while anything is being processed, even while the page or app is hidden: pause it while hidden (phone battery), and for a large closet re-check only the items still changing (measure first).
- [ ] The item page's "It starts by itself once Claude can be reached" also shows when an item is only waiting its turn in a normal batch; reword it for that case.
- [ ] After a photo of several pieces is added, its row on Add could list the items it became (today it keeps "Check the pieces").

### Stop C: today's outfit
Original phase 4 and the rating parts of phase 6. The first stop the owner uses every day.
- Daily outfit builder (weather, event, mood, build-around-item) on the rule-based outfit engine.
- Layering rules from the weight class (what can be worn under or over what), not only from category.
- Mannequin layering, outfit rating with reasons, wear log, laundry state.
- [x] The outfit as worn is dressed a layer at a time on Today, with one set of motion timings and the look taken from moodbit.app (large light titles, typewriter-style labels, soft tints) (16 November, #240).
- [ ] Dressing asks the server for each layer on its own: up to four requests for one outfit, each a few milliseconds of drawing. One request that returns every layer in the outfit's frame would be lighter, if it ever shows as slow.

### Stop D: what's missing, and shopping
Original phase 5.
- Gap analysis (counts by code, explanations by the model), shopping by web search, wishlist, "would this work?", computer layout first.
- Price checks (#112: run by the app itself while it runs).
- [ ] On a phone, What's missing's larger title (since #240) pushes its "Would this work?" button onto a line of its own: fit both on one line, or decide that is fine.

### After D, each its own smaller stop
- Multi-item photos: done in #151 (Claude finds the pieces, the owner checks the boxes; see DECISIONS, "Several items from one photo"). Video sweeps are out (owner's decision). Still to learn: how well Claude boxes a cluttered bed.
- Taste learning analytics, cost per wear, never worn (rest of original phase 6).
- Trip packing (historical weather beyond the 16-day forecast, count-only basics).
- "Your nines" (the owner's idea, 20 November; the app is now called Nines): the nine pieces worn most, shown as a three-by-three square in the Wardrobe.
- Rework the colours (the owner, 20 November, after seeing Nines' mark on the screens: "we'll probably rework the colors later"). A change to the design system's colour tokens, decided once and written down in DECISIONS ("The design system"), light and dark together; the brand mark's own colours (`--brand-edge`) go with it.
- Extras: calendar-aware suggestions, offline edit queue. Cut: resale suggestions, seasonal storage rotation.

### Definition of done for a stop
Tests pass, the packaged build is green in CI, demo mode works, docs are updated, and the owner is told exactly what to try from the downloaded program and what is uncertain.

## Parked
- Browser tests in `08-wears` timed out twice in local full runs (once each test in the file), both times while reviewers were also running on the machine: the demo closet's tiles were missing or kept being replaced for a minute. Not reproduced in five further runs, three of them under deliberate heavy load, and never on GitHub. Cause not found. If it comes back: run with `--trace retain-on-failure` and look at what keeps re-rendering the grid after a profile switch.
- Batches API as an opt-in "economy" mode for very large imports.
- Server-side refusal fallback for the stronger model (beta); tagging currently fails clearly on a refusal.
