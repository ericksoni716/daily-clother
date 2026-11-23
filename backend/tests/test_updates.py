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

from closet import cli, db, instance, updates

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
            "assets": assets if assets is not None else [asset("Nines.exe", NEW_EXE)]}


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
    exe = folder / "Nines.exe"
    exe.write_bytes(OLD_EXE)
    return exe


@pytest.fixture
def updater(services, program):
    """The services' updater as if this were Nines 0.2.1, packaged, on Windows; the helper is never really started."""
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


RELEASE_BODY = """Nines 0.3.0, built from 0123abc.

## What's new

### Changed

- Trips pack **lighter**, and the list
  wraps onto a second line.
- <b>Not bold</b>

### Fixed

1. A sock no longer goes missing.

## First run on Windows

1. Download **Nines.exe** below.

## Good to know

The demo closet works at once.
"""


def test_release_notes_are_only_the_whats_new_section_as_written():
    notes = updates.parse_release(release(body=RELEASE_BODY.replace("\n", "\r\n")))["notes"]
    assert notes == ("### Changed\n\n- Trips pack **lighter**, and the list\n  wraps onto a second line.\n"
                     "- <b>Not bold</b>\n\n### Fixed\n\n1. A sock no longer goes missing.")
    # the install steps are not what is new
    assert "First run" not in notes and "Nines.exe" not in notes and "built from" not in notes
    # a curly apostrophe or other capitals name the section too; the last section runs to the end
    curly = "## What’s New\n\n- One thing.\n"
    assert updates.parse_release(release(body=curly))["notes"] == "- One thing."


def test_a_release_without_whats_new_has_no_notes():
    # releases before the section was written: install steps only, so nothing shown under "What's new"
    old = RELEASE_BODY.split("## What's new")[0] + "## First run on Windows\n\n1. Download it.\n"
    for body in (old, "Faster outfits.\n\nFixes a crash.", "", None, 12):
        assert updates.parse_release(release(body=body))["notes"] == ""
    assert updates.parse_release(release(body="## What's new\n\n## First run\n\n1. x"))["notes"] == ""


def test_long_release_notes_are_cut_at_the_end_of_a_line():
    lines = [f"- Change number {i} is described in a sentence of some length." for i in range(200)]
    notes = updates.parse_release(release(body="## What's new\n\n" + "\n".join(lines)))["notes"]
    assert notes.endswith("\n\n…") and len(notes) <= updates.NOTES_CHARS + 3
    kept = notes[:-3].split("\n")
    assert kept == lines[:len(kept)] and len(kept) > 10   # whole lines only, from the start


def test_rate_limit_and_offline_are_noted_quietly(updater, github):
    updater.check()
    assert updater.available()["version"] == "0.3.0"
    checked = updater.status()["checked_at"]
    headers = Message()
    headers["X-RateLimit-Remaining"] = "0"
    github.fail = urllib.error.HTTPError(updates.API_URL, 403, "rate limit exceeded", headers, None)
    status = updater.check()
    assert "asked Nines to wait" in status["check_error"]
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
    assert not list((cfg.data_dir / "updates").glob("*Nines.exe*"))
    assert not updater.status()["ready"]


@pytest.mark.parametrize("digest", [None, "md5:abc", "sha256:not-hex"])
def test_no_digest_means_no_install(updater, github, digest):
    entry = asset("Nines.exe", NEW_EXE, digest=digest)
    github.latest = release(assets=[entry])
    github.add(entry, NEW_EXE)
    updater.check()
    with pytest.raises(updates.UpdateError, match="no checksum"):
        updater.prepare(updater.available())


def test_a_download_larger_than_the_release_says_is_thrown_away(updater, github):
    entry = asset("Nines.exe", NEW_EXE)
    entry["size"] = 5
    github.latest = release(assets=[entry])
    github.add(entry, NEW_EXE)
    updater.check()
    with pytest.raises(updates.UpdateError, match="larger than the release said"):
        updater.prepare(updater.available())


