# Developing Closet

How the code is laid out, the rules that keep it that way, what deserves a test, and how to
add a screen, an endpoint, a migration or a background job. What makes a change look and
read like the rest of the app is in [DESIGN.md](DESIGN.md); what each screen does is in
[USING.md](USING.md); why things are the way they are is in [DECISIONS.md](DECISIONS.md).

## Running from source

Python 3.12 (what CI uses) and Node 22.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m closet              # the app, on 127.0.0.1

cd ../frontend
npm ci
npm run dev                   # the page alone; passes /api and /media to a backend on port 8765
npm run build                 # writes the page into backend/closet/web/, which the backend serves
```

`CLOSET_DATA_DIR` chooses the data folder, `CLOSET_PORT` the port (`backend/closet/config.py`
has every such name). Point `CLOSET_DATA_DIR` at a temporary folder when trying something, so
a real closet is never touched.

## Module map

### Backend (`backend/closet/`)

| Area | Modules |
| --- | --- |
| The program | `cli.py` (entry point: start, restore, backup, reset-passphrase), `config.py` (where things live, from the environment), `state.py` (program-wide settings in one JSON file; `DEFAULTS` lists every key), `instance.py` (one copy at a time, and its port), `window.py`, `window_mac.py` (Closet's own window), `tray.py`, `autostart.py`, `net.py` (outbound HTTPS in the packaged program), `updates.py` (checking for a release, fetching it, swapping it in). |
| The web API | `app.py`: `build_services` wires the settings, the database and every background worker (tests pass stand-ins here), and `create_app` defines every route. `gate.py` (login and size limits, before a body is read), `limits.py`, `auth.py` (one passphrase, sessions), `phone.py` (the Tailscale address for the phone, looked up in the background by `phone.Watch`). |
| Data | `db.py` (SQLite, and migrations by `PRAGMA user_version`), `migrations/NNNN_name.sql`, `items.py` (reading and changing items), `images.py` (a photo into the files the closet keeps), `backup.py`, `storage.py`, `demo.py` and `demo_data/` (the demo closet, a database of its own). |
| A photo becomes an item | `jobs.py` (the cutout queue, in the `jobs` table), `cutout.py`, `modelstore.py` (the background-removal models), `tagjobs.py` (the queue that asks Claude to describe an item, and `apply_answer`), `illustrations.py` (each item's drawing, kept up to date), `patjobs.py` (measuring a pattern), `progress.py` (how far the work on an item has got, in the page's words, and `GET /api/progress`), `palette.py`, `sources.py` (several items from one photo), `failures.py` (why a step failed, in words safe to show). |
| What an item is | `look.py` (its look, read from one place: the description the drawing was made from, with the owner's corrections over it, and its coarse shape as drawn; every screen and rule that tells how a garment looks reads it here), `kinds.py` (its kind, from the taxonomy), `vocab.py` (the small coarse vocabulary), `details.py` (the details the owner can set), `corrections.py` (picking a detail, saying what is wrong, undo), `history.py`, `review.py` (the review queue). |
| Shoes | `shoeviews.py` (photos sorted into views), `tracejobs.py` and `shoes.py` (traced from the side photo, for the closet picture), `shoedraw.py` (drawn by Claude for the figure, two shoes at a time). |
| Getting dressed | `outfits.py` (outfits by rule; pure), `outfit_rules.py` (the owner's rules, read from the taxonomy file), `today.py` (weather, wears and laundry fed to the engine), `weather.py`, `climate.py`, `day.py`, `daynote.py` (the day in the owner's words), `wears.py` (what was worn, and laundry), `worn.py` (outfits worn, and ratings), `taste.py` (what ratings teach). |
| Claude as stylist | `styling.py` (what the stylist is told and what is kept; pure), `stylejobs.py` (asked in the background, kept for the day; also what the style conversation shares with it: the routes in order, why a question failed, keeping and taking back a thing to remember), `styleahead.py` (asked before the first look), `styleprofile.py` (Your style: its lines with where each came from, and the text built from them), `stylechat.py` (the style conversation in Settings), `stylequestions.py` (the questions the stylist cannot infer, asked one at a time). |
| What to buy, what to pack | `gaps.py` (what's missing, by rule; pure), `life.py` (how the owner lives), `wishlist.py`, `shop.py` (finds for a wish, and prices), `wouldwork.py` (pure) and `wouldjobs.py` (Would this work?), `insights.py` (pure), `trips.py` (packing by rule; pure), `tripweather.py`, `savedtrips.py`. |
| Reaching Claude | `apikey.py` (the key, in the computer's keychain), `spend.py` (every call recorded, the monthly limit, estimates). The calls themselves are in `tagger/`. |

`tagger/` is everything that asks Claude. `routes.py` chooses the way in (the Claude plan
through `claude_cli.py`, or the API key); `schema.py` is the shape of a description and
`tagging.py` asks for one; `taxonomy.py` is the owner's taxonomy as far as a drawing shows it,
with `COVERAGE`; `surfaceform.py` is the cloth's surface on the same call. One module per
other question: `addsort.py` (what each photo on Add shows), `garments.py` (boxes round
several pieces), `landmarks.py`, `correcting.py` (the owner's sentence into changes),
`views.py` (which side of a shoe), `shoedrawing.py` (a shoe drawn), `dayread.py` (the day's
note), `stylist.py` (the outfits, and the style conversation), `shopping.py` (shops and prices).

`drawing/` draws. `templates.py` (the garment shapes), `illustrate.py` and `fills.py` (shape
plus fill), `item.py` (one item, as the app calls it), `stored.py` (a measured pattern as a
fill), `accessories.py`; the figure: `figure.py`, `fitting.py`, `worn.py`; shoes: `trace.py`,
`traced.py`, `sideshoe.py` (traced from the side), `frontshoe.py` (the template seen from the
front), `drawn.py`, `turned.py`, `photocheck.py` (drawn by Claude), with worked examples in
`shoe_examples/`.

`patterns/` measures a pattern from the item's own photo (`measure.py` picks the method;
`stripes.py`, `plaid.py`, `flatten.py`, `straighten.py`, `prints.py`, `masks.py`), and turns
Claude's description of the cloth into a fill (`surface.py`, `described.py`).

Outside the server: `backend/tests/` (one `test_<module>.py` per module; `conftest.py` has the
stand-ins, `e2e_backend.py` starts the app for the browser tests), `bench/` (the shoe tracing
bench, `closet_bench/trace_shoes.py`, whose `fills` and `illustrate` are the drawing's same
modules, re-exported for it; and `hardcases/`, the demo closet's open-licence photos; the
tests of the tagger and the drawing are in `backend/tests/`, `test_taxonomy.py` and
`test_templates_and_tagger.py`), `tools/` (developer scripts that draw sheets to look at, and
`whats_new.py`, which the release runs for its notes; never shipped), `packaging/` (the
PyInstaller build and its smoke test).

### Frontend (`frontend/`)

| Place | What's in it |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Start-up: first run, login, the "can't reach Closet" screens. |
| `src/Shell.tsx` | The frame: sidebar on a computer, tab bar on a phone (the four places and Add), the banners, which screen a route shows, and taking the new address in place of a moved one. |
| `src/places.ts` | The four places and Add: `placeOf` (which place a route belongs to, the link lit in the sidebar and the tab bar) and `movedTo` (where the addresses of merged places lead now). |
| `src/router.tsx` | The router, written by hand: `parseRoute` (every route; a moved address parses as the screen it moved to), `navigate`, `Link`, `itemPath`, the `WIDE` media query. |
| `src/store.tsx` | `ClosetProvider`: the open closet's query cache, `useApp()` (which closet, offline, the toast, switching closets, logging out), and the one poll of the work under way (`GET /api/progress`), which reads the lists and an item again when its work moves on. |
| `src/api.ts` | The one client, `api.*`, with a readable `ApiError`, and what a closing page may still send. `src/types.ts` has the response types, kept by hand. |
| `src/queryKeys.ts` | Every query key, and `TOUCHES`: which keys each kind of edit makes stale. Keys are made here and nowhere else. |
| `src/settings.ts` | The settings read, which also fills the model, updates, style and spend keys; the slow checks Settings makes beside it; what a settings save has already written; when to ask again for the phone's address. `src/savedCopy.ts` chooses between what was read and this device's copy. |
| `src/settingsLines.ts` | What the main Settings page says in one line each about Claude, Updates and the backups (`claudeLine`, `updatesLine`, `backupLine`), its groups in order (`mainGroups`), and what only the computer is offered (`computerOnly`), as pure functions with their test beside them. `src/here.ts` tells the computer from the phone (`deviceOf`). |
| `src/queryClient.ts` | The query cache's defaults (fresh for a minute, asked again on coming back after 10 seconds away). |
| `src/queries.ts` | The queries more than one screen reads (`useItems`, `useItemSummary`, `itemQuery`, `useVocab`, `useModel`, `useProgress`, `useItemProgress`, …), writing a saved item into the cache (`itemSaved`, `writeItem`, `dropItem`), saving (`useEdit`, `useItemEdit`) and `usePoll`. |
| `src/work.ts` | How often to ask for the work under way (`progressPoll`) and which items to read again when it moves on (`movedOn`), as pure functions. |
| `src/progress.ts` | An item's progress as the page shows it: which entry wins, the strip's dots and note, the tile's mark, the "Working on N items" line, a row's title on Add, the drawing's placeholder. The words come from the server (`progress.py`). |
| `src/screens/` | One file per screen, with its CSS beside it. Today: `Today`, `Worn` (the history, and `RecentOutfits` and the rating that Today shows), `Trips`. Closet: `Closet`, `ItemDetail`, `Review`. Add: `Add`, `Several`. Wardrobe: `Wardrobe` (the page: it reads the gaps, the wishlist and the insights, and lays them out), with its parts in `Missing` (worth buying, the wishlist, a wish's card), `Insights` (not worn, worn most, More numbers), `Shop` (finds for a wish) and `WouldWork`. Settings: `Settings` and `Advanced` (`/settings/advanced`, loaded only when opened, with `React.lazy` in `Shell.tsx`). `Setup`, `Login`, `Static` come before the shell. |
| `src/components/ui/` | The shared pieces every screen is built from, exported from `index.ts` and listed with the tokens in its `README.md`: `Button`, `Card` and `Section`, `Chips`, `EmptyState`, `Fold`, `HowItWorks`, `ItemThumb`, `Markdown` (a small safe part of Markdown, read by `src/markdown.ts`, drawn as text), `Notice`, `PageHeader`, `SaveStatus` (with `useSaveStatus`), `SegmentedControl`, `Sheet` (and `PHONE`, the phone-or-wider query), `ShowMore`, with `focus.ts` for keeping Tab inside what is open. Their tests are `ui.test.ts`, drawn to markup in Node. |
| `src/components/` | Pieces used by more than one screen or too big to sit in one: `FixDetails`, `ItemAbout` (the item page's summary line and notes box, with their test drawn by `react-dom/server`), `KindPicker`, `ItemPic`, `OutfitFigure`, `Progress` (the strip and the step's mark) and `WorkingLine`, the shoe pieces (`ShoePhotos`, `ShoeTrace`, `ShoeDrawn`), `LifeQuestions`, `WhereYouAre`, `PhoneAccess`, `Talk` (talking to Claude: the turns, the things to remember with Save and Undo, the box; on Today and in Settings), `StyleTalk` (the style conversation and its questions) and `StyleLines` (every line of Your style, to change, remove or add), `Updates` (the banner, the Settings line `UpdatesLine` and the Advanced part `UpdatesManage`), `Toggle` (the switch and `StatusLine`), `ModelBanner`, `RestoreNotice`, `RetakeButton`, `AddedItem`, `Icons`. |
| `src/<feature>.ts` | The logic and the words of a feature, with no React in it and its test beside it (`today.ts` and `today.test.ts`, `trips.ts`, `gaps.ts`, `insights.ts`, `worn.ts`, `wouldwork.ts`, `shop.ts`, `shoe.ts`, `spend.ts`, `updates.ts`, `corrections.ts`, `tagging.ts`, `drawing.ts`, `progress.ts`, `look.ts` (the item page's summary line and its one notes box), `style.ts` (Your style: its lines, where each came from, the conversation's polling), `figure.ts`, `kinds.ts`, `review.ts`, `several.ts`, `addsort.ts`, `added.ts`). `labels.ts` has the plain words for the server's vocabulary. |
| `src/uploadQueue.ts`, `src/uploads.ts`, `src/resize.ts` | Adding photos: resized in the browser, two at a time, each retried under one key. |
| `src/leave.ts`, `src/landing.ts`, `src/theme.ts`, `src/location.ts` | Saves still waiting when the page closes; which screen the app opens on; light or dark; asking the browser where you are. |
| `src/styles.css` | The tokens (`:root`) and the shared styles. `src/design.test.ts` fails on a size, radius, colour or motion value that is not a token. |
| `sw/sw.js`, `public/` | The service worker (written by hand; the build fills in the files to keep) and the manifest and icons. |
| `e2e/` | The browser tests: `server.ts` starts a backend on a fresh data folder, `fixtures.ts` logs in, `a11y.ts` runs axe. |
| `scripts/` | `phone-check.mjs` (below; it also counts each screen's words) and `make-icons.mjs`. |

## Structure rules

- **Routes are thin.** A route in `app.py` reads the request, calls the feature's module and
  returns what it gives back. The work is in the module named for the feature.
- **Rules are pure.** `outfits`, `gaps`, `trips`, `insights`, `wouldwork`, `styling` and `day`
  take plain data and return plain data: no database, no network, no clock (today is passed
  in). The module beside each one (`today.py`, `savedtrips.py`, `wouldjobs.py`) does the
  reading and writing. Keep new rules that way; it is why they are quick to test.
- **Only `tagger/` asks Claude,** always through `routes.py`, and every call is recorded by
  `spend.py` and held under the API key's monthly limit. Nothing about the demo closet is
  ever sent.
- **Slow work never holds a request.** Uploads return at once and the work is done by a
  worker started in `build_services`. Anything that has to survive a restart is kept in the
  database.
- **Two kinds of settings.** What belongs to the program (the passphrase, the place, the
  backup folder, how Claude is reached) is a key in `state.py`'s `DEFAULTS`. What belongs to
  a closet is in that closet's database, so the real and the demo closet keep theirs apart
  and a backup takes it along.
- **The taxonomy file is the source of truth** for what a garment can be
  (`docs/menswear-taxonomy.json`); `tagger/taxonomy.py` stays equal to it, and a test checks.
- **OpenCV is imported only inside the code that reads a photo,** so drawing an item needs
  none of it.
- **On the page: words and logic out of the screen.** A screen file lays things out. What it
  says and how it decides live in `src/<feature>.ts`, tested there. Sizes, colours, radii and
  motion come from the tokens; a shared piece comes from `components/ui/` before a new one is
  written.
- **One of each.** Before adding a helper, a status word or a sentence, search for the one
  that exists. The assessment found the same progress words in four files and the same fact
  stored three ways; a new copy is a bug even when it works.

## What deserves a test, and where

Pick the lowest layer that can show the behaviour, and test it once.

1. **Rules and calculations** (taxonomy, outfits, gaps, trips, spend, geometry): unit tests
   on the module, as a table of cases, with no HTTP and no demo closet. A handful of cases
   per rule and the edge that broke. Under a tenth of a second each.
2. **Each endpoint**: through `TestClient`, one success and one test for each distinct
   refusal. Don't run the rule's cases again through the API. Give the test a tiny closet,
   not the demo, unless the demo is what is being tested.
3. **Words and decisions on the page**: a unit test beside the `src/<feature>.ts` file
   (vitest).
4. **The browser** (Playwright, `frontend/e2e/`): one test for each thing the owner does on a
   screen, or each state they can see, asserting what they see. Never a backend rule again.
   No fixed sleeps. A screenshot goes to `testInfo.outputPath()`, never into `docs/`.
5. **A bug fix**: a test at the lowest layer that reproduces the bug, written first.
6. **Anything over a second**: make the input smaller, or mark it `slow` and say so in the
   pull request. An image test uses the smallest image that shows the case. See *Slow
   tests* below for which tests may be marked and where they run.
7. **Migrations**: `test_db.py` already brings every version up to date. Add a test only
   when the migration changes data that is already there.
8. **Design rules**: once, as a rule over every file, as `design.test.ts` does. Not per
   screen.
9. **Code that talks to the computer** (keychain, tray, window, start at login): a stand-in
   at the edge only, and assert the outcome (Quit stopped the server), not that the call
   returned.

A new screen, sheet or sentence is also looked at: run the phone check (below) and open the
pictures.

### Slow tests

Some backend tests carry the `slow` marker: pure image tests that take seconds each and do
not depend on the computer they run on. Today that is all of `test_patterns.py` (measuring
stripes, plaid and prints), the image tests in `test_trace.py` that take over a second
(shoe tracing; a few cheap ones stay unmarked so every pull request still traces a shoe),
`test_shoedrawing_turned.py` (shoes drawn by Claude), and the few tests in `test_turned.py`
and `test_surface.py` that take seconds. A whole file is marked with
`pytestmark = pytest.mark.slow` at the top; a single test with `@pytest.mark.slow`.

A test gets the marker only when it is an image algorithm with no platform code in it, it
still takes over a second after its input has been made as small as the case allows, and
the code it covers has its path in the `slow` job of `.github/workflows/ci.yml`. A route
or rule test that is slow because it builds the demo closet is made faster instead, not
marked. The marker never skips anything by itself:

```bash
cd backend
python -m pytest -q                       # everything, slow tests included: the check before a pull request
python -m pytest -q -n auto -m "not slow" # the quick set, while you work
python -m pytest -q -n auto -m slow       # only the slow ones
```

Where they run in CI:

- **On every pull request and push to `main`**, the Linux and Windows backend jobs run
  `-m "not slow"`.
- **When a pull request touches the code they cover** (`closet/patterns/`,
  `closet/drawing/trace.py`, `traced.py`, `drawn.py`, `turned.py`,
  `closet/tagger/shoedrawing.py`, the made-up shoe photos in `tests/shoe_photos.py`, a file
  with slow tests in it, the requirements files, `pyproject.toml` or `ci.yml`), the `slow`
  job runs `-m slow` on Linux. The required check
  waits for it; when nothing it covers changed, it passes without running them. On a push
  to `main` it compares with the commit before only.
- **On the night after `main` changed** (and when started by hand), the `nightly` workflow
  runs every test on Linux and Windows; a night with no new merge runs nothing. A failure there reaches the owner as GitHub's usual email.

If a slow test covers new code, add that code's path to the pattern in the `slow` job.

## The phone check

```bash
cd frontend && npm run build && npm run phone-check      # or: node scripts/phone-check.mjs <out-dir>
```

It starts a backend of its own on a temporary data folder (the same stand-ins as the browser
tests, with a copy of the demo closet as the owner's closet), gives a few things long names,
opens every screen at 375, 393, 402, 430 and 440px wide, light and once dark, and takes a
full-page picture of each into `frontend/phone-shots/`, then opens the sheets of Settings → Your
style (the conversation, every line) and pictures those. It fails when a screen is wider than
the phone or throws an error. `CLOSET_PYTHON` names the Python with the backend's
requirements, as for the browser tests. A new screen is added to its list of routes.

It also prints how much each screen asks you to read, at 393px in light: the words on the
page, the words in the first phone screen (above the tab bar) and the page's height, and
lists as warnings the screens over the budget in [DESIGN.md](DESIGN.md) (about 150 words in
the first screen, 350 on the page). It does not fail on them yet. `PHONE_CHECK_SIZES=393`
pictures only that width, for a quick look while working.

It is run by hand, before a pull request that changes anything visible. CI does not run it.

## Adding a screen

Before adding one, read the Screens section of [DESIGN.md](DESIGN.md): the app has four
places and Add, so a new card, fold or sheet on an existing screen is the usual answer, and a
new screen is a page one level down inside one of the places, never a fifth tab without a
decision in DECISIONS.

1. The route in `parseRoute` (`src/router.tsx`), under its place's address (`/today/…`,
   `/wardrobe/…`), and its place in `placeOf` (`src/places.ts`), with a case in
   `places.test.ts`. If it replaces an address, that address goes in `movedTo` so bookmarks
   still land.
2. `src/screens/<Name>.tsx`, built from `components/ui/` (see its `README.md`): a `PageHeader`
   with `back={{ to: '/<place>', label: '<Place>' }}`, then `Section`s; `ShowMore`, `Fold`
   and `HowItWorks` keep it inside the word budget. Its words and decisions in
   `src/<name>.ts` with a test. Its data read and saved as *Reading and saving data* says,
   sharing the queries the place's page already reads.
3. The branch in `Shell.tsx` that shows it, and the link on its place's page that reaches it.
4. Its route in `scripts/phone-check.mjs`.
5. One browser test for what the owner does there, and the screen added to the lists in
   `e2e/17-accessibility.spec.ts`.
6. A paragraph in `docs/USING.md`, a line in `CHANGELOG.md` under Unreleased, and the
   owner's steps in `README.md` if there are any.

## Reading and saving data

The page reads through TanStack Query. Why, and the numbers: [DECISIONS.md](DECISIONS.md), "Data loading".

- **Keys.** Every key is made by a function in `src/queryKeys.ts`, whose first element is its own name
  (`queryKeys.trip(id)` is `['trip', id]`). A screen never writes a key by hand. A new read gets its key there
  first, and the edits that change it list its name in `TOUCHES`.
- **Reading.** `useQuery({ queryKey: queryKeys.x(), queryFn: api.x })` in the screen; a query more than one screen
  reads goes in `src/queries.ts` as an options function or a hook. Gate the screen once on its main query
  (`if (!data) return <Loading />`), then draw everything together. What was read stays fresh for a minute, so
  coming back to the screen shows it at once. Data that changes behind the owner's back (an item while work runs)
  can ask for `staleTime: 0` or `refetchOnMount: 'always'`: what is kept still shows first.
- **The open closet.** `useApp()` gives the closet (real or demo), offline, the toast and the actions on the closet
  as a whole. Each closet has its own cache, so no key needs the closet in it.
- **Saving.** A save names its kind of edit, and what that kind touches is made stale after it succeeds:
  `const save = useEdit('trip'); await save(() => api.patchTrip(id, changes))`. A save that answers with the item
  uses `useItemEdit()` (or `itemSaved(qc, item)` when the call is already made): the item is written into the
  lists and its own entry, and the rest is made stale. Put an answer you already have in with
  `qc.setQueryData(queryKeys.x(), answer)` rather than asking again. The screen still says "Saved" or the error.
- **Polling while work runs.** Decide how often as a pure function of the data, in `src/<feature>.ts` with a test
  (as `src/work.ts` does). When only one screen watches the query, give it
  `refetchInterval: (q) => (running(q.state.data) ? 2000 : false)`. When several screens show the same data, poll
  once, in one place (the work under way, `GET /api/progress`, is polled in `ClosetProvider`, which reads the
  closet's list and an item again when its work moves on, so a screen never polls items itself), with the query's
  own `refetchInterval` or `usePoll(ms, tick)`. A tick asks with `{ cancelRefetch: false }`, so a slow answer is not called off.
- **Offline.** A query keeps what it had when a read fails; `useApp().offline` says Closet cannot be reached.
  Coming back online asks again for everything on screen.

Moving a screen off `useEffect`, for example:

```tsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { useEdit } from '../queries';
import { queryKeys } from '../queryKeys';
import { useApp } from '../store';

