"""Making sure only one copy of the program runs, and choosing its port.

A copy is either an ordinary one (the window, or the browser, in the same process as the server) or a background copy
(`Nines --background`: the server alone, nothing shown). Its lock file says which. Opened beside a background copy,
the program is only a window onto it, in a process of its own, and keeps a small lock file of its own (the window's
door, below) so that opening the program again brings that window forward instead of making a second one."""
from __future__ import annotations

import errno
import hmac
import json
import os
import re
import secrets
import signal
import socket
import threading
import time
import urllib.request
from contextlib import contextmanager

from .config import Config

# the header another copy of the program sends to ask this one to quit or to show its window; its value is the token
# in the lock file
QUIT_HEADER = "X-Closet-Instance-Token"


@contextmanager
def startup_lock(cfg: Config, timeout: float = 60):
    """Serialize launches until the first copy can answer. Closing (or crashing) releases the OS lock."""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    # Keep this file: unlinking it would let another launch lock a different file at the same path.
    with open(cfg.lock_path.with_suffix(".startup"), "a+b") as guard:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    guard.seek(0)
                    msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another copy of Nines is still starting. Try opening it again in a moment.")
                time.sleep(0.05)
        yield guard.close


def running_info(cfg: Config) -> dict | None:
    """The copy already running for this data folder, if any: its port, version and process id."""
    try:
        lock = json.loads(cfg.lock_path.read_text())
        port = int(lock["port"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            health = json.loads(r.read())
        if health.get("app") == "closet":
            return {"port": port, "version": str(health.get("version") or ""), "pid": lock.get("pid"),
                    "token": lock.get("token"), "background": lock.get("background") is True}
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


def show_running(info: dict) -> bool:
    """Ask the copy described by `info` to show its window, as `stop_running` asks it to quit (with the token from its
    lock file). True when it did; False when it has no window to show (it uses the browser, it runs without a window,
    or it is from before Nines had one), and the browser should be opened instead."""
    if not info.get("token"):
        return False
    _allow_foreground(info.get("pid"))
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/instance/show", method="POST", data=b"",
                                     headers={QUIT_HEADER: str(info["token"])})
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200 and json.loads(r.read()).get("shown") is True
    except Exception:
        return False


def _allow_foreground(pid) -> None:
    """Windows only lets a program bring its window to the front when the owner was just using it. This program was
    just opened by the owner, so it may hand that permission on to the process that will show its window."""
    if os.name == "nt" and isinstance(pid, int) and pid > 0:
        try:
            import ctypes
            ctypes.WinDLL("user32").AllowSetForegroundWindow(pid)
        except Exception:
            pass


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


def write_lock(cfg: Config, port: int, background: bool = False) -> None:
    """`background`: this copy is a background copy, with no window to show (a launch beside it opens a window onto it)."""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    lock = {"pid": os.getpid(), "port": port, "token": secrets.token_urlsafe(32)}
    if background:
        lock["background"] = True
    cfg.lock_path.write_text(json.dumps(lock))


def clear_lock(cfg: Config) -> None:
    try:
        if json.loads(cfg.lock_path.read_text()).get("pid") == os.getpid():
            cfg.lock_path.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------- the window's door
# A window-only process (the program opened beside a background copy) listens on a loopback port of its own for one
# request: show your window. Its lock file holds its process id, that port and a random token; only something that can
# read the closet's folder can ask, as with the token in the main lock file. A lock whose process has gone, whose port
# does not answer or whose answer is not "shown" is stale, and the next window-only process writes its own over it.

def window_lock_path(cfg: Config):
    return cfg.lock_path.with_name("closet-window.lock")


class WindowDoor:
    """The listening side, in the window-only process. `on_show()` shows the window; True when it did. `commands` are
    the other requests it takes, by name ("off": stop keeping Nines running, which Windows asks about on this screen,
    closet/background.py); each starts its work and returns True when it took the request."""

    def __init__(self, cfg: Config, on_show, commands: dict | None = None):
        self.cfg = cfg
        self.on_show = on_show
        self.commands = dict(commands or {})
        self.token = secrets.token_urlsafe(32)
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(4)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        path = window_lock_path(cfg)
        part = path.with_suffix(".part")
        part.write_text(json.dumps({"pid": os.getpid(), "port": self.port, "token": self.token}))
        os.replace(part, path)
        self._thread = threading.Thread(target=self._serve, name="window-door", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:   # socket.timeout
                continue
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(3)
                    given, _, command = conn.makefile("rb").readline(256).strip().partition(b" ")
                    if not hmac.compare_digest(given, self.token.encode("ascii")):
                        conn.sendall(b"no\n")
                        continue
                    if not command:
                        conn.sendall(b"shown\n" if self.on_show() else b"no\n")
                        continue
                    work = self.commands.get(command.decode("ascii", "replace"))
                    conn.sendall(b"ok\n" if work is not None and work() else b"no\n")
                except Exception:
                    pass

    def close(self) -> None:
        """Stop answering and remove the lock file, if it is still this process's."""
        if self._stop.is_set():
            return
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            path = window_lock_path(self.cfg)
            if json.loads(path.read_text()).get("pid") == os.getpid():
                path.unlink()
        except Exception:
            pass


def show_window_process(cfg: Config, timeout: float = 3.0) -> bool:
    """Ask the window-only process already open for this closet to bring its window forward. False when there is none
    (no lock, a stale one, or a window that could not be shown), and this launch should open its own."""
    return ask_window_process(cfg, None, timeout)


def ask_window_process(cfg: Config, command: str | None, timeout: float = 3.0) -> bool:
    """Send `command` to the window-only process open for this closet (None: show your window). True when it took it."""
    try:
        lock = json.loads(window_lock_path(cfg).read_text())
        pid, port, token = lock["pid"], int(lock["port"]), str(lock["token"])
    except Exception:
        return False
    if not isinstance(pid, int) or pid <= 0 or not _pid_alive(pid):
        return False
    if command is None:
        _allow_foreground(pid)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.settimeout(timeout)
            conn.sendall(token.encode("ascii") + (b" " + command.encode("ascii") if command else b"") + b"\n")
            return conn.makefile("rb").readline(64).strip() == (b"ok" if command else b"shown")
    except Exception:
        return False
