# Settings, phone access and Updates: UX and code audit

Repo: `/home/user/daily-clother` (read-only; nothing in it was changed). Paths below are relative to it.

## How it was measured

- Backend deps were installed into a scratch venv. The frontend was built with `vite build --outDir <scratchpad>/web`, so `backend/closet/web` was not touched. The server ran from `<scratchpad>/serve.py` (`build_services(web_dir=...)`, a fresh data dir in the scratchpad, `auto_download_model=False`) with the demo closet switched on.
- Outbound traffic was blocked: HTTPS_PROXY/HTTP_PROXY pointed at a dead port, so the update check and Open-Meteo failed, which is expected. A fake `tailscale` script on PATH reported "running" and a share of `https://closet-pc.example-tailnet.ts.net` pointing at Closet, so the QR path rendered.
- Playwright (the pre-installed copy, `chromium.launch()` with no options) loaded `/settings` at 390x844 (isMobile, DPR 2) and 1440x900, full page. It recorded every `/api/*` request, the page height every 100 ms, and CLS.
- Screenshots are in `shots-settings/`:
  - `settings-phone.png`, `settings-desktop.png`, plus `-partN.png` crops and `-first-screen.png`
  - `slow-tailscale/settings-phone-cold-600ms.png`: the page before `/api/settings` has arrived
  - `updates-with-release-phone.png`: the Updates card with a release available (the `/api/updates` response was mocked using the real release-body template)
  - raw numbers: `measure.json`, `slow-tailscale/measure.json`

### Numbers

| | Phone 390 | Desktop 1440 |
|---|---|---|
| Full-page height | **6,120 px** (about 7.3 screens); 6,858 px with an update available | 5,011 px |
| Top-level cards | 9: Your closet, Where you are, How you live, Look, Your style, Describing clothes, Updates, Phone access, Advanced (plus Log out and Quit) | same |
| Sub-sections | 6: Background removal, Laundry, Before it needs washing, Backups, Storage, Background-removal model | same |
| Controls (demo closet, no API key) | 21 buttons, 4 text inputs, 1 textarea, 4 switches, 4 radios, 6 selects, 3 disclosures, 2 links | same |
| Words on the page | 1,105 | 1,105 |
| API requests on load | 16 (`/api/tagging` twice, `/api/model` twice, `/api/review` twice) | 16 |
| CLS, fast Tailscale | 0 (the shifts happen below the fold) | **0.37** ("poor" starts at 0.25) |
| CLS, Tailscale at 1 s per CLI call | **0.42** | 0.32 |

Height over time on the phone:
- Fast Tailscale: 5,941 px at 109 ms, 6,036 px at 209 ms, 6,120 px at 510 ms.
- Slow Tailscale: **3,391 px at 101 ms → 3,475 px at 402 ms → 6,036 px at 2,105 ms → 6,120 px at 2,306 ms.** Half the page appears two seconds late. `/api/settings` took 2,071 ms, and `/api/weather`, `/api/tagging/spend` and the second `/api/tagging` only start after it returns.

---

## 1. Settings is a long, unordered list

**Cause.** `frontend/src/screens/Settings.tsx:150-226` renders every feature as a card, in the order the features were added. "Your closet" (`:151-176`) is a grab-bag holding seven unrelated things: demo, autostart, the model, laundry, re-wear, backups and storage. There is no hierarchy and no "set once / change often" split. The only Advanced area (`:208-219`) holds just the model URL, the data path and the version.

### Inventory

