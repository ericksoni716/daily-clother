"""Making sure only one copy of the program runs, and choosing its port."""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import signal
import socket
import time
import urllib.request

from .config import Config

# the header a newer copy sends to ask this one to quit; its value is the token in the lock file
QUIT_HEADER = "X-Closet-Instance-Token"


def running_info(cfg: Config) -> dict | None:
    """The copy already running for this data folder, if any: its port, version and process id."""
    try:
        lock = json.loads(cfg.lock_path.read_text())
        port = int(lock["port"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            health = json.loads(r.read())
        if health.get("app") == "closet":
            return {"port": port, "version": str(health.get("version") or ""), "pid": lock.get("pid"),
                    "token": lock.get("token")}
    except Exception:
        pass
    return None


def running_instance(cfg: Config) -> int | None:
    """The port of a copy that is already running for this data folder, if any."""
    info = running_info(cfg)
    return info["port"] if info else None


def _release(version: str) -> tuple[int, ...] | None:
    """(0, 2, 0) for "0.2.0"; None for a version that is not a plain release, such as "0.1.0-dev"."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", version.strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_newer(mine: str, theirs: str) -> bool:
    """Whether release `mine` is newer than release `theirs`. Unknown or development versions are never newer."""
    a, b = _release(mine), _release(theirs)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        # its own copy of kernel32 with the types declared, so a handle is not cut to 32 bits on 64-bit Windows
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_running(cfg: Config, info: dict, timeout: float = 20.0) -> bool:
    """Ask the copy described by `info` to quit, and wait until it has. True once it has gone.

    A copy from this version on quits cleanly when asked with the token from its lock file. An older copy
    has no way to be asked, so it is stopped by its process id: on a Mac that is the same as Quit (it
    handles the signal), on Windows the process is ended."""
    port, pid = info["port"], info.get("pid")
    asked = False
    if info.get("token"):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/instance/quit", method="POST", data=b"",
                                         headers={QUIT_HEADER: str(info["token"])})
            with urllib.request.urlopen(req, timeout=3) as r:
                asked = r.status == 202
        except Exception:
            asked = False
    if not asked:
        if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gone_pid = not isinstance(pid, int) or not _pid_alive(pid)
        if gone_pid and running_instance(cfg) is None:
            return True
        time.sleep(0.25)
    return False


def quit_token_matches(cfg: Config, given: str | None) -> bool:
    """Whether `given` is the quit token this very process wrote into the lock file."""
    if not given:
        return False
    try:
        lock = json.loads(cfg.lock_path.read_text())
    except Exception:
        return False
    token = lock.get("token")
    return lock.get("pid") == os.getpid() and isinstance(token, str) and hmac.compare_digest(token, given)


def port_free(host: str, port: int) -> bool:
    """Whether the server could listen on `port`. Like the server, a port whose last connections are still
    closing counts as free (except on Windows, where that option means something else and is not needed)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    """After an older copy has quit, give the system a moment to let go of its port."""
    deadline = time.monotonic() + timeout
    while not port_free(host, port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.25)
    return True


def pick_port(host: str, preferred: int, tries: int = 20) -> int:
    for port in range(preferred, preferred + tries):
        if port_free(host, port):
            return port
    raise RuntimeError(f"No free port between {preferred} and {preferred + tries - 1}.")


def write_lock(cfg: Config, port: int) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.lock_path.write_text(json.dumps({"pid": os.getpid(), "port": port, "token": secrets.token_urlsafe(32)}))


def clear_lock(cfg: Config) -> None:
    try:
        if json.loads(cfg.lock_path.read_text()).get("pid") == os.getpid():
            cfg.lock_path.unlink()
    except Exception:
        pass
