"""Who may come in, checked before a body is read (closet/gate.py): the address, the window's key, the page's header.

The doors from outside are in test_tailnet.py (Tailscale) and test_access.py (Cloudflare); the size limits, the gate's
last check, in test_uploads.py."""
import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import gate
from closet.state import State

KEY = "a-window-key-for-tests"
PHONE = "closet-pc.example-tailnet.ts.net"
ME = {"Tailscale-User-Login": "owner@example.com", "Tailscale-User-Name": "Sam Owner"}


@pytest.mark.parametrize("header, name", [
    ("127.0.0.1:8765", "127.0.0.1"), ("LOCALHOST", "localhost"), ("[::1]:8765", "[::1]"),
    ("closet-pc.example-tailnet.ts.net", "closet-pc.example-tailnet.ts.net"), ("", ""), ("[::1", "[::1"),
])
def test_the_name_in_the_host_header(header, name):
    assert gate.host_name(header) == name


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "closet-pc.example-tailnet.ts.net"])
def test_this_computer_and_tailscale_are_let_in(client, host):
    assert client.get("/api/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("host", ["closet.example", "127.0.0.1.example", "ts.net", ".ts.net", "evil-ts.net", "", "0.0.0.0"])
def test_any_other_address_is_refused(client, host):
    r = client.get("/api/health", headers={"host": host})
    assert r.status_code == 403 and r.json() == {"detail": gate.WRONG_ADDRESS}
    page = client.get("/", headers={"host": host})
    assert page.status_code == 403 and page.headers["content-type"].startswith("text/html")
    assert "Nines is not at this address" in page.text


def test_a_change_without_the_pages_header_is_refused_and_says_to_reload(client, services):
    client.headers.pop(gate.CLIENT_HEADER)
    r = client.post("/api/profile", json={"profile": "demo"})
    assert r.status_code == 403 and r.json() == {"detail": gate.OLD_PAGE}
    assert client.get("/api/session").json()["profile"] == "main"   # nothing was done
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)("/api/settings").status_code == 403
    assert client.post("/api/profile", json={"profile": "demo"}, headers={gate.CLIENT_HEADER: "1"}).status_code == 200


def test_another_copy_of_the_program_needs_no_header(client, services):
    client.headers.pop(gate.CLIENT_HEADER)
    r = client.post("/api/instance/show")
    assert r.status_code == 403 and r.json() == {"detail": "Not allowed."}   # its own token check, not the header


@pytest.fixture
def keyed(services):
    """Nines as the launcher runs it: with the key of its own window in force."""
    return TestClient(app_module.create_app(services, window_key=KEY), follow_redirects=False)


def test_with_a_key_this_computer_needs_it(keyed):
    r = keyed.get("/api/session")
    assert r.status_code == 401 and r.json() == {"detail": gate.OPEN_FROM_ICON}
    page = keyed.get("/settings")   # an old bookmark: a page to read, not the page's own sentence
    assert page.status_code == 401 and page.headers["content-type"].startswith("text/html")
    assert "<h1>Open Nines from its icon</h1>" in page.text
    assert keyed.post("/api/profile", json={"profile": "demo"}).status_code == 401
    assert keyed.get("/api/health").status_code == 200
    assert keyed.post("/api/instance/show").json() == {"detail": "Not allowed."}   # the lock file's token instead


def test_opening_the_keyed_address_sets_the_cookie_and_leads_on_without_the_key(keyed):
    assert keyed.get("/?key=not-the-key").status_code == 401 and not keyed.cookies
    assert keyed.get("/api/session?key=" + KEY).status_code == 401   # only a page swaps the key, never a call
    r = keyed.get(f"/item/a%20b?key={KEY}&from=icon")
    assert r.status_code == 303 and r.headers["location"] == "/item/a%20b?from=icon"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"closet_key_8765={KEY};")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Max-Age=34560000" in cookie
    assert keyed.get("/api/session").status_code == 200
    assert KEY not in keyed.get("/api/session").text
    assert keyed.get("/%2Felsewhere.example?key=" + KEY).headers["location"] == "/elsewhere.example"


def test_order_address_then_key_then_header(keyed):
    assert keyed.get("/api/health", headers={"host": "closet.example"}).status_code == 403
    keyed.headers.pop(gate.CLIENT_HEADER)
    assert keyed.post("/api/profile", json={"profile": "demo"}).status_code == 401
    keyed.get(f"/?key={KEY}")
    assert keyed.post("/api/profile", json={"profile": "demo"}).json() == {"detail": gate.OLD_PAGE}


