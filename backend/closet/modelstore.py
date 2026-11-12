"""The background-removal model file: missing, downloading, failed or ready.

The model is about 170 MB, so it is downloaded into the data folder on first
run rather than shipped inside the program. Downloads resume where they
stopped, and the finished file must match a pinned checksum. A file dropped
into the models folder by hand is checked the same way.
"""
from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import net
from .cutout import MODELS, sha256_of
from .state import State

log = logging.getLogger("closet.model")

MODEL = "isnet-general-use"
USER_AGENT = "Closet/1 (model download)"


class ModelStore:
    def __init__(self, models_dir: Path, state: State, on_ready: Callable[[], None] | None = None,
                 name: str = MODEL, sha256: str | None = None, default_url: str | None = None):
        self.dir, self.state, self.name = models_dir, state, name
        self.sha256 = sha256 or MODELS[name].sha256
        self.default_url = default_url or MODELS[name].url
        self.on_ready = on_ready
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status = "missing"
        self._error: str | None = None
        self._done = 0
        self._total: int | None = None
        self._cancel = threading.Event()

    # ---- paths
    @property
    def path(self) -> Path:
        return self.dir / f"{self.name}.onnx"

    @property
    def _part(self) -> Path:
        return self.dir / f"{self.name}.onnx.part"

    @property
    def _marker(self) -> Path:
        return self.dir / f"{self.name}.onnx.verified"

    @property
    def url(self) -> str:
        return self.state.get("model_url") or self.default_url

    # ---- state
    def refresh(self) -> None:
        """Work out the state from what is on disk (also verifies a hand-placed file)."""
        with self._lock:
            if self._status == "downloading":
                return
            if self.path.exists():
                if self._marker.exists() and self._marker.read_text().strip() == self.sha256:
                    self._status, self._error = "ready", None
                    return
                self._verify_locked()
                return
            self._status = "failed" if self._error else "missing"
            self._done = self._part.stat().st_size if self._part.exists() else 0

    def _verify_locked(self) -> None:
        digest = sha256_of(self.path)
        if digest == self.sha256:
            self._marker.write_text(self.sha256)
            self._status, self._error = "ready", None
        else:
            self._status = "failed"
            self._error = ("The model file in the data folder is not the expected file (checksum mismatch). "
                           "Delete it and download again.")

    def info(self) -> dict:
        with self._lock:
            return {"state": self._status, "downloaded_bytes": self._done, "total_bytes": self._total,
                    "error": self._error, "url": self.url, "path": str(self.path), "sha256": self.sha256,
                    "name": self.name}

    @property
    def ready(self) -> bool:
        return self._status == "ready"

    # ---- download
    def start_download(self) -> bool:
        """Begin or resume the download in the background. False if not needed."""
        with self._lock:
            if self._status in ("ready", "downloading"):
                return False
            self._status, self._error = "downloading", None
            self._cancel.clear()
            self._thread = threading.Thread(target=self._download, name="model-download", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _fail(self, message: str) -> None:
        with self._lock:
            self._status, self._error = "failed", message

    def _download(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        have = self._part.stat().st_size if self._part.exists() else 0
        req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=30, context=net.ssl_context()) as resp:
                if have and resp.status != 206:  # server ignored the range: start over
                    have = 0
                length = resp.headers.get("Content-Length")
                with self._lock:
                    self._done = have
                    self._total = have + int(length) if length else None
                with open(self._part, "ab" if have else "wb") as f:
                    while True:
                        if self._cancel.is_set():
                            self._fail("The download was stopped. It will continue from where it left off.")
                            return
                        chunk = resp.read(1 << 18)
                        if not chunk:
                            break
                        f.write(chunk)
                        with self._lock:
                            self._done += len(chunk)
        except urllib.error.HTTPError as e:
            if e.code == 416:  # the partial file is already complete (or longer than the real one)
                pass
            else:
                self._fail(f"The download server answered with an error ({e.code}). Check the download address in "
                           "Settings, or place the model file by hand (see the README).")
                return
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("model download failed: %s: %s", type(e).__name__, e)
            if net.is_certificate_error(e):
                self._fail("The download server's security certificate could not be checked on this computer, so "
                           "nothing was downloaded. If this is a work computer or network, try another network, "
                           "or place the model file by hand (see the README).")
                return
            self._fail("Could not reach the download server. Check the internet connection and try again; "
                       "the download continues from where it stopped. Photos you add meanwhile are kept and "
                       "will be processed once the model is here.")
            return
        with self._lock:
            total, done = self._total, self._done
        if total is not None and done < total:
            self._fail("The connection dropped before the download finished. Try again to continue it.")
            return
        digest = sha256_of(self._part)
        if digest != self.sha256:
            self._part.unlink(missing_ok=True)
            with self._lock:
                self._done = 0
            self._fail("The downloaded file did not match its checksum and was discarded. Try again; if it keeps "
                       "failing, check the download address in Settings.")
            return
        self._part.replace(self.path)
        self._marker.write_text(self.sha256)
        with self._lock:
            self._status, self._error = "ready", None
        if self.on_ready:
            self.on_ready()