def test_only_this_computers_file_is_picked():
    rel = updates.parse_release(release(assets=[asset("Nines.exe", b"w"), asset("Nines-mac-arm64.zip", b"m")]))
    assert updates.asset_for(rel, "win32")["name"] == "Nines.exe"
    assert updates.asset_for(rel, "darwin")["name"] == "Nines-mac-arm64.zip"
    assert updates.asset_for(rel, "linux") is None
    # the program was Closet.exe until 0.11.0; a release carrying only the old names has nothing for this one
    old = updates.parse_release(release(assets=[asset("Closet.exe", b"w"), asset("Closet-mac-arm64.zip", b"m")]))
    assert updates.asset_for(old, "win32") is None and updates.asset_for(old, "darwin") is None


# ------------------------------------------------------------------ replacing the program
def test_windows_program_is_renamed_then_replaced_and_restored(tmp_path, program):
    package = tmp_path / "download.exe"
    package.write_bytes(NEW_EXE)
    where = updates.layout("win32", str(program))
    assert where.old == program.with_name("Nines.old.exe")
    updates.swap(where, package, hashlib.sha256(NEW_EXE).hexdigest())
    assert program.read_bytes() == NEW_EXE and where.old.read_bytes() == OLD_EXE
    assert sorted(p.name for p in program.parent.iterdir()) == ["Nines.exe", "Nines.old.exe"]
    assert updates.restore(where)
    assert program.read_bytes() == OLD_EXE and not where.old.exists()
    assert sorted(p.name for p in program.parent.iterdir()) == ["Nines.exe"]
    assert not updates.restore(where)   # nothing kept: nothing to put back


def test_a_package_that_changed_after_checking_is_not_used(tmp_path, program):
    package = tmp_path / "download.exe"
    package.write_bytes(NEW_EXE + b"!")
    with pytest.raises(updates.UpdateError, match="changed after it was checked"):
        updates.swap(updates.layout("win32", str(program)), package, hashlib.sha256(NEW_EXE).hexdigest())
    assert program.read_bytes() == OLD_EXE


def mac_bundle(root: Path, content: bytes) -> Path:
    app = root / "Nines.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Nines").write_bytes(content)
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
    package = tmp_path / "Nines-mac-arm64.zip"
    with zipfile.ZipFile(package, "w") as z:
        for f in (built / "Nines.app").rglob("*"):
            z.write(f, f.relative_to(built))
    return package


