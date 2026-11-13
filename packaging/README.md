# Packaging

The real build of Closet is **`closet.spec`** (PyInstaller). `spike/` is the
throwaway proof that came before it; it is kept only because its ffmpeg proof
is needed when ffmpeg returns in a later phase. Its manual-only workflow,
`.github/workflows/packaging-spike.yml`, does not build Closet.

| File | Purpose |
| --- | --- |
| `closet.spec` | Builds the program from `backend/closet` plus its data (`migrations/`, `demo_data/`, `web/`), onnxruntime, pillow-heif's native libraries and pystray. Stops if `web/index.html`, the migrations or the demo data are missing. |
| `requirements-build.txt` | PyInstaller and its hooks, exact pins. Install with `backend/requirements.txt`. |
| `smoke_test.py` | Drives a built program end to end. Standard library only. |
| `../.github/workflows/release.yml` | Manual release: build, test, publish. |
| `../.github/workflows/ci.yml` | Lint and tests from source on every pull request (never builds the program). |
| `../.github/workflows/package-check.yml` | Builds the Linux program and runs the smoke test (see below). |

What the build produces:

| OS | Output | Notes |
| --- | --- | --- |
| Windows | `dist/Closet.exe` | One file, windowed (no console window), icon drawn by `closet.tray.icon_image()`. |
| macOS (Apple Silicon) | `dist/Closet.app` | Windowed menu-bar app (`LSUIElement`, no Dock icon), bundle id `app.closet`, macOS 14+. One folder inside the bundle (one-file `.app` is deprecated in PyInstaller 6). Ad-hoc signed only. The release zips it with `ditto -c -k --keepParent` as `Closet-mac-arm64.zip`. |
| Linux | `dist/closet` | One file, console. For local checks only; not released. |

## Build locally

Keep the virtualenv and the build output outside the repository.

```sh
# 1. the web page (writes backend/closet/web/)
(cd frontend && npm ci && npm run build)

# 2. a clean venv with the runtime and build pins (CI uses Python 3.12)
python3.12 -m venv /tmp/closet-venv
/tmp/closet-venv/bin/pip install -r backend/requirements.txt -r packaging/requirements-build.txt

# 3. optional: stamp a version (the release does this; git-ignored)
echo 'VERSION = "0.1.0"' > backend/closet/_build_version.py

# 4. build (under a minute)
/tmp/closet-venv/bin/python -m PyInstaller --noconfirm --clean packaging/closet.spec \
    --distpath /tmp/closet-dist --workpath /tmp/closet-build

# 5. test (any Python 3.10+)
python3 packaging/smoke_test.py /tmp/closet-dist/closet                  # Linux
python3 packaging/smoke_test.py /tmp/closet-dist/closet \
    --cutout --model /path/to/isnet-general-use.onnx                     # with the model
```

On Windows use `Scripts\python.exe` and `Closet.exe`; on macOS pass
`/tmp/closet-dist/Closet.app/Contents/MacOS/Closet` to the smoke test.

## What the smoke test checks

Each run gets a fresh temporary data folder (`CLOSET_DATA_DIR`) and
`CLOSET_NO_AUTO_DOWNLOAD=1`, so nothing is downloaded or touched.
`ANTHROPIC_API_KEY` is removed from the program's environment, so it never
calls Claude with a key.

- `selfcheck --out FILE` exits 0 and every check is ok (webp, heic,
  onnxruntime, database, web_page, drawing, model_state, tagger), with `model_state`
  = `missing`. The drawing check draws a shirt from its tags with the
  bundled `closet.drawing` package.
- `--no-browser --no-tray --port N`: `/api/health` answers within 120 s with
  `app: closet`, `model_state: missing`, `setup_required: true`; `GET /` is
  the built page (`id="root"`), and every script and style sheet it links
  to under `/assets/` is served with a JavaScript or CSS type (a wrong type
  would leave a blank page); `POST /api/setup` gives 204 and a session
  cookie; `GET /api/items` is 200; `GET /api/tagging` is 200 and lists the
  plan route then the API route (which proves the tagger package and its
  `models.json` were bundled); after switching to the demo profile there
  are 30 items and a demo item's drawing is served as SVG;
  `POST /api/quit` makes the program exit with code 0 within 30 s; the data
  folder has `closet.db` and no `closet.lock`.
