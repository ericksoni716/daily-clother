# Closet: adding items, fixing details, the item page, taps and transitions

A read-only audit of `/home/user/daily-clother`. Nothing in the repo was changed. The paths below are relative to that folder, and the line numbers are from the copy that was audited.

## How it was checked

- The repo was copied to the scratchpad with tar. Dependencies went into a scratchpad venv and into the copy's `node_modules`, and the frontend was built inside the copy.
- The backend ran from the copy as `python -m tests.e2e_backend` with `CLOSET_E2E_FAKES=1 CLOSET_E2E_SEED=demo` on 127.0.0.1:8791, with a scratchpad data folder. In this mode the owner's closet starts as a copy of the demo closet. The background model is replaced by `fake_cutter`, which keeps the middle of the photo. Claude is replaced by `fake_claude`, which answers "Navy polo" after 1 s. The photo sorter is `fake_add_sorter`, and weather is blocked. Nothing was sent to Claude or to any other outside service.
- I could not observe these stages live: the real ISNet cutout and its timing, a real Claude description, the Claude landmarks call, pattern measuring (the fake answer is a solid polo), and shoe sorting, tracing and drawing. Their timings below come from `docs/DECISIONS.md` and from code comments.
- Playwright Chromium ran at 390x844 with touch, `isMobile` and an iPhone user agent. A PerformanceObserver recorded `layout-shift` and `event` entries. One run added 4x CPU throttling and 80 ms of network latency to stand in for an iPhone over Tailscale. This is not WebKit, so the iOS-specific behaviour (back-swipe, standalone mode, `:active`) is reasoned from code and from known Safari behaviour.
- Screenshots are in `shots-items/`:
  - `03-item-full.png`: the item page, full length
  - `04-item-full-open.png`: the same, with every fold open
  - `05-fix-top.png`, `06-fix-full.png`, `07-fix-detail-open.png`: fix details
  - `21-add-*.png`: the add flow
  - `23-new-item-*.png`: a new item's page
  - `01-closet.png`, `11-after-back.png`: the closet, before and after going back
  - The scripts are in `pw/`.

---

## 1. What happens to a photo after it is added

### The pipeline as built

| # | Stage | Where it runs | Typical time | State kept | Code |
|---|---|---|---|---|---|
| 0 | Resize and upload in the browser | Local, in the browser | ~0.2 s per photo plus upload | `uploads` queue in the browser (`waiting/resizing/uploading/done/duplicate/failed/missing`) | `uploads.ts`, `uploadQueue.ts`; `Add.tsx:36-44` STATUS_TEXT |
| 1 | Sorting the tray (one piece, several pieces, or a shoe) | **Claude** (`sorting` = Sonnet; up to 10 photos per call at 512 px) | A few seconds | React state only (`sorting`) | `Add.tsx:170-207`, `POST /api/add/sort` |
| 2 | Item created, photo stored | Local, on the server | ~0.2 s | `items` row, cutout job queued | `app.py:657 create_item`, `jobs.enqueue_cutout` |
| 3 | Background removal | Local (ISNet ONNX, plus a second model, plus `recheck`) | Seconds; waits indefinitely while the model downloads | `jobs` row (`kind='cutout'`), `items.cutout_state` = pending/processing/ready/failed | `jobs.py:66-125` |
| 4 | Describing | **Claude** (`describing` = Sonnet; plan or API key) | About 12 s per photo by the API, up to a minute through the plan (DECISIONS 1153 and 446) | `jobs` row (`kind='tag'`), `items.tag_state` = waiting/working/done/failed, `tag_error` | `jobs.py:118-121` enqueues it; `tagjobs.py:129-187` runs it |
| 4b | Drawing | Local, **in the same transaction as 4** | Milliseconds | None: drawn at once | `tagjobs.py:286` `illustrations.redraw` inside `apply_answer` |
| 5 | Pattern measuring (plaid, stripes, prints, graphics) | Local OpenCV, **preceded for tops by a Claude landmarks call** | 1 s to 2 min (DECISIONS 1105) | `items.pattern_state` = waiting/working/done/failed. **There is no job row.** | `tagjobs.py:283`; `patjobs.py:171-235` (landmarks at 192-196) |
| 6 | Shoe: photos sorted into views | **Claude** | Waits 10 s for quiet, then seconds | `items.views` state | `shoeviews.py` |
| 7 | Shoe: traced | Local GrabCut, in the cutout worker | 2-3 s | `items.trace_state` | `tracejobs.py:231` |
| 8 | Shoe: drawn by Claude for the figure | **Claude** (Opus, several rounds) | **4-10 minutes**, about $2 by the API | `items.drawn` state | `shoedraw.py` |
| side | A photo of several pieces: finding the pieces | **Claude** | Seconds | `sources` table, `state='finding'` | `Several.tsx`, `/api/sources` |

