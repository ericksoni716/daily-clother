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
`ItemSummary`: `id, name, category, color, color_hex, pattern, location, rating, status, cutout_state, thumb_url, has_illustration, illustration_url, has_photo, created_at, updated_at`.
`illustration_url` (or null) is an SVG image address that changes whenever the drawing changes, so it can be used in an `<img>` and cached forever.
`cutout_state` is `none` (no photo), `pending`, `processing`, `ready` or `failed`. `thumb_url` is the cutout thumbnail once ready, the photo thumbnail before that, or null.

`Item` is the summary plus `formality, season, brand, size, material, fit_notes, condition, price_cents, acquired_on, notes, rating_reason, illustration_svg, cutout_error, silhouette{}, confidence{}, source{}, photos[]`.
Each photo: `id, kind, url, thumb_url, cutout_url, cutout_thumb_url, width, height` (`cutout_*` are null until ready).

| Call | Result |
|---|---|
| `GET /api/vocab` | Allowed values: `category, color, pattern, formality, season, location, condition, rating` (lists) and `silhouette` (object of lists). |
| `GET /api/items?status=active\|archived&category=&q=` | `{items: [ItemSummary]}`, newest first. |
| `POST /api/items` multipart: `photo` (file), `client_key`, optional `name` | 201 `Item` with `cutout_state: "pending"`. Sending the same `client_key` again returns the first item with 200, so retries never duplicate. 400 if the file is not a readable photo. |
| `GET /api/items/{id}` | `Item` |
| `PATCH /api/items/{id}` JSON of fields to change | `Item`. Changeable: `name, category, color, color_hex, pattern, formality, season, location, condition, rating, rating_reason, brand, size, material, fit_notes, acquired_on, notes, price_cents, status, silhouette` (silhouette is merged; a null value removes a key). 422 with a readable message for a value outside the vocabulary. |
| `DELETE /api/items/{id}` | 204; the item and its images are removed. |
| `POST /api/items/{id}/retry-cutout` | 202 `Item` |
| `GET /api/items/{id}/illustration.svg` | The item's illustration as `image/svg+xml`; 404 if it has none. |
| `GET /media/{path}` | A WebP image; cacheable forever (paths never change content). |

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
| `GET /api/storage` | `{items, photos_bytes, cutouts_bytes, thumbnails_bytes, database_bytes, backups_bytes, model_bytes, logs_bytes, total_bytes, data_dir, free_bytes}` for the active profile. |
| `POST /api/backup` | The backup record; 409 with the record (and its `error`) if it failed. |
| `POST /api/profile {profile: "main"\|"demo"}` | Switches between the real closet and the demo closet. |
| `POST /api/quit` | 202; the program exits shortly after. |
