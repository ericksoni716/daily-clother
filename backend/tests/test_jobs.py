import hashlib
import http.server
import sqlite3
import threading
import time

import pytest

from closet import db, jobs, tagjobs
from closet.modelstore import ModelStore
from closet.state import State

from .conftest import fake_cutter, upload


def drain(services):
    return services.worker.drain()


def test_cutout_waits_for_the_model_then_runs_automatically(client, services, cfg):
    item = upload(client).json()
    assert drain(services) == 0  # model missing: the job waits, it does not fail
    assert client.get(f"/api/items/{item['id']}").json()["cutout_state"] == "pending"
    services.worker.is_ready = lambda: True
    assert drain(services) == 1
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["cutout_state"] == "ready" and body["photos"][0]["cutout_url"].endswith(".cut.webp")
    assert body["thumb_url"].endswith(".cut.t.webp")
    cut = client.get(body["photos"][0]["cutout_url"])
    assert cut.status_code == 200 and len(cut.content) > 100
    assert client.get("/api/settings").json()["pending_cutouts"] == 0


def test_a_failing_cutout_is_retried_then_reported_and_can_be_tried_again(client, services):
    services.worker.is_ready = lambda: True
    calls = {"n": 0}

    def broken(img):
        calls["n"] += 1
        raise RuntimeError("model exploded")

    services.worker.cutter = broken
    item = upload(client).json()
    assert drain(services) == jobs.MAX_ATTEMPTS and calls["n"] == jobs.MAX_ATTEMPTS
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["cutout_state"] == "failed" and "try again" in body["cutout_error"]
    services.worker.cutter = fake_cutter
    assert client.post(f"/api/items/{item['id']}/retry-cutout").status_code == 202
    assert drain(services) == 1
    assert client.get(f"/api/items/{item['id']}").json()["cutout_state"] == "ready"


def test_work_interrupted_by_a_shutdown_resumes_on_the_next_start(client, services, cfg):
    item = upload(client).json()
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE jobs SET state = 'running'")
    conn.execute("UPDATE items SET cutout_state = 'processing'")
    assert jobs.requeue_interrupted(conn) == 1
    conn.close()
    services.worker.is_ready = lambda: True
    assert drain(services) == 1
    assert client.get(f"/api/items/{item['id']}").json()["cutout_state"] == "ready"


@pytest.mark.parametrize("kind", ["cutout", "tag"])
def test_startup_fails_interrupted_jobs_that_used_all_attempts(client, services, cfg, claude, kind):
    item = upload(client).json()
    services.worker.is_ready = lambda: True
    if kind == "tag":
        assert drain(services) == 1
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("UPDATE jobs SET state = 'running', attempts = 3 WHERE kind = ?", (kind,))
        conn.execute(f"UPDATE items SET {kind}_state = ?", ("processing" if kind == "cutout" else "working",))
        assert jobs.requeue_interrupted(conn) == 1
        job = conn.execute("SELECT state, attempts FROM jobs WHERE kind = ?", (kind,)).fetchone()
        assert (job["state"], job["attempts"]) == ("failed", 3)
    finally:
        conn.close()
    claude.mode = "answers"
    assert drain(services) == 0
    assert services.tag_worker.drain() == 0
    body = client.get(f"/api/items/{item['id']}").json()
    assert body[f"{kind}_state"] == "failed"
    assert "try again" in body[f"{kind}_error"].lower()
    assert claude.calls == []


@pytest.mark.parametrize("failures", [1, 3])
def test_cutout_save_failure_is_recovered_on_the_next_round(client, services, cfg, monkeypatch, failures):
    item = upload(client).json()
    services.worker.is_ready = lambda: True
    enqueue = tagjobs.enqueue

    def busy(conn, item_id):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(tagjobs, "enqueue", busy)
    for _ in range(failures):
        with pytest.raises(sqlite3.OperationalError):
            drain(services)
    monkeypatch.setattr(tagjobs, "enqueue", enqueue)
    assert drain(services) == (1 if failures < jobs.MAX_ATTEMPTS else 0)
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["cutout_state"] == ("ready" if failures < jobs.MAX_ATTEMPTS else "failed")