There is one database `jobs` table for cutouts and descriptions only. Patterns, traces, views and shoe drawings are columns on `items`, each with its own worker. Nothing is pushed to the page: there is no SSE and no websocket. Everything is **polled**:

- `store.tsx:124-140` fetches the whole `/api/items` list (about 36 KB for 49 items) every 2 s while a cutout or description is running. It slows to every **10 s** while items wait for Claude, while the model is missing, or while a shoe is drawn. It does not poll at all for pattern measuring: `pattern_state` is not in the summary (`store.tsx:201-203`).
- `ItemDetail.tsx:96-113` polls the single item every 2, 4, 5 or 10 s, depending on six different states.
- `Add.tsx:291-301` polls `/api/sources` every 3 s.

### Every place progress is shown, each in its own words

| Place | What it shows | Code |
|---|---|---|
| Add tray header | "Sorting 2 photos…" | `Add.tsx:487` |
| Add import row, upload line | "Waiting / Resizing / Uploading / Added / Failed" | `Add.tsx:36-44, 642-650` |
| Add import row, title line (on the **same row** as the upload line) | "Removing background…" or "Waiting for the model", "Claude is describing it…", "Waiting to be described by Claude", or the name | `added.ts:30-38`, `AddedItem.tsx:24-34` |
| Add, above the rows | Why items wait (the monthly limit or sign-in) | `Add.tsx:617-621` |
| Closet tile | **Only** the cutout: "Removing background…" / "Waiting for the model" / "Background not removed". Nothing for describing, measuring or drawing | `Closet.tsx:297-299, 312-313` |
| Item picture | Busy badge for the cutout | `ItemDetail.tsx:638` |
| Item drawing placeholder | "Waiting to be described; the drawing comes after." | `drawing.ts:18-23` |
| Item notice above the name | "Measuring the plaid from the photo… a minute or two" | `ItemDetail.tsx:236-240` |
| Item notice under the wear panel | "Claude is describing this item…" / "Waiting to be described…" | `ItemDetail.tsx:286-300`, `tagging.ts:7-21` |
| Item Details hint | "Suggested by Claude; change anything that's wrong." | `ItemDetail.tsx:302-303` |
| Item: shoe notices | Trace, views and drawing ("four to ten minutes") | `TraceNotice`, `ShoePhotos`, `ShoeDrawn` |
| Top of the app | Model download | `ModelBanner.tsx` |

**What I saw live** (`21-add-*.png`): within about 650 ms of choosing two photos, each row showed **"Added ✓"** (the upload) and, beside it, a spinner with **"Waiting for the model"**. Nothing changed for about 10 s, and then the rows jumped straight to "Navy polo". "Claude is describing it…" never appeared, although the fake took 1 s per item. The model's state was `missing`, so `fast` was false (`store.tsx:131-132`) and the list was polled only every 10 s. With the real plan route the describing stage is longer and would show, but any stage shorter than the poll interval is skipped.

So the owner's confusion has these causes:

