"""Finding the address to use from the phone (via Tailscale)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_CANDIDATES = [
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    "/usr/local/bin/tailscale",
    "/opt/homebrew/bin/tailscale",
]


def find_tailscale() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    return None


def parse_status(text: str) -> dict:
    data = json.loads(text)
    me = data.get("Self") or {}
    name = (me.get("DNSName") or "").rstrip(".")
    return {"running": data.get("BackendState") == "Running", "address": f"https://{name}" if name else None}


def info(port: int, runner=subprocess.run) -> dict:
    """What Settings shows about phone access. Never raises."""
    out = {"tailscale_installed": False, "running": False, "address": None,
           "command": f"tailscale serve --bg {port}"}
    exe = find_tailscale()
    if not exe:
        return out
    out["tailscale_installed"] = True
    try:
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        r = runner([exe, "status", "--json"], capture_output=True, encoding="utf-8", errors="replace", timeout=4,
                   **kwargs)
        if r.returncode == 0:
            out.update(parse_status(r.stdout))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return out