def test_tailscale_is_never_asked_for_the_key_and_cannot_get_it(keyed):
    phone = {"host": PHONE, **ME}
    assert keyed.get("/api/session", headers=phone).status_code == 200
    r = keyed.get(f"/?key={KEY}", headers=phone)
    assert r.status_code == 200 and "set-cookie" not in r.headers
    assert keyed.post("/api/profile", json={"profile": "demo"}, headers=phone).status_code == 200


def test_the_key_is_made_once_and_kept(cfg):
    state = State(cfg.state_path)
    key = gate.window_key(state)
    assert len(key) >= 40
    assert gate.window_key(State(cfg.state_path)) == key   # the same after a restart
    assert gate.keyed_url("http://127.0.0.1:8765/", key) == f"http://127.0.0.1:8765/?key={key}"
    assert gate.keyed_url("http://127.0.0.1:8765/", None) == "http://127.0.0.1:8765/"


# ------------------------------------------------------------------ no passphrase: the door decides


def test_health_reports_the_model_state(client):
    body = client.get("/api/health").json()
    assert body["app"] == "closet" and body["status"] == "ok" and body["model_state"] == "missing"
    assert "setup_required" not in body


def test_the_computers_own_door_needs_only_the_key(keyed):
    """With the key's cookie, everything opens: no passphrase, no session, nothing else asked."""
    assert keyed.get("/api/items").status_code == 401
    keyed.get(f"/?key={KEY}")
    assert keyed.get("/api/items").status_code == 200
    assert keyed.put("/api/settings", json={"stylist_on": False}).status_code == 200
    assert keyed.get("/api/session").json() == {"authenticated": True, "version": app_module.__version__,
                                               "profile": "main"}


def test_without_a_key_in_force_this_computer_is_let_straight_in(client):
    """As tests make the app (no window key), the first call of a first run already reaches the closet."""
    assert client.get("/api/items").json() == {"items": []}
    assert client.get("/api/settings").json()["came_in"] == {"via": "computer", "login": None, "name": None}


def test_an_old_session_cookie_is_ignored_and_taken_away(client):
    client.cookies.set("closet_session", "a-token-from-an-older-nines")
    assert client.get("/api/items").status_code == 200
    r = client.get("/api/session")
    assert r.status_code == 200 and r.json()["authenticated"] is True
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("closet_session=") and "Max-Age=0" in cookie and "a-token" not in cookie
    assert "set-cookie" not in TestClient(client.app).get("/api/session").headers   # nothing to take away


@pytest.mark.parametrize("path", ["/api/setup", "/api/login", "/api/logout"])
def test_the_passphrases_old_calls_tell_an_old_page_to_reload(client, path):
    """A page from an older Nines shows the sentence it is given; reloading brings the new page."""
    r = client.post(path, json={"passphrase": "anything at all"})
    assert r.status_code == 410 and r.json() == {"detail": gate.OLD_PAGE}
    assert "anything at all" not in r.text


def test_every_call_refuses_a_tailscale_request_that_names_no_one(services):
    """No call of the API is open on its own: each is behind its door. (Before, each module tested that its calls
    needed the login; the door's check is the same for every call, so it is tested once here, over all of them.)"""
    app = app_module.create_app(services)
    phone = TestClient(app, base_url=f"https://{PHONE}")
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/") or route.path == "/api/health":
            continue
        path = route.path.replace("{", "").replace("}", "")   # any value will do: the door answers first
        for method in route.methods - {"HEAD"}:
            r = phone.request(method, path)
            assert r.status_code == 401 and r.json() == {"detail": gate.NO_TAILSCALE_VIEWER}, (method, path)
            checked += 1
    assert checked > 100


def test_the_old_passphrase_is_taken_out_of_the_settings_file(cfg):
    cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
    old = {"passphrase": {"salt": "c2FsdA==", "hash": "aGFzaA==", "n": 32768, "r": 8, "p": 1},
           "sessions": {"abc": 1.0}, "failed_logins": [1.0], "profile": "demo", "update_mode": "never"}
    cfg.state_path.write_text(json.dumps(old), encoding="utf-8")
    state = State(cfg.state_path)
    kept = json.loads(cfg.state_path.read_text(encoding="utf-8"))
    assert not {"passphrase", "sessions", "failed_logins"} & set(kept)
    assert kept["profile"] == "demo" and kept["update_mode"] == "never" and state.get("profile") == "demo"
    before = cfg.state_path.stat().st_mtime_ns
    State(cfg.state_path)   # nothing more to take out: not written again
    assert cfg.state_path.stat().st_mtime_ns == before
