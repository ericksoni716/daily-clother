"""A newer copy of the program that finds an older one running says so and offers to replace it."""
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
from types import SimpleNamespace

import pytest

from closet import cli, instance


def test_versions_are_compared_as_releases():
    assert instance.is_newer("0.2.0", "0.1.1")
    assert instance.is_newer("0.10.0", "0.9.3")
    assert instance.is_newer("1.0", "0.9.9")
    assert not instance.is_newer("0.2.0", "0.2.0")
    assert not instance.is_newer("0.2", "0.2.0")
    assert not instance.is_newer("0.1.1", "0.2.0")
    # a copy run from source, or one that does not say, is never treated as older or newer
    assert not instance.is_newer("0.1.0-dev", "0.1.0")
    assert not instance.is_newer("0.2.0", "0.1.0-dev")
    assert not instance.is_newer("0.2.0", "")


def test_quit_endpoint_needs_this_copys_token(cfg, anon, services):
    quits = []
    services.on_quit = lambda: quits.append(1)
    # no lock file yet: nothing is accepted
    assert anon.post("/api/instance/quit", headers={instance.QUIT_HEADER: "x"}).status_code == 403
    instance.write_lock(cfg, 8765)
    token = json.loads(cfg.lock_path.read_text())["token"]
    assert len(token) >= 32
    assert anon.post("/api/instance/quit").status_code == 403
    assert anon.post("/api/instance/quit", headers={instance.QUIT_HEADER: token + "x"}).status_code == 403
    # a lock written by another process does not let its token through here
    cfg.lock_path.write_text(json.dumps({"pid": os.getpid() + 1, "port": 8765, "token": token}))
    assert anon.post("/api/instance/quit", headers={instance.QUIT_HEADER: token}).status_code == 403
    assert not quits
    instance.write_lock(cfg, 8765)
    token = json.loads(cfg.lock_path.read_text())["token"]
    assert anon.post("/api/instance/quit", headers={instance.QUIT_HEADER: token}).status_code == 202
    time.sleep(0.6)
    assert quits == [1]


# a stand-in for an older copy: answers /api/health like Closet 0.1.1 and has no way to be asked to quit
OLD_COPY = textwrap.dedent("""
    import http.server, json, sys
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"app": "closet", "status": "ok", "version": "0.1.1"}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    s = http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H)
    print("ready", flush=True)
    s.serve_forever()
""")


@pytest.fixture
def old_copy(cfg):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-c", OLD_COPY, str(port)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "ready"
    # reap it as soon as it ends, as the system does for a real copy; otherwise it lingers as a zombie
    threading.Thread(target=proc.wait, daemon=True).start()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.lock_path.write_text(json.dumps({"pid": proc.pid, "port": port}))  # an older copy's lock: no token
    yield SimpleNamespace(proc=proc, port=port)
    if proc.poll() is None:
        proc.kill()
    proc.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="stops the stand-in with a signal")
def test_an_older_copy_without_a_quit_endpoint_is_stopped(cfg, old_copy):
    info = instance.running_info(cfg)
    assert info == {"port": old_copy.port, "version": "0.1.1", "pid": old_copy.proc.pid, "token": None}
    assert instance.stop_running(cfg, info, timeout=10)
    old_copy.proc.wait(timeout=5)
    assert instance.running_info(cfg) is None


def _args(**kw):
    return SimpleNamespace(**{"no_browser": True, "no_tray": False, "port": None, "replace": False, **kw})


@pytest.fixture
def newer(monkeypatch):
    monkeypatch.setattr(cli, "__version__", "0.3.0")
    said, asked = [], []
    monkeypatch.setattr(cli, "_say", said.append)
    return SimpleNamespace(said=said, asked=asked)


@pytest.mark.skipif(sys.platform == "win32", reason="stops the stand-in with a signal")
def test_owner_who_keeps_the_old_copy_is_not_replaced(cfg, old_copy, newer, monkeypatch):
    monkeypatch.setattr(cli, "_ask", lambda q, yes, no, headless=False: newer.asked.append(q) or False)
    assert cli.serve(_args(), cfg) == 0
    assert "older Closet (0.1.1)" in newer.asked[0] and "0.3.0" in newer.asked[0]
    assert old_copy.proc.poll() is None   # still running


@pytest.mark.skipif(sys.platform == "win32", reason="stops the stand-in with a signal")
def test_when_nobody_can_be_asked_the_owner_is_told(cfg, old_copy, newer, monkeypatch):
    monkeypatch.setattr(cli, "_ask", lambda q, yes, no, headless=False: None)
    assert cli.serve(_args(), cfg) == 0
    assert "older Closet (0.1.1) is already running" in newer.said[0]
    assert old_copy.proc.poll() is None


@pytest.mark.skipif(sys.platform == "win32", reason="stops the stand-in with a signal")
def test_owner_who_chooses_the_new_copy_gets_it(cfg, old_copy, newer, monkeypatch):
    monkeypatch.setattr(cli, "_ask", lambda q, yes, no, headless=False: True)
    followed = []
    monkeypatch.setattr(cli, "_follow_start_at_login", lambda: followed.append(1))
    started = []

    def build_services(c):   # stop just before the server starts; the old copy must be gone by then
        started.append(instance.running_info(c))
        raise RuntimeError("stop here")
    import closet.app
    monkeypatch.setattr(closet.app, "build_services", build_services)
    assert cli.serve(_args(), cfg) == 2
    assert old_copy.proc.wait(timeout=5) is not None
    assert started == [None] and followed == [1]


def test_a_copy_that_will_not_close_is_reported(cfg, newer, monkeypatch):
    monkeypatch.setattr(instance, "running_info", lambda c: {"port": 1, "version": "0.1.1", "pid": None, "token": None})
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: pytest.fail("--replace does not ask"))
    assert cli.serve(_args(replace=True), cfg) == 4
    assert "did not close" in newer.said[0]


def test_the_same_or_a_newer_copy_running_is_just_opened(cfg, newer, monkeypatch):
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: pytest.fail("nothing to ask"))
    for running in ("0.3.0", "0.4.0", "0.1.0-dev"):
        monkeypatch.setattr(instance, "running_info", lambda c, v=running: {"port": 1, "version": v, "pid": 1, "token": None})
        assert cli.serve(_args(), cfg) == 0
    assert not newer.said


def test_started_at_login_never_waits_on_a_question():
    assert cli._ask("?", "yes", "no", headless=True) is None