- (a) Two status systems share each row: the upload says done while the processing says waiting.
- (b) Status words are written separately in `added.ts`, `tagging.ts`, `drawing.ts` and `Closet.busyLabel`, so the same stage has three phrasings.
- (c) The closet grid hides every stage after the cutout.
- (d) The drawing really is the same step as describing for an ordinary garment (`tagjobs.py:286`). But the UI says "the drawing comes after", and for plaids and shoes there is a later step (measuring, tracing, Claude drawing) that redraws it again. Nothing names that step.
- (e) On the item page, the measuring notice sits above the name and the describing notice sits below the wear panel.
- (f) Polling every 10 s hides short stages.

### Proposed fix: one progress model, shown in one place (M-L)

1. **Server, one stage per item (M).** Add `progress` to the item summary in `items.summary`, worked out from the existing columns, so no migration is needed:
   ```
   progress: { stage: 'cutout'|'describing'|'detail'|'shoe-drawing'|'done'|'failed'|'waiting',
               step: 1..3, of: 3, words: "Removing the background", waiting_for?: "the model"|"Claude"|"your monthly limit",
               error?, can_retry, started_at }
   ```
   The steps:
   1. **Cutting out**: local, a few seconds.
   2. **Describing and drawing**: Claude, under a minute. Say plainly that the drawing appears as soon as Claude has described the item.
   3. **Finishing the drawing**: only for patterned items and shoes. "Measuring the plaid" (1-2 min) or "Drawing the shoe" (4-10 min).

   Each step says whether it is local or uses Claude, and how long it usually takes. Put the words in one backend function, or one `progress.ts` that replaces `addedLine`, `tagNotice`, `drawingPlaceholder` and `busyLabel`.
2. **One place per item.** On the item page, one progress strip directly under the picture shows the 3 steps as dots with the current step's words. It replaces the busy badge, the measuring notice and the describing notice (`ItemDetail.tsx:236-300`, `638`). On the closet tile, a small ring or dot with the step number replaces the cutout-only badge (`Closet.tsx:312`).
3. **One place overall.** A single "Working on N items" pill above the closet grid or the tab bar opens a list of items in progress. It replaces the import list's processing line, which would then show the upload only, with the rest handed over to the pill. On Add, each row shows **either** the upload state **or**, once uploaded, the item's progress, never both (`Add.tsx:651-655`).
4. **Polling (S).** Poll every 2 s while any item is in a non-waiting stage, measuring included: add `pattern_state`, `trace_state` and `drawn_state` to the summary check in `store.tsx:46-52`. Better still, add a cheap `GET /api/progress` that returns only the items in progress, rather than the 36 KB list. An SSE stream would be cleaner but is not needed.

---

## 2. Fixing details

**What exists now** (`components/FixDetails.tsx`, screenshots `05-fix-top.png` and `06-fix-full.png`):

- The "Fix the details" button sits under the picture (`FixDetails.tsx:47-54`). It inserts a panel **between the picture and the name** (`ItemDetail.tsx:231`).
- The panel lists **every** detail for the garment's kind, by group. A shirt has about 24 rows: neckline, collar, front, number of buttons, button colour, V insert, sleeve length, cuffs, seams, side stripe, pockets, hem, cut, fabric, fibre, weight, knit, corduroy, colour effect, pattern's name, pattern direction, shade. Tapping a row loads drawn choice tiles (`FixDetails.tsx:87-92, 126-152`).
- The text box already exists: **"Or say what's wrong"** (`SayIt`, `FixDetails.tsx:213-291`). It is the **last** thing in the panel (`:153`), below all 24 rows, so on a phone it is about two screens down. It only renders once `options.kind` has loaded.
- Its flow: `POST /api/items/{id}/correct` (`app.py:907`, `corrections.understand`, on the `tagging` model, Haiku). That returns "Claude understood: …" with **Make these changes** / **Cancel**, and **Make these changes** calls `POST …/correct/confirm` (`app.py:924`).
- In the demo closet it returns 409 ("never sent to Claude", `app.py:876-879`).

