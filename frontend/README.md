# Closet web app

React + TypeScript + Vite. `npm run build` writes the page into `../backend/closet/web/`, which the backend serves at `/`.
No UI kit, no web fonts, no requests outside the Closet server.

## Commands

```sh
npm install
npm run dev        # dev server; proxies /api and /media to a backend on http://127.0.0.1:8765
npm run lint       # eslint
npm run typecheck  # tsc
npm test           # vitest unit tests (upload queue, labels, silhouette groups, resizing)
npm run build      # production build into ../backend/closet/web
npm run e2e        # Playwright browser tests (builds first, starts its own backend)
npm run icons      # redraw the PNG icons in public/icons (they are committed)
```

### Browser tests

`npm run e2e` builds the page, starts the backend on a free port with a fresh temporary data folder and
`CLOSET_NO_AUTO_DOWNLOAD=1`, runs the tests, then stops it. Environment variables:

| Variable | Meaning |
|---|---|
| `CLOSET_PYTHON` | Python with the backend's requirements installed (default `python`). |
| `PLAYWRIGHT_CHROMIUM_PATH` | Use this Chromium instead of Playwright's downloaded one. |
| `CLOSET_E2E_MODEL` | Path to `isnet-general-use.onnx`; enables the test that waits for a real cutout. |
| `CLOSET_E2E_TMP` | Where to make the temporary data folders (default: the system temp folder). |
| `E2E_SKIP_BUILD=1` | Reuse an existing build. |

## Layout

- `src/App.tsx` – first run, login, "closed" screens; `src/Shell.tsx` – sidebar (≥1000px) or bottom tab bar, banners.
- `src/screens/` – Closet grid (with the master–detail panel on wide screens), ItemDetail, Add, Settings, Setup, Login.
- `src/uploadQueue.ts` – the upload queue (one at a time, one `client_key` per file reused on every retry,
  automatic retries for dropped connections); `src/resize.ts` – in-browser resize to 2400px JPEG.
- `src/api.ts` – API client; notices when answers come from the offline copy.
- `sw/sw.js` – the hand-written service worker. The build fills in the list of files to precache.
  App files are precached; items, vocabulary and session are network-first with the saved copy as fallback;
  `/media/*` and illustration SVGs are cache-first. Nothing but GET is saved; logging out clears the saved data.
- `public/` – web manifest and icons.
