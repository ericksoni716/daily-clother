"""Packaging spike: a tiny FastAPI app that proves the heavy dependencies
(onnxruntime, Pillow/WebP, pillow-heif, an ffmpeg binary, bundled static files)
survive a PyInstaller one-file build.

Run from source:   python app.py [--port 8765]
Self-check only:   python app.py --selfcheck   (prints JSON, exit 0 if all pass)
"""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable

__version__ = "0.0.1-spike"

DEFAULT_PORT = 8765
STATIC_MARKER = "closet-spike-static-ok"
FROZEN = bool(getattr(sys, "frozen", False))

# A windowed (no console) PyInstaller build has sys.stdout/sys.stderr set to
# None, which breaks uvicorn's logging setup and any print(). The spike is a
# console build, but keep the guard so flipping console=False does not crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def bundle_dir() -> Path:
    """Directory holding bundled read-only resources.

    Frozen: the directory PyInstaller unpacked the one-file archive into
    (sys._MEIPASS). From source: the folder containing this file.
    """
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return bundle_dir().joinpath(*parts)


# --------------------------------------------------------------------------
# Self-checks. Heavy imports live inside each check so that a missing native
# library is reported as a failed check instead of killing the process.
# --------------------------------------------------------------------------


def check_onnxruntime() -> dict[str, Any]:
    import numpy as np
    import onnxruntime as ort

    model = resource_path("fixtures", "tiny_add.onnx")
    session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    x = np.arange(1 * 3 * 4 * 4, dtype=np.float32).reshape(1, 3, 4, 4)
    (y,) = session.run(None, {session.get_inputs()[0].name: x})
    if y.shape != x.shape or not np.allclose(y, x + 1.0):
        raise AssertionError(f"unexpected model output: shape={y.shape}")
    return {
        "onnxruntime": ort.__version__,
        "numpy": np.__version__,
        "providers": ort.get_available_providers(),
        "model": str(model),
    }


def check_pillow_webp() -> dict[str, Any]:
    import PIL
    from PIL import Image, features

    if not features.check("webp"):
        raise RuntimeError("Pillow was built without WebP support")
    raw = bytes(
        v
        for y in range(32)
        for x in range(32)
        for v in (x * 8, y * 8, (x + y) * 4, (x * y) % 256)
    )
    src = Image.frombytes("RGBA", (32, 32), raw)
    buf = io.BytesIO()
    src.save(buf, format="WEBP", lossless=True)
    out = Image.open(io.BytesIO(buf.getvalue()))
    out.load()
    if out.format != "WEBP" or out.mode != "RGBA" or out.size != src.size:
        raise AssertionError(f"bad decode: {out.format} {out.mode} {out.size}")
    got = out.tobytes()
    if got[3::4] != raw[3::4]:
        raise AssertionError("WebP round trip changed the alpha channel")
    # Lossless WebP does not keep RGB under fully transparent pixels unless
    # saved with exact=True, so only compare pixels that are visible.
    for i in range(0, len(raw), 4):
        if raw[i + 3] and got[i : i + 3] != raw[i : i + 3]:
            raise AssertionError(f"lossless WebP changed visible pixel {i // 4}")
    return {"pillow": PIL.__version__, "webp_bytes": buf.tell()}


def check_pillow_heif() -> dict[str, Any]:
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    detail: dict[str, Any] = {
        "pillow_heif": pillow_heif.__version__,
        "libheif": pillow_heif.libheif_version(),
    }

    # Preferred path: encode in memory, decode it back.
    try:
        raw = bytes(v for y in range(64) for x in range(64) for v in (x * 4, y * 4, 128))
        src = Image.frombytes("RGB", (64, 64), raw)
        buf = io.BytesIO()
        src.save(buf, format="HEIF", quality=90)
        out = Image.open(io.BytesIO(buf.getvalue()))
        out.load()
        if out.size != src.size:
            raise AssertionError(f"bad decode size {out.size}")
        r, g, b = out.convert("RGB").getpixel((32, 32))
        if abs(r - 128) > 24 or abs(g - 128) > 24 or abs(b - 128) > 24:
            raise AssertionError(f"decoded pixel far from source: {(r, g, b)}")
        detail.update(path="encode+decode", heic_bytes=buf.tell())
        return detail
    except Exception as exc:  # encoder missing on this platform -> fall back
        detail["encode_error"] = f"{type(exc).__name__}: {exc}"

    # Fallback path: decode the tiny bundled fixture.
    fixture = resource_path("fixtures", "tiny.heic")
    out = Image.open(fixture)
    out.load()
    if out.size != (16, 16):
        raise AssertionError(f"bad fixture decode size {out.size}")
    detail.update(path="fixture-decode", fixture=str(fixture))
    return detail


def _run_quiet(cmd: list[str], timeout: float = 60.0) -> None:
    kwargs: dict[str, Any] = {}
    if sys.platform.startswith("win"):
        # Never flash a console window when the app itself is windowed.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        **kwargs,
    )
    if proc.returncode != 0:
        tail = proc.stdout.decode("utf-8", "replace")[-800:]
        raise RuntimeError(f"{Path(cmd[0]).name} exited {proc.returncode}: {tail}")