So the text-first path is already built and works. It is buried and framed as the fallback.

**What to change:**

1. **(S)** Make the "Fix the details" button open a **sheet** (or a pushed sub-view) whose first and only content is:
   - the drawing,
   - a multi-line text box, "What's wrong with it?", with the same placeholder, autofocused only on a computer (on a phone, focusing opens the keyboard over the drawing),
   - **Ask Claude** as the main button,
   - one secondary link: **"Change the details one by one"**.

   Reuse `SayIt` as it is. Keep the confirm step: "Claude understood: … Make these changes".
2. **(S-M)** Move the current group list (`FixDetails.tsx:116-152`) to its own screen, reached only from that link and from the "Not right? Change …" link in the confirm result. Give it a route such as `/item/:id/details` so Back works and the scroll position is its own. The worn-line words (`ItemDetail.tsx:275-278`) can deep-link to it with `focus`.
3. In the demo, and when no route to Claude can be used, open straight onto the one-by-one screen with one line saying why. This uses the same routes check as tagging.
4. After **Make these changes**, close the sheet. Show "Changed as you said" with **Undo**, which uses the existing history undo (`api.undo`).

Effort: M overall. Corrections by sentence need no backend change.

---

## 3. The item page: every piece of text

Inventory of `03-item-full.png` and `04-item-full-open.png`, top to bottom (`ItemDetail.tsx:221-405`):

| # | Text or field | Data source | Notes |
|---|---|---|---|
| 1 | "‹ Closet" | Route | Pushes a new history entry (see 5) |
| 2 | Picture, plus **Drawing / Cutout / Photo** | `illustration_url`, `photos[0]` | |
| 3 | "Not in the drawing" list | `seen_not_drawn` + `drawing_notes` | Near-duplicate of 18b |
| 4 | **Fix the details** | | Opens the 24-row panel above the name |
| 5 | Measuring, cutout-failed and pattern-failed notices | `pattern_state`, `cutout_state` | Progress, see 1 |
| 6 | **Name** (editable textarea) | `items.name` | |
| 7 | "Shirt · Light blue" | `category`, `color` | **Duplicates** 10 (What is it) and 11 (Colour) |
| 8 | "Regular fit · long sleeves" (links) | `as_worn`, **derived from the drawing** (`illustrations.worn`, `items.py:107`) | **Contradicts** the Details card: "Fit: **Not set**" and "Length: Not set" (13/14), while Fix details says "Cut: regular". Duplicates "Sleeves: Long sleeves" (12) |
| 9 | Wear panel: "Worn 3 times, last on Tuesday", "Clean · Worn once since washed", **Wore it today**, **Put in the laundry**, Recent wears with Remove | `wears`, `laundry` | Useful |
| 9b | Describing or waiting notice | `tag_state` | Progress, see 1 |
| — | **Details** card, hint "Suggested by Claude…" / "Described in advance for the demo" | `tag_state`, `tag_route` | Hint duplicates 9b |
| 10 | What is it? "Shirts / Kind not said yet" | `kind`, `kind_by` | "Shirts" is the category plural; "Kind not said yet" is jargon |
| 11 | Colour "Light blue (oxford blue)" | `color`, `shade`, `color_hex` | |
| 12 | Pattern | `pattern`, `pattern_colors` | |
| 13 | Formality, Season, Where it lives | `formality`, `season`, `location` | Rarely changed; location is useful |
| 14 | Sleeves, Neckline, Length, Fit | `items.silhouette` (owner/AI) | **Three sources for the same facts**: silhouette (here), answer details plus `own_details` (Fix details: "Sleeve length", "Cut", "Neckline", "Collar"), and `as_worn` (8). They can disagree, and do in the screenshot |
| 15 | How you feel about it, plus "Why? (optional)" | `rating`, `rating_reason` | Near-duplicate of 16d/16e |
| 16 | **More details** fold: (a) Brand, (b) Size, (c) Material, (d) **Fit notes**, (e) Condition chips (no label, `ItemDetail.tsx:353`), (f) Price, (g) Date acquired, (h) **How I wear it** ("Claude reads this…"), (i) **Notes** | Plain columns | (d), (h), (i) and 15's "why" are four free-text boxes about one item. Material duplicates Claude's "Fabric" and "Fibre" (Fix details, 18). Condition has no visible label |
| 17 | "What Claude saw" fold: Fit, Sleeves, Collar, Front opening, Buttons, Button colour, Cuffs, Seams, Pockets, Hem, Fabric, Shade, "Seen but not drawn yet", "Described by …" | `tag_answer.details` (`detailLines`) | **Duplicates** Fix details (2) almost one for one, read-only, with different labels ("Buttons on the front" vs "Number of buttons", "Fit" vs "Cut") |
| 18b | "Seen but not drawn yet" | `seen_not_drawn` | Duplicates 3 |
| 19 | History fold | `history` | Useful but rare |
| 20 | **Describe it again** | | Rare |
| 21 | Archive, Delete | | |

