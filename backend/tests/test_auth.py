import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from closet import auth
from closet.state import State

from .conftest import PASSPHRASE


def test_first_run_requires_a_passphrase_then_logs_in(anon):
    assert anon.get("/api/session").json() == {"authenticated": False, "setup_required": True, "version": anon.get("/api/health").json()["version"], "profile": "main"}
    assert anon.get("/api/items").status_code == 401
    assert anon.post("/api/setup", json={"passphrase": "short"}).status_code == 422
    r = anon.post("/api/setup", json={"passphrase": PASSPHRASE})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anon.get("/api/session").json()["authenticated"] is True
    assert anon.get("/api/items").status_code == 200
    assert anon.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 409


def test_concurrent_setup_keeps_the_first_passphrase_and_session(anon, services, monkeypatch):
    hashing = Barrier(2)
    real_hash = auth._hash

    def together(*args):
        hashing.wait(timeout=10)
        return real_hash(*args)

    def setup(passphrase):
        browser = TestClient(anon.app)
        response = browser.post("/api/setup", json={"passphrase": passphrase})
        return passphrase, response, browser

    with monkeypatch.context() as patch:
        patch.setattr(auth, "_hash", together)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(setup, (PASSPHRASE, "another synthetic passphrase")))

    assert sorted(response.status_code for _, response, _ in results) == [204, 409]
    passphrase, _, browser = next(result for result in results if result[1].status_code == 204)
    assert browser.get("/api/session").json()["authenticated"] is True
    assert len(services.state.get("sessions")) == 1
    assert browser.post("/api/login", json={"passphrase": passphrase}).status_code == 204


def test_cookie_is_marked_secure_behind_https(anon):
    r = anon.post("/api/setup", json={"passphrase": PASSPHRASE}, headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_logout_and_login_again(client):
    assert client.post("/api/logout").status_code == 204
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/login", json={"passphrase": "wrong wrong wrong"}).status_code == 401
    assert client.post("/api/login", json={"passphrase": PASSPHRASE}).status_code == 204
    assert client.get("/api/items").status_code == 200


def test_wrong_guesses_are_slowed_down(client, services):
    client.post("/api/logout")
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/login", json={"passphrase": "nope nope nope"}).status_code == 401
    r = client.post("/api/login", json={"passphrase": PASSPHRASE})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    services.state.update(failed_logins=[time.time() - auth.WINDOW_SECONDS - 1] * auth.MAX_FAILURES)
    assert client.post("/api/login", json={"passphrase": PASSPHRASE}).status_code == 204


@pytest.mark.parametrize("failures", [0, auth.MAX_FAILURES - 1])
def test_concurrent_wrong_guesses_obey_and_persist_the_limit(client, services, monkeypatch, failures):
    state = services.state
    state.update(failed_logins=[time.time()] * failures)
    readers = Barrier(10)
    real_get = state.get

    def overlapping_reads(key):
        value = real_get(key)
        if key == "failed_logins":
            readers.wait(timeout=10)
        return value

    def guess(_):
        return TestClient(client.app).post("/api/login", json={"passphrase": "synthetic wrong guess"})

    with monkeypatch.context() as patch:
        patch.setattr(state, "get", overlapping_reads)
        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(guess, range(10)))

    statuses = [response.status_code for response in responses]
    assert statuses.count(401) == auth.MAX_FAILURES - failures
    assert statuses.count(429) == 10 - (auth.MAX_FAILURES - failures)
    assert all(int(r.headers["retry-after"]) > 0 for r in responses if r.status_code == 429)
    assert len(state.get("failed_logins")) == auth.MAX_FAILURES
    reloaded = State(state.path)
    assert reloaded.get("failed_logins") == state.get("failed_logins")
    with pytest.raises(auth.AuthError) as blocked:
        auth.check_passphrase(reloaded, PASSPHRASE)
    assert blocked.value.status == 429


def test_passphrase_is_never_stored_in_the_clear(client, cfg):
    text = cfg.state_path.read_text()
    assert PASSPHRASE not in text and "hash" in text


def test_expired_and_unknown_sessions_are_refused(services):
    token = auth.new_session(services.state)
    assert auth.session_valid(services.state, token)
    assert not auth.session_valid(services.state, "made-up")
    services.state.mutate(lambda d: d["sessions"].update({k: time.time() - 1 for k in d["sessions"]}))
    assert not auth.session_valid(services.state, token)


def test_health_is_open_and_reports_model_state(anon):
    body = anon.get("/api/health").json()
    assert body["app"] == "closet" and body["status"] == "ok" and body["model_state"] == "missing" and body["setup_required"]
