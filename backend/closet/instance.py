"""Making sure only one copy of the program runs, and choosing its port."""
from __future__ import annotations

import json
import os
import socket
import urllib.request

from .config import Config


def running_instance(cfg: Config) -> int | None:
    """The port of a copy that is already running for this data folder, if any."""
    try:
        port = int(json.loads(cfg.lock_path.read_text())["port"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            if json.loads(r.read()).get("app") == "closet":
                return port
    except Exception:
        pass
    return None


def pick_port(host: str, preferred: int, tries: int = 20) -> int:
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port between {preferred} and {preferred + tries - 1}.")


def write_lock(cfg: Config, port: int) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.lock_path.write_text(json.dumps({"pid": os.getpid(), "port": port}))


def clear_lock(cfg: Config) -> None:
    try:
        if json.loads(cfg.lock_path.read_text()).get("pid") == os.getpid():
            cfg.lock_path.unlink()
    except Exception:
        pass
