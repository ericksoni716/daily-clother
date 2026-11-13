"""New releases: checked with a stand-in for GitHub's API, fetched and checked, and installed in a temp folder
with stand-in programs. Nothing here reaches the network or replaces a real program."""
import hashlib
import io
import json
import socket
import subprocess
import sys
import textwrap
import threading
import time
import urllib.error
import zipfile
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest

from closet import cli, instance, updates

NEW_EXE = b"the new program, 0.3.0"
OLD_EXE = b"the program running now, 0.2.1"


def asset(name: str, data: bytes, digest: str | None = "right") -> dict:
    url = f"https://github.com/ericksoni716/daily-clother/releases/download/v0.3.0/{name}"
    entry = {"name": name, "browser_download_url": url, "size": len(data)}
    if digest == "right":
        entry["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
    elif digest is not None:
        entry["digest"] = digest
    return entry


def release(version="0.3.0", draft=False, prerelease=False, assets=None, body="Faster outfits.\n\nFixes a crash."):
    return {"tag_name": f"v{version}", "draft": draft, "prerelease": prerelease, "body": body,
            "html_url": f"https://github.com/ericksoni716/daily-clother/releases/tag/v{version}",
            "published_at": "2026-11-20T10:00:00Z",
            "assets": assets if assets is not None else [asset("Closet.exe", NEW_EXE)]}


class FakeGitHub:
    """Stands in for GitHub: the releases API answers `latest`, and downloads come from `files`."""

    def __init__(self, latest=None):
        self.latest = latest if latest is not None else release()
        self.files = {}
        self.fail: BaseException | None = None
        self.asked: list[str] = []

    def add(self, entry: dict, data: bytes) -> None:
        self.files[entry["browser_download_url"]] = data

    def __call__(self, url, accept):
        self.asked.append(url)
        if url == updates.API_URL:
            if self.fail is not None:
                raise self.fail
            return io.BytesIO(json.dumps(self.latest).encode())
        if url in self.files:
            return io.BytesIO(self.files[url])
        raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)


@pytest.fixture
def github(monkeypatch):
    gh = FakeGitHub()
    gh.add(gh.latest["assets"][0], NEW_EXE)
    monkeypatch.setattr(updates, "open_url", gh)
    return gh


@pytest.fixture
def program(tmp_path):
    """A stand-in for the packaged program on Windows, in a folder of its own."""
    folder = tmp_path / "Programs"
    folder.mkdir()
    exe = folder / "Closet.exe"
    exe.write_bytes(OLD_EXE)
    return exe


@pytest.fixture
def updater(services, program):
    """The services' updater as if this were Closet 0.2.1, packaged, on Windows; the helper is never really started."""
    u = services.updater
    u.version, u.platform, u.frozen, u.executable = "0.2.1", "win32", True, str(program)
    u.launch_args = ["--no-browser", "--port", "8765"]
    u.spawned = []
    u.spawn = lambda prog, plan: u.spawned.append((prog, json.loads(Path(plan).read_text())))
    return u


def wait_idle(u, timeout=10):
    deadline = time.monotonic() + timeout
    while u.busy not in (None, "restarting") and time.monotonic() < deadline:
        time.sleep(0.02)
    time.sleep(0.05)


# ------------------------------------------------------------------ checking
def test_only_a_newer_final_release_counts(updater, github):
    for latest, expected in (("0.3.0", "0.3.0"), ("0.2.1", None), ("0.2.0", None), ("0.10.0", "0.10.0")):
        github.latest = release(latest)
        updater.check()
        assert (updater.available() or {}).get("version") == expected, latest
        assert updater.status()["latest"] == latest
    # a draft or a prerelease is never offered, whatever its number
    for odd in (release("0.9.0", draft=True), release("0.9.0", prerelease=True), {"tag_name": "nightly"}, [], "oops"):
        github.latest = odd
        updater.check()
        assert updater.available() is None
        assert updater.status()["check_error"] is None
    assert github.asked and all(u == updates.API_URL for u in github.asked)


