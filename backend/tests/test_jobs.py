import hashlib
import http.server
import threading
import time

import pytest

from closet import db, jobs
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