def check_ffmpeg_frame() -> dict[str, Any]:
    import imageio_ffmpeg
    from PIL import Image

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    bundled = Path(exe).is_absolute() and bundle_dir() in Path(exe).resolve().parents
    if FROZEN and not bundled:
        # imageio-ffmpeg silently falls back to a system ffmpeg on PATH; in a
        # frozen build that would hide a packaging failure.
        raise RuntimeError(f"ffmpeg resolved outside the bundle: {exe}")
    if os.name == "posix" and Path(exe).is_file() and not os.access(exe, os.X_OK):
        os.chmod(exe, 0o755)

    with tempfile.TemporaryDirectory(prefix="closet-spike-") as tmp:
        clip = os.path.join(tmp, "clip.mp4")
        frame = os.path.join(tmp, "frame.png")
        base = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        _run_quiet(
            base
            + ["-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10"]
            + ["-pix_fmt", "yuv420p", clip]
        )
        _run_quiet(base + ["-ss", "0.5", "-i", clip, "-frames:v", "1", frame])
        with Image.open(frame) as img:
            img.load()
            size, mode, fmt = img.size, img.mode, img.format
        clip_bytes = os.path.getsize(clip)
    if fmt != "PNG" or size != (160, 120):
        raise AssertionError(f"unexpected frame: {fmt} {size}")
    return {
        "imageio_ffmpeg": imageio_ffmpeg.__version__,
        "ffmpeg": imageio_ffmpeg.get_ffmpeg_version(),
        "exe": exe,
        "exe_in_bundle": bundled,
        "clip_bytes": clip_bytes,
        "frame": f"{fmt} {size[0]}x{size[1]} {mode}",
    }


def check_static_file() -> dict[str, Any]:
    index = resource_path("static", "index.html")
    text = index.read_text(encoding="utf-8")
    if STATIC_MARKER not in text:
        raise AssertionError(f"marker {STATIC_MARKER!r} not found in {index}")
    return {
        "path": str(index),
        "bytes": len(text.encode("utf-8")),
        "meipass": getattr(sys, "_MEIPASS", None),
    }


CHECKS: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("onnxruntime", check_onnxruntime),
    ("pillow_webp", check_pillow_webp),
    ("pillow_heif", check_pillow_heif),
    ("ffmpeg_frame", check_ffmpeg_frame),
    ("static_file", check_static_file),
]


def run_selfcheck() -> dict[str, Any]:
    """Run every check. Never raises; each failure is reported as a string."""
    results: dict[str, Any] = {}
    for name, fn in CHECKS:
        started = time.perf_counter()
        try:
            detail = fn()
            entry: dict[str, Any] = {"ok": True, "error": None, "detail": detail}
        except BaseException as exc:  # noqa: BLE001 - includes SystemExit from bad native libs
            if isinstance(exc, KeyboardInterrupt):
                raise
            entry = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=6),
            }
        entry["seconds"] = round(time.perf_counter() - started, 3)
        results[name] = entry
    return {
        "ok": all(entry["ok"] for entry in results.values()),
        "version": __version__,
        "frozen": FROZEN,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "checks": results,
    }


# --------------------------------------------------------------------------
# Web app
# --------------------------------------------------------------------------

_server_holder: dict[str, Any] = {}


def create_app():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="closet-spike", version=__version__, docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "model_state": "missing"}

    @app.get("/selfcheck")
    def selfcheck() -> dict[str, Any]:
        # Sync endpoint: FastAPI runs it in a worker thread, so the event loop
        # (and /health) stays responsive while ffmpeg runs.
        return run_selfcheck()

    @app.post("/shutdown")
    def shutdown() -> dict[str, str]:
        server = _server_holder.get("server")
        if server is not None:
            server.should_exit = True  # uvicorn finishes this response, then stops
        return {"status": "shutting-down"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(resource_path("static", "index.html"), media_type="text/html")

    app.mount("/static", StaticFiles(directory=str(resource_path("static"))), name="static")
    return app


def serve(port: int) -> int:
    import uvicorn

    config = uvicorn.Config(
        create_app(),  # pass the object: import strings do not work when frozen
        host="127.0.0.1",
        port=port,
        log_level="info",
        # Pin the pure-Python implementations so nothing is auto-detected at
        # run time (auto-detection is what usually needs hidden imports).
        loop="asyncio",
        http="h11",
        ws="none",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    _server_holder["server"] = server
    server.run()
    # If the port is already taken uvicorn logs the error and exits the
    # process itself with code 3; we never get here in that case.
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="closet-spike", description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port on 127.0.0.1")
    parser.add_argument(
        "--selfcheck",
        action="store_true",
        help="run the dependency checks, print JSON, exit 0 only if all pass",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    if args.selfcheck:
        report = run_selfcheck()
        print(json.dumps(report, indent=2))
        sys.stdout.flush()
        return 0 if report["ok"] else 1
    return serve(args.port)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
