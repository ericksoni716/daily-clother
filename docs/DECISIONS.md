# Decisions

What was decided and why, newest phase last. A fresh conversation should be
able to resume from this file, `BACKLOG.md` and the README.

## How the work is organised

The brief asked for eight phases with a stop after each. That was changed with
the owner once it was clear the recognition work does not depend on the app.

| Decision | Why |
|---|---|
| Two tracks: recognition and drawing, and the app | What the tagger reports and what the drawing shows is judged from render sheets and tagging reports, not from the installed program, and it will keep growing with the taxonomy. Gating the app on it stalled the app. |
| Track 1 (recognition and drawing) is reviewed continuously, with two checkpoints and no stops | The checkpoints are coverage of the taxonomy's visible values and accuracy on the owner's own photos. It needs no packaged build. Original phase 0 and the drawing half of phase 2 live here. |
| Track 2 (the app) has four main stops, then smaller ones | A stop is worth it only where something can only be checked on the owner's machine, where direction could change, or where money is spent. A: the program on the PC and iPhone (phase 1). B: the real wardrobe in (phase 2 and single-photo import, review queue and cost cap from phase 3). C: today's outfit (phase 4 with ratings from phase 6). D: gaps and shopping (phase 5). |
| Multi-item photos and video sweeps move behind the outfit builder | They are capture conveniences; the outfit builder and shopping are the two features the owner said matter most. Open for the owner to reverse. |
| The app stores the tagger's full answer, its schema version and the cutout for every item | This is what keeps the tracks independent: better drawings need no data change, and a taxonomy edit only means re-tagging, which is free on the Claude plan. |
| Template anchor points are fixed; category, formality, season and weight class are settled before stop C | The mannequin view relies on the anchors, and outfit and gap logic read those four vocabularies. Finer details can keep growing after stop C. |
| The repository is public | The owner made it public so that Actions minutes are free and unlimited for tests, builds and agent sessions. Commit metadata and tracked files were checked for personal details first. Going public cannot be recalled once copies exist, so the rule that photos and keys never get committed now protects against something irreversible. |
| App work can be done by Copilot cloud agents, orchestrated from a Claude session | The owner has a large monthly allowance of Copilot AI credits and wants to spare the Claude plan's weekly budget. Agents work from issues, open pull requests against `main`, and `ci` is the gate. `AGENTS.md` holds their rules; `copilot-setup-steps.yml` prepares their environment. Taste-driven drawing work stays in the Claude session with the owner. |
| The orchestrating Claude session merges pull requests when `ci` is green and its own review is clean | The owner's choice, for speed with several agents. It still stops and asks before merging anything that changes a recorded decision, touches releases or the release request file, or looks risky. |
| The first agent task is a bake-off | The same well-specified stop B task goes to Opus 5.5, Gemini 4 Argon and GPT 6 Astra (the strong models the owner's Copilot offers). They are compared on tests passed, review findings and rework needed, and the result decides which model gets which kind of task. |
| Garment shapes are reviewed in a standing gallery, not ad-hoc sheets | The owner expects many rounds of review. `tools/make_review_gallery.py` builds one page with every garment, every taxonomy value, the weight ladder, trousers and shoes; it is published as a private Claude artifact where the owner marks each drawing "looks right" or "needs work" with a note. Marks are stored per drawing with the round they were made on, so a mark on an older drawing is flagged for another look after a rework. |
| The app's interface gets a design pass later | The owner wants the interface-design review run on the app, after more features exist; the current UI is known to need a lot of work. |
| Agents are started through the `start agent` workflow so the model can be chosen | Assigning an issue with the tools the orchestrating session has cannot name a model, and GitHub then picks one itself; the first agent run landed on a model the owner does not want and was cancelled. The workflow makes the same assignment through the REST API with a `model` field. It needs a fine-grained personal access token of the owner, kept as `COPILOT_AGENT_TOKEN` in an `agents` environment limited to `main`, because the built-in token may not assign Copilot. |
| CI runs on every pull request and push to `main` | It was manual-only while minutes cost money. |
| "Phase" in older entries below means the original numbering | Phase 1 is stop A, phases 2 and 3 are mostly stop B, phase 4 is stop C, phase 5 is stop D. |

## Before phase 0 (agreed with the owner)

| Decision | Why |
|---|---|
| Menswear only: mannequin, base shapes and shopping | Owner's answer. |
| Runs on a Windows PC; the Mac (Apple Silicon) build is made only when asked | Owner's answer; macOS build minutes cost 5x Windows. |
| Home is New York City, prices in US dollars | Owner's answer; used for weather and shopping. |
| Illustrations are parametric templates, not freeform SVG written per item | Same attributes always give the same drawing, redraws are free, and every item of a category shares anchor points the mannequin view needs. Freeform SVG stays as a fallback for unusual items. |
| Gap numbers ("completes 9 outfits") are counted by code | A rule-based outfit-validity engine enumerates outfits; the model proposes and explains, it does not do the arithmetic. The outfit builder uses the same engine. |
| Background removal calls the ONNX model directly | The `rembg` package drags in numba, scipy and scikit-image, the main packaging risk. Pre- and post-processing is about 40 lines. |
| The program gets a tray icon with Quit, a single-instance check and optional start at login | A double-clicked server has no window. Nightly backups only run while it is running, so it also catches up on start. |
| API key is kept in the OS keychain, environment variable as fallback | An encrypted file needs a key from somewhere; a passphrase-derived key would stall background jobs until login. |
| Keep the uncut 1600px photo beside the cutout | A bad cutout can be redone; costs roughly 100 MB for a few hundred items. |
| Backup and restore move to phase 1; the love/like/meh/dislike chip arrives by phase 3 | Real data and migrations start in phase 1; phases 4 and 5 rely on ratings. |
| The bench ships inside the packaged program as a `bench` command | The owner does not install Python. |
| No Batches API for now | It is asynchronous, which clashes with "usable immediately", and tagging is cheap enough that half price saves pennies. Kept in the backlog. |
| Scheduled work (price drops, queued shopping searches, and optionally an overnight refresh of the gap list) runs as a Claude Code scheduled task on the owner's Claude plan, exchanging files with the app through Google Drive | No API credits. The cloud task cannot reach the PC over Tailscale, so the app writes `wishlist.json` into a Google Drive for desktop folder and reads back `price-checks.json`, validated against the same schema as any AI output. The owner chose Google Drive; the app needs no Google credentials because the scheduled task uses the Drive connector. Built in phase 5. |
| The overnight gap refresh is optional | Counting outfits is instant code. Only proposing candidate pieces and writing the explanations needs a model call; running that overnight on the Claude plan keeps the list current for free, otherwise it refreshes on demand through the API. |
| "Would this work?" on iPhone is paste-a-link or pick-a-photo; no Apple Shortcut | iOS does not let home-screen web apps appear in the share sheet. The owner is fine with copy and paste. |
| Development may use Claude subagents (Haiku, Sonnet, Opus) as a stand-in for API calls | Owner's go-ahead. Stand-in answers are scored by the same bench, labelled as such, and never reported as cost or timing figures. |
| Packaged build runs on demand and at each phase sign-off, Windows by default | Private repo with limited Actions minutes; nothing runs in Actions until the owner says go. Releases hold the downloads; no stored build artifacts or caches. |

## Phase 1

| Decision | Why |
|---|---|
| Phase 1 started before phase 0 was fully closed, at the owner's request | The paid API key is deliberately the last step. Phase 1 makes no Claude calls, so it needs no key. |
| SQLite through Python's built-in driver, with numbered `.sql` migrations and `PRAGMA user_version` | No ORM or migration library to package. A copy is taken before any migration; a database from a newer program is refused; a failed migration rolls back. |
| Program-wide settings live in `settings.json`, not the database | Passphrase hash, sessions, backup folder and model address are not part of a closet, so a restored or demo closet does not change who can log in. |
| The demo closet is a second closet under `demo/`, switched from Settings | Trying things never touches real data, the owner does not need command-line flags, and backups ignore it. Seven demo items are real open-licence photos with pre-made cutouts; the rest are drawn from templates. |
| Passphrase stored as a scrypt hash; session cookie is HttpOnly and SameSite=Strict; five wrong guesses lock login for five minutes | Standard library only. The server listens on 127.0.0.1; Tailscale serve is the only way in from outside. |
| Uploads carry a client-made key | A retry after a dropped connection returns the first item instead of creating a duplicate. |
| The cutout queue is rows in the database, processed by one worker thread | Nothing is lost on quit; interrupted jobs resume; jobs wait while the model is missing instead of failing; three attempts before an item is marked failed. |
| The uploaded full-size file is never written to disk | Only the 1600px photo, its cutout and thumbnails are stored, all WebP. |
| Backups are dated database snapshots plus an add-only copy of the images, 14 snapshots kept | Snapshots use SQLite's own backup so they are consistent while the app runs. Restore moves the current closet aside instead of deleting it. |
| ffmpeg is left out of the phase 1 program | Video arrives in phase 3. The spike proved it can be bundled, but it adds about 105 MB to a file that unpacks on every start; phase 3 will decide between bundling and download-on-first-use like the model. |
| CI and release workflows are manual-only for now | The owner has not yet approved spending Actions minutes. Files travel between release jobs through a draft release, because artifact storage is exhausted. |
| Outbound HTTPS uses the computer's own trusted certificates (`truststore`), with a bundled certificate file as fallback | The first Mac build could not download its model. The likely cause, not yet confirmed on the owner's Mac: a packaged Python has no certificate store on macOS, so the HTTPS connection fails and was reported as no connection. The system store also works on a work computer whose network adds its own certificate. The release build now checks an HTTPS connection from the packaged program, and a certificate failure has its own message. |
| A release is started with the `release` workflow's Run button (or the same call from the orchestrating session) | For one day, before the workflows were on `main`, a release was started by editing a request file; that trigger is removed now that the normal route works. Windows and macOS can be built separately. |

## Reaching Claude: two routes

Decided with the owner after phase 1: the app can reach Claude two ways, and
uses whichever is available.

| Decision | Why |
|---|---|
| Two routes: the owner's Claude plan through the Claude Code command-line tool (`claude -p`), and an API key | Either can run dry: the plan has usage limits, the API key has a credit balance. |
| Default order is plan first, API key second; testing and the bench default to the plan | Plan calls bill nothing. The API key is only used when the plan cannot be. |
| A route that is out of credit, not signed in or not installed is skipped for the rest of that run; a bad answer is retried on the same route and never moved to the paid one | Falling back must not turn a prompt problem into a bill. |
| The plan route removes `ANTHROPIC_API_KEY` from the subprocess environment and never uses `--bare` | Claude Code prefers an API key when it sees one, which would bill the API silently; bare mode cannot read the plan login. |
| Same prompt, same schema, same validation on both routes | The plan route passes the schema with `--json-schema` and reads `structured_output`; images are written to a temporary folder and opened with the Read tool, the only tool allowed. |
| Cost shown for plan calls is labelled as an estimate at API prices | Claude Code reports `total_cost_usd` as a client-side estimate; nothing is charged per call on a plan. It includes Claude Code's own overhead, so it overstates what the API route would cost. |
| The spend cap applies to the API route only | Plan usage is limited by the plan itself. |

Facts checked in Anthropic's documentation on 2026-11-12:
- Windows install needs no Node.js: `irm https://claude.ai/install.ps1 | iex` in PowerShell, or `winget install Anthropic.ClaudeCode`. The program lands in `%USERPROFILE%\.local\bin\claude.exe`; the app looks there as well as on PATH.
- Signing in once with `claude` persists (stored in `%USERPROFILE%\.claude\.credentials.json`); later `claude -p` calls from another program use it. `claude auth status` exits 0 when signed in.
- The support pages say `claude -p` under a plan login draws on the plan's limits. The legal page restricts third-party developers offering Claude login to their users, and says this does not prevent an end user signing in to the unmodified Claude Code program with their own plan. A personal program calling that program on the owner's own machine appears to be inside those terms, but the docs do not say so in as many words, and Anthropic reserves the right to change enforcement.
- When a limit is hit the message reads "You've hit your session limit · resets …" (or weekly). The exit code for that case is not documented; the app matches on the message.

## Illustration

| Decision | Why |
|---|---|
| Style B: bold outer outline, inner lines about a third of its weight, garment-coloured fill | Owner's choice. The demo closet is drawn in it. Styles A and C stay in the bench for comparison only. |
| Template proportions are measured from reference drawings, not drawn from memory | The first shirt had a collar made of two separate shapes, a neck opening too narrow for a neck and a placket drawn over the collar. The owner supplied a flat drawing of a shirt; an independent review measured it (normalised to shoulder width) and the top template was rebuilt from those numbers. |
| A collar is one folded band that is part of the garment's outline | Seen from the front: a U-shaped opening with the band line across it, two leaves meeting in an X, and on button-front shirts the collar stand with the top button below the meeting point. Polo and zip collars get shorter leaves and no stand. |
| Seams are a separate layer under folded parts | The placket, yoke and armhole seams lie on the body, so the collar covers their tops. Details that sit on top (pockets, sleeve hems) stay in the upper layer. |
| Collars and shirt cuffs are the body's colour | Tinting them made a white shirt look as if it had a grey collar. Rib cuffs and hems keep a slight tint. |
| The drawing keeps each garment's own details; the template only supplies consistent proportions | The owner's correction: the first schema tagged seven coarse shape fields and guessed everything else from the category, so every polo got two buttons and a henley looked like a long-sleeved tee. That was never agreed. Now the tagger reports a `details` block (how the front opens, button count and colour, pockets, hem, cuffs, cloth surface, contrast trim, waist, shoe style, sole and lace colour, feature flags) and the drawing follows what it saw, not the category. |
| Details the drawing cannot show yet are recorded, not dropped | `other_features` holds free-text distinctive details ("embroidered chest logo"). The app shows them beside the drawing as seen but not drawn, and they are the list the option vocabulary grows from. |
| The detail vocabulary is the owner's menswear taxonomy (`docs/menswear-taxonomy.json`), word for word | The owner supplied it after seeing the first ad-hoc detail fields. The tagger reports its visible axes (fit, sleeve length, neckline, collar, placket, cuff, sleeve construction, pockets, hem, fabric structure, colour texture, pattern and its orientation); back details and closure material, which cannot be seen from the front, are not asked for. `bench/closet_bench/taxonomy.py` holds a frozen copy of those axes, kept equal to the JSON by a test, the mapping from each value to the drawing, and a coverage table saying whether each value is drawn exactly, approximately or not yet. |
| Weight and fibre are tagged and drawn | The owner's correction: they decide how a garment sits and what it can be layered over or under (a fleece shirt against a linen one, a thick wool jacket against a thin bomber, a wool flannel against a light cotton one). The tagger reports fibre, a weight class (lightweight, midweight, heavyweight, super_heavy), knit gauge and corduroy wale. The drawing shows weight as edge thickness, bulk and band depth, and fuzzy cloth as a soft edge. The outfit engine will use the weight class for layering rules (what fits under what) when it is built. |
| Hip patch pockets are in the taxonomy | The owner asked for `hip_patch_double` and `hip_flap_double` to be added to the pockets axis after a flannel overshirt in the test photos had no matching value. |
| Detail fields use "none", "na", "same" or 0, never null | The API limits how many nullable properties one answer schema may have; the coarse fields already use most of that allowance. |
| Cloth surfaces (corduroy, rib knit, cable knit, waffle) are drawn tone-on-tone over the colour | They are regular enough to draw, and a drawn surface stays crisp at any size. Irregular cloth (marl, plaid, floral) still comes from the photo as a tile. |
| Fits are calibrated from real garment measurements, not from a reference drawing | The owner found everything drawn slim. Checked: the regular fit had a chest of 0.85 of the shoulder width, where a real regular shirt laid flat has about 1.2 (56 cm pit to pit against 46 cm shoulders). The stock illustration used for the shirt was itself slim at the chest. Its collar, placket and details stay; body and sleeve proportions come from flat measurements of real garments. |
| Sleeves start at the edge of the body, never inside its width | The owner's first note on every shirt in the review gallery: "arms should be in line with the width of the shirt". The measurement-based recalibration had drawn the real, narrower shoulder seam and laid the sleeves over the sides of a wider chest, so the arms began inside the garment. The drawn shoulder point now sits just outside the chest's width, the armhole runs down the body's edge, and no sleeve overlaps the body. Body width and length still come from real measurements; the armhole is drawn deeper than life so the sleeve keeps its width. |
| Anchor points are points on the wearer, not on the garment | Neck base and the shoulders of a 46 cm frame, the same for every top. How far the cloth extends beyond them is the fit. |
| Tailored jackets have their own construction | A blazer drawn as a shirt body with lapels was rejected as narrow and wrong. Jackets are built from the measurements of a real two-button jacket: structured shoulder, suppressed waist, lapel gorge and roll to the top button, button stance, cutaway quarters, welt and flap or patch pockets. |
| Garments that open all the way down can be drawn open | The owner expects jackets, cardigans and overshirts to be shown both buttoned and open over a shirt. Composing an outfit is the outfit view (stop C), but the drawing has to support it, so the open state and a proof that layers line up on the shared anchors are built in track 1. In the closet grid an item is shown closed by default. |
| Reference drawings may be downloaded from Wikimedia Commons, Openclipart and SVG Repo | Added to the `daily-clother` environment at the owner's prompting. They are looked at and measured, never copied into the repo. Commons rate-limits hard: one request, then wait. |

## Phase 0 findings

See `docs/PHASE0.md` for the results and what is still open.
