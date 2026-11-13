# API

The backend serves JSON under `/api`, images under `/media`, and the built web
page for every other path. All errors are `{"detail": "a sentence the owner can
read"}` with a matching status code. Everything except `health`, `session`,
`setup` and `login` needs the session cookie (set by `setup` or `login`,
HttpOnly, SameSite=Strict); without it the answer is 401.

## Session
| Call | Result |
|---|---|
| `GET /api/health` | `{app:"closet", status:"ok", version, model_state, setup_required, profile}` |
| `GET /api/session` | `{authenticated, setup_required, version, profile}` |
| `POST /api/setup {passphrase}` | 204 and logs in. 422 if shorter than 8 characters, 409 if already set. |
| `POST /api/login {passphrase}` | 204. 401 if wrong; 429 with `Retry-After` after 5 wrong tries in 5 minutes. |
| `POST /api/logout` | 204 |

## Items
`ItemSummary`: `id, name, category, color, color_hex, pattern, location, rating, status, cutout_state, thumb_url, has_illustration, illustration_url, has_photo, last_worn, wear_count, wears_since_wash, laundry, created_at, updated_at`.
`last_worn` is the date of the latest wear (`YYYY-MM-DD`) or null; `wear_count` counts every wear; `wears_since_wash` counts wears recorded since the item was last marked clean; `laundry` is `clean` or `laundry`. `location` says where the item lives when it is clean (`closet`, `drawer` or `storage`); being in the wash is `laundry`, not a location.
`illustration_url` (or null) is an SVG image address that changes whenever the drawing changes, so it can be used in an `<img>` and cached forever.
`cutout_state` is `none` (no photo), `pending`, `processing`, `ready` or `failed`. `thumb_url` is the cutout thumbnail once ready, the photo thumbnail before that, or null.

`Item` is the summary plus `formality, season, brand, size, material, fit_notes, condition, price_cents, acquired_on, notes, rating_reason, illustration_svg, cutout_error, silhouette{}, confidence{}, source{}, photos[], recent_wears[]` (the 10 latest wear dates, newest first).
Each photo: `id, kind, url, thumb_url, cutout_url, cutout_thumb_url, width, height` (`cutout_*` are null until ready).

| Call | Result |
|---|---|
| `GET /api/vocab` | Allowed values: `category, color, pattern, formality, season, location, condition, rating` (lists) and `silhouette` (object of lists). |
| `GET /api/items?status=active\|archived&category=&q=&laundry=clean\|laundry` | `{items: [ItemSummary]}`, newest first. |
| `POST /api/items` multipart: `photo` (file), `client_key`, optional `name` | 201 `Item` with `cutout_state: "pending"`. Sending the same `client_key` again returns the first item with 200, so retries never duplicate. 400 if the file is not a readable photo. |
| `GET /api/items/{id}` | `Item` |
| `PATCH /api/items/{id}` JSON of fields to change | `Item`. Changeable: `name, category, color, color_hex, pattern, formality, season, location, condition, rating, rating_reason, brand, size, material, fit_notes, acquired_on, notes, price_cents, status, silhouette` (silhouette is merged; a null value removes a key). 422 with a readable message for a value outside the vocabulary (including `location: "laundry"`; use the laundry call instead). |
| `DELETE /api/items/{id}` | 204; the item and its images are removed. |
| `POST /api/items/{id}/retry-cutout` | 202 `Item` |
| `GET /api/items/{id}/wears` | `{wears: [{worn_on, created_at}]}`, newest first. |
| `POST /api/items/{id}/wears {worn_on?}` | Records a wear. `worn_on` is `YYYY-MM-DD` and defaults to today in the computer's local date. 201 `Item`; 200 `Item` if that day was already recorded (one wear per item per day). 422 for a date in the future or not in that form. |
| `DELETE /api/items/{id}/wears/{YYYY-MM-DD}` | 200 `Item`. 404 if there is no wear on that day. |
| `POST /api/items/{id}/laundry {state: "laundry"\|"clean"}` | 200 `Item`. Marking an item clean sets `wears_since_wash` to 0 (also when it was already clean: it has just been washed). |
| `GET /api/items/{id}/illustration.svg` | The item's illustration as `image/svg+xml`; 404 if it has none. |
| `GET /media/{path}` | A WebP image; cacheable forever (paths never change content). |