def test_cutout_recovery_leaves_the_running_tagger_alone(client, services, cfg):
    item = upload(client).json()
    services.worker.is_ready = lambda: True
    assert drain(services) == 1
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE kind = 'tag'")
        conn.execute("UPDATE items SET tag_state = 'working'")
        assert drain(services) == 0
        assert conn.execute("SELECT state FROM jobs WHERE kind = 'tag'").fetchone()[0] == "running"
        assert conn.execute("SELECT tag_state FROM items WHERE id = ?", (item["id"],)).fetchone()[0] == "working"
    finally:
        conn.close()


def test_deleting_an_item_drops_its_queued_job(client, services):
    item = upload(client).json()
    client.delete(f"/api/items/{item['id']}")
    services.worker.is_ready = lambda: True
    assert drain(services) == 0


def test_an_item_deleted_while_its_cutout_runs_leaves_no_pictures_behind(client, services, cfg):
    item = upload(client).json()
    services.worker.is_ready = lambda: True

    def deleted_meanwhile(img):
        assert client.delete(f"/api/items/{item['id']}").status_code == 204
        return fake_cutter(img)

    services.worker.cutter = deleted_meanwhile
    drain(services)
    assert not (cfg.images_dir("main") / item["id"]).exists()


# ---- model download states

PAYLOAD = bytes(range(256)) * 4000  # about 1 MB
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    truncate_at = None
    hits = []

    def do_GET(self):
        rng = self.headers.get("Range")
        start = int(rng.split("=")[1].rstrip("-")) if rng else 0
        Handler.hits.append(start)
        body = PAYLOAD[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if Handler.truncate_at is not None:
            body = body[: Handler.truncate_at]
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Handler.truncate_at, Handler.hits = None, []
    yield f"http://127.0.0.1:{srv.server_address[1]}/model.onnx"
    srv.shutdown()


def store(tmp_path, url, digest=DIGEST, on_ready=None):
    return ModelStore(tmp_path / "models", State(tmp_path / "settings.json"), on_ready=on_ready, sha256=digest, default_url=url)


def test_download_verifies_the_checksum_and_becomes_ready(tmp_path, server):
    ready = []
    m = store(tmp_path, server, on_ready=lambda: ready.append(1))
    m.refresh()
    assert m.info()["state"] == "missing"
    assert m.start_download() is True
    m.wait(10)
    info = m.info()
    assert info["state"] == "ready" and info["downloaded_bytes"] == len(PAYLOAD) == info["total_bytes"] and ready == [1]
    again = store(tmp_path, server)
    again.refresh()
    assert again.ready and again.start_download() is False


def test_the_second_model_downloads_from_its_own_address_setting(tmp_path, server):
    """The second model keeps its download address under its own setting. That setting was missing from the
    settings' defaults, so reading it failed inside the download thread: since 0.5.0 the second model never
    downloaded, stayed "downloading" for good, and every cutout was made by the first model alone."""
    from closet.modelstore import SECOND_MODEL
    m = ModelStore(tmp_path / "models", State(tmp_path / "settings.json"), name=SECOND_MODEL, url_key="second_model_url",
                   sha256=DIGEST, default_url=server)
    assert m.info()["url"] == server
    assert m.start_download() is True
    m.wait(10)
    assert m.ready


def test_a_download_that_breaks_unexpectedly_fails_and_can_be_tried_again(tmp_path, server, monkeypatch):
    """Whatever goes wrong inside the download thread, the model is never left "downloading" for good."""
    m = store(tmp_path, server)
    real = m._download_file
    monkeypatch.setattr(m, "_download_file", lambda: {}["missing"])
    assert m.start_download() is True
    m.wait(10)
    assert m.info()["state"] == "failed" and m.info()["error"]
    monkeypatch.setattr(m, "_download_file", real)
    assert m.start_download() is True
    m.wait(10)
    assert m.ready


def test_a_real_closet_reports_both_models(cfg):
    """Built as the program builds it (the real cutter, so the real second model): GET /api/model answers."""
    from fastapi.testclient import TestClient

    from closet import app as app_module

    from .conftest import PASSPHRASE
    sv = app_module.build_services(cfg, web_dir=None)
    try:
        client = TestClient(app_module.create_app(sv))
        assert client.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        body = client.get("/api/model").json()
        assert body["name"] == "isnet-general-use" and body["state"] == "missing"
        assert body["second"]["name"] == "u2net" and body["second"]["state"] == "missing"
        assert body["second"]["url"].endswith("/u2net.onnx")
    finally:
        sv.stop()


def test_an_interrupted_download_resumes_where_it_stopped(tmp_path, server):
    Handler.truncate_at = 300_000
    m = store(tmp_path, server)
    m.start_download()
    m.wait(10)
    info = m.info()
    assert info["state"] == "failed" and "dropped" in info["error"] and info["downloaded_bytes"] == 300_000
    Handler.truncate_at = None
    m.start_download()
    m.wait(10)
    assert m.ready and Handler.hits == [0, 300_000]


def test_a_wrong_file_is_discarded_with_a_clear_message(tmp_path, server):
    m = store(tmp_path, server, digest="0" * 64)
    m.start_download()
    m.wait(10)
    info = m.info()
    assert info["state"] == "failed" and "checksum" in info["error"] and info["downloaded_bytes"] == 0
    assert not m.path.exists()


@pytest.mark.parametrize("operation", ["mkdir", "replace", "write_text"])
def test_model_download_disk_failures_allow_retry(tmp_path, server, monkeypatch, operation):
    from pathlib import Path

    m = store(tmp_path, server)
    original = getattr(Path, operation)

    def unavailable(path, *args, **kwargs):
        if path in (m.dir, m._part, m._marker):
            raise PermissionError("cannot write model file")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, unavailable)
    assert m.start_download()
    m.wait(10)
    assert m.info()["state"] == "failed"
    assert m.info()["error"] and not m.ready
    monkeypatch.setattr(Path, operation, original)
    assert m.start_download()
    m.wait(10)
    assert m.ready