- Migrations: the selfcheck counts as many bundled migrations as
  `backend/closet/migrations/` has (another folder with `--migrations DIR`),
  and the new main closet and the demo closet are both at the latest one
  (`PRAGMA user_version`).
- `--cutout --model FILE` copies the model into the data folder and requires
  `selfcheck --cutout` to pass, including a real background removal.
- `--expect-version X` also requires that version in the report and in
  `/api/health` (the release passes it).

On failure it prints the reason, the program's output and the tail of
`closet.log`, and kills the whole process tree (bootloader and app).

## Automatic check (`package-check` workflow)

Builds `dist/closet` on Linux exactly as the release builds its programs
(same spec, `backend/requirements.txt` + `requirements-build.txt`, Python
3.12, the frontend built into it, a version stamped as `0.0.0-check.<run>`)
and runs the default smoke test with `--expect-version`. About 4 minutes.

- Runs on every push to `main`, on pull requests that change `packaging/`,
  `backend/requirements*.txt`, any `backend/closet/**/__init__.py`, what the
  spec reads (`__main__.py`, `cli.py`, `config.py`, `tray.py`, migrations,
  demo data, the tagger's `models.json`, the frontend's package files and
  Vite config) or the workflow itself, and by hand (Actions > package-check
  > Run workflow).
- Not checked there: Windows and macOS (only the release builds them), the
  background-removal check (`--cutout`, needs the model from the internet)
  and the tray. It creates no release or tag, uploads nothing and uses no
  cache.

## Release procedure

1. Merge what you want released; make sure `ci` passes (Actions > ci > Run workflow).
2. Actions > **release** > Run workflow on that branch; enter the version (`0.1.0`, no `v`), tick macOS if wanted.
3. The workflow creates a draft release, builds and tests Windows (and macOS), uploads each file to the draft.
4. If everything passed it publishes the release, which creates the tag `v<version>` on that commit; otherwise it deletes the draft and fails.
5. Never create tags by hand. To retry a failed version, just run it again.

## Known risks (nothing has run on Windows or macOS yet)

- **Windows windowed mode.** `sys.stdout` is `None`; the code guards for it
  and `selfcheck --out` writes to a file. An unexpected crash shows a
  PyInstaller error dialog, which on CI blocks until the smoke test's timeout
  kills it.
- **Windows tray.** The smoke test runs `--no-tray`, so the tray icon (the
  only window) is never exercised in CI. Try it by hand after the first
  release: icon visible, "Open Closet", "Start when I log in", "Quit Closet".
- **Windows pillow-heif DLLs and the VC++ runtime.** Collected from the
  wheel's file list as in the spike; a GitHub runner has the VC++ runtime
  installed, so a pass does not prove the exe starts on a clean PC.
- **Windows SmartScreen / antivirus.** Unsigned one-file exes that unpack
  DLLs into `%TEMP%` are often flagged, and the first start is slow.
- **macOS Gatekeeper.** Ad-hoc signed only; downloaded copies are
  quarantined and need "Open Anyway" in Privacy & Security. The release
  checks the unzipped bundle with `codesign --verify --deep --strict`.
- **macOS tray.** pystray's macOS backend needs pyobjc (installed as
  pystray's dependency, not pinned in `backend/requirements.txt`); it is not
  exercised by the smoke test (`--no-tray`).
- **Icon.** Generated at build time from `closet.tray.icon_image()`
  (ICO on Windows, ICNS on macOS); if that fails the build continues
  without one and prints a warning.
- **Excludes.** `setuptools`, `pkg_resources`, `distutils`, `onnx`,
  `onnxruntime.tools/quantization/transformers`, `numpy.f2py`, `tkinter` and
  test frameworks are excluded. Verified on Linux only.