def test_release_notes_are_plain_text_and_short():
    body = "\n\n" + "\n".join(f"<b>line {i}</b>" for i in range(30))
    notes = updates.parse_release(release(body=body))["notes"]
    assert notes.startswith("<b>line 0</b>")   # as written: the page shows it as text, never as HTML
    assert notes.count("\n") == updates.NOTES_LINES and notes.endswith("…")
    assert updates.parse_release(release(body=None))["notes"] == ""


def test_rate_limit_and_offline_are_noted_quietly(updater, github):
    updater.check()
    assert updater.available()["version"] == "0.3.0"
    checked = updater.status()["checked_at"]
    headers = Message()
    headers["X-RateLimit-Remaining"] = "0"
    github.fail = urllib.error.HTTPError(updates.API_URL, 403, "rate limit exceeded", headers, None)
    status = updater.check()
    assert "asked Closet to wait" in status["check_error"]
    assert status["available"]["version"] == "0.3.0" and status["checked_at"] == checked   # what was found is kept
    github.fail = urllib.error.URLError(OSError("Network is unreachable"))
    status = updater.check()
    assert "could not reach GitHub" in status["check_error"]
    # tried again after an hour, not after a day
    assert not updater.due(time.time() + 60)
    assert updater.due(time.time() + updates.RETRY_AFTER + 1)
    github.fail = urllib.error.HTTPError(updates.API_URL, 404, "Not Found", Message(), None)
    status = updater.check()   # nothing published yet: an answer, not a problem
    assert status["check_error"] is None and status["available"] is None


def test_a_good_check_lasts_a_day(updater, github):
    assert updater.due()
    updater.check()
    assert not updater.due(time.time() + 3600)
    assert updater.due(time.time() + updates.CHECK_EVERY + 1)


# ------------------------------------------------------------------ download and verify
def test_the_download_is_checked_against_githubs_digest(updater, github, cfg):
    updater.check()
    path = updater.prepare(updater.available())
    assert path.read_bytes() == NEW_EXE and path.parent == cfg.data_dir / "updates"
    assert updater.status()["ready"]
    # a file that does not match is thrown away, and nothing is ready
    github.files[github.latest["assets"][0]["browser_download_url"]] = b"something else"
    updater.state.update(update_ready=None)
    path.unlink()
    with pytest.raises(updates.UpdateError, match="did not match the checksum"):
        updater.prepare(updater.available())
    assert not list((cfg.data_dir / "updates").glob("*Closet.exe*"))
    assert not updater.status()["ready"]


@pytest.mark.parametrize("digest", [None, "md5:abc", "sha256:not-hex"])
def test_no_digest_means_no_install(updater, github, digest):
    entry = asset("Closet.exe", NEW_EXE, digest=digest)
    github.latest = release(assets=[entry])
    github.add(entry, NEW_EXE)
    updater.check()
    with pytest.raises(updates.UpdateError, match="no checksum"):
        updater.prepare(updater.available())


def test_a_download_larger_than_the_release_says_is_thrown_away(updater, github):
    entry = asset("Closet.exe", NEW_EXE)
    entry["size"] = 5
    github.latest = release(assets=[entry])
    github.add(entry, NEW_EXE)
    updater.check()
    with pytest.raises(updates.UpdateError, match="larger than the release said"):
        updater.prepare(updater.available())


def test_only_this_computers_file_is_picked():
    rel = updates.parse_release(release(assets=[asset("Closet.exe", b"w"), asset("Closet-mac-arm64.zip", b"m")]))
    assert updates.asset_for(rel, "win32")["name"] == "Closet.exe"
    assert updates.asset_for(rel, "darwin")["name"] == "Closet-mac-arm64.zip"
    assert updates.asset_for(rel, "linux") is None


