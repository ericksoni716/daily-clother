# Packaging spike

Throwaway program that answers one question before the real app exists:
**do the heavy native dependencies survive a PyInstaller one-file build?**

It is a tiny FastAPI app (`app.py`) frozen into a single console executable
named `closet-spike` (`closet-spike.exe` on Windows). Nothing here is meant to
be reused as-is except the lessons in "Notes for the real build".

## What it proves

`GET /selfcheck` (and the `--selfcheck` CLI flag) runs five checks inside the
frozen program. Each reports `ok` / `error` and never raises.

| Check | What it does |
| --- | --- |
| `onnxruntime` | Creates an `InferenceSession` on the bundled `fixtures/tiny_add.onnx` (125 bytes, `y = x + 1`) and runs it on a numpy array. Calls onnxruntime directly; `rembg` is not used. |
| `pillow_webp` | Encodes and decodes a lossless RGBA WebP in memory and compares alpha and visible pixels. |
| `pillow_heif` | Encodes a 64x64 image to HEIC in memory and decodes it back. If encoding is unavailable it decodes the bundled `fixtures/tiny.heic` instead. `detail.path` says which ran: `encode+decode` or `fixture-decode`. |
| `ffmpeg_frame` | Uses the ffmpeg binary from the `imageio-ffmpeg` wheel to render a 1-second `testsrc` clip into a temp dir, extracts one frame as PNG and opens it with Pillow. When frozen it fails if ffmpeg resolves to anything outside the bundle (imageio-ffmpeg silently falls back to a system `ffmpeg`). |
| `static_file` | Resolves `static/index.html` through `sys._MEIPASS` and reads it. The smoke test also fetches it over HTTP from `/`. |

Other endpoints: `GET /health` returns
`{"status":"ok","version":"0.0.1-spike","model_state":"missing"}`
(`model_state` is a hard-coded placeholder) and `POST /shutdown` stops the
server so the process exits with code 0. The server binds `127.0.0.1` only;
`--port` defaults to 8765.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | The app, the checks and the CLI. |
| `closet_spike.spec` | PyInstaller spec: one-file, console, UPX off. Fails the build if the ffmpeg binary, onnxruntime libraries or libheif libraries are not found. |
| `smoke_test.py` | Standard-library test that drives a built executable. |
| `make_fixture.py` | Regenerates `fixtures/` (dev only, needs `onnx`). |
| `requirements.txt` | Runtime dependencies, exact pins, transitive ones included. |
| `requirements-build.txt` | PyInstaller and its hooks package, exact pins. |
| `fixtures/`, `static/` | Tiny bundled files (125, 466 and 365 bytes). |
| `../../.github/workflows/packaging-spike.yml` | Manual-only CI build and smoke test. |

## Run it locally

Keep the virtualenv and the build output outside the repository.

```sh
python3.12 -m venv /tmp/spike-venv
/tmp/spike-venv/bin/pip install -r requirements.txt -r requirements-build.txt

# from source
/tmp/spike-venv/bin/python app.py --selfcheck
/tmp/spike-venv/bin/python app.py --port 8765

# build the one-file executable (about a minute)
/tmp/spike-venv/bin/python -m PyInstaller --noconfirm --clean \
    --distpath /tmp/spike-dist --workpath /tmp/spike-build closet_spike.spec

# test it (any Python 3.10+; standard library only)
python3 smoke_test.py /tmp/spike-dist/closet-spike
```

On Windows use `py -3.12`, `Scripts\python.exe` and `closet-spike.exe`.
Without `--distpath` / `--workpath` PyInstaller writes `build/` and `dist/`
next to the spec; both are in `.gitignore`.

To regenerate the fixtures: `pip install onnx==1.23.2`, then
`python make_fixture.py`.

## CI

`.github/workflows/packaging-spike.yml` runs **only** from the Actions tab
("Run workflow"). The Windows job always runs on `windows-latest`. The macOS
job runs on `macos-latest` (Apple Silicon) only when the `build_macos` box is
ticked. Each job installs the pins on Python 3.12, builds, prints the
executable's size, lists the bundled native files and runs `smoke_test.py`.
Nothing is uploaded. The only cache is setup-python's pip cache, which is
stored in the same Actions cache storage as `actions/cache`; if that storage
is full the save step only warns.

## Verified locally (Linux x86_64, glibc 2.39)

Built and smoke-tested with both CPython 3.13.18 and CPython 3.12.3. Both passed all five checks
through the CLI and over HTTP, served `/`, and exited 0 after `/shutdown`.

| Python | Executable size | `--selfcheck` wall time | Time to `/health` |
| --- | --- | --- | --- |
| 3.12.3 | 122,225,928 bytes (116.6 MiB) | 2.7 s | 2.5 s |
| 3.13.18 | 127,397,872 bytes (121.5 MiB) | 2.5 s | 2.5 s |