**The root problem:** three separate stores describe what the garment looks like:

- `items.silhouette`: the Details rows.
- `tag_answer.details` plus `own_details`: Fix details and What Claude saw.
- `as_worn`: the worn line.

Each has its own editor and its own words.

### Proposed layout (M for the frontend; L to merge the data)

1. **Picture**, then the view switch. "Not in the drawing" becomes an info icon on the picture.
2. **Progress strip**, only while work is going on (see 1).
3. **Name**, and one line under it: **"Oxford shirt · Light blue · Regular fit · Long sleeves"**. Take this from **one** source: the drawn answer, `as_worn`, which already folds the owner's fields over Claude's. Under it, one link-button: **"Something wrong? Tell Claude"**, which is the new fix sheet from 2. Drop line 7.
4. **Wearing** card, as now.
5. **About it** (your own words): "How you feel about it" (rating chips with a reason box), and **one** notes box, "Notes for you and Claude", merging `wear_notes`, `fit_notes`, `notes` and `rating_reason`. Keep the columns for now; show `wear_notes` as the box and fold the other three in on save, or keep them as one-line fields under a "More" fold.
6. **Details** card, folded: What is it, Colour, Pattern, Where it lives, Formality, Season. **Remove** the silhouette rows (Sleeves, Neckline, Length, Fit) from this card: they belong to the one-by-one screen (see 2) and come from the same store as the worn line.
7. **Shopping facts**, folded: Brand, Size, Material, Condition (with a label), Price, Date acquired.
8. **Folded, at the bottom:** History, Describe it again, Archive and Delete. **Remove "What Claude saw"**: the one-by-one screen shows the same values, marked "Claude's" or "set by you". Keep "Described by Claude on <date>" as one line there.

**Data (L, needs a decision):** make `silhouette` derived from the drawn answer, or the reverse, so that there is one editable store for appearance. At least, make the Details rows read through `illustrations.drawn_answer` so they cannot disagree with the worn line.

---

## 4. Taps that resize the page and feel laggy

Measured with 4x CPU throttling and 80 ms latency (`slow.js`):

- Interaction-to-next-paint was 40-88 ms on every tap. The JavaScript is not slow in itself.
- The lag the owner feels comes from **layout moving after the tap** and from **waiting on the network**.