export function TripsScreen() {
  const { offline, toast } = useApp();
  const trips = useQuery({ queryKey: queryKeys.trips(), queryFn: api.trips, enabled: !offline });
  const save = useEdit('trip');
  if (!trips.data) return trips.error ? <p role="alert">{trips.error.message}</p> : <Loading />;
  const remove = (id: string) => save(() => api.removeTrip(id)).then(() => toast('Removed'), (e: Error) => toast(e.message, 'error'));
  // ...lay out trips.data
}
```

## Adding an endpoint

1. The work, as a function in the feature's module, tested there.
2. The route in `create_app` (`app.py`), beside the feature's other routes, with
   `dependencies=protected` unless it has to answer before login. The request body is a
   Pydantic model; what comes back is a plain dict. Make the route a plain `def` (FastAPI runs
   it on a worker thread). An `async def` route runs on the one event loop, so it must not
   draw, decode a photo, start a command, ask Claude or write to the closet itself: it awaits
   the body, then hands that work to `run_in_threadpool` (the `conn` from `conn_dep` may be
   used there). Anything Settings shows that is quick to read goes into `settings_payload`
   as well.
3. If it takes an upload, its limit in `limits.py`.
4. The call in `src/api.ts` and its type in `src/types.ts`; for a read, its key in `src/queryKeys.ts`, and for a
   save, its kind of edit in `TOUCHES` (see *Reading and saving data*).
5. One success and one test per refusal, through `TestClient`.
6. Its entry in `docs/API.md`.

## Adding a migration

Add `backend/closet/migrations/NNNN_what_it_does.sql` with the next free number. `db.migrate`
runs each one above the database's `user_version`, in order, each in one transaction, after
taking a copy of the database. Never edit a migration that has merged; add another. If `main`
takes your number before your pull request merges, renumber yours to the next free one and
say so. There is no `0002`. The demo closet is a database too and is migrated the same way.

## Adding background work

1. Decide where its state lives. A step every item goes through belongs in the `jobs` table
   (`jobs.py` for cutouts, `tagjobs.py` for descriptions); a step only some items have keeps
   a state column on the item, as patterns, traces and shoe drawings do.
2. A worker with `start`, `wake` and `stop`, added to `Services` in `app.py`, which takes a
   stand-in for whatever is slow or outside (the model, Claude) so tests never wait for it.
3. What was interrupted is picked up at the next start (`requeue_interrupted`).
4. A failure is stored through `failures.py`, so what is shown and logged holds no key and
   no path.
5. What the page says about it is one phrase in one place: `backend/closet/progress.py`. Add its
   states to `progress.of` (which step it belongs to, and whether it is working, next in line or
   waiting for something named), its words beside the others there, and its columns to
   `_UNDER_WAY`, with a case in `tests/test_progress.py`. Don't write status words in a screen.
6. The page then follows it by itself: `GET /api/progress` lists the item while its work runs,
   the closet's provider polls that, and the item and the lists are read again when its stage
   changes. An edit that starts the work should name `progress` in `TOUCHES`.

## Releasing

The owner starts a release (Actions, **release**); nobody makes a tag by hand, and agents do
not start it. `CHANGELOG.md` under `## Unreleased` is where what changed is written as it
merges.

The release's notes start with a `## What's new` section taken from the changelog by
`tools/whats_new.py`, at the commit being released: the `## <version>` section if the
changelog has one with something in it, otherwise `## Unreleased`. When both are empty the
section is left out, and nothing about the changelog can stop a release. Settings > Updates
shows only that section (`_notes` in `backend/closet/updates.py`), behind "What's new in
<version>"; a release without it shows no notes.

`main` takes no direct pushes, so the release workflow does not rewrite the changelog. After
a release, the next pull request that touches `CHANGELOG.md` moves the released lines from
`## Unreleased` under a new `## <version>` heading, so Unreleased starts empty again.
