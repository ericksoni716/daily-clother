"""Finding the address to use from the phone (via Tailscale)."""
from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

_CANDIDATES = [
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    "/usr/local/bin/tailscale",
    "/opt/homebrew/bin/tailscale",
]
_LOCAL = {"127.0.0.1", "localhost"}


def find_tailscale() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    return None


def parse_status(text: str) -> dict:
    """Whether Tailscale is running. This computer's name alone is not Closet's address."""
    data = json.loads(text)
    return {"running": data.get("BackendState") == "Running"}


def _reaches(target: object, port: int) -> bool:
    """Whether a serve target (a proxy URL or a TCP forward) is Closet on this computer."""
    if not isinstance(target, str) or not target:
        return False
    url = urlsplit(target if "://" in target else f"http://{target}")
    try:
        return url.scheme == "http" and (url.hostname or "").lower() in _LOCAL and url.port == port
    except ValueError:
        return False


def parse_serve(text: str, port: int) -> dict:
    """Read `tailscale serve status --json`: where Closet is shared, and which HTTPS ports others use.

    Returns {"closet": (host, https port) or None, "taken": sorted ports used by something else}.
    Only a share of the whole site (path "/") counts: the page uses absolute paths, so a path
    share like /closet would not work.
    """
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        return {"closet": None, "taken": []}
    configs = [data] + [c for c in (data.get("Foreground") or {}).values() if isinstance(c, dict)]
    who: dict[int, set[str]] = {}
    shares: list[tuple[str, int]] = []
    for cfg in configs:
        for key, tcp in (cfg.get("TCP") or {}).items():
            if not str(key).isdigit():
                continue
            seen = who.setdefault(int(key), set())
            forward = (tcp or {}).get("TCPForward")
            if forward:
                seen.add("closet" if _reaches(forward, port) else "other")
        for hostport, web in (cfg.get("Web") or {}).items():
            host, _, p = str(hostport).rpartition(":")
            if not p.isdigit():
                continue
            seen = who.setdefault(int(p), set())
            for path, handler in ((web or {}).get("Handlers") or {}).items():
                if _reaches((handler or {}).get("Proxy"), port):
                    seen.add("closet")
                    if path == "/" and host:
                        shares.append((host, int(p)))
                else:
                    seen.add("other")
    taken = sorted(p for p, seen in who.items() if "other" in seen or not seen)
    closet = min(shares, key=lambda s: (s[1] != 443, s[1])) if shares else None
    return {"closet": closet, "taken": taken}


def address(host: str, https_port: int) -> str:
    return f"https://{host}" if https_port == 443 else f"https://{host}:{https_port}"


def start_command(port: int, taken: list[int]) -> str:
    """A `tailscale serve` command for Closet that does not take a port another app already uses."""
    if 443 not in taken:
        return f"tailscale serve --bg {port}"
    free = next(p for p in itertools.chain((8443, 8444), itertools.count(10000)) if p not in taken)
    return f"tailscale serve --bg --https={free} {port}"


def _run(exe: str, args: list[str], runner) -> str | None:
    kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    r = runner([exe, *args], capture_output=True, encoding="utf-8", errors="replace", timeout=4, **kwargs)
    return r.stdout if r.returncode == 0 else None


def info(port: int, runner=subprocess.run) -> dict:
    """What Settings shows about phone access. Never raises.

    `address` is set only when a Tailscale share really reaches Closet; `stop_command` stops
    that share and no other.
    """
    out = {"tailscale_installed": False, "running": False, "address": None,
           "command": start_command(port, []), "stop_command": None, "others_share": False}
    exe = find_tailscale()
    if not exe:
        return out
    out["tailscale_installed"] = True
    errors = (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError)
    try:
        text = _run(exe, ["status", "--json"], runner)
        if text is not None:
            out.update(parse_status(text))
    except errors:
        pass
    try:
        text = _run(exe, ["serve", "status", "--json"], runner)
        if text is not None:
            serve = parse_serve(text, port)
            out["command"] = start_command(port, serve["taken"])
            out["others_share"] = bool(serve["taken"])
            if serve["closet"]:
                host, https_port = serve["closet"]
                out["address"] = address(host, https_port)
                out["stop_command"] = f"tailscale serve --https={https_port} off"
    except errors:
        pass
    return out