The 3.12 venv held exactly the pinned packages, as CI will. The 3.13 venv
also held the dev-only `onnx` and `pyyaml`, which is why that build is larger.

No trouble with Python 3.13 wheels. HEIC ran the `encode+decode` path. The
fallback path was exercised from source by forcing the encoder to fail. The
smoke test's failure paths were exercised with fake executables (not frozen,
never answers `/health`, exits early, missing file).

Wheels for the exact pins exist for CPython 3.12 on `win_amd64` and macOS
`arm64` (resolved with `pip install --dry-run --platform ...`). The Windows
and macOS wheels of onnxruntime, pillow-heif and imageio-ffmpeg were
downloaded and their file layout inspected to write the spec.

## Not verified

Nothing has been built or run on Windows or macOS, and the workflow has never
been run. Specific things that may bite:

- **Windows, pillow-heif DLLs.** The wheel drops `libheif-*.dll`,
  `libde265-*.dll`, `libx265-*.dll`, `libstdc++-6-*.dll`, `libgcc_s_seh-1-*.dll`
  and `libwinpthread-1-*.dll` loose in the `site-packages` root, not in a
  `.libs` folder. The spec collects them from the wheel's file list into the
  bundle root. Untested.
- **Windows, VC++ runtime.** onnxruntime needs `msvcp140.dll` and
  `vcruntime140_1.dll`. PyInstaller should bundle them, but a GitHub runner
  has them installed system-wide, so a passing CI run does not prove the exe
  starts on a clean PC. Check the "List bundled native files" step, then try
  the exe on a machine without the VC++ redistributable.
- **Windows, antivirus and SmartScreen.** Unsigned one-file executables that
  unpack DLLs and a 105 MB `ffmpeg.exe` into `%TEMP%` are a common false
  positive, and Defender scanning that unpack makes startup slow. Startup
  time on Windows is unknown (2.5 s on Linux).
- **Windows, console window.** The spike is a console build. With
  `console=False`, `sys.stdout` is `None`; `app.py` already redirects to
  `os.devnull` and starts ffmpeg with `CREATE_NO_WINDOW`, but neither was
  exercised.
- **macOS, signing and Gatekeeper.** PyInstaller ad-hoc signs on arm64, which
  is enough on the build machine. A downloaded copy is quarantined and needs
  a Developer ID signature plus notarization, or a manual override. The
  bundled ffmpeg is re-signed by PyInstaller; untested.
- **macOS, minimum version.** The onnxruntime and numpy arm64 wheels are
  tagged `macosx_14_0`, so the result needs macOS 14 or later.
- **macOS, delocate libraries.** The spec places `pillow_heif/.dylibs/*` at
  that same path. If PyInstaller's own analysis places them elsewhere they
  are bundled twice (about 12 MB), which is harmless.
- **macOS `.app` bundle.** The spike builds a bare one-file executable, not a
  `.app`. Bundle layout, `Info.plist` and windowed mode are not covered.
- **Executable sizes on Windows and macOS** are unknown. The ffmpeg binary is
  105 MB on Windows and 52 MB on macOS uncompressed. On Linux it is 173 MB
  uncompressed and takes about 65 MiB of the 117 MiB executable.

## Notes for the real build

- The `imageio-ffmpeg` binary dominates the size and is unpacked to a temp
  dir on every start of a one-file program. Consider a one-folder build, a
  smaller ffmpeg build, or fetching ffmpeg on first use.
- The ffmpeg file name is platform and version specific
  (`ffmpeg-win-x86_64-v9.0.2.exe`, `ffmpeg-macos-aarch64-v9.0`,
  `ffmpeg-linux-x86_64-v9.0.2`). Always ask `imageio_ffmpeg.get_ffmpeg_exe()`;
  never hard-code the name. Reject a result outside the bundle.
- `collect_dynamic_libs("pillow_heif")` finds nothing on Linux or Windows
  because the libraries live outside the package folder. Use the wheel's file
  list (`dist_native_libs` in the spec).
- `collect_dynamic_libs("onnxruntime")` is enough; do not use `collect_all`,
  which drags in `onnxruntime.transformers` / `quantization` / `tools`.
- Use plain `uvicorn` (no `[standard]`), pass the app object rather than an
  import string, and pin `loop="asyncio"`, `http="h11"`. No hidden imports
  beyond the `pyinstaller-hooks-contrib` uvicorn hook were needed this way.
- Stop the server by setting `server.should_exit = True` on a
  `uvicorn.Server` you own; the process then exits 0. If the port is taken
  uvicorn exits the process with code 3, so the real app should pick a free
  port first.
- Lossless WebP does not keep RGB values under fully transparent pixels
  unless saved with `exact=True`. Relevant for cut-out images.
- File uploads will need `python-multipart`, which is not in this spike.
- `setuptools` (about 130 modules) ends up in the bundle. The importer was
  not tracked down; it is a candidate for `excludes` later.