def test_offline_gives_a_clear_message_and_uploads_still_work(tmp_path):
    m = store(tmp_path, "http://127.0.0.1:9/none")
    m.start_download()
    m.wait(10)
    info = m.info()
    assert info["state"] == "failed" and "internet connection" in info["error"]


def test_a_model_file_placed_by_hand_is_checked(tmp_path, server):
    m = store(tmp_path, server)
    m.dir.mkdir(parents=True)
    m.path.write_bytes(PAYLOAD)
    m.refresh()
    assert m.ready
    bad = store(tmp_path / "other", server)
    bad.dir.mkdir(parents=True)
    bad.path.write_bytes(b"wrong")
    bad.refresh()
    assert bad.info()["state"] == "failed" and "checksum mismatch" in bad.info()["error"]


def test_model_endpoints_report_state_and_take_a_custom_address(client):
    assert client.get("/api/model").json()["state"] == "missing"
    assert client.put("/api/model/url", json={"url": "ftp://x"}).status_code == 422
    assert client.put("/api/model/url", json={"url": "https://example.com/m.onnx"}).json()["url"] == "https://example.com/m.onnx"
    assert client.put("/api/model/url", json={"url": ""}).json()["url"].startswith("https://github.com/")


def _cutter(look: dict):
    """Stands in for the models: a box in the middle of the photo, solid, or see-through in stripes the way the
    first model leaves a striped shirt (`look["as"]`)."""
    import numpy as np
    from PIL import Image

    from closet.cutout import make_cutout

    def cut(img):
        w, h = img.size
        mask = np.zeros((h, w), np.uint8)
        mask[h // 6:h * 5 // 6, w // 4:w * 3 // 4] = 255
        if look["as"] == "striped":
            mask[:, np.arange(w) % 4 != 0] = 0
        return make_cutout(img, Image.fromarray(mask, "L"))[0]
    return cut


def test_a_cutout_made_before_the_second_model_came_is_made_again_when_it_would_change_it(client, services, cfg):
    """The owner's striped shirt, cut out by the first model alone while the second was still downloading (or
    failed to): see-through, and left that way. Once the second model is here, it is made again, once."""
    look, second = {"as": "striped"}, {"ready": False}
    services.worker.is_ready = lambda: True
    services.worker.second = lambda: second["ready"]
    services.worker.cutter = _cutter(look)
    shirt = upload(client, key="shirt").json()
    assert drain(services) == 1
    look["as"] = "solid"
    plain = upload(client, key="plain").json()    # made alone too, but nothing the second model would change
    assert drain(services) == 1
    conn = db.connect(cfg.db_path("main"))
    try:
        def recorded(item):
            return conn.execute("SELECT cutout_second FROM photos WHERE item_id = ?", (item["id"],)).fetchone()[0]

        def cutouts(item):
            return conn.execute("SELECT count(*) FROM jobs WHERE kind = 'cutout' AND item_id = ?", (item["id"],)).fetchone()[0]

        assert recorded(shirt) == 0 and recorded(plain) == 0
        conn.execute("UPDATE photos SET cutout_second = NULL WHERE item_id = ?", (shirt["id"],))   # made before 0035
        assert drain(services) == 0                    # still no second model: nothing is looked at
        second["ready"] = True                         # it has come: the two together cut the shirt out solid
        assert drain(services) == 1
        assert cutouts(shirt) == 2 and cutouts(plain) == 1
        assert recorded(shirt) == 1 and recorded(plain) == 1
        body = client.get(f"/api/items/{shirt['id']}").json()
        assert body["cutout_state"] == "ready"
        from PIL import Image

        from closet.patterns import masks
        with Image.open(cfg.images_dir("main") / body["photos"][0]["cutout_url"].removeprefix("/media/")) as cut:
            assert masks.see_through(cut.getchannel("A")) < masks.SEE_THROUGH
        assert drain(services) == 0                    # each is looked at once
        assert cutouts(shirt) == 2
    finally:
        conn.close()


def test_a_cutout_made_with_the_second_model_there_is_not_looked_at_again(client, services, cfg):
    look = {"as": "striped"}                           # both models leave it see-through: making it again won't help
    services.worker.is_ready = lambda: True
    services.worker.second = lambda: True
    services.worker.cutter = _cutter(look)
    item = upload(client).json()
    assert drain(services) == 1
    assert drain(services) == 0
    conn = db.connect(cfg.db_path("main"))
    try:
        assert conn.execute("SELECT cutout_second FROM photos").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM jobs WHERE kind = 'cutout' AND item_id = ?", (item["id"],)).fetchone()[0] == 1
    finally:
        conn.close()


def test_model_endpoints_give_the_second_model_and_download_both(client, services, tmp_path, server):
    assert client.get("/api/model").json()["second"] is None       # a cutter standing in: there is no second model
    services.second_model = store(tmp_path / "second", server)
    body = client.get("/api/model").json()
    assert body["state"] == "missing" and body["second"]["state"] == "missing"
    services.model = store(tmp_path / "first", server)
    services.model.dir.mkdir(parents=True)
    services.model.path.write_bytes(PAYLOAD)                       # the first one is here already
    body = client.post("/api/model/download").json()
    assert body["state"] == "ready" and body["second"]["state"] in ("downloading", "ready")
    services.second_model.wait(10)
    assert client.get("/api/model").json()["second"]["state"] == "ready"


def test_worker_thread_picks_up_jobs_when_woken(client, services):
    services.worker.is_ready = lambda: True
    services.worker.start()
    item = upload(client).json()
    deadline = time.time() + 10
    while time.time() < deadline and client.get(f"/api/items/{item['id']}").json()["cutout_state"] != "ready":
        time.sleep(0.05)
    assert client.get(f"/api/items/{item['id']}").json()["cutout_state"] == "ready"


# ---- outbound HTTPS (the model download)

def test_https_uses_a_verifying_context_with_trusted_certificates():
    import ssl

    from closet import net
    ctx = net.ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert net.trust_source() == "system certificates"   # truststore is a pinned requirement


def test_a_certificate_failure_is_told_apart_from_no_connection():
    import ssl
    import urllib.error

    from closet import net
    cert = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
    assert net.is_certificate_error(cert)
    assert not net.is_certificate_error(urllib.error.URLError(OSError("Network is unreachable")))
    assert not net.is_certificate_error(TimeoutError())


def test_the_model_download_passes_the_trusted_context(tmp_path, monkeypatch):
    import ssl
    import urllib.error
    import urllib.request

    from closet.modelstore import ModelStore
    from closet.state import State
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["context"] = context
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    store = ModelStore(tmp_path / "models", State(tmp_path / "settings.json"))
    store._download()
    assert isinstance(seen["context"], ssl.SSLContext)
    info = store.info()
    assert info["state"] == "failed" and "certificate" in info["error"]
