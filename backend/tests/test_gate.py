"""Who may come in, checked before a body is read (closet/gate.py): the address, the window's key, the page's header.

The login and the size limits, the gate's other two checks, are in test_auth.py and test_uploads.py."""
import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import gate
from closet.state import State

from .conftest import PASSPHRASE

KEY = "a-window-key-for-tests"


@pytest.mark.parametrize("header, name", [
    ("127.0.0.1:8765", "127.0.0.1"), ("LOCALHOST", "localhost"), ("[::1]:8765", "[::1]"),
    ("closet-pc.example-tailnet.ts.net", "closet-pc.example-tailnet.ts.net"), ("", ""), ("[::1", "[::1"),
])
def test_the_name_in_the_host_header(header, name):
    assert gate.host_name(header) == name


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "closet-pc.example-tailnet.ts.net"])
def test_this_computer_and_tailscale_are_let_in(anon, host):
    assert anon.get("/api/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("host", ["closet.example", "127.0.0.1.example", "ts.net", ".ts.net", "evil-ts.net", "", "0.0.0.0"])
def test_any_other_address_is_refused(anon, host):
    r = anon.get("/api/health", headers={"host": host})
    assert r.status_code == 403 and r.json() == {"detail": gate.WRONG_ADDRESS}
    page = anon.get("/", headers={"host": host})
    assert page.status_code == 403 and page.headers["content-type"].startswith("text/html")
    assert "Nines is not at this address" in page.text


def test_a_change_without_the_pages_header_is_refused_and_says_to_reload(anon, services):
    anon.headers.pop(gate.CLIENT_HEADER)
    r = anon.post("/api/setup", json={"passphrase": PASSPHRASE})
    assert r.status_code == 403 and r.json() == {"detail": gate.OLD_PAGE}
    assert anon.get("/api/session").json()["setup_required"] is True   # nothing was done
    for method in ("put", "patch", "delete"):
        assert getattr(anon, method)("/api/settings").status_code == 403
    assert anon.post("/api/setup", json={"passphrase": PASSPHRASE},
                     headers={gate.CLIENT_HEADER: "1"}).status_code == 204


def test_another_copy_of_the_program_needs_no_header(anon, services):
    anon.headers.pop(gate.CLIENT_HEADER)
    r = anon.post("/api/instance/show")
    assert r.status_code == 403 and r.json() == {"detail": "Not allowed."}   # its own token check, not the header


@pytest.fixture
def keyed(services):
    """Closet as the launcher runs it: with the key of its own window in force."""
    return TestClient(app_module.create_app(services, window_key=KEY), follow_redirects=False)


def test_with_a_key_this_computer_needs_it(keyed):
    r = keyed.get("/api/session")
    assert r.status_code == 401 and r.json() == {"detail": gate.OPEN_FROM_ICON}
    page = keyed.get("/settings")   # an old bookmark: a page to read, not the page's own sentence
    assert page.status_code == 401 and page.headers["content-type"].startswith("text/html")
    assert "<h1>Open Nines from its icon</h1>" in page.text
    assert keyed.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 401
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
    assert keyed.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 401
    keyed.get(f"/?key={KEY}")
    assert keyed.post("/api/setup", json={"passphrase": PASSPHRASE}).json() == {"detail": gate.OLD_PAGE}


def test_tailscale_is_never_asked_for_the_key_and_cannot_get_it(keyed):
    phone = {"host": "closet-pc.example-tailnet.ts.net"}
    assert keyed.get("/api/session", headers=phone).status_code == 200
    r = keyed.get(f"/?key={KEY}", headers=phone)
    assert r.status_code == 200 and "set-cookie" not in r.headers
    assert keyed.post("/api/setup", json={"passphrase": PASSPHRASE}, headers=phone).status_code == 204


def test_the_key_is_made_once_and_kept(cfg):
    state = State(cfg.state_path)
    key = gate.window_key(state)
    assert len(key) >= 40
    assert gate.window_key(State(cfg.state_path)) == key   # the same after a restart
    assert gate.keyed_url("http://127.0.0.1:8765/", key) == f"http://127.0.0.1:8765/?key={key}"
    assert gate.keyed_url("http://127.0.0.1:8765/", None) == "http://127.0.0.1:8765/"