def test_mac_bundle_is_unpacked_checked_and_swapped_then_restored(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = mac_bundle(apps, OLD_EXE)
    package = mac_zip(tmp_path)
    where = updates.layout("darwin", str(installed / "Contents" / "MacOS" / "Nines"))
    assert where.installed == installed and where.old == apps / "Nines.old.app"
    assert where.old_program == apps / "Nines.old.app" / "Contents" / "MacOS" / "Nines"
    tools = FakeMacTools()
    updates.swap(where, package, hashlib.sha256(package.read_bytes()).hexdigest(), run=tools)
    assert (installed / "Contents" / "MacOS" / "Nines").read_bytes() == NEW_EXE
    assert (where.old / "Contents" / "MacOS" / "Nines").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Nines.app", "Nines.old.app"]   # the unpacking folder is gone
    names = [c[0] for c in tools.calls]
    assert names == ["ditto", "xattr", "codesign"]
    # the quarantine mark is only taken off the bundle Nines unpacked, never the installed one
    assert tools.calls[1][:3] == ["xattr", "-dr", "com.apple.quarantine"] and "-update" in tools.calls[1][3]
    assert updates.restore(where)
    assert (installed / "Contents" / "MacOS" / "Nines").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Nines.app"]


def test_mac_bundle_that_fails_its_signature_check_is_not_installed(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    installed = mac_bundle(apps, OLD_EXE)
    package = mac_zip(tmp_path)
    where = updates.layout("darwin", str(installed / "Contents" / "MacOS" / "Nines"))
    with pytest.raises(updates.UpdateError, match="signature"):
        updates.swap(where, package, hashlib.sha256(package.read_bytes()).hexdigest(), run=FakeMacTools(signed=False))
    assert (installed / "Contents" / "MacOS" / "Nines").read_bytes() == OLD_EXE
    assert sorted(p.name for p in apps.iterdir()) == ["Nines.app"]


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
    assert helper == Path(updater.executable).with_name("Nines.old.exe")   # the helper is the old program, kept aside
    assert plan["from"] == "0.2.1" and plan["to"] == "0.3.0" and plan["args"] == ["--no-browser", "--port", "8765"]
    assert sorted(plan["snapshots"]) == ["demo", "main"] and all(Path(v).is_file() for v in plan["snapshots"].values())
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
    assert not Path(updater.executable).with_name("Nines.old.exe").exists()


@pytest.mark.parametrize("failure", ["plan", "outcome"])
def test_failed_handover_files_put_the_old_program_back(updater, github, monkeypatch, failure):
    updater.check()
    write_text, unlink = Path.write_text, Path.unlink

    def fail_plan(path, *args, **kwargs):
        if path == updates.plan_path(updater.cfg):
            raise OSError("disk full")
        return write_text(path, *args, **kwargs)

    def fail_outcome(path, *args, **kwargs):
        if path == updates.outcome_path(updater.cfg):
            raise PermissionError("file is locked")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text" if failure == "plan" else "unlink",
                        fail_plan if failure == "plan" else fail_outcome)
    with pytest.raises(updates.UpdateError, match="put this one back"):
        updater.install(updater.available())
    assert Path(updater.executable).read_bytes() == OLD_EXE
    assert not updater.where.old.exists()
    assert not updater.spawned


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


@pytest.mark.parametrize("during_restart", ["install", "check", "tick"])
def test_restart_keeps_the_old_program_until_the_helper_finishes(updater, github, during_restart):
    updater.set_mode("auto")
    updater.check()
    updater.install_now()
    wait_idle(updater)
    assert updater.busy == "restarting"
    if during_restart == "check":
        updater.check()
    elif during_restart == "tick":
        updater.tick()
    with pytest.raises(updates.UpdateError, match="already"):
        updater.install_now()
    assert updater.busy == "restarting"
    assert len(updater.spawned) == 1
    assert Path(updater.executable).with_name("Nines.old.exe").read_bytes() == OLD_EXE


def test_a_failed_handover_allows_the_owner_to_retry(updater, github):
    updater.check()
    updater.install_now()
    wait_idle(updater)
    assert updates.restore(updater.where)
    updates._write_outcome(updater.cfg, {"to": "0.3.0", "ok": False, "note": "The old copy kept running."})
    assert updater.status()["busy"] is None
    updater.install_now()
    wait_idle(updater)
    assert len(updater.spawned) == 2
    assert updater.busy == "restarting"
    assert updater.where.old.read_bytes() == OLD_EXE


# ------------------------------------------------------------------ by itself, and when it must not
def test_ask_first_fetches_ahead_and_waits(updater, github):
    updater.tick()
    status = updater.status()
    assert status["ready"] and status["mode"] == "ask" and not updater.spawned
    assert Path(updater.executable).read_bytes() == OLD_EXE


def test_check_now_gets_a_found_release_ready_without_waiting_for_the_next_look(updater, github, client):
    # the loop has looked (nothing was out then) and sleeps for half an hour; Check now finds 0.3.0
    updater.state.update(update_check={"at": updates._now(), "ok": True, "error": None, "latest": "0.2.1",
                                       "available": None})
    looks = []
    real_tick = updater.tick
    updater.tick = lambda now=None: (real_tick(now), looks.append(1))
    updater.start(first_after=0)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not looks:
        time.sleep(0.02)
    assert len(looks) == 1 and github.asked == []   # its first look found nothing to do; the next is in 30 minutes
    status = client.post("/api/updates/check").json()
    assert status["available"]["version"] == "0.3.0" and not status["ready"]
    # the release is ready inside the look, a moment before the wrapper above counts the look: wait for both
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (len(looks) == 2 and updater.status()["ready"]):
        time.sleep(0.05)
    assert len(looks) == 2 and updater.status()["ready"]   # looked again at once: fetched, checked, offered
    assert not updater.spawned and Path(updater.executable).read_bytes() == OLD_EXE   # "Ask me first": not installed


def test_check_now_with_nothing_newer_leaves_the_loop_asleep(updater, github):
    github.latest = release("0.2.1")
    assert updater.check_now()["available"] is None
    assert not updater._soon.is_set()


def test_install_by_themselves(updater, github):
    updater.set_mode("auto")
    updater.tick()
    assert Path(updater.executable).read_bytes() == NEW_EXE and len(updater.spawned) == 1


def test_a_version_the_helper_undid_is_not_installed_again_by_itself(updater, github, cfg):
    updater.set_mode("auto")
    updates.outcome_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    updates.outcome_path(cfg).write_text(json.dumps(
        {"at": "2026-11-13T09:00:00Z", "from": "0.2.1", "to": "0.3.0", "ok": False, "note": "it did not answer"}))
    updater.tick()
    assert not updater.spawned and Path(updater.executable).read_bytes() == OLD_EXE
    assert updater.state.get("update_install")["ok"] is False


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


def test_the_choice_is_kept_in_settings(client, cfg):
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
    assert not program.with_name("Nines.failed.exe").exists()
    # the new one was started for the hand-over, then the old one again as it was started before
    assert started == [(NEW_EXE, ["--no-browser", "--port", "8765", "--replace"]),
                       (OLD_EXE, ["--no-browser", "--port", "8765"])]
    u = services.updater
    last = u.status()["last_install"]
    assert last["ok"] is False and "it did not answer within 0.5 seconds" in last["note"]
    assert "0.3.0 was installed but did not start" in last["note"] and "0.2.1 was put back and started again" in last["note"]
    assert not updates.outcome_path(cfg).exists()   # taken into the settings
    assert u.state.get("update_install") == last


def test_going_back_also_puts_back_a_closet_the_new_program_upgraded(cfg, tmp_path, program):
    where, plan = swapped(tmp_path, program)
    path = cfg.db_path("main")
    db.migrate(path, cfg.local_backups_dir)
    snap = cfg.local_backups_dir / "pre-update-main-0.2.1-x.sqlite"
    db.snapshot(path, snap)
    conn = db.connect(path)   # the new program upgraded the closet before it failed
    conn.execute(f"PRAGMA user_version = {db.latest_version() + 1}")
    conn.close()
    plan["snapshots"] = {"main": str(snap), "elsewhere": str(snap)}
    assert not updates.watch(cfg, plan, start=lambda w, a: None, timeout=0.3, poll=0.1)
    db.migrate(path, cfg.local_backups_dir)   # the old program can open it again
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.latest_version()
    conn.close()
    assert len(list(cfg.local_backups_dir.glob("upgraded-main-*.sqlite"))) == 1   # the upgraded one is kept
    assert "put back as it was just before the update" in json.loads(updates.outcome_path(cfg).read_text())["note"]


def test_a_closet_the_new_program_did_not_touch_is_left_as_it_is(cfg, tmp_path):
    path = cfg.db_path("main")
    db.migrate(path, cfg.local_backups_dir)
    snap = tmp_path / "snap.sqlite"
    db.snapshot(path, snap)
    assert updates.restore_closets(cfg, {"main": str(snap)}) == []
    assert not list(cfg.local_backups_dir.glob("upgraded-*"))


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
    old = program.with_name("Nines.old.exe")
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