| # | Section / control | Where | Backend | What it does | Would a user change it? | Verdict |
|---|---|---|---|---|---|---|
| 1 | Show the demo closet (switch) | `:152-158` | `POST /api/profile` | Swaps to a sample closet | Rarely: try once, and while showing someone | Advanced. A "Demo closet · Leave" ribbon already exists at the top. Its hint says "About 30", but the README says about 40 |
| 2 | Start Closet when I log in (switch) | `:159-170` | `PUT /api/settings {autostart}`, `autostart.py` | Login item on the PC | Once | **Automatic** (turn on at first run) or Advanced. Hide it on the phone: it describes the computer |
| 3 | Background removal: state + Download button, second model + button | `:171`, `ModelSection :232-272` | `GET /api/model`, `POST /api/model/download` | Downloads the ONNX cutout models | Never, since they download on start (`app.py:114-128`, `auto_download_model=True` by default, `config.py:22`) | **Automatic.** Remove it from Settings. Keep only the error banner (`ModelBanner`). See #3 |
| 4 | Laundry: auto switch | `:338-340` | `PUT /api/settings {laundry.auto}` | Worn clothes go to the laundry | Once | Keep, in a "Laundry" group |
| 5 | Laundry day (select) | `:343-351` | same `laundry.day` | Day everything becomes clean | Occasionally | Keep |
| 6 | Before it needs washing: 5 selects | `RewearSection :359-396` | `PUT /api/settings {rewear}` | Wears before a wash, per kind | Rarely; the defaults are fine | Collapse under Laundry as "Wears between washes" (a disclosure) |
| 7 | Backups: folder text input, Save, last good backup, Back up now | `BackupSection :398-451` | `PUT /api/settings {backup_folder}`, `POST /api/backup`; `backup.py` Scheduler (daily) | Daily copy to a folder on the PC | Once to set up | Move down into "Your data". On the phone, show the status only (a path typed on the phone is the PC's path) |
| 8 | Storage: total + 6 rows + free space | `StorageSection :453-517` | `GET /api/storage` (walks folders on every request) | Disk usage | Never acted on | Advanced, as one line: "2.7 MB, 62 GB free" |
| 9 | Where you are: privacy paragraph, Using X, weather line, search + Search, Use my location, Back to New York | `components/WhereYouAre.tsx` | `PUT /api/settings {place}`, `GET /api/places`, `GET /api/weather` (outside service) | Home place for the weather | Occasionally (a move) | Keep, collapsed to "Weather for **New York** · Change". The privacy text goes behind the Change step |
| 10 | Plan a trip link | `:180` | — | Navigation | — | Delete from Settings (Trips is linked from Today) |
| 11 | How you live: button opening LifeQuestions (situations, work dress, vacation, **style words**) | `:182-190`, `LifeQuestions.tsx` | `PUT /api/settings {life}` | Feeds What's missing | Occasionally | Keep, as a single row. Drop its "My style in a few words" field (`LifeQuestions.tsx:96-101`): a second style input that its own hint says is "not interpreted or used" |
| 12 | Look: Light / Dark / Device | `LookSection :34-42` | localStorage | Theme | Rarely | Keep, as a compact row at the top or under "This device" |
| 13 | Your style: Let Claude choose my outfits (switch) | `:85-97` | `PUT /api/settings {stylist_on}` | Turns off the LLM stylist | Rarely (an escape hatch) | Keep the switch, moved into a "Claude" group |
| 14 | Your style: textarea (4000), counter, examples, Save, Back to starting text | `:100-118` | `GET/PUT /api/style/profile`, `styleprofile.py` | Free-text style profile read by the stylist | Learned through chat (see #5) | Becomes a read-only summary with "Edit" in a sheet |
| 15 | Describing clothes: route list (plan, API key), status lines, Check again | `TaggingSection :534-650` | `GET /api/tagging` (runs `claude auth status`) | Shows how Claude is reached | Only when it breaks | One status line; details in Advanced. See #6 |
| 16 | API key box: paste / replace / remove | `ApiKeyBox :656-739` | `PUT/DELETE /api/settings/api-key` | Keychain key | Once | Advanced |
| 17 | Which to use: 4 radios | `RouteOrderChoice :743-776` | `PUT /api/settings {tagging_route_order}` | Route order | Almost never | Advanced; reduce to 2 choices or remove |
| 18 | Allow the API key (switch) + monthly limit + spend history + details (tokens, model, per-photo cost) | `ApiKeySpend :778-901` | `GET /api/tagging/spend`, `PUT /api/settings` | Billing guard | Once | Advanced, except a one-line "This month: $x of $y" when the key is in use |
| 19 | "No items are waiting to be described" | `:641-644` | `pending_tags` | Queue count | — | Delete. Show it only when > 0, and on the closet, not in Settings |
| 20 | Updates: version, last checked, error, last install, mode (3 segments) + hint, Check now, available line, notes, release page, Install now, explanation, "can't replace itself" | `components/Updates.tsx:68-166` | `GET/PUT /api/updates`, `POST /api/updates/check|install` | Self-update | The mode once; Install when offered | One line + Install. Mode goes to Advanced. See #7 |
| 21 | Phone access: instructions, QR, address, stop command / setup command | `:202-206`, `components/PhoneAccess.tsx` | `settings.phone` from `phone.info()` (runs `tailscale` twice) | Pair the iPhone | Once | Hide it when the client is already remote. On the PC, collapse it after the share works. See #8 |
| 22 | Advanced: model download URL + Save address + Use default, manual file paths for both models, data folder, version | `ModelAddress :275-315`, `:212-217` | `PUT /api/model/url` | Offline model install | Practically never | Keep in Advanced; the model URL can go into a "Troubleshooting" sub-part |
| 23 | Log out | `:223-224` | `POST /api/logout` | — | Rarely | Keep at the bottom |
| 24 | Quit Closet (confirm) | `QuitButton :916-929` | `POST /api/quit` | Stops the server | Rarely; **dangerous from the phone** (it cannot be restarted remotely) | Hide on the phone / remote clients, or move it into Advanced |

**Experiment leftovers / dead weight:**
- the route-order radios (4 permutations for a single user);
- the token/model "Details" table (`:870-887`);
- the duplicated monthly history: it is listed twice, in `:857-866` and again in `:879-884`;
- `pending_tags` shown even at 0;
- the second "style words" field in LifeQuestions;
- the manual-download second-model paths;
- the Storage breakdown.

**Settings payload fields the page never uses:** `heic_supported`, `port`, `pending_cutouts` and `profile` are in `settings_payload` (`backend/closet/app.py:1374-1393`). `life_prompt_dismissed` is used elsewhere.

### Proposed fix: new outline

Main page, about 1.5 phone screens:

1. **Your style**: a read-only 3-line summary of what Closet knows, then "Talk to Claude about your style" (opens chat) · "Edit the text". The switch "Let Claude choose my outfits" sits underneath.
2. **Everyday**
   - Weather for *New York* · Change
   - How you live · Edit answers
   - Laundry: switch + day; "Wears between washes" in a disclosure
3. **Claude**: one status line ("Using your Claude plan · working", or a red line with a single action). "Manage" goes to Advanced.
4. **Updates**: "Closet 0.4.0 · up to date" or "0.4.1 is ready · What's new · Install".
5. **Phone**: on the PC only, and only until it works. After that, one line: "Shared at https://… · Show QR".
6. **This device**: Look (Light/Dark/Auto).
7. **Your data**: "Backed up daily to D:\… · last 3 h ago" (or "Choose a backup folder", PC only).
8. Log out (and Quit Closet, on the PC only).

**Advanced** (a separate route `/settings/advanced`, not a `<details>`): Demo closet; Start at login; API key, route order, monthly limit and spending; update mode; storage; backup folder edit + Back up now; model download address and manual files; data folder; version; Quit.

**Delete:** the Background removal card, the Plan-a-trip link, "No items are waiting", the token details table, the duplicated history list, the LifeQuestions style-words field, and the "can't replace itself" paragraph in dev builds.

**Automatic:** the model download (already automatic), autostart (on at first run, with a tray toggle), and the backup folder (default to a `Closet backups` folder in iCloud Drive or OneDrive when present, otherwise prompt once).

**Effort:** M for the regroup and the Advanced route. The e2e suite has 21 specs touching settings, so expect test churn: M-L.

---

## 2. Sections pop in after page load

**Cause.** The page makes **7 independent requests of its own** (plus the shell's), and each card renders whatever it has as soon as its own request lands:

| Request | Triggered at | Gates |
|---|---|---|
| `GET /api/settings` | `Settings.tsx:129-142` | autostart toggle, Laundry, Re-wear, Backups, Phone access, the "Let Claude choose" switch, the API-key box, spend, LifeQuestions button state, the WhereYouAre "Using" line, the data path |
| `GET /api/model` (twice: `Settings.tsx:141` and `store.tsx:105`) | | Background removal |
| `GET /api/storage` | `StorageSection :458-470` | Storage |
| `GET /api/style/profile` | `StyleSection :55-65` | Your style textarea |
| `GET /api/tagging` (**twice**) | `TaggingSection :541-553` | route status |
| `GET /api/tagging/spend` | `ApiKeySpend :786-796` | spend |
| `GET /api/weather` | `WhereYouAre.tsx:140-151` | weather line |
| `GET /api/updates` | store, `Updates.tsx:11-18` | Updates |

### Why it shifts so much

- **`/api/settings` is the slow one, and most of the page waits for it.** `settings_payload` (`backend/closet/app.py:1374-1393`) calls `sv.phone_info()` (`app.py:173-178`). That runs `tailscale status --json` and then `tailscale serve status --json` **serially** (`backend/closet/phone.py:105-136`, each with a 4 s timeout at `phone.py:101`), cached for only 30 s. It also reads the keychain (`apikey.info()` → `_saved()`, which on a Mac shells out to `security`) and calls `autostart.is_enabled()`. With the Tailscale CLI at 1 s per call, `/api/settings` took 2,071 ms and the page grew from 3,475 to 6,120 px at 2.1 s (CLS 0.42).
  - Worst case: a hung tailscaled means 8 s of half a page.
  - Every `PUT /api/settings`, including flipping the laundry switch, also returns `settings_payload`, so it pays the keychain and autostart cost too (Tailscale is cached for 30 s).
- **Sub-sections are inserted above content that has already rendered.** Backups (`:174`) is inserted *above* Storage (`:175`), Laundry and Re-wear *above* both. Storage, Where you are and everything below jump down by about 2,500 px (compare `slow-tailscale/settings-phone-cold-600ms.png` with `settings-phone.png`).
- **`/api/tagging` fires twice.** Its effect depends on `keySource` and `chosenOrder` (`:538-539`, `:553`), which are `null` until settings arrive and then change. The second run also does `setStatus(null)` (`:544`), so the route list flashes back to "Checking…" and re-runs `claude auth status`.
- **`/api/tagging/spend` re-fetches on every settings object change:** its deps are `[offline, settings]` (`:796`).
- **Loading placeholders are one-line hints** ("Loading your style…", "Adding up…", "Finding out about new versions…", "Looking up today's weather…"). They are replaced by blocks hundreds of pixels tall (the textarea, the storage list, the Updates card). Nothing reserves height.

### Fix

1. Make `/api/settings` fast and complete:
   - Move `phone.info()` out of the payload into its own `GET /api/phone`, rendered last and only on the PC (see #8).
   - Or compute it in a background thread on start and refresh it every few minutes, returning the cached value immediately; never block the request on a subprocess.
   - Run the two Tailscale calls concurrently anyway.
   - Cache `apikey.info()` (invalidate on PUT/DELETE of the key) and `autostart.is_enabled()`.
2. Fold the cheap reads into the same response: style profile summary, model state, update status (already in memory) and the spend summary. Then the page renders in one pass. Keep the genuinely slow probes (`claude auth status`, the storage walk, weather) as separate requests whose result is a single line in a fixed-height row.
3. Render the page skeleton from a single "ready" flag: hold the whole list (or show a skeleton with the final row heights) until `/api/settings` is in. Never insert a sub-section above already-rendered content.
4. Fix the TaggingSection effect: keep the previous status while refetching, and depend on a stable key computed once settings exist. Fix the ApiKeySpend deps (`settings.tagging_api_cap_usd`, `tagging_api_enabled`). Drop the duplicate `refreshModel()` in Settings, because the store already polls it.
5. After the regroup most of these cards are gone from the main page, and the shift problem mostly disappears with them.

**Effort:** S for the effect fixes and duplicate requests; M for the payload consolidation and moving Tailscale off the request path.

---

## 3. "Background removal" looks random

**What it controls.** Downloading two ONNX segmentation models (the first about 170 MB, plus a second one "which fixes cutouts the first one gets wrong"). Cutouts can't be made without them (`ModelBanner.tsx:10-29`, `Settings.tsx:232-272`). There are no options in it: only a status line and a Download / Try again button.

**Is it already automatic?** Yes. `Services.start()` downloads both models at program start (`backend/closet/app.py:114-115, 127-128`), unless the developer env var `CLOSET_NO_AUTO_DOWNLOAD` is set (`config.py:69`). Failures already surface on the closet through `ModelBanner` (with its own retry button). The Settings card is redundant once the model is ready, which is the normal state. Its manual-address twin lives in Advanced (`:275-315`).

**Fix:**
- Delete `ModelSection` from the main page.
- Keep `ModelBanner` for missing / failed / downloading. Add automatic retry with backoff in `ModelStore` (for example after 1 min, 10 min and 1 h) so a failed download heals without a button.
- Keep the address/paths under Advanced → Troubleshooting.
- Show "Background model 170 MB" only as a Storage row in Advanced.

**Effort:** S.

---

## 4. Backups at the top, Storage prominent

**Cause.** Both are children of the first card, "Your closet" (`Settings.tsx:174-175`), so they sit near the top. Storage renders before settings load (it has its own fetch), so for a moment it is the second thing on screen (`slow-tailscale/settings-phone-cold-600ms.png`).

**What Backups is.** It is **local**, not cloud.
- `backend/closet/backup.py`: dated SQLite snapshots plus a content-addressed image store, written to a folder **on the computer** that you type in. It can be a USB drive, or a folder that iCloud Drive, OneDrive or Dropbox syncs, which is the only "cloud" part, and that is up to you.
- The `Scheduler` (`backup.py:592-620`) backs up once a day while Closet runs, keeping 14 snapshots (`KEEP_SNAPSHOTS = 14`, `:39`). Nothing runs until a folder is set.
- Separately, Closet keeps pre-update copies in `<data>/backups` (the "Backups on this computer" row in Storage; `updates.KEEP_SNAPSHOTS = 3`).
- The demo closet is never backed up.
- The folder is a free-text path validated on the server (`app.py` `put_settings`: "is not a folder on this computer"). Typing it on the phone is awkward, and the placeholder is a Windows path, `D:\Closet backups`, even on a Mac (`Settings.tsx:436`).

**What Storage shows.** `GET /api/storage` (`app.py:1555-1558`, `storage.usage`) walks the folders on every visit. It shows the total, Photos, Cutouts, Thumbnails, local Backups, the model and "Everything else", plus free disk space and the item count (`Settings.tsx:483-507`). Nothing in it can be acted on.

**Fix:**
- Main page, under "Your data" near the bottom: "Backed up every day to *iCloud Drive/Closet backups* · last good backup 3 h ago" (red if the last one failed), plus a "Back up now" link.
- If no folder is set: one sentence and a "Choose folder" button. On the PC, use a native folder picker through pywebview's `create_file_dialog(FOLDER_DIALOG)` when running in Closet's own window. On the phone: "Set this on your computer."
- Optionally, auto-propose the iCloud Drive or OneDrive folder when it exists.
- Storage: one line in Advanced ("Closet uses 2.7 MB · 62 GB free"), with the breakdown in a disclosure.

**Effort:** S to move and condense; M with the folder picker and auto-default.

---

## 5. "Your style" is a form, not a conversation

**What exists:**
- **There is a chat.** It is on **Today**: `Conversation` (`frontend/src/screens/Today.tsx:881-...`, rendered at `:848`, sending via `say()` at `:276`), backed by `stylejobs.py` (docstring `:24-46`). You write about the day's outfits ("too dressy", "why not the navy blazer?"). Claude answers, may re-choose, and **may offer up to two things to remember**.
- **Remembering already writes the style profile.** `stylejobs.settle()` (`stylejobs.py:460-...`) appends a "- line" to the profile through `styleprofile.save(conn, ..., "claude")`, or appends to a piece's "How I wear it" note. You must tap Save on each offer (`POST /api/style/answers/{id}/remember`, `app.py`).
- **Storage.** A versioned `style_profile` table in the closet DB (`styleprofile.py`: every save adds a row, with `source` of `owner` or `claude`; max 4000 characters). The starting text is a two-line default (`styling.py:43-44`).
- **Use.** `styleprofile.text_for_stylist()` goes into `styling.brief(profile=...)`, the prompt for the daily outfit choice. It "wins over the general menswear guide". The demo never asks Claude.
- **Limits of the chat:**
  - It only exists when Claude's outfits are on Today, so not in the demo, not with the stylist off, and not offline.
  - It is scoped to *today's outfits*.
  - The day's messages reset each day; only saved "remember" lines persist.
  - There is no place to just talk about your style, and no onboarding interview.
  - Settings shows the profile as a raw editable textarea, with no sign of which lines came from the chat.
- **A second, unused "style" input** exists in How you live (`LifeQuestions.tsx:96-101`, `life.py` `style_words`), labelled "not interpreted or used".

**What it would take to make chat primary:**
1. **A style conversation entry point** that is not tied to today's outfits. Two options:
   - (a) Reuse the Today conversation with a "style" mode, which needs no outfits on the page.
   - (b) Add a small `/style` chat screen. It needs a backend job like `stylejobs` but with a "profile interview" brief: ask 5-6 questions (climate, work dress, colours, no-gos, fit), then propose profile lines with the same remember/settle flow.

   This reuses `settle` and `styleprofile.save(..., "claude")`. Backend M, frontend M.
2. **Settings → Your style becomes a read-only summary:**
   - the profile's lines (or the first 3 and "+N more"), each marked "you said on Nov 12" using `style_profile.source` and `created_at`;
   - a "Talk about your style" button and a small "Edit text" link that opens the existing textarea in a sheet;
   - the "Let Claude choose my outfits" switch stays.

   `GET /api/style/profile` would need to return lines with their source, so the history rows need splitting into line-level provenance or a diff. S-M.
3. Drop `style_words` from LifeQuestions, or migrate it into the profile once.
4. Optionally, make "remember" offers easier to accept (for example "Save all").

**Effort:** M (summary plus chat entry point reusing Today) to L (a dedicated interview chat).

---

## 6. The API key / Claude plan section is enormous

**What's in it.** "Describing clothes", `Settings.tsx:534-901`, about 470 lines of TSX. In the screenshots it is about 1,850 px on the phone (`settings-phone-part3/4.png`), even with **no key and the plan working**:
- an intro sentence;
- an ordered list of two routes (plan, API key), each with a name, a status dot and a hint;
- the API key box: status, paste field, explanation with a console link, Replace / Remove with confirm, the "no keychain" text;
- "Closet will try your Claude plan first" and up to three error variants with install links;
- Check again;
- "No items are waiting to be described";
- **Which to use**: 4 radios, two disabled with "(save an API key first)";
- a hint about Allow;
- the **Allow the API key** switch with a 4-line hint;
- the **Monthly limit and spending** disclosure: limit field, suggestion, this month, history by month, a pricing disclaimer, and a nested **Details** table (model, tokens in/out, per-photo cost, left this month, the history *again* with call counts);
- the turned-off notice, the limit-reached notice and the waiting line.

**Fix.** Collapse it to a status line plus one action, with everything else in Advanced → Claude:
- Plan ready, key not used: "Claude: using your Claude plan." (green). Nothing else.
- Key in use: "Claude: using your API key · $1.20 of $5 this month." Plus "Manage".
- Broken: one red sentence and one button ("Install Claude Code and sign in", "Check again", or "Allow the key").
- In Advanced:
  - the key box;
  - the route choice as **2 options**: "Plan first, key as backup" / "Key only". The `api-first` and `plan` permutations add little; `plan` equals "don't allow the key";
  - Allow + limit;
  - spending, without the duplicate history and the token table (or keep that behind "Details").
- Merge "Allow the API key" and the limit into one step: "Use the key, up to $__ a month". The server already requires both (`app.py` `put_settings`).
- Move `pending_tags` to the closet's review note.

**Effort:** M (mostly frontend; e2e specs `08-tagging`, `11-spend`, `13-api-key` and `13-route-order` will need rewriting).

---

## 7. Updates is too long, and the release notes are broken markdown

**Cause, length.** `components/Updates.tsx:124-164` always shows:
- the version as a `<dl>`;
- "Last checked…";
- the check error;
- the last install;
- the "When a new version is out" label, a 3-way segmented control and a mode hint;
- Check now;
- the available line;
- and, in builds that can't self-update (dev, Linux), a paragraph saying so.

That is about 900 px on the phone, and about 1,160 px with a release (`updates-with-release-phone.png`). The mode is a set-once choice. In "Ask first" mode the app-wide `UpdateBanner` (`Updates.tsx:21-41`) already offers Install on every screen.

**Cause, markdown.**
- **Backend.** `backend/closet/updates.py:92-105` (`_notes`) keeps the first 12 lines / 1500 chars of the GitHub release `body` *as raw text*, explicitly "shown as text, never as a web page". The body is markdown.
- **Frontend.** `Updates.tsx:147` renders it in a `<div>` styled `white-space: pre-line` (`styles.css:393-396`). The `## headings`, `**bold**` and numbered lists therefore show literally, and the 12-line cut ends mid-list with "…".
- **The content is wrong too.** The release body is generated in `.github/workflows/release.yml:323-363`: "Closet X, built from <sha>", then "## First run on Windows / Mac" install steps and "## Good to know". **It contains no "what's new" at all.** So the card labelled "What's new in 0.4.0" (`aria-label`, `Updates.tsx:147`) shows first-install instructions, with a commit hash, to someone who is updating. There is no markdown library in the frontend (`package.json`: only qrcode-generator and React), deliberately.

**Fix:**
1. **Content.** Write real change notes into the release: a `## What's new` section at the top, for example from a `CHANGELOG.md` "Unreleased" section or the workflow input. Put the install instructions below it. In `_notes`, extract only the `## What's new` section, which also avoids the 12-line cut.
2. **Rendering.** Either:
   - (a) strip markdown to plain text on the server (`#` headings to bold-free lines, `**x**` to `x`, `1.` / `-` to `•`), simple and safe; or
   - (b) parse a tiny safe subset in the frontend (headings, bold, lists, links to github.com) into React elements, which needs no `dangerouslySetInnerHTML` and no dependency.

   Hide the notes behind "What's new" (a disclosure) by default.
3. **Shrink the section** to one line plus an action:
   - "Closet 0.3.2 · up to date · checked today"; or
   - "Closet 0.4.0 is ready (95 MB) · What's new · Install now".

   Move the mode control, Check now, the last-install note and "can't replace itself" to Advanced. Show failures as a single red line.

**Effort:** S for the frontend shrink and plain-text stripping; S-M for the release-workflow change. That needs the owner's sign-off, because AGENTS.md says agents never edit the release workflow.

---

## 8. The QR still shows when the app is already open on the phone

**Cause.** The decision is purely server-side state, with no notion of *who is asking*:
- `Settings.tsx:202-206` renders `PhoneAccess` whenever `settings` exists.
- `PhoneAccess.tsx:18-33` shows the QR and the instructions whenever `phone.address` is set.
- `phone.address` is set by `phone.info()` (`backend/closet/phone.py:105-136`) when `tailscale serve status --json` shows a `/` share proxying to Closet's port.

Once you have done the setup, which is exactly when you are using the phone, the QR is shown **to the phone itself**. The request's origin is never consulted: no `request.headers` or `request.client` in `settings_payload`, and no `window.location` check anywhere in the frontend (a grep for `location.host|origin|standalone|userAgent` finds nothing).

The phone's view at 390 px shows the full QR card (`settings-phone-part4.png`, address `https://closet-pc.example-tailnet.ts.net`). The setup steps include Terminal commands (`tailscale serve --bg 8765`, the stop command) that can't be run on an iPhone.

Closet listens on 127.0.0.1 only (AGENTS.md hard rule), so a phone request arrives through `tailscale serve`. It reaches Closet from 127.0.0.1 but carries:
- the `Host` header (or `X-Forwarded-Host`) of the ts.net name;
- `X-Forwarded-Proto: https` and `X-Forwarded-For: 100.x.y.z`;
- `Tailscale-User-Login` / `Tailscale-User-Name`.

In the browser, `location.origin` is `https://<host>.ts.net[:port]`.

**Precise condition.** Show the connect UI (QR, address, commands) only when the page is opened on the computer itself, that is:

```
location.hostname ∈ {"127.0.0.1", "localhost", "[::1]"}   // or Closet's own pywebview window
```

Hide it when any of the following holds:
- `location.origin === phone.address` (already on the shared address), or more generally `location.hostname` is not loopback; or
- on the server, the request carries `Tailscale-User-Login`, or `X-Forwarded-For`, or `X-Forwarded-Proto: https`, or a `Host` that is not loopback; or
- the page runs as an installed PWA (`matchMedia('(display-mode: standalone)')` or `navigator.standalone`). This is a useful extra signal; it is not enough on its own, because the PC could also install it.

On a remote client, replace the card with at most one line: "You're connected from your phone through Tailscale." Or show nothing. Also hide Quit Closet, Start at login and the backup-folder input there, since all three are about the computer.

Implementation:
- Client-only: `const remote = !['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)`. S.
- Better: the server adds `"client": {"remote": bool, "via": "tailscale"|"local"}` to the session/settings payload from the request headers. Then `phone.info()`, with its subprocesses, need not run at all for remote clients, which also fixes part of #2. S-M.

**Effort:** S.

---

## Other problems found in this scope

1. **Quit Closet on the phone** (`Settings.tsx:225`, `:916-929`). Quitting from the phone stops the server, and it can't be started again from the phone. The confirm text even says so. Hide it for remote clients.
2. **Desktop-only settings shown on the phone:** Start at login, a typed backup folder path (with a Windows placeholder on a Mac), the model's manual file paths, and the Tailscale commands.
3. **Demo hint inconsistency.** "About 30 sample clothes" (`Settings.tsx:154`) vs. "about 40 items" (README:822); the demo has 49 items in Storage.
4. **Duplicate spend history**: listed in `:857-866` and again inside Details (`:879-884`).
5. **A slow, uncached probe on every Settings visit:** `GET /api/tagging` runs `claude auth status` each time, twice per visit (see #2); `GET /api/storage` walks all image folders each time (`DECISIONS.md:93`).
6. **Every `PUT /api/settings` recomputes the full payload**, including the keychain read and autostart, so toggling laundry pays for them; Tailscale is cached for 30 s.
7. **`phone.info()` timeouts are serial (2 × 4 s), with only a 30 s cache.** A hung tailscaled blocks `/api/settings` for up to 8 s, and with it most of Settings.
8. **Weather is looked up on every Settings visit** (`WhereYouAre.tsx:140-151`). That is an outside request merely to show a line in Settings. When it is offline it adds a red error and a "Try again" button to Settings (`settings-phone-part2.png`).
9. **The Advanced `<details>` is collapsed but still mounted.** Its data arrives with `/api/settings`, so the data path shows "…" until then. Moving it to its own route lets it load lazily.
10. **Section hints are long paragraphs** (Your style 45 words, Laundry 45, Where you are about 75 words of privacy text). 1,105 words in total on a settings page.
11. **The "Plan a trip" link** in "Where you are" (`:180`) is navigation inside Settings.
12. **Release-notes label mismatch:** `aria-label="What's new in X"` is applied to install instructions (#7).