# ------------------------------------------------------------------ replacing the program
def test_windows_program_is_renamed_then_replaced_and_restored(tmp_path, program):
    package = tmp_path / "download.exe"
    package.write_bytes(NEW_EXE)
    where = updates.layout("win32", str(program))
    assert where.old == program.with_name("Closet.old.exe")
    updates.swap(where, package, hashlib.sha256(NEW_EXE).hexdigest())
    assert program.read_bytes() == NEW_EXE and where.old.read_bytes() == OLD_EXE
    assert sorted(p.name for p in program.parent.iterdir()) == ["Closet.exe", "Closet.old.exe"]
    assert updates.restore(where)
    assert program.read_bytes() == OLD_EXE and not where.old.exists()
    assert sorted(p.name for p in program.parent.iterdir()) == ["Closet.exe"]
    assert not updates.restore(where)   # nothing kept: nothing to put back


def test_a_package_that_changed_after_checking_is_not_used(tmp_path, program):
    package = tmp_path / "download.exe"
    package.write_bytes(NEW_EXE + b"!")
    with pytest.raises(updates.UpdateError, match="changed after it was checked"):
        updates.swap(updates.layout("win32", str(program)), package, hashlib.sha256(NEW_EXE).hexdigest())
    assert program.read_bytes() == OLD_EXE


def mac_bundle(root: Path, content: bytes) -> Path:
    app = root / "Closet.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Closet").write_bytes(content)
    (app / "Contents" / "Info.plist").write_text("<plist/>")
    return app


class FakeMacTools:
    """Stands in for ditto, xattr and codesign."""

    def __init__(self, signed=True):
        self.signed, self.calls = signed, []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "ditto":
            assert cmd[1:3] == ["-x", "-k"]
            with zipfile.ZipFile(cmd[3]) as z:
                z.extractall(cmd[4])
            return SimpleNamespace(returncode=0)
        if cmd[0] == "codesign":
            assert cmd[1:4] == ["--verify", "--deep", "--strict"]
            return SimpleNamespace(returncode=0 if self.signed else 1)
        return SimpleNamespace(returncode=0)


def mac_zip(tmp_path: Path) -> Path:
    built = tmp_path / "built"
    built.mkdir()
    mac_bundle(built, NEW_EXE)
    package = tmp_path / "Closet-mac-arm64.zip"
    with zipfile.ZipFile(package, "w") as z:
        for f in (built / "Closet.app").rglob("*"):
            z.write(f, f.relative_to(built))
    return package


