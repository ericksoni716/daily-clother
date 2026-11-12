# Decisions

What was decided and why, newest phase last. A fresh conversation should be
able to resume from this file, `BACKLOG.md` and the README.

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

## Phase 0 findings

See `docs/PHASE0.md` for the results and what is still open.