## Outfits
| Call | Result |
|---|---|
| `POST /api/outfits/suggest {low_c, high_c, rain?, occasion?, mood?, build_around?, leave_out?, worn_days_ago?, count?}` | Today's outfits from the open closet, chosen by rule (`backend/closet/outfits.py`). `low_c` and `high_c` are the day's low and high in °C; `rain` true or false (default false); `occasion` one of the formality values (default `casual`); `mood` `usual`, `sharp` or `relaxed` (default `usual`); `build_around` an item id that must be in every outfit; `leave_out` a list of item ids; `worn_days_ago` an object of item id to days since last worn (0 is today); `count` 1 to 10 (default 3). Answer: `{outfits: [{pieces: {base, mid, outer, bottom, shoes, accessories[]}, score, reasons[], warnings[]}], missing[]}`. `pieces` holds item ids (`mid` and `outer` may be null); `score` is 0 to 100, best first; `reasons` say why the pieces go together and `warnings` what to be aware of, both as sentences. When no outfit can be made `outfits` is empty and `missing` says why ("There are no shoes in this closet yet."). Archived items, items in the laundry and items rated dislike are never used. 422 with a sentence for a bad value or a `build_around` item that is not in the open closet; 400 for a body that is not JSON. |

## What's missing
| Call | Result |
|---|---|
| `GET /api/gaps` | What the open closet is missing, found by rule (`backend/closet/gaps.py`) from its items and wear log. Answer: `{enough, message, gaps: [gap], notes: [{kind, text, items[]}], checked: {items, wears, days}}`. When the closet has fewer than 8 pieces of clothing `enough` is false, `message` says so in a sentence and `gaps` is empty; otherwise `message` is null. Each gap: `{id, name, look_for: {category, formality, season, weight_class, colors[], pattern, material}, why[], score, found_by[], evidence: {days: [{temperature, low_c, high_c, rain, occasion, words}], items[]}}`, best first, at most 8. `name` is in plain words ("A rain-proof outer layer"); `look_for` uses the item fields (null where it does not matter; `material` is a phrase); `why` is sentences naming the owner's items; `score` is 0 to 100; `found_by` is one or more of `days`, `thin_place`, `orphan`, `worn_most`, `basic`; `evidence.items` are item ids of the open closet. `notes` holds things that are not gaps (`never_worn`: items with no wear in the log). Archived items are left out; items in the laundry count as owned. The answer is kept until an item or a wear changes (a wash does not count), so a second call is instant. |

## Background-removal model
| Call | Result |
|---|---|
| `GET /api/model` | `{state: missing\|downloading\|failed\|ready, downloaded_bytes, total_bytes, error, url, path, sha256, name}` |
| `POST /api/model/download` | 202; starts or resumes the download. |
| `PUT /api/model/url {url}` | Sets the download address (https only); empty restores the default. |

## Settings and program
| Call | Result |
|---|---|
| `GET /api/settings` | `{version, profile, data_dir, port, backup_folder, last_backup{at, ok, error, folder, kind}, last_good_backup, pending_cutouts, phone{tailscale_installed, running, address, command}, autostart (true/false, or null when unavailable), heic_supported}` |
| `PUT /api/settings {backup_folder?, autostart?}` | Same shape. 422 if the folder does not exist. |
| `GET /api/storage` | Disk space used by the open closet, worked out by walking its folders on each call: `{items, photos_bytes, cutouts_bytes, thumbnails_bytes, database_bytes, backups_bytes, model_bytes, logs_bytes, total_bytes, data_dir, free_bytes}`. Photos, cutouts, thumbnails, the database and `items` (archived included) are the open closet's own; the background-removal model, the logs and the backups kept inside the data folder are shared by the real and demo closets. `total_bytes` is the sum of the seven `_bytes` parts; `free_bytes` is the free space on the disk holding the data folder (null if it cannot be read). A missing folder counts as 0; no file names are returned. |
| `GET /api/tagging` | The ways Closet can reach Claude: `{order: ["plan", "api"], routes: [{id, available, detail}]}`, with `routes` in the order they are tried. `plan` is the owner's Claude plan through Claude Code: available when the `claude` command is found (on PATH or in `~/.local/bin`) and `claude auth status` says it is signed in. `api` is an API key: available when `ANTHROPIC_API_KEY` is set. `detail` is empty when available, otherwise a sentence saying why not ("No API key is set."). Asks Claude nothing and costs nothing; the check runs in a worker thread and gives up on Claude Code after 5 seconds. Never contains the key, the account or any folder. |
| `POST /api/backup` | The backup record; 409 with the record (and its `error`) if it failed. |
| `POST /api/profile {profile: "main"\|"demo"}` | Switches between the real closet and the demo closet. |
| `POST /api/quit` | 202; the program exits shortly after. |