| Cause | Evidence | Fix | Effort |
|---|---|---|---|
| **Fix details is inserted above the name and pushes the page down**, then grows again when options arrive about 270 ms later. Closing it collapses everything | CLS **0.22** on opening and **0.34** on closing (`item.js`); sources `header.detail-head` and `section.wear`. `ItemDetail.tsx:231`, `FixDetails.tsx:76-85, 111` | Open it as a sheet or a sub-route (see 2). Never insert it in the flow above content | S |
| The button label changes width ("Fix the details" ↔ "Close the details") in a centred row beside the view switch, so the switch shifts sideways | `FixDetails.tsx:51`, `.picture-controls` centred | Fixed label; or it goes away with the sheet | S |
| **`.btn:active { transform: scale(0.97) }`** on every button, and `.big-button` at 0.99. On iOS, React's root touch listeners make `:active` apply, so every press visibly shrinks the control, and a shrinking full-width button reads as the page moving | `styles.css:263, 761` | Use an opacity or background change on press. Keep scale only on small icon buttons, if at all | S |
| Wear tap: "Wore it today" becomes "Worn today + Undo" and the Recent wears list grows a row | CLS 0.04; `ItemDetail.tsx:546-576` | Reserve the row (keep the button width; add the new wear with no reflow above the fold); it is below the action, so it is acceptable | S |
| Item page opens on a bare skeleton (only the picture) and waits for `GET /api/items/{id}` and `vocab`. On Tailscale that is a visible blank of 250 ms or more on every open | `ItemDetail.tsx:191-198`; measured 256 ms | Render at once from the closet's summary (`items.active`), as the offline branch already does (`:167-182`), and fill in when the full item arrives. Keep the last full item in a small cache by id | S-M |
| **Every save runs the whole app**: `upsert` → `setItems` → a new context `value` (`store.tsx:193-196`) → every `useCloset()` consumer (30 of them) and the whole `Shell` re-render. No component is memoised: `grep memo(` finds nothing. While any item is busy, the 2 s poll replaces `items.active` with a new array **even when nothing changed** (`store.tsx:86`) | Code | Compare before `setItems` (skip when equal, by `id:updated_at`). Split the context: items, profile and offline, actions. `React.memo` the closet `Tile` | M |
| `useReviewCount` refetches `/api/review` after every item change **and every route change** | `Review.tsx:30-45`; seen after every PATCH and pick | Refetch only when `tag_state` changes, debounced | S |
| **Synchronous redraw inside an `async def` route**: `patch_item` is `async` but calls `items.update`, which redraws the illustration (`items.py:348`), on the event loop. This blocks every other request, including the poll, until it finishes | `app.py:701-710` | Make it a plain `def` (FastAPI runs it in its threadpool), as `set_details` already is | S |
| Confirmation waits for the network: the chip value is optimistic (`applyPatch`) but the toast appears only after the server answers (316 ms measured). Fix-detail picks have no optimism at all: the tile is disabled while `busy` (`FixDetails.tsx:99-108`) | Code; timing | Mark the chosen tile at once; save in the background | S |
| Sheet on a phone: no body scroll lock, so the page behind it scrolls on iOS when you drag past the sheet's end. It slides in over 300 ms (`styles.css:607-612`) | Code | `overflow: hidden` on body while it is open (or `<dialog>`); shorten to 200 ms | S |
| `.shell { min-height: 100dvh }`. Short pages (Add is exactly 844 px tall) change height as the Safari toolbar shows and hides; `--figure-h: min(62vh, …)` on Today uses `vh` | `styles.css:84, 325` | Use `svh` for minimums, or none (the tab bar is fixed anyway) | S |
| Tab to Today: CLS 0.17 (`today-loading` skeleton 184 px → content 322 px; then the worn question card is inserted) | `slow.js` | Size the skeleton like the result; reserve the question card's space | S |
| Checked and **not** a cause: input font sizes. All inputs are 16 px or more, so iOS does not zoom on focus | `fonts.js` | | |

---

## 5. Page transitions

**How they are built:** there are none.

