# What daily-clother should borrow from Homestead

Read-only comparison, 19 Nov 2026. "H" = Homestead (`/home/user/empower-personal-app`), "DC" = daily-clother
(`/home/user/daily-clother`). Paths are relative to each repo root. No figures, names or emails from Homestead's
data are reproduced here.

---

## 1. Repo and agent-context organization

### How Homestead does it
- **`CLAUDE.md` (72 lines)** is a short router rather than a manual: what the app is, which doc to read for
  which kind of change (DESIGN before anything visible, DEVELOPING before anything structural, USING for page
  behavior, BACKLOG/REVIEW for what's next), a "Starting a new conversation" section that says *don't scan the
  repo, go to the Module map*, "Keeping a conversation short", standing wishes (privacy, release rules, things
  not to rename), and **"Before saying a change is done"**: the exact commands (pytest, tsc, lint, build, then
  `money serve --demo` + `phone-check.cjs`), plus "every user-visible change gets a CHANGELOG line under
  Unreleased and a USING.md paragraph".
- **Module map** (`docs/DEVELOPING.md:140-170`): one table row per backend package and frontend place, one line
  each, including where query keys live and what each lib does. Then **Structure rules** (`:172-196`: api → ledger
  → db, plain-dict responses, settings via a registry, "one of each helper"), and recipes **Adding a page**
  (`:470-482`, six numbered steps including the phone-check page list and Penny's guide), **Adding an endpoint**,
  **Adding a migration**.
- **`docs/DESIGN.md` (210 lines)**: who it's for, the jobs in order of frequency, 10 numbered principles, a
  Writing section, a Pages section, and a **Checklist for any change** (`:197-210`) that ends with the docs and
  checks to update.
- **`CHANGELOG.md` with `## Unreleased`**, and the release workflow (`packaging/release.py:44-47`) refuses to
  release without that section and turns it into the version's notes. Every user-visible change adds a line.
- **`docs/BACKLOG.md`** opens with *Yours to do* (what the owner must act on); **`docs/REVIEW.md` /
  `docs/REVIEW-phone.md`** are dated design reviews with measured before/after tables (screens long per page at
  375/393/402/440) and a "What to build first" list marked **Built** as items land.
- **Project skill** `.claude/skills/design-review/SKILL.md`: start demo server, run `design-sweep.cjs` (every
  page at desktop + phone, reduced motion, word count vs the 500-word budget) and `phone-check.cjs` (every page at
  five iPhone sizes, fails on horizontal overflow, injects long names first), then review each page against the
  DESIGN checklist and output a findings table.
- `frontend/src/design-system/README.md` + `index.ts`: one entry point that re-exports every primitive, for
  design tools and agents.

### How daily-clother does it today
- **`AGENTS.md` (125 lines)**: hard rules, a Layout table (`AGENTS.md` "Layout" section, one row per top folder,
  but `backend/closet/` is one long sentence listing ~60 modules), checks to run, conventions, and a long
  "Drawing in 3D" section. Written for Copilot agents working one issue per PR.
- **`README.md` is 845 lines** mixing the owner's user guide (install, iPhone, Claude Code, backups) with
  development notes. **`docs/DECISIONS.md` is 1,317 lines** in ~20 sections, chronological, mixing design-system
  rules (`:1230-1256`), Settings ordering (`:1258-1268`), drawing details and phase history. There is no
  per-screen behavior doc (no USING.md equivalent) and no design principles + checklist doc.
- **No CHANGELOG.** Release notes come from wherever GitHub's release body comes from.
- **`docs/BACKLOG.md`** may not be edited by agents ("the orchestrating session keeps it"), so later agents have
  no reliable "what's left of this piece of work" trail except PR descriptions.
- No `.claude/` directory, no skills, no CLAUDE.md. `frontend/scripts/` has only `make-icons.mjs`.
- Strong points H lacks: CI runs everything on PRs; `frontend/e2e/` (27 Playwright specs incl.
  `04-layout.spec.ts` 390px overflow, `17-accessibility.spec.ts` axe on phone and desktop, light and dark,
  `18-phone-qr.spec.ts`); `frontend/src/design.test.ts` fails on off-scale font sizes, non-token radii/colours and
  off-token motion. These are better than H's checklist-only enforcement.

### Recommendation
1. **Add `CLAUDE.md` as a thin router that imports `@AGENTS.md`** (Copilot keeps reading AGENTS.md; Claude Code
   gets the same content), plus H's "Starting a new conversation" and "Before saying a change is done" sections.
   Keep AGENTS.md's hard rules.
2. **Split docs by question** (move, don't rewrite):
   - `docs/DEVELOPING.md`: a **Module map** with one line per backend module (the 60 in `backend/closet/`) and
     per frontend file/folder (`screens/`, `components/ui/`, `store.tsx`, `api.ts`, `router.tsx`, the ~40
     pure-logic `*.ts` files at `src/` root), **Structure rules**, and recipes *Adding a screen / an endpoint / a
     migration / a background job*. Move the dev half of README here.
   - `docs/DESIGN.md`: who it's for and the jobs (wardrobe version: "what do I wear today, on the phone, in ten
     seconds" first), 6-8 principles, Writing rules, and a **checklist for any change**. Pull the design-system
     bullets out of DECISIONS `:1230-1256` into it; leave DECISIONS for decisions with their *why*.
   - `docs/USING.md`: one paragraph per screen saying what it does; this is what kills duplicated/scattered text,
     because there's one place to check what a screen already says.
3. **Add `CHANGELOG.md` with `## Unreleased`**, required by the release workflow (port `packaging/release.py`'s
   check), and make "a CHANGELOG line for every user-visible change" part of done. The in-app update notes then
   come from it (see section 5).
4. **Let agents append to BACKLOG** under a "Left over from finished work" heading (or a separate
   `docs/FOLLOWUPS.md`) so context survives between agents without editing the orchestrator's plan.
5. **Port the review loop**: a `frontend/scripts/phone-check.mjs` (every screen at 375/393/402/440 against the
   demo closet with long item names injected, screenshots out, non-zero exit on overflow; DC's e2e already checks
   390 only), a `design-sweep.mjs` with word counts per screen, and a `.claude/skills/design-review/SKILL.md`
   pointing at DESIGN.md. Reuse DC's existing Playwright fixtures/server (`frontend/e2e/server.ts`).

---

## 2. Web app over Tailscale / phone access

### How Homestead does it
- **Binding**: the server only ever listens on 127.0.0.1. Phones come in through **Tailscale Serve**
  (`https://<computer>.<tailnet>.ts.net` → `127.0.0.1:8765`), which gives free HTTPS with a real certificate (no
  cert handling in the app) and adds `Tailscale-User-Login` / `-Name` headers.
- **Request context is decided in middleware** (`backend/money/api/app.py:190-241`): Host must be
  127.0.0.1/localhost, or end in `.ts.net` on the hub, or be the configured Cloudflare host; the viewer comes from
  the Tailscale headers (`tailnet_viewer`, `:63-78`, refusing Funnel traffic) and on Windows is believed only
  after `tailnet.py` confirms the peer process is tailscaled. `local` is true only for the desktop window's
  cookie. Both are put on `request.state` and **echoed by `GET /api/hub/status`** (`api/hub.py:58-78`: `is_hub`,
  `viewer`, `local`, `can_set_up`). Changes also need an `x-money-client: 1` header (CSRF guard).
- **Auth/device pairing**: none on the phone. Membership of the tailnet *is* the login (plus an optional "Who's
  allowed" list). The desktop window gets a random token via `/?token=` → httpOnly cookie.
- **Connect-a-phone UI**: `frontend/src/pages/Hub.tsx`. The QR (`QrCode`, `:44-53`, white background for cameras)
  lives only in `ShareLink` (`:102-141`), rendered only by `TailscaleSteps` once Tailscale reports a URL
  (`:204`). `TailscaleSteps` is rendered only in the branch `hub.running || restarting` (`:929-964`), i.e. **the
  desktop app window on the hub computer**. A phone is served by the hub process (`settings.hub` true →
  `is_hub: true`), so it takes the `is_hub` branch (`:908-927`): "You're on the household hub as <name>", sync
  schedule, update, who's allowed, visits. No steps, no QR. The whole card is a `Fold phoneClosed` whose status
  line says which situation you're in (`:1040-1060`).
- **Client-side checks** for the same idea: `lib/offline.ts:31` `onThisComputer` (hostname 127.0.0.1/localhost)
  and `:34` `.ts.net` hostname → keep a saved copy by default.
- **PWA**: `public/manifest.webmanifest` (`display: standalone`, maskable icon), `index.html` apple meta tags,
  `public/sw.js` served `no-cache` while assets are long-cached (`api/app.py:280-292`); `index.html` always
  `no-cache` so an updated hub shows on every phone; `vite:preloadError` reloads once after an update
  (`App.tsx:47-56`).
- **Standalone handling**: `lib/standalone.ts` sets `<html data-standalone>`; CSS changes `--tabbar-h`
  (`index.css:302-308`): in Safari the tab bar floats above Safari's bar, from the home screen it docks to the
  bottom with the home indicator inside its padding (`components/layout/Phone.tsx:31-52`).

### How daily-clother does it today
- Also binds 127.0.0.1 only and uses Tailscale Serve (`backend/closet/phone.py`), with a passphrase login on every
  device (`auth.py`, `gate.py`). `phone.info()` (`phone.py:104-136`) shells out to `tailscale status/serve status
  --json` and returns `address` when a share reaches Closet.
- `settings_payload` (`backend/closet/app.py:1374-1395`) includes `"phone": sv.phone_info()` with **no knowledge
  of the request**: it never looks at the Host header or Tailscale headers.
- `SettingsScreen` renders "Phone access" whenever settings have loaded (`frontend/src/screens/Settings.tsx:202-206`),
  and `PhoneAccess` (`components/PhoneAccess.tsx:18-31`) shows the QR whenever `phone.address` is set. So the
  phone, opened at that very address, is shown a QR code of the page it is on, with instructions to scan it.
- Manifest and apple meta tags exist (`index.html`, `public/manifest.webmanifest`); service worker is generated at
  build (`vite.config.ts`); there is no standalone detection at all (no `display-mode` check anywhere in `src`).

### Recommendation
- **Make the server say where the request came from.** In `settings_payload(conn, request)` add
  `phone.here = "phone"` when `request.headers["host"]` ends with `.ts.net` (or equals the share's host) or a
  `tailscale-user-login` header is present; `"computer"` for 127.0.0.1/localhost. This is a UI hint, not an auth
  decision, so no peer-process check is needed (the passphrase login stays, per AGENTS.md).
- **Frontend fallback**: `const onComputer = ['127.0.0.1','localhost'].includes(location.hostname)`. On the
  phone, replace the QR with one line: if not standalone, "To open Closet like an app, tap Share, then Add to Home
  Screen"; if standalone, nothing (or the address, folded under Advanced). Show the QR and `tailscale serve`
  steps only `onComputer`.
- **Port `useStandalone`** (`H lib/standalone.ts`, 30 lines) and the `--tabbar-h` split so the tab bar sits right
  in both Safari and home-screen mode.
- Send `Cache-Control: no-cache` for `index.html` and `sw.js` and long cache for hashed assets, and add the
  `vite:preloadError` reload-once handler, so the phone picks up a new build without a stale white screen.
- Don't copy: H's Windows hub (scheduled task, UAC), Cloudflare Access, `tailnet.py` process check, "Who's allowed",
  visits log. They're for several people sharing one server; DC has one owner with a passphrase.

---

## 3. Page navigation and transitions on iPhone

### How Homestead does it
- **react-router `BrowserRouter`** (`main.tsx`), routes in `App.tsx:120-150`. Home and Transactions are bundled;
  every other page is `lazy()` (`App.tsx:19-31`, `lib/pages.ts`), all page code is prefetched when idle 3s after
  load (`App.tsx:58-64`), and a page's code *and its first query* are prefetched on `onTouchStart` of a tab
  (`components/layout/Phone.tsx:52`, `lib/prefetch.ts`), so by the time the tap lands the data is usually there.
- **No page-to-page animation on purpose.** `Suspense` fallback is a 3px top bar that only appears after 200ms
  (`App.tsx:67-79`). Cards fade in with a short stagger **only the first time a page is shown per app load**
  (`lib/motion.ts:9-12, 48`), so tab switching is instant afterwards. A drawer that the browser already animated
  (iOS swipe back) appears/disappears with no slide of its own (`lib/drawer.ts:10-12`, `ui.tsx:810-842`); the
  changelog's latest fix is exactly a double slide on swipe-back.
- **Scroll restoration** (`components/layout/ScrollMemory.tsx`): `history.scrollRestoration = 'manual'` (`:66`),
  one saved position per history entry, kept in sessionStorage across reloads; Push to a new page scrolls to top,
  Back retries the saved position for up to 2.5s while data arrives, and stops if the user scrolls.
- **Motion tokens** in one file (`lib/motion.ts`: one curve, tap/arrive/draw durations, two springs) mirrored as
  CSS variables; `MotionConfig reducedMotion="user"` (`main.tsx`).
- **Touch CSS** (`index.css:318-405`): 16px fields on `pointer: coarse` (stops Safari's zoom-on-focus);
  `overscroll-behavior-y: contain` and `overflow-x: clip` on html/body (nothing poking out can make Safari zoom
  the page out); `-webkit-touch-callout: none` and `user-select: none` on controls, kept on inputs; pressed
  controls **dim by opacity after 70ms** (so a scroll doesn't flash rows) rather than scale; a no-op `touchstart`
  listener so Safari applies `:active` (`main.tsx:51`); `.hit` adds an invisible 40px hit area.
- **Viewport**: `viewport-fit=cover`, safe-area insets on body sides, `--tabbar-h` includes the bottom inset,
  `svh`/`dvh` used only for sheets.

### How daily-clother does it today
- Hand-rolled router (`frontend/src/router.tsx`): `navigate()` pushes state, notifies `useSyncExternalStore`
  listeners, then `window.scrollTo(0,0)` (`:11-18`). **No `history.scrollRestoration = 'manual'`** and no saved
  positions, so on Back the browser restores scroll before the screen (which refetches) is tall enough, and it
  lands short or jumps.
- `Shell.tsx:31-41` mounts screens by `if/else` on the route; every screen is in the main bundle (no lazy, so no
  code wait, fine) **but every screen keeps its data in local state and refetches on mount** (e.g.
  `screens/Trips.tsx:90-117`, "Loading your trips…" at `:130`). Each tab switch is therefore blank → spinner →
  content, and the header button appears only after load (`Trips.tsx:127` `primary={trips && …}`), which shifts
  the title row.
- No tap prefetch, no standalone mode, no touchstart listener (so `:active` press styles mostly don't show on
  iOS), `.btn:active { transform: scale(0.97) }` (`styles.css:263`).
- `body { overflow-x: hidden }` (`styles.css:215`) rather than `clip` on html+body; no `overscroll-behavior`.
- One select is 14px (`components/LifeQuestions.css:12`), which makes iOS zoom in on tap and stay zoomed: one
  literal "the page resizes when I tap" cause. Others: banners mounting at the top of the shell after load
  (`Shell.tsx:63-100`: Restarting, UpdateBanner, RestoreNotice, offline banner push everything down), headers
  gaining buttons after load, and the 2s polling re-render (section 4).
- Good already: tokens for motion (`--ease-out`, `--dur-quick/move`) enforced by `design.test.ts`, reduced-motion
  handling, safe-area padding, a tab bar.

### Recommendation
- **Keep the hand-rolled router** (it's small and tested), but add H's ScrollMemory logic to it: set
  `history.scrollRestoration = 'manual'`, keep `Map<historyKey, scrollY>` (store a key in `history.state` on
  push), restore on popstate with the retry-until-tall-enough loop, scroll to top on push.
- **Keep screens' data across navigation** (section 4: a query cache) so going back to a tab renders its last data
  immediately. That's what makes the transitions feel calm, not an animation.
- **Do not add page slide transitions**; iOS's own swipe-back already animates, and an app slide on top is the
  double animation H had to remove. If anything, H's first-visit-only fade.
- Port H's touch CSS block wholesale (16px fields on coarse pointers, `overflow-x: clip` + `overscroll-behavior-y:
  contain` on html/body, `touch-callout`/`user-select` rules, opacity press feedback with the 70ms delay, the
  `touchstart` listener). Replace `scale(0.97)` on press with the opacity dim.
- Reserve space for anything that appears late: render the header's primary button disabled/placeholder from the
  start, and put update/restore notices into one slot that doesn't push content (or a toast).
- Prefetch on `onTouchStart` of tab links once a query cache exists.

---

## 4. Data loading and perceived smoothness

### How Homestead does it
- **TanStack Query** for everything (`main.tsx:13-24`): `staleTime` 60s, `gcTime` 24h, `refetchOnWindowFocus` only
  after 10s away (`:35-45`), mutations never wait for a connection. Every key lives in `lib/keys.ts`; **`TOUCHES`**
  (`keys.ts:202-297`) says which keys each kind of edit refreshes, and `useEdit` (`lib/api.ts:232-248`) invalidates
  exactly those after a save, with a `settling` flag for "Bringing in the latest figures…".
- **Saved copy on device** (`lib/offline.ts`): the query cache is dehydrated to localStorage (cap 3MB, 14 days,
  versioned by `DATA_VERSION`) and restored before first render, so the app opens instantly with what you saw last,
  then refreshes. A page that crashes on an old copy drops it and retries (`App.tsx` `PageError`).
- **Avoiding pop-in**: pages gate once on their main query (`Settings.tsx:1105-1108` `if (!meta) return
  <PageLoading/>`), then render all cards together; folded cards render their title and one-line status even while
  closed; `keepPreviousData` for filter changes; structural sharing means a refetch with identical data doesn't
  re-render.
- **Optimistic-ish edits**: the server returns the changed row, which is written into every list showing it
  (`useTxnEdit`, `api.ts:257-271`), and the rest refreshes behind it. Saves say "Saving…", "Saved", "Didn't save ·
  Try again".
- **Background work**: polling that adapts to state, e.g. `refetchInterval: running ? 2000 : 60000`
  (`api.ts:293` sync status; `AskPenny.tsx:934`; `hub.ts:97` update every 2s while updating). Penny's answers use
  **SSE** (`api.ts:403-409`) with polling fallback. Long jobs report a **named state machine**: hub update
  `downloading | verifying | checking | restarting | done | failed` (`lib/hub.ts:74-83`), each with one sentence and
  a spinner (`pages/Hub.tsx:330-350`). The mascot's `hay` pose means "working on it".

### How daily-clother does it today
- **Hand-rolled**: `api.ts` (390 lines) plus a context store (`store.tsx`) for items/vocab/model, and every screen
  fetching its own data in `useEffect` into local state (e.g. 9 `useEffect`s in `Settings.tsx`, 12 in `Today.tsx`).
  localStorage copies (`saveTrips` etc.) are used only when offline.
- **Polling replaces the whole items list every 2s** while anything is being cut out or described
  (`store.tsx:124-140`), with a fresh array each time even if nothing changed, so every consumer of `items`
  (closet grid, Today) re-renders every 2s; downloads poll every 1.5s (`:142-148`). This is a likely source of
  "taps lag" on a phone while uploads are processing.
- Pop-in: Settings renders subsections conditionally on separately loaded data (`Settings.tsx:171-175`
  `{model && …}`, `{settings?.laundry && …}`, `{settings?.rewear && …}`, `{settings && <Backup…>}`) and each
  section fetches its own data (style `:55-66`, storage `:458-470`, tagging `:541-552`, spend `:786-795`, updates
  `Updates.tsx:10-18`), each with its own "Loading…/Checking…/Adding up…" line, so the page grows in five or six
  steps after opening.
- Background work progress is per item (`cutout_state`, `tag_state`, `drawn_state` badges), plus the model banner,
  the upload queue on Add, and per-screen polls (`Shop.tsx:40`, `WouldWork.tsx:108`, `Several.tsx:46`,
  `ItemDetail.tsx:98`). There's no single place that says "3 photos being cut out, 2 being described, Claude is
  choosing today's outfits".

### Recommendation
- **Adopt TanStack Query** (one dependency, pinned; justify in the PR as AGENTS.md asks). Start with items,
  settings, trips, today, worn: a `keys.ts` with every key and a `TOUCHES` map, a `useEdit` that invalidates
  them. Structural sharing alone stops the 2s full re-render; `staleTime` + cache stops the per-tab spinner.
- **Persist the cache** like `H lib/offline.ts` (dehydrate a whitelist to localStorage, versioned), replacing the
  ad-hoc `saveTrips`/`loadSavedTrips` copies; the phone then opens straight onto the last closet/Today.
- **Settings: one fetch, one gate.** Return everything Settings needs (settings, model, storage summary, tagging
  status, spend, update status) from one `GET /api/settings` (or fetch them in parallel and gate on all), render
  every section at once with folded headings and status lines.
- **One work-status endpoint**: `GET /api/work` → `{cutouts: {waiting, running}, describing, drawing_shoes,
  stylist: state, model_download: {bytes,total}, update: state}`; poll it at 2s while anything runs, 60s
  otherwise (`refetchInterval: (q) => q.state.data?.busy ? 2000 : 60000`), and refetch `items` only when its
  counts change. Show it as one slim line/pill in the shell ("Cutting out 3 photos · describing 2"), with a named
  state and sentence per long job, as H's update states do. Consider SSE later only for the stylist's answer.
- Reserve layout for late content (skeletons the same height as the content, already started in
  `Insights.css:12`, `Missing.css:50`).

---

## 5. Settings page structure

### How Homestead does it
- `pages/Settings.tsx:1105-1135`: **six headed groups in a fixed order**: Your household · Connections and sync
  (Empower, Sync, Hub) · Notifications · <character> (Penny, Ask Penny, Memory) · Backup and data · Diagnostics.
- **Every card is a `Fold`** (`components/ui.tsx:1040-1155`): title, optional count, and a **one-line status**
  ("Not set up yet", "On, with … of the monthly limit used"), chevron; `phoneClosed` folds only on a phone
  (desktop shows the open card); `open` forces it open when something needs you (error, update waiting, failed
  sync, `#hash` link). Open/closed is remembered for the session. Measured effect: Settings went from 6.2 to 2.2
  screens on a phone (`docs/REVIEW-phone.md`, table at top).
- **One gate** before rendering (`if (!meta) return <PageLoading/>`), so groups don't appear one by one.
- **Secrets**: API key field is `type=password`, "kept encrypted on <this computer> and never shown again", Save /
  Replace / Remove (remove asks first because it can't be undone), test button, and a `Segmented` "An API key /
  Your Claude plan" switch (`Settings.tsx:397-470`). Status line shows month spend against the cap.
- **Updates**: in the Hub card: "Homestead X is out. The hub is on Y." plus a **"What's new" link to the release
  page** (`pages/Hub.tsx:354-380`); notes are not rendered in-app. Progress is the named state machine. The
  release notes themselves come from `CHANGELOG.md` Unreleased. (H's `components/Markdown.tsx` is a tiny safe
  renderer, bold/code/links/lists, text only, used for Penny's answers.)

### How daily-clother does it today
- `screens/Settings.tsx:122-229`: groups in the order DECISIONS fixed (`DECISIONS.md:1258-1268`): Your closet (demo,
  autostart, background removal, laundry, re-wear, backups, storage), Where you are, How you live, Look, Your
  style (an 8-row textarea), Describing clothes (routes, order, API key, spend), Updates, Phone access, Advanced
  (`<details>`), Log out / Quit. All open; the review measured ~4,850px on a phone (`BACKLOG.md` "Bigger
  redesigns").
- Sections pop in as each fetch lands (see section 4). Phone access appears only after settings load, and shows a
  QR on the phone itself (section 2).
- Updates (`components/Updates.tsx:63-166`): version, last check, mode switch (auto / ask / never), Check now, and
  **raw release notes text** in a `white-space: pre-line` box (`styles.css` `.update-notes`, backend
  `updates.py:92` keeps "the first lines as plain text"), so Markdown `##`, `-`, `**` show literally.

### Recommendation
- **Port `Fold`** (with `status`, `open`-when-urgent, `phoneClosed`, session memory) into `components/ui/`, styled
  with DC's tokens, and rebuild Settings as **five or six groups that start folded on a phone**, each with a
  status line:
  1. *Your closet*: demo switch, where you are, how you live (status: "New York · answers saved").
  2. *Look*: theme (status: "Same as this device").
  3. *Claude*: how it's reached (plan / key, one Segmented like H's), key, monthly limit, "let Claude choose my
     outfits", and Your style as remembered lines (section 7). Status: "Your Claude plan · $x of $y this month".
  4. *Laundry and re-wear*.
  5. *This computer*: start at login, background-removal model, backups, storage, phone access (computer only),
     updates. Status: "Backed up yesterday · version 0.x".
  6. *Advanced*, then Log out / Quit as a row.
  Anything that needs action (model missing, update waiting, key refused, backup failed) passes `open`.
- **Render all groups at once** after one gate (section 4).
- **Release notes**: either do what H does (a "What's new" link), or render them with a ~40-line safe Markdown
  subset like `H components/Markdown.tsx` (paragraphs, lists, bold, code, links as text, never HTML), fed from a
  CHANGELOG section. Don't show raw Markdown.

---

## 6. Design system

### How Homestead does it
- Tailwind v4 over CSS custom-property tokens in `frontend/src/index.css` (light/dark), primitives in
  `components/ui.tsx` (Card, Button, Fold, ShowMore, Segmented, Field, HowWorkedOut, Empty, PennySays, …),
  re-exported from `design-system/index.ts` with a README. Chart palette in `lib/palette.ts`, motion in
  `lib/motion.ts`. Principle 10 "One system": a new colour, font, button style or motion value is a design-system
  change.
- **Writing rules** (`DESIGN.md` "Writing"): plain words, second person, sentences not labels, money via
  `money()`, dates via `dayLabel`, no exclamation marks, drop a sentence rather than squeeze it, phone summaries
  must make sense cold. Reading load is a budget: one-line sub-captions, two-sentence footnotes, explanations
  behind one "How this is worked out" affordance, under ~500 words per page (the sweep counts).
- Enforcement is mostly human: the checklist, the `/design-review` skill, the phone check. No token lint.

### How daily-clother does it today
- Plain CSS: `styles.css` (927 lines) with a good token set (`:root` ink/surface/line levels, 1.25 type scale,
  4px spacing, radii, `--tap: 44px`, motion), per-screen CSS files, and 9 primitives in `components/ui/` (Button,
  Card/Section, Chips, EmptyState, ItemThumb, Notice, PageHeader, SegmentedControl, Sheet) styled with `:where()`.
- **`design.test.ts` enforces** the type scale, radius tokens, colour tokens, motion tokens and label styling.
  DECISIONS records the system (`:1230-1256`). Accessibility enforced by axe e2e.
- Missing: a principles doc, writing rules beyond "plain words", a reading-load budget, and shared "fold", "show
  more", "how this works" primitives, so each screen invents its own (`.more summary`, `<details>`), which is part
  of the scattered/duplicated text.

### Recommendation
- **Keep DC's CSS + tokens + `design.test.ts`**; don't migrate to Tailwind. DC's enforcement is better than H's.
- Add to `components/ui/`: `Fold`, `ShowMore` (first N on a phone, "See all N"), `HowItWorks` (one closed-by-default
  explanation affordance, replacing ad-hoc hint paragraphs), `SaveStatus` ("Saving… / Saved / Didn't save · Try
  again"). Then a design-review pass replaces hand-rolled versions.
- Write `docs/DESIGN.md` with a Writing section and a **per-screen word budget** (H's 500 desktop words is a good
  start; DC's phone screens should be far lower), and add the word count to the sweep. Add "one thing, one home":
  a sentence that appears on two screens links instead.
- A `components/ui/README.md` listing the primitives and tokens (H's design-system README pattern), so agents
  reuse rather than invent.

---

## 7. Assistant / chat and learning preferences

### How Homestead does it
- Penny is a chat (`components/AskPenny.tsx`, `assistant/runner.py` on a background thread, SSE stream) with read
  tools that call the same ledger code as the pages and `propose_*` tools that write **proposals**, never changes
  (`assistant/tools.py:695-1145`). The user ticks items, Apply / Skip / Undo; Penny says she did something only
  after the app confirms.
- **Preferences are learned by asking, not by forms**: `assistant/questions.py` lists what the app can't learn from
  data, each with why it matters and where it's recorded; Penny asks one or two when they bear on an answer, the
  weekly check-in asks one, and each answer (even "no") is stored so it's never asked twice. Principle 4: "No setup
  wizard: Penny asks for what's missing when it matters, and records the answer."
- **Memory** (`docs/PENNY.md:39-41`, Settings → Memory): short facts, readable and deletable; Penny proposes a new
  one (`propose_note`) when told something worth keeping.
- Penny reads `assistant/guide.md` (the app's own guide), kept true when a page changes.
- Evals harness (`backend/evals/penny/`) with a free oracle/null stand-in and a cost-capped paid run.

### How daily-clother does it today
- Already halfway there: on Today the owner can talk to Claude about the outfits (`screens/Today.tsx:881-1000`
  `Conversation`; migration `0033_style_talk.sql`), Claude may offer up to two things to **remember**
  (`tagger/stylist.py:103`), saved only on tap, to Your style or the piece's "How I wear it"
  (`styleprofile.py:14` `SOURCES = ("owner", "claude")`). The owner already put the interview on hold because the
  conversation can glean it (`BACKLOG.md`, Step 4).
- But Settings' **Your style is a free-text 4,000-character textarea** (`Settings.tsx:46-121`) with "Back to the
  starting text", so remembered lines vanish into one blob the owner must edit by hand. "How you live" is a
  multi-question form (`components/LifeQuestions.tsx`). `taste.py` learns from wears and ratings with no text.

### Recommendation
- Make **Your style a list of remembered lines** (like H's Memory): each line with where it came from ("You said
  on Nov 12", "Starting rule"), Remove, and Edit; plus one "Add a line" box. Store them as rows rather than one
  text, and build the stylist's profile text from them. Keep the full text view under Advanced if wanted.
- Port H's **questions** idea: a `questions.py` listing what the stylist can't infer (runs warm/cold, dress code at
  work, colours avoided, how formal on weekends), each with why and where it's stored. The stylist asks at most one
  per day inside the Today conversation when it bears on the outfit; the answer becomes a remembered line;
  "no" is recorded. Then "How you live" can shrink to what isn't conversational (frequencies) or be asked the same
  way.
- Keep Claude's offers as proposals (save on tap, undoable), which DC already does.
- Don't copy: H's full chat drawer, SSE runner, propose_* catalogue, MCP server, app guide for the assistant,
  scheduled check-ins. DC's assistant is scoped to the day's outfits; a cheap version of H's eval stand-in (a fake
  stylist answering from scripts for e2e/screenshots) is worth having, and `tools/style_demo_days.py` is a start.

---

## 8. Backend structure

### How Homestead does it
- `api/app.py:151-300` `create_app` includes ~22 routers from `api/<area>.py` (`APIRouter(prefix=...)`,
  `Depends(get_db)`), middleware for access, timing (Server-Timing header, slowest routes on the Hub page), security
  headers, gzip, and the SPA fallback. Rule: api → ledger → db; responses are plain dicts built in the ledger.
- Settings registry `settings_keys.py` (every key with default and description, `KEY.get(conn)`).
- Migrations `migrations/NNN_name.sql` applied in a transaction with `schema_version` (26).
- Tests: 81 files; demo data pinned to a date; property-style generated households; `-m "not slow"` quick set.
- Release: version in one place, Actions workflow writes it, moves CHANGELOG Unreleased, tags, builds, tests, runs
  phone check, publishes. Hub self-update: checksum, run new build with `--hub-check`, then **`--trial` on a copy
  of the database** (migrations + every page endpoint) before swapping, backup, swap helper, auto-rollback, "go
  back to previous version" with its data.

### How daily-clother does it today
- `backend/closet/app.py` is **1,661 lines**: `build_services` (`:182`) and one `create_app(sv)` (`:529`) that
  defines ~96 routes as closures. Feature logic is in ~60 well-named modules (good), but routes aren't grouped.
- Program-wide state in a JSON file (`state.py`, `DEFAULTS` with comments: effectively a registry already) plus
  per-closet SQLite; 36 numbered migrations with the "never edit, renumber on conflict" rule; 86 test files;
  `gate.py` checks login and size limits before reading bodies.
- `updates.py` (829 lines): daily check of a public repo's releases, SHA-256 verify, backup, swap, helper,
  rollback within a minute, user-chosen mode (auto / ask / never). Close to H minus the trial-on-copy.

### Recommendation
- **Split `app.py` into routers** by feature (`api/items.py`, `api/today.py`, `api/trips.py`, `api/settings.py`,
  `api/updates.py`, `api/phone.py`, …) with a shared `deps.py` for `conn_dep`/`require_auth`; one PR per router,
  no behavior change. Add H's "Adding an endpoint" recipe to DEVELOPING.md.
- Add a **Server-Timing middleware** and log the slowest GETs (H `api/app.py:256-268`): cheap, and directly useful
  for "taps lag".
- Add **gzip** (`GZipMiddleware`) if not present, for phone over Tailscale.
- Consider H's **trial on a database copy** before an update swaps in (migrations + one GET per screen) once real
  closets exist; DC's migrations are frequent and an update that breaks on the owner's data is the worst case.
- Keep DC's `state.py` / per-closet DB split and gate.

---

## Do not copy

- The Windows hub, scheduled task, UAC setup, Cloudflare Access, `tailnet.py` process check, "Who's allowed",
  visits log, offsite encrypted backups, Web Push. Multi-person, finance-grade concerns.
- Penny's full proposal/undo engine, MCP server, assistant app guide, scheduled check-ins/recaps, paid evals
  harness. DC's assistant is narrow.
- The characters/rigs and pose contract (`design/CHARACTERS.md`, `components/characters/`), ECharts, the
  household property-test generators, tax tables, the Claude Design `design-system/` export.
- Tailwind. DC's tokens + `design.test.ts` are stronger.
- H's long docs volume (USING.md is 1,462 lines). Port the structure, not the length.

## What daily-clother does better

- CI that runs backend, bench, lint, typecheck, unit and **Playwright e2e on every PR**; H has parked front-end
  tests.
- **Automated design enforcement** (`design.test.ts`) and **axe accessibility** checks at phone and desktop sizes,
  light and dark, with 44px tap targets.
- Focus management (`components/ui/focus.ts`), `:where()` zero-specificity primitives.
- DECISIONS with a *why* for each choice; work split into tracks with stops the owner tries.
- Update modes the owner chooses (auto / ask / never) and a full-screen "Restarting" overlay that reloads itself.
- Pure logic pulled out of components into tested `src/*.ts` modules (`today.ts`, `trips.ts`, `labels.ts`…).

---

## Ranked list of things to port

| # | What | Effort | Impact |
|---|---|---|---|
| 1 | Hide the phone QR on the phone: `phone.here` from Host/`tailscale-user-login` in `settings_payload`, plus `location.hostname` fallback; show "Add to Home Screen" line instead when not standalone | S | High: fixes a visible wrong thing on every phone visit to Settings |
| 2 | H's touch CSS block: 16px fields on coarse pointers, `overflow-x: clip` + `overscroll-behavior-y: contain`, touch-callout/user-select, opacity press with 70ms delay, `touchstart` listener; drop `scale(0.97)` | S | High: removes zoom-on-tap "resizes", makes taps feel native |
| 3 | Scroll memory in `router.tsx`: `scrollRestoration='manual'`, per-entry positions, restore-with-retry on Back, top on push; no page slide animations | S | High: most of the "transitions are a mess on iPhone" |
| 4 | `CLAUDE.md` router importing AGENTS.md; DEVELOPING.md with Module map, structure rules, recipes; DESIGN.md with principles, writing rules, checklist; USING.md per screen; CHANGELOG.md with Unreleased required by release | M | High: future agents stop duplicating text and inventing patterns |
| 5 | TanStack Query (keys + TOUCHES + useEdit), persisted cache for the phone; stop the 2s full-list replacement | M-L | High: no per-tab spinners, no polling re-render lag, instant reopen |
| 6 | One `/api/work` status with adaptive polling and one shell status line; named states for long jobs | M | High: background progress becomes legible |
| 7 | `Fold` primitive + Settings rebuilt as 5-6 folded groups with status lines, one load gate, urgent-opens | M | High: Settings goes from ~4,850px to about two screens, no pop-in |
| 8 | Reserve layout for late content: header buttons from first render, one notice slot, same-height skeletons | S | Medium: removes remaining shifts |
| 9 | `useStandalone` + tab bar docked vs floating; `no-cache` index.html/sw.js; reload once on `vite:preloadError` | S | Medium: home-screen app looks and updates right |
| 10 | Your style as remembered lines (Memory pattern) + a `questions.py` the stylist asks one at a time in the Today conversation | M | Medium-high: learning through conversation, not a textarea |
| 11 | phone-check + design-sweep scripts (four widths, long names, word counts) and a `/design-review` skill | M | Medium: keeps 1-8 from regressing |
| 12 | `ShowMore`, `HowItWorks`, `SaveStatus` primitives; word budget per screen | M | Medium: shorter, less duplicated screens |
| 13 | Safe Markdown subset for release notes from CHANGELOG (or a "What's new" link) | S | Low-medium |
| 14 | Split `app.py` into routers; Server-Timing + gzip middleware | M (split), S (middleware) | Medium for agents, low for the owner |
| 15 | Trial-on-a-database-copy before an update swaps in | M | Low now, high the first time a migration fails on real data |
