import time

from closet import auth

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
