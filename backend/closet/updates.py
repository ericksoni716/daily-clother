"""New releases: checking for one, fetching it, and putting it in place of this program.

Releases are published on this public repository's GitHub page. Once a day (and when the owner presses "Check
now") the program asks GitHub's API which release is the latest, without a token and without anything about the
owner. If it is newer than this program, the packaged program for this computer is downloaded into the data folder
and its SHA-256 compared with the digest GitHub lists for the file; a file that does not match is thrown away and
never run. Installing backs up every closet first, then puts the new program where this one is (the old one is
kept beside it), and starts a small helper (this very program, from its kept copy) that starts the new one and
watches it. The new program hands over through the launcher's usual "newer copy replaces older" path, so the port
and the login stay the same. If it has not answered within a minute, the helper puts the old program back,
starts it, and writes down why.

The owner chooses in Settings: install by themselves, ask first (the default), or never check. Only the packaged
program on Windows or a Mac can replace itself; on Linux, and when running from source, a newer release is only
reported, with a link to its page.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import __version__, backup, db, instance, net
from .config import PROFILES, Config
from .state import State

log = logging.getLogger("closet.updates")

REPO = "ericksoni716/daily-clother"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
USER_AGENT = "Closet-updater"
MODES = ("auto", "ask", "never")
DEFAULT_MODE = "ask"
ASSETS = {"win32": "Closet.exe", "darwin": "Closet-mac-arm64.zip"}   # the release's file for each computer
CHECK_EVERY = 24 * 3600       # a successful check is good for a day
RETRY_AFTER = 3600            # an unanswered check is tried again after an hour
START_WITHIN = 60             # seconds the new program has to answer before the old one is put back
TIDY_WAIT = 90                # how long the new program waits for the helper's verdict before tidying up
NOTES_LINES = 12
NOTES_CHARS = 1500
MAX_ANSWER = 2_000_000        # bytes of GitHub's answer read at most
MAX_DOWNLOAD = 1_500_000_000  # a program larger than this is not what was released
KEEP_SNAPSHOTS = 3            # pre-update copies of each closet kept in the local backups folder
WATCH_COMMAND = "update-watch"

PHASES = ("checking", "downloading", "backing-up", "replacing", "restarting")


class UpdateError(RuntimeError):
    """Something stopped an update; the message is a sentence for the owner."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds(at: str | None) -> float | None:
    try:
        return datetime.strptime(str(at), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# ------------------------------------------------------------------ talking to GitHub
def open_url(url: str, accept: str):
    """An HTTPS answer to read from. Tests replace this so nothing is fetched."""
    if not url.lower().startswith("https://"):
        raise UpdateError("Closet only downloads updates over a secure (https) connection.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept,
                                               "X-GitHub-Api-Version": "2022-11-28"})
    return urllib.request.urlopen(req, timeout=30, context=net.ssl_context())