def test_mac_bundle_is_unpacked_checked_and_swapped_then_restored(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = mac_bundle(apps, OLD_EXE)
    package = mac_zip(tmp_path)
    where = updates.layout("darwin", str(installed / "Contents" / "MacOS" / "Closet"))
    assert where.installed == installed and where.old == apps / "Closet.old.app"
    assert where.old_program == apps / "Closet.old.app" / "Contents" / "MacOS" / "Closet"
    tools = FakeMacTools()
    updates.swap(where, package, hashlib.sha256(package.read_bytes()).hexdigest(), run=tools)
    assert (installed / "Contents" / "MacOS" / "Closet").read_bytes() == NEW_EXE
    assert (where.old / "Contents" / "MacOS" / "Closet").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Closet.app", "Closet.old.app"]   # the unpacking folder is gone
    names = [c[0] for c in tools.calls]
    assert names == ["ditto", "xattr", "codesign"]
    # the quarantine mark is only taken off the bundle Closet unpacked, never the installed one
    assert tools.calls[1][:3] == ["xattr", "-dr", "com.apple.quarantine"] and "-update" in tools.calls[1][3]
    assert updates.restore(where)
    assert (installed / "Contents" / "MacOS" / "Closet").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Closet.app"]


def test_mac_bundle_that_fails_its_signature_check_is_not_installed(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = mac_bundle(apps, OLD_EXE)
    package = mac_zip(tmp_path)
    where = updates.layout("darwin", str(installed / "Contents" / "MacOS" / "Closet"))
    with pytest.raises(updates.UpdateError, match="signature"):
        updates.swap(where, package, hashlib.sha256(package.read_bytes()).hexdigest(), run=FakeMacTools(signed=False))
    assert (installed / "Contents" / "MacOS" / "Closet").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Closet.app"]


def test_only_windows_and_mac_programs_replace_themselves(tmp_path):
    assert updates.layout("linux", str(tmp_path / "closet")) is None
    assert updates.layout("darwin", str(tmp_path / "closet")) is None   # not inside a bundle


# ------------------------------------------------------------------ installing
def test_install_backs_up_every_closet_first(updater, github, cfg, monkeypatch, tmp_path):
    from closet import demo
    demo.ensure(cfg)
    folder = tmp_path / "Backups"
    folder.mkdir()
    updater.state.update(backup_folder=str(folder))
    seen = []
    real_swap = updates.swap

    def swap(where, package, sha256, run=None):
        seen.append((sorted(p.name.split("-0.2.1-")[0] for p in cfg.local_backups_dir.glob("pre-update-*")),
                     updater.state.get("last_backup")))
        return real_swap(where, package, sha256, run)
    monkeypatch.setattr(updates, "swap", swap)
    updater.check()
    updater.install(updater.available())
    (backups, last), = seen
    assert backups == ["pre-update-demo", "pre-update-main"]
    assert last["ok"] and last["kind"] == "update"
    assert Path(updater.executable).read_bytes() == NEW_EXE
    (helper, plan), = updater.spawned
    assert helper == Path(updater.executable).with_name("Closet.old.exe")   # the helper is the old program, kept aside
    assert plan["from"] == "0.2.1" and plan["to"] == "0.3.0" and plan["args"] == ["--no-browser", "--port", "8765"]
    assert updater.busy == "restarting"


def test_no_backup_no_install(updater, github, tmp_path):
    updater.state.update(backup_folder=str(tmp_path / "unplugged drive"))
    updater.check()
    with pytest.raises(updates.UpdateError, match="backup before updating did not work"):
        updater.install(updater.available())
    assert Path(updater.executable).read_bytes() == OLD_EXE and not updater.spawned


def test_a_helper_that_cannot_start_puts_the_old_program_back(updater, github):
    def broken(prog, plan):
        raise OSError("no such file")
    updater.spawn = broken
    updater.check()
    with pytest.raises(updates.UpdateError, match="put this one back"):
        updater.install(updater.available())
    assert Path(updater.executable).read_bytes() == OLD_EXE
    assert not Path(updater.executable).with_name("Closet.old.exe").exists()


def test_install_from_the_page(updater, github, client):
    client.post("/api/updates/check")
    status = client.get("/api/updates").json()
    assert status["available"]["version"] == "0.3.0" and status["can_install"] and not status["ready"]
    r = client.post("/api/updates/install")
    assert r.status_code == 202
    wait_idle(updater)
    assert updater.busy == "restarting" and len(updater.spawned) == 1
    # a second press while it is going is refused plainly
    updater._lock.acquire()
    try:
        r = client.post("/api/updates/install")
        assert r.status_code == 409 and "already" in r.json()["detail"]
    finally:
        updater._lock.release()


def test_a_bad_download_is_reported_on_the_page(updater, github, client):
    github.files[github.latest["assets"][0]["browser_download_url"]] = b"tampered"
    client.post("/api/updates/check")
    assert client.post("/api/updates/install").status_code == 202
    wait_idle(updater)
    status = client.get("/api/updates").json()
    assert "did not match the checksum" in status["problem"] and status["busy"] is None
    assert Path(updater.executable).read_bytes() == OLD_EXE and not updater.spawned


# ------------------------------------------------------------------ by itself, and when it must not
def test_ask_first_fetches_ahead_and_waits(updater, github):
    updater.tick()
    status = updater.status()
    assert status["ready"] and status["mode"] == "ask" and not updater.spawned
    assert Path(updater.executable).read_bytes() == OLD_EXE


def test_install_by_themselves(updater, github):
    updater.set_mode("auto")
    updater.tick()
    assert Path(updater.executable).read_bytes() == NEW_EXE and len(updater.spawned) == 1


def test_a_failed_download_is_not_retried_every_half_hour(updater, github):
    github.files.clear()
    updater.tick()
    asked = len(github.asked)
    assert updater.status()["problem"]
    updater.tick()
    assert len(github.asked) == asked


def test_never_check_and_from_source_do_nothing(updater, github, client):
    updater.set_mode("never")
    updater.tick()
    assert github.asked == []
    updater.set_mode("ask")
    updater.frozen = False   # running from source
    updater.tick()
    assert github.asked == []
    # from source, a release is reported with a link but never installed
    status = client.post("/api/updates/check").json()
    assert status["available"]["version"] == "0.3.0" and not status["can_install"]
    assert status["available"]["page"].startswith("https://github.com/ericksoni716/daily-clother/releases/")
    r = client.post("/api/updates/install")
    assert r.status_code == 409 and "release page" in r.json()["detail"]
    assert Path(updater.executable).read_bytes() == OLD_EXE


def test_linux_program_only_reports(updater, github):
    updater.platform = "linux"
    updater.tick()
    status = updater.status()
    assert status["available"]["version"] == "0.3.0" and not status["can_install"] and not status["ready"]
    assert github.asked == [updates.API_URL]


def test_the_choice_is_kept_in_settings_and_needs_the_login(anon, client, cfg):
    from fastapi.testclient import TestClient
    fresh = TestClient(anon.app)
    for call in (fresh.get("/api/updates"), fresh.put("/api/updates", json={"mode": "auto"}),
                 fresh.post("/api/updates/check"), fresh.post("/api/updates/install")):
        assert call.status_code == 401
    assert client.get("/api/updates").json()["mode"] == "ask"
    assert client.put("/api/updates", json={"mode": "never"}).json()["mode"] == "never"
    assert json.loads(cfg.state_path.read_text())["update_mode"] == "never"
    assert client.put("/api/updates", json={"mode": "sometimes"}).status_code == 422


# ------------------------------------------------------------------ the helper: hand over, or go back
NEW_COPY = textwrap.dedent("""
    import http.server, json, os, sys
    port, lock, version = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"app": "closet", "status": "ok", "version": version}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    s = http.server.HTTPServer(("127.0.0.1", port), H)
    open(lock, "w").write(json.dumps({"pid": os.getpid(), "port": port, "token": "t"}))
    s.serve_forever()
""")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def swapped(tmp_path, program):
    package = tmp_path / "download.exe"
    package.write_bytes(NEW_EXE)
    where = updates.layout("win32", str(program))
    updates.swap(where, package, hashlib.sha256(NEW_EXE).hexdigest())
    return where, {"from": "0.2.1", "to": "0.3.0", "platform": "win32", "installed": str(where.installed),
                   "old": str(where.old), "inner": ".", "args": ["--no-browser", "--port", "8765"],
                   "old_pid": 999_999_999, "data_dir": "unused", "timeout": 60}


def test_helper_hands_over_to_a_new_program_that_answers(cfg, tmp_path, program):
    where, plan = swapped(tmp_path, program)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    procs, started = [], []

    def start(w, args):   # a stand-in new program: writes its lock file and answers /api/health as 0.3.0
        started.append((w.program, args))
        p = subprocess.Popen([sys.executable, "-c", NEW_COPY, str(free_port()), str(cfg.lock_path), "0.3.0"])
        procs.append(p)
        return p
    try:
        assert updates.watch(cfg, plan, start=start, timeout=20, poll=0.1)
    finally:
        for p in procs:
            p.kill()
            p.wait()
    assert started == [(program, ["--no-browser", "--port", "8765", "--replace"])]   # the launcher's replace path
    assert program.read_bytes() == NEW_EXE
    outcome = json.loads(updates.outcome_path(cfg).read_text())
    assert outcome["ok"] and outcome["to"] == "0.3.0"


def test_helper_puts_the_old_program_back_when_the_new_one_never_answers(cfg, services, tmp_path, program):
    where, plan = swapped(tmp_path, program)
    started = []

    def start(w, args):
        started.append((w.program.read_bytes(), args))
        return None   # started, but it never writes its lock file or answers
    assert not updates.watch(cfg, plan, start=start, timeout=0.5, poll=0.1)
    assert program.read_bytes() == OLD_EXE and not where.old.exists()
    assert not program.with_name("Closet.failed.exe").exists()
    # the new one was started for the hand-over, then the old one again as it was started before
    assert started == [(NEW_EXE, ["--no-browser", "--port", "8765", "--replace"]),
                       (OLD_EXE, ["--no-browser", "--port", "8765"])]
    u = services.updater
    last = u.status()["last_install"]
    assert last["ok"] is False and "it did not answer within 0.5 seconds" in last["note"]
    assert "0.3.0 was installed but did not start" in last["note"] and "0.2.1 was put back and started again" in last["note"]
    assert not updates.outcome_path(cfg).exists()   # taken into the settings
    assert u.state.get("update_install") == last


def test_helper_goes_back_when_the_new_program_stops_by_itself(cfg, tmp_path, program):
    where, plan = swapped(tmp_path, program)
    calls = []

    def start(w, args):
        calls.append(args)
        if len(calls) == 1:
            return subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
        return None
    assert not updates.watch(cfg, plan, start=start, timeout=20, poll=0.1)
    note = json.loads(updates.outcome_path(cfg).read_text())["note"]
    assert "stopped by itself (exit code 3)" in note
    assert program.read_bytes() == OLD_EXE and len(calls) == 2


def test_the_old_program_still_running_is_left_alone_after_going_back(cfg, tmp_path, program, monkeypatch):
    where, plan = swapped(tmp_path, program)
    monkeypatch.setattr(instance, "running_info", lambda c: {"port": 8765, "version": "0.2.1", "pid": plan["old_pid"]})
    calls = []
    assert not updates.watch(cfg, plan, start=lambda w, a: calls.append(a), timeout=0.3, poll=0.1)
    assert len(calls) == 1 and program.read_bytes() == OLD_EXE
    assert "kept running" in json.loads(updates.outcome_path(cfg).read_text())["note"]


def test_the_helper_is_this_program_run_with_a_hidden_command(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(updates, "run_watch", lambda plan: seen.append(plan) or 0)
    assert cli.main(["update-watch", str(tmp_path / "plan.json")]) == 0
    assert seen == [str(tmp_path / "plan.json")]


def test_new_program_removes_the_old_one_once_it_has_started(updater, program):
    old = program.with_name("Closet.old.exe")
    old.write_bytes(OLD_EXE)
    program.write_bytes(NEW_EXE)
    updater.version = "0.3.0"
    updates._write_outcome(updater.cfg, {"at": updates._now(), "from": "0.2.1", "to": "0.3.0", "ok": True, "note": None})
    updater.tidy(wait=5)
    assert not old.exists() and program.read_bytes() == NEW_EXE
    assert updater.status()["last_install"]["ok"]


def test_a_check_from_the_running_program_does_not_hold_up_the_others(updater, github):
    # checking and installing take turns: a check while an install runs simply answers with what is known
    updater._lock.acquire()
    try:
        status = updater.check()
    finally:
        updater._lock.release()
    assert github.asked == [] and status["checked_at"] is None
    t = threading.Thread(target=updater.check)
    t.start()
    t.join(5)
    assert github.asked == [updates.API_URL]