- The router is about 100 lines (`router.tsx`): `pushState` plus `useSyncExternalStore` on `popstate`.
- There is no View Transitions API, no route animation, no gesture code. The only `pointerdown` listeners close popovers.
- `history.scrollRestoration` is left on `auto`.
- `navigate()` scrolls to the top on every push for a phone (`router.tsx:17, 25-30`).
- On a phone the item page **replaces** the closet (`Shell.tsx:40-41`), so the closet unmounts and is rebuilt on return.

**What breaks:**

1. **The "‹ Closet" link is a forward navigation, not Back** (`ItemDetail.tsx:595-601`, `Link to={backTo}`). Measured (`backlink.js`):
   - closet scrolled to 2717 px → item → tap "‹ Closet" → the closet opens **at the top** (scrollY 0);
   - `history.length` grows 3 → 4 → 5;
   - the browser's Back then goes **forward into the item again**.

   In the **standalone PWA** on iOS there is no browser Back button and no edge-swipe back, so this link is the only way back, and it always loses the owner's place and piles up history. This alone explains most of "transitions are a mess".
2. In Safari (a tab), the edge swipe goes back through real history and does restore the scroll position: in Chromium the closet came back at the same 615 px. But it lands on whatever extra entries step 1 created, which feels random. Safari's own swipe animation shows a snapshot; adding a CSS or View Transitions animation on top would double-animate. That is a reason **not** to add one.
3. Sheets and the fix panel are not in history, so a back-swipe while one is open leaves the whole item page.
4. Every navigation shows the skeleton first (see 4), which looks like a flash.
5. The first open of a tab redirects to `/today` with `replace` (`landing.ts`). That is fine, but it happens after the closet list loads, so the closet can flash first.

**Recommendation: do not add animated transitions.** Make navigation correct and calm (S-M):

- **Back link (S):** call `history.back()` when the previous entry is in the app. Record that with `history.state = { idx }` in `navigate`. Fall back to `navigate(backTo, { replace: true })` when the item was opened directly.
- **Keep the closet's scroll on a phone (S):** keep the scroll position in `filterMemory`-style memory keyed by route and restore it on mount. Or, better, keep `ClosetScreen` mounted but hidden (`display:none`) while the item is shown, so the grid, its images and its scroll survive.
- **No flash (S-M):** render the item from its summary at once (see 4).
- **(Optional)** If some motion is wanted, use a 150 ms opacity fade on `.shell-content` only for in-app *forward* pushes, and none on `popstate`, so it never fights Safari's swipe. Respect `prefers-reduced-motion`.
- **(Optional)** Put a `?sheet=` state into history for the fix sheet, so back-swipe closes the sheet first.

---

## Other problems found in this scope

- **Contradictory facts on one screen** (see 3): "Regular fit" in the worn line, "Fit: Not set" in Details, "Cut: regular" in Fix details. It needs one source.
- "What is it? **Shirts** / Kind not said yet": the plural of the category stands in for the kind, and "kind" is jargon (`ItemDetail.tsx:474-477`).
- The Condition chip group in More details has no visible label (`ItemDetail.tsx:353`).
- Colour value truncates: "Light blue (oxf…" (`.detail-row-text` nowrap with ellipsis).
- Closet tiles show nothing while an item is described or measured, so a new item looks finished with a placeholder name ("New item" or the category).
- When the model is missing, the Add rows read "Waiting for the model" with no link to the download. The model banner is on the closet page, not on Add.
- The add intro paragraph plus the shoe tips push **Take photos** halfway down the first screen (`20-add-empty.png`, `21-add-02.png`). Fold the shoe tips until a shoe is sorted.
- Pattern measuring is not polled by the store, so the closet grid's drawing goes stale until a reload (`store.tsx:46-52`).
- `GET /api/items` (the full list, about 36 KB for 49 items, more for a real closet) is the progress channel for the whole app.
- `detail_options` is fetched again on every `stamp` change, that is every save (`FixDetails.tsx:35, 76-85`); with polling during work this refetches in a loop.
- In the demo, "Or say what's wrong" is offered and then refused with a 409. Hide it there.