def _notes(body: object) -> str:
    """The first lines of the release's notes, as plain text (shown as text, never as a web page)."""
    if not isinstance(body, str):
        return ""
    lines = [ln.rstrip() for ln in body.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    text = "\n".join(lines[:NOTES_LINES]).strip()
    if len(text) > NOTES_CHARS:
        text = text[:NOTES_CHARS].rstrip() + "…"
    elif len(lines) > NOTES_LINES and any(ln.strip() for ln in lines[NOTES_LINES:]):
        text += "\n…"
    return text


def parse_release(data: object) -> dict | None:
    """The parts of GitHub's answer Closet uses, or None for anything but a published, final release v<version>."""
    if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v\d+(\.\d+)*", tag):
        return None
    page = data.get("html_url")
    if not isinstance(page, str) or not page.startswith(f"https://github.com/{REPO}/releases/"):
        page = RELEASES_PAGE
    assets = []
    for a in data.get("assets") or []:
        if not isinstance(a, dict):
            continue
        url, name = a.get("browser_download_url"), a.get("name")
        if not isinstance(url, str) or not url.startswith("https://") or not isinstance(name, str):
            continue
        size = a.get("size")
        assets.append({"name": name, "url": url, "size": size if isinstance(size, int) and size > 0 else None,
                       "digest": a.get("digest") if isinstance(a.get("digest"), str) else None})
    published = data.get("published_at")
    return {"version": tag[1:], "notes": _notes(data.get("body")), "page": page,
            "published_at": published if isinstance(published, str) else None, "assets": assets}


def asset_for(release: dict, platform: str) -> dict | None:
    wanted = ASSETS.get(platform)
    return next((a for a in release.get("assets") or [] if a["name"] == wanted), None) if wanted else None


def _expected_sha256(asset: dict) -> str:
    digest = (asset.get("digest") or "").strip().lower()
    algorithm, _, value = digest.partition(":")
    if algorithm != "sha256" or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise UpdateError("GitHub gave no checksum for this download, so Closet will not install it. "
                          "You can still download it by hand from the release page.")
    return value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _read_error(e: BaseException) -> str:
    if isinstance(e, urllib.error.HTTPError):
        remaining = e.headers.get("X-RateLimit-Remaining") if e.headers is not None else None
        if e.code == 429 or (e.code == 403 and remaining == "0"):
            return "GitHub asked Closet to wait before asking again. It will check again later by itself."
        if e.code == 404:
            return "No release of Closet has been published yet."
        return f"GitHub answered with an error ({e.code}). Closet will check again later by itself."
    if net.is_certificate_error(e):
        return ("Closet could not check GitHub's security certificate, so it did not ask. A network that inspects "
                "secure connections can cause this. It will check again later by itself.")
    if isinstance(e, UpdateError):
        return str(e)
    return "Closet could not reach GitHub (this computer may be offline). It will check again later by itself."


# ------------------------------------------------------------------ where the program is, and replacing it
@dataclass(frozen=True)
class Layout:
    """Where the program is installed and where the old one is kept while a new one takes over."""
    platform: str
    installed: Path   # Closet.exe on Windows, Closet.app on a Mac
    old: Path         # Closet.old.exe, Closet.old.app
    inner: Path       # the program inside `installed` that is run (the same path on Windows)

    @property
    def old_program(self) -> Path:
        """The old program to run, once it has been moved aside."""
        return self.old if self.inner == Path(".") else self.old / self.inner

    @property
    def program(self) -> Path:
        return self.installed if self.inner == Path(".") else self.installed / self.inner


def layout(platform: str = sys.platform, executable: str | None = None) -> Layout | None:
    exe = Path(executable or sys.executable).absolute()
    if platform == "win32":
        return Layout(platform, exe, exe.with_name(f"{exe.stem}.old{exe.suffix}"), Path("."))
    if platform == "darwin":
        bundle = next((p for p in exe.parents if p.suffix == ".app"), None)
        if bundle is None:
            return None
        return Layout(platform, bundle, bundle.with_name(f"{bundle.stem}.old.app"), exe.relative_to(bundle))
    return None


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Runs one of the Mac's own tools (ditto, xattr, codesign). Tests replace this."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def swap(where: Layout, package: Path, sha256: str, run=None) -> None:
    """Put the verified `package` where the program is installed; the current one is kept as `where.old`."""
    run = run or _run
    if sha256_file(package) != sha256:   # checked again just before it is used
        raise UpdateError("The downloaded update changed after it was checked, so nothing was installed.")
    if where.old.exists():
        try:
            _remove(where.old)   # left from an earlier update
        except OSError as e:
            raise UpdateError(f"The copy of the old program kept from the last update ({where.old}) could not be removed: {e}")
    if where.platform == "win32":
        staged = where.installed.with_name(f"{where.installed.stem}.new{where.installed.suffix}")
        try:
            shutil.copyfile(package, staged)   # into the same folder, so taking its place is a rename
        except OSError as e:
            raise UpdateError(f"The new program could not be put beside this one ({e}). Nothing was changed.")
        if sha256_file(staged) != sha256:
            staged.unlink(missing_ok=True)
            raise UpdateError("The new program was damaged while it was being put in place. Nothing was changed.")
        _exchange(where, staged)
        return
    if where.platform != "darwin":
        raise UpdateError("Closet can only replace itself on Windows and on a Mac.")
    stage = where.installed.with_name(f".{where.installed.stem}-update")
    shutil.rmtree(stage, ignore_errors=True)
    try:
        stage.mkdir()
        unzip = run(["ditto", "-x", "-k", str(package), str(stage)])
        if unzip.returncode != 0:
            raise UpdateError("The update could not be unpacked. Nothing was changed.")
        apps = [p for p in stage.iterdir() if p.suffix == ".app" and p.is_dir()]
        if len(apps) != 1 or not (apps[0] / where.inner).is_file():
            raise UpdateError("The update did not hold the Closet program. Nothing was changed.")
        new_app = apps[0]
        # only this bundle, which Closet downloaded and checked itself, loses the "downloaded from the internet" mark
        run(["xattr", "-dr", "com.apple.quarantine", str(new_app)])
        signed = run(["codesign", "--verify", "--deep", "--strict", str(new_app)])
        if signed.returncode != 0:
            raise UpdateError("The new program's signature did not check out, so it was not installed.")
        _exchange(where, new_app)
    except OSError as e:
        raise UpdateError(f"The new program could not be put in place ({e}). Nothing was changed.")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _exchange(where: Layout, new: Path) -> None:
    """The running program can be renamed but not overwritten: move it aside, then move the new one in."""
    os.replace(where.installed, where.old)
    try:
        os.replace(new, where.installed)
    except OSError:
        os.replace(where.old, where.installed)
        raise


def restore(where: Layout) -> bool:
    """Put the old program back where it was. False when there is no old program to put back."""
    if not where.old.exists():
        return False
    failed = where.installed.with_name(f"{where.installed.stem}.failed{where.installed.suffix}")
    if where.installed.exists():
        try:
            _remove(failed)
        except OSError:
            pass
        os.replace(where.installed, failed)
    os.replace(where.old, where.installed)
    try:
        _remove(failed)
    except OSError:   # a program that is still running cannot be deleted on Windows; it is tidied next time
        log.info("could not remove %s yet", failed)
    return True


def backup_all(cfg: Config, state: State, version: str) -> dict[str, Path]:
    """A copy of every closet before the program is replaced, with the program's own backup code: SQLite's backup
    into the local backups folder, and the owner's usual backup when a backup folder has been chosen. Returns the
    local copy of each closet, by profile."""
    made: dict[str, Path] = {}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for profile in PROFILES:
        src = cfg.db_path(profile)
        if not src.exists():
            continue
        dest = cfg.local_backups_dir / f"pre-update-{profile}-{version}-{stamp}.sqlite"
        try:
            db.snapshot(src, dest)
        except Exception as e:
            raise UpdateError(f"Your closet could not be backed up before updating ({e}), so nothing was installed.")
        made[profile] = dest
        for old in sorted(cfg.local_backups_dir.glob(f"pre-update-{profile}-*.sqlite"),
                          key=lambda p: p.stat().st_mtime)[:-KEEP_SNAPSHOTS]:
            old.unlink(missing_ok=True)
    if state.get("backup_folder"):
        result = backup.run_backup(cfg, state, kind="update")
        if not result["ok"]:
            raise UpdateError(f"The backup before updating did not work, so nothing was installed: {result['error']}")
    return made


# ------------------------------------------------------------------ starting programs
def clean_env() -> dict:
    """The environment for another program: a packaged program must unpack itself afresh, not reuse ours."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _detached() -> dict:
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True, "env": clean_env()}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return kwargs


def spawn_helper(program: Path, plan_path: Path) -> None:
    subprocess.Popen([str(program), WATCH_COMMAND, str(plan_path)], **_detached())


def start_program(where: Layout, args: list[str]):
    """Start the program installed at `where` with `args`. Returns the process when it is our child."""
    if where.platform == "darwin":
        subprocess.run(["open", "-n", str(where.installed), "--args", *args], timeout=60, check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=clean_env())
        return None
    return subprocess.Popen([str(where.program), *args], **_detached())


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and instance._pid_alive(pid):
        time.sleep(0.2)
    if instance._pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


# ------------------------------------------------------------------ the helper that watches the new program
def outcome_path(cfg: Config) -> Path:
    return cfg.data_dir / "updates" / "outcome.json"


def plan_path(cfg: Config) -> Path:
    return cfg.data_dir / "updates" / "plan.json"


def _write_outcome(cfg: Config, outcome: dict) -> None:
    path = outcome_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _user_version(path: Path) -> int:
    conn = db.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def restore_closets(cfg: Config, snapshots: dict) -> list[str]:
    """Run by the helper (the old program's code) after the new program was stopped: a closet the new program
    already upgraded could no longer be opened by the old one, so it gets its copy from before the update back. The
    upgraded closet is kept beside the backups. Returns the profiles put back."""
    put_back = []
    target = db.latest_version()
    for profile, snap in (snapshots or {}).items():
        if profile not in PROFILES:
            continue
        path, snap = cfg.db_path(profile), Path(snap)
        try:
            if not path.exists() or not snap.is_file() or _user_version(path) <= target:
                continue
            db.snapshot(path, cfg.local_backups_dir / f"upgraded-{profile}-{time.strftime('%Y%m%d-%H%M%S')}.sqlite")
            for extra in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
                extra.unlink(missing_ok=True)
            part = path.with_name(path.name + ".part")
            shutil.copyfile(snap, part)
            part.replace(path)
            put_back.append(profile)
            log.info("put back the %s closet from before the update", profile)
        except Exception:
            log.exception("could not put back the %s closet from %s", profile, snap)
    return put_back


def watch(cfg: Config, plan: dict, start=None, timeout: float | None = None, poll: float = 0.5) -> bool:
    """Run by the helper: start the new program and wait for it. If it has not written its lock file and answered
    /api/health as the new version within `timeout` seconds, stop it, put the old program back, start that, and
    write down why. True when the new program took over."""
    start = start or start_program
    where = Layout(plan["platform"], Path(plan["installed"]), Path(plan["old"]), Path(plan["inner"]))
    timeout = plan.get("timeout", START_WITHIN) if timeout is None else timeout
    log.info("starting Closet %s in place of %s", plan["to"], plan["from"])
    proc, problem = None, None
    try:
        proc = start(where, list(plan["args"]) + ["--replace"])
    except Exception as e:
        problem = f"it could not be started ({e})"
    deadline = time.monotonic() + timeout
    while problem is None and time.monotonic() < deadline:
        info = instance.running_info(cfg)
        if info and info["version"] == plan["to"] and info.get("pid") != plan.get("old_pid"):
            log.info("Closet %s is running", plan["to"])
            _write_outcome(cfg, {"at": _now(), "from": plan["from"], "to": plan["to"], "ok": True, "note": None})
            return True
        if proc is not None and proc.poll() is not None and proc.returncode not in (0, None):
            problem = f"it stopped by itself (exit code {proc.returncode})"
            break
        time.sleep(poll)
    problem = problem or f"it did not answer within {timeout:g} seconds"
    log.warning("Closet %s did not start: %s; going back to %s", plan["to"], problem, plan["from"])
    try:
        lock = json.loads(cfg.lock_path.read_text())
        pid = lock.get("pid")
        if isinstance(pid, int) and pid not in (plan.get("old_pid"), os.getpid()) and instance._pid_alive(pid):
            _kill(pid)
    except Exception:
        pass
    if proc is not None and proc.poll() is None:
        _kill(proc.pid)
    note = f"Closet {plan['to']} was installed but did not start: {problem}. "
    try:
        restore(where)
    except OSError as e:
        log.exception("could not put the old program back")
        note += (f"The old program could not be put back by itself ({e}); it was kept as {where.old}. "
                 "Download Closet again from the releases page.")
        _write_outcome(cfg, {"at": _now(), "from": plan["from"], "to": plan["to"], "ok": False, "note": note})
        return False
    still = instance.running_info(cfg)
    if still and still.get("pid") == plan.get("old_pid"):
        note += f"Closet {plan['from']} kept running and is still in place."
    else:
        if restore_closets(cfg, plan.get("snapshots") or {}):
            note += "Your closet was put back as it was just before the update. "
        try:
            start(where, [a for a in plan["args"] if a != "--replace"])
            note += f"Closet {plan['from']} was put back and started again."
        except Exception as e:
            note += f"Closet {plan['from']} was put back; start it again yourself ({e})."
    _write_outcome(cfg, {"at": _now(), "from": plan["from"], "to": plan["to"], "ok": False, "note": note})
    return False


def run_watch(plan_file: str) -> int:
    """The helper's entry point (`closet update-watch PLAN`)."""
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    from .config import load
    base = load()
    cfg = Config(Path(plan["data_dir"]), base.host, base.port, base.auto_download_model)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(cfg.logs_dir / "updater.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    ok = watch(cfg, plan)
    Path(plan_file).unlink(missing_ok=True)
    return 0 if ok else 1


# ------------------------------------------------------------------ the updater in the running program
class Updater:
    """Checks for releases, fetches and checks the download, and installs it. One step at a time."""

    def __init__(self, cfg: Config, state: State, *, version: str = __version__, platform: str = sys.platform,
                 frozen: bool | None = None, executable: str | None = None, check_every: float = 1800,
                 spawn=None, run=None):
        self.cfg, self.state, self.version, self.platform = cfg, state, version, platform
        self.frozen = is_frozen() if frozen is None else frozen
        self.executable = executable or sys.executable
        self.check_every = check_every
        self.spawn = spawn or spawn_helper
        self.run = run
        self.launch_args: list[str] = []   # how this copy was started (set by the launcher), for the new one
        self.busy: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---------------------------------------------------------------- what the owner sees
    @property
    def where(self) -> Layout | None:
        return layout(self.platform, self.executable)

    @property
    def can_install(self) -> bool:
        return self.frozen and self.platform in ASSETS and self.where is not None

    def mode(self) -> str:
        mode = self.state.get("update_mode")
        return mode if mode in MODES else DEFAULT_MODE

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError("Choose to install updates by themselves, to be asked first, or never to check.")
        self.state.update(update_mode=mode)

    def available(self) -> dict | None:
        """The newest release found, if it is newer than this program."""
        release = (self.state.get("update_check") or {}).get("available")
        if isinstance(release, dict) and instance.is_newer(str(release.get("version")), self.version):
            return release
        return None

    def last_install(self) -> dict | None:
        """How the last update went; the helper writes it into a file of its own, taken in here."""
        path = outcome_path(self.cfg)
        try:
            outcome = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            outcome = None
        if isinstance(outcome, dict):
            self.state.update(update_install=outcome)
            path.unlink(missing_ok=True)
            if not outcome.get("ok") and self.busy == "restarting":
                self.busy = None   # the helper went back to this copy, which is still running
        return self.state.get("update_install")

    def status(self) -> dict:
        last = self.last_install()
        check = self.state.get("update_check") or {}
        release = self.available()
        ready = self.state.get("update_ready") or {}
        problem = self.state.get("update_problem") or {}
        asset = asset_for(release, self.platform) if release else None
        return {
            "version": self.version,
            "mode": self.mode(),
            "can_install": self.can_install,
            "checked_at": check.get("at"),
            "check_error": None if check.get("ok", True) else check.get("error"),
            "latest": check.get("latest"),
            "available": {k: release.get(k) for k in ("version", "notes", "page", "published_at")} if release else None,
            "download_size": asset.get("size") if asset else None,
            "ready": bool(release and self.can_install and ready.get("version") == release["version"]
                          and Path(str(ready.get("path"))).is_file()),
            "problem": problem.get("note") if release and problem.get("version") == release["version"] else None,
            "busy": self.busy,
            "last_install": last,
            "releases_page": RELEASES_PAGE,
        }

    # ---------------------------------------------------------------- checking
    def check(self) -> dict:
        """Ask GitHub for the latest release and remember the answer. Never raises; problems are noted quietly."""
        if not self._lock.acquire(blocking=False):
            return self.status()
        try:
            self._check()
        finally:
            self._lock.release()
        return self.status()

    def _check(self) -> None:
        previous = self.state.get("update_check") or {}
        self.busy = "checking"
        try:
            with open_url(API_URL, "application/vnd.github+json") as answer:
                data = json.loads(answer.read(MAX_ANSWER))
            release = parse_release(data)
            newer = release if release and instance.is_newer(release["version"], self.version) else None
            self.state.update(update_check={"at": _now(), "ok": True, "error": None,
                                            "latest": release["version"] if release else None, "available": newer})
            if newer:
                log.info("Closet %s is out (this is %s)", newer["version"], self.version)
        except Exception as e:
            error = _read_error(e)
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:   # nothing published yet: an answer, not a failure
                self.state.update(update_check={"at": _now(), "ok": True, "error": None, "latest": None, "available": None})
            else:
                log.info("update check did not get an answer: %s", e)
                self.state.update(update_check={**previous, "ok": False, "error": error, "failed_at": _now(),
                                                "at": previous.get("at")})
        finally:
            self.busy = None

    def due(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        check = self.state.get("update_check") or {}
        if not check.get("ok", True) and check.get("failed_at"):
            failed = _seconds(check["failed_at"])
            return failed is None or now - failed >= RETRY_AFTER
        last = _seconds(check.get("at"))
        return last is None or now - last >= CHECK_EVERY

    # ---------------------------------------------------------------- download and install
    def _problem(self, version: str, note: str) -> None:
        log.warning("update to %s: %s", version, note)
        self.state.update(update_problem={"version": version, "at": _now(), "note": note})

    def prepare(self, release: dict) -> Path:
        """Download this computer's file of `release` into the data folder and check it against GitHub's digest."""
        asset = asset_for(release, self.platform)
        if asset is None:
            raise UpdateError(f"Closet {release['version']} has no download for this computer.")
        expected = _expected_sha256(asset)
        folder = self.cfg.data_dir / "updates"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{release['version']}-{asset['name']}"
        ready = self.state.get("update_ready") or {}
        if dest.is_file() and ready.get("path") == str(dest) and sha256_file(dest) == expected:
            return dest
        for old in folder.iterdir():   # older downloads and a half-finished one
            if old.is_file() and old.name not in ("outcome.json", "plan.json"):
                old.unlink(missing_ok=True)
        part = dest.with_name(dest.name + ".part")
        h, total = hashlib.sha256(), 0
        limit = min(asset["size"] or MAX_DOWNLOAD, MAX_DOWNLOAD)
        try:
            with open_url(asset["url"], "application/octet-stream") as answer, open(part, "wb") as out:
                while chunk := answer.read(1 << 20):
                    total += len(chunk)
                    if total > limit:
                        raise UpdateError("The download was larger than the release said, so it was thrown away.")
                    h.update(chunk)
                    out.write(chunk)
        except UpdateError:
            part.unlink(missing_ok=True)
            raise
        except Exception as e:
            part.unlink(missing_ok=True)
            raise UpdateError("The update could not be downloaded: " + _read_error(e).replace(
                " It will check again later by itself.", " Try again later."))
        if h.hexdigest() != expected:
            part.unlink(missing_ok=True)
            raise UpdateError("The download did not match the checksum GitHub gave for it, so it was thrown away and "
                              "nothing was installed.")
        os.replace(part, dest)
        self.state.update(update_ready={"version": release["version"], "path": str(dest), "sha256": expected,
                                        "at": _now()}, update_problem=None)
        log.info("downloaded and checked Closet %s (%d bytes)", release["version"], total)
        return dest

    def _fetch(self, release: dict) -> Path | None:
        self.busy = "downloading"
        try:
            return self.prepare(release)
        except UpdateError as e:
            self._problem(release["version"], str(e))
            return None
        finally:
            self.busy = None

    def install(self, release: dict) -> None:
        """Back up, put the new program in place, and start the helper that hands over to it. Raises UpdateError."""
        where = self.where
        if not self.can_install or where is None:
            raise UpdateError("Only the downloaded Closet program on Windows or a Mac can update itself. "
                              "Download the new version from the release page.")
        self.busy = "downloading"
        package = self.prepare(release)
        expected = (self.state.get("update_ready") or {}).get("sha256") or ""
        self.busy = "backing-up"
        snapshots = backup_all(self.cfg, self.state, self.version)
        self.busy = "replacing"
        swap(where, package, expected, run=self.run)
        plan = {"from": self.version, "to": release["version"], "platform": where.platform,
                "installed": str(where.installed), "old": str(where.old), "inner": str(where.inner),
                "args": list(self.launch_args), "old_pid": os.getpid(), "data_dir": str(self.cfg.data_dir),
                "timeout": START_WITHIN, "snapshots": {k: str(v) for k, v in snapshots.items()}}
        path = plan_path(self.cfg)
        path.write_text(json.dumps(plan, indent=1), encoding="utf-8")
        outcome_path(self.cfg).unlink(missing_ok=True)
        try:
            self.spawn(where.old_program, path)
        except Exception as e:
            restore(where)
            raise UpdateError(f"Closet could not start the new version ({e}), so it put this one back.")
        self.busy = "restarting"
        log.info("handing over to Closet %s", release["version"])

    def install_now(self) -> dict:
        """Start installing the release found (in the background). Raises UpdateError when it cannot start."""
        release = self.available()
        if release is None:
            raise UpdateError("There is no newer version to install.")
        if not self.can_install:
            raise UpdateError("Only the downloaded Closet program on Windows or a Mac can update itself. "
                              "Download the new version from the release page.")
        if not self._lock.acquire(blocking=False):
            raise UpdateError("Closet is already checking for or installing an update.")
        self.busy = "downloading"

        def job() -> None:
            try:
                self.install(release)
            except UpdateError as e:
                self.busy = None
                self._problem(release["version"], str(e))
            except Exception as e:
                self.busy = None
                log.exception("update failed")
                self._problem(release["version"], f"The update did not finish: {e}")
            finally:
                self._lock.release()
        threading.Thread(target=job, name="update-install", daemon=True).start()
        return self.status()

    # ---------------------------------------------------------------- once a day, by itself
    def tick(self, now: float | None = None) -> None:
        """Check when due, fetch a newer release ahead of time, and install it when the owner chose that."""
        if self.mode() == "never" or not self.frozen:
            return
        if self.due(now):
            self.check()
        release = self.available()
        if release is None or not self.can_install:
            return
        last = self.last_install() or {}   # also takes in the helper's verdict on an update that was undone
        if last.get("to") == release["version"] and last.get("ok") is False:
            return   # this version already failed to start here; the owner can still choose Install
        problem = self.state.get("update_problem") or {}
        checked = _seconds((self.state.get("update_check") or {}).get("at")) or 0
        if problem.get("version") == release["version"] and (_seconds(problem.get("at")) or 0) >= checked:
            return   # it went wrong since the last check; tried again after the next one, not every half hour
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self.status()["ready"] or self._fetch(release):
                if self.mode() == "auto":
                    try:
                        self.install(release)
                    except UpdateError as e:
                        self.busy = None
                        self._problem(release["version"], str(e))
        finally:
            self._lock.release()

    def tidy(self, wait: float = TIDY_WAIT) -> None:
        """Run by the new program once it is up: wait for the helper's verdict, then remove the old program it kept
        and the download it came from."""
        where = self.where
        self.last_install()
        if where is not None and self.frozen and where.old.exists():
            deadline = time.monotonic() + wait
            while not self._stop.is_set() and time.monotonic() < deadline:
                last = self.last_install() or {}
                if last.get("to") == self.version and last.get("ok"):
                    break
                self._stop.wait(1)
            deadline = time.monotonic() + 60
            while not self._stop.is_set():   # on Windows the helper's copy is in use until the helper has quit
                try:
                    _remove(where.old)
                    log.info("removed the old program %s", where.old)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        log.info("could not remove %s; it will be tried again next time", where.old)
                        break
                    self._stop.wait(2)
        if where is not None and self.frozen:
            failed = where.installed.with_name(f"{where.installed.stem}.failed{where.installed.suffix}")
            try:
                _remove(failed)
            except OSError:
                pass
        folder = self.cfg.data_dir / "updates"
        ready = self.state.get("update_ready") or {}
        if ready.get("version") and not instance.is_newer(str(ready["version"]), self.version):
            Path(str(ready.get("path"))).unlink(missing_ok=True)
            self.state.update(update_ready=None)
        if folder.is_dir():
            for f in folder.glob("*.part"):
                f.unlink(missing_ok=True)

    def start(self, first_after: float = 60) -> None:
        def loop() -> None:
            self._stop.wait(first_after)   # let the program settle first
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    log.exception("update check failed")
                self._stop.wait(self.check_every)

        def tidy() -> None:
            try:
                self.tidy()
            except Exception:
                log.exception("tidying after an update failed")
        for target, name in ((loop, "update-checker"), (tidy, "update-tidy")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
