"""Settings in one quick request: phone access looked up in the background, the cheap parts of the page in the one
payload, the keychain and start at login read once, and the slow work of a request kept off the event loop."""
import asyncio
import json
import threading
import time
from types import SimpleNamespace

from closet import apikey, autostart, illustrations, phone, sources
from closet import app as app_module
from closet.tagger import routes as tagger_routes

from .conftest import pile_bytes, upload

HOST = "my-pc.example-tailnet.ts.net"
SHARED = json.dumps({"TCP": {"443": {"HTTPS": True}},
                     "Web": {f"{HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}}}})
RUNNING = json.dumps({"BackendState": "Running"})


def wait_for(check, seconds=5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return check()


# ---------------------------------------------------------------- phone access, in the background
def test_settings_answer_at_once_while_tailscale_hangs(client, services, monkeypatch):
    release, asked = threading.Event(), []

    def hanging(args, **_):   # stands in for a Tailscale that does not answer until it is let go
        asked.append(args[1:3])
        release.wait(5)
        return SimpleNamespace(returncode=0, stdout=SHARED if args[1] == "serve" else RUNNING)

    monkeypatch.setattr(phone, "find_tailscale", lambda: "/usr/bin/tailscale")
    services.phone_watch = phone.Watch(8765, look=lambda port: phone.info(port, runner=hanging))
    try:
        started = time.monotonic()
        r = client.get("/api/settings")
        assert r.status_code == 200 and r.json()["phone"] is None   # not known yet: the page says it is checking
        r = client.put("/api/settings", json={"stylist_on": True})
        assert r.status_code == 200 and r.json()["phone"] is None
        assert time.monotonic() - started < 2   # neither waited for the 5 s the stand-in hangs
        # the two commands are asked at the same time, and the second request did not start a lookup of its own
        assert wait_for(lambda: len(asked) == 2)
        assert sorted(asked) == [["serve", "status"], ["status", "--json"]]
    finally:
        release.set()
    assert services.phone_watch.wait(5)
    got = client.get("/api/settings").json()["phone"]
    assert got["address"] == f"https://{HOST}" and got["running"] is True and len(asked) == 2


def test_phone_access_is_looked_up_again_once_it_is_old():
    now, answers, looked = [100.0], iter([{"address": None}, {"address": "https://pc.example"}]), []

    def look(port):
        looked.append(port)
        return next(answers)

    watch = phone.Watch(8765, look=look, clock=lambda: now[0])
    watch.start()   # at start, before anyone asks
    assert watch.wait(5) and looked == [8765]
    assert watch.current() == {"address": None}
    now[0] += phone.STALE_SECONDS - 1
    assert watch.current() == {"address": None} and watch.wait(5) and len(looked) == 1   # still fresh: not asked
    now[0] += 1
    assert watch.current() == {"address": None}   # old: the last answer at once, and a new lookup behind it
    assert watch.wait(5) and len(looked) == 2
    assert watch.current() == {"address": "https://pc.example"}


def test_a_lookup_that_fails_keeps_the_last_answer_and_only_one_runs_at_a_time():
    release, calls = threading.Event(), []

    def look(port):
        calls.append(port)
        release.wait(5)
        if len(calls) > 1:
            raise RuntimeError("broken stand-in")
        return {"address": None}

    watch = phone.Watch(8765, look=look, stale=0)
    for _ in range(5):
        assert watch.current() is None
    release.set()
    assert watch.wait(5) and calls == [8765]
    assert watch.current() == {"address": None}   # stale at once (0 s): asks again, and that one fails
    assert watch.wait(5) and watch.current() == {"address": None}


# ---------------------------------------------------------------- one payload for the page
def test_settings_carry_what_their_own_endpoints_answer(client, services):
    client.put("/api/style/profile", json={"text": "Navy and grey, mostly."})
    body = client.get("/api/settings").json()
    assert body["model"] == client.get("/api/model").json()
    assert body["updates"] == client.get("/api/updates").json()
    assert body["style_profile"] == client.get("/api/style/profile").json()
    assert body["style_profile"]["text"] == "Navy and grey, mostly."
    assert body["tagging_spend"] == client.get("/api/tagging/spend").json()
    # what a change answers with is the same whole payload
    body = client.put("/api/settings", json={"stylist_on": True}).json()
    assert {"model", "updates", "style_profile", "tagging_spend", "phone", "api_key", "autostart"} <= set(body)
    assert body["tagging_spend"] == client.get("/api/tagging/spend").json()


def test_the_key_is_read_from_the_keychain_once_until_it_is_saved_or_removed(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(apikey, "check", lambda key: None)
    read = []
    real = apikey.info
    monkeypatch.setattr(apikey, "info", lambda: read.append(1) or real())
    for _ in range(3):
        assert client.get("/api/settings").json()["api_key"]["set"] is False
    client.put("/api/settings", json={"stylist_on": True})   # toggling a switch does not read it again
    assert len(read) == 1
    r = client.put("/api/settings/api-key", json={"key": "sk-ant-test-only-0123456789"})
    assert r.json()["api_key"]["set"] is True and r.json()["api_key"]["checked"] is True
    assert "checked" not in client.get("/api/settings").json()["api_key"]   # the note was not kept
    assert client.get("/api/settings").json()["api_key"]["set"] is True and len(read) == 2
    assert client.delete("/api/settings/api-key").json()["api_key"]["set"] is False
    assert client.get("/api/settings").json()["api_key"]["set"] is False and len(read) == 3


def test_start_at_login_is_read_once_until_it_is_changed(client, monkeypatch):
    on, read = [False], []
    monkeypatch.setattr(autostart, "program", lambda: "/opt/Closet/closet")
    monkeypatch.setattr(autostart, "is_enabled", lambda *a, **k: read.append(1) or on[0])
    monkeypatch.setattr(autostart, "set_enabled", lambda enabled, *a, **k: on.__setitem__(0, enabled))
    assert client.get("/api/settings").json()["autostart"] is False
    assert client.get("/api/settings").json()["autostart"] is False and len(read) == 1
    assert client.put("/api/settings", json={"autostart": True}).json()["autostart"] is True
    assert client.get("/api/settings").json()["autostart"] is True and len(read) == 2

    def refuses(enabled, *a, **k):
        on[0] = enabled   # it may have changed part way before it failed: read again either way
        raise RuntimeError("could not")
    monkeypatch.setattr(autostart, "set_enabled", refuses)
    assert client.put("/api/settings", json={"autostart": False}).status_code == 409
    assert client.get("/api/settings").json()["autostart"] is False and len(read) == 3


def test_the_route_check_is_kept_a_few_seconds_and_asked_again_when_its_answer_may_change(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    now, asked = [1000.0], []
    monkeypatch.setattr(app_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    real = tagger_routes.status
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: asked.append(order) or real(order))
    first = client.get("/api/tagging").json()
    assert client.get("/api/tagging").json() == first and asked == ["auto"]   # the page's second ask: no new check
    client.put("/api/settings", json={"tagging_route_order": "plan"})
    assert client.get("/api/tagging").json()["order"] == ["plan"] and asked == ["auto", "plan"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only")   # a key appears: the API route's line changes
    client.put("/api/settings", json={"tagging_route_order": "auto"})
    assert client.get("/api/tagging").json()["routes"][1]["available"] is True and len(asked) == 3
    now[0] += app_module.TAGGING_FRESH_SECONDS
    client.get("/api/tagging")
    assert len(asked) == 4   # old: Claude Code's sign-in is asked again


# ---------------------------------------------------------------- slow work off the event loop
def on_event_loop() -> bool:
    """Whether the caller runs on the event loop, where it would hold up every other request (a worker thread has
    no running loop). Asked of the work itself, so the answer does not depend on how long anything takes."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_an_item_is_redrawn_off_the_event_loop(client, monkeypatch):
    item = upload(client).json()
    real, seen = illustrations.redraw, []

    def redraw(conn, item_id):
        seen.append(on_event_loop())
        real(conn, item_id)
    monkeypatch.setattr(illustrations, "redraw", redraw)
    r = client.patch(f"/api/items/{item['id']}", json={"color": "navy"})
    assert r.status_code == 200 and r.json()["color"] == "navy"
    assert seen == [False]
    # what a wrong change answers is unchanged
    assert client.patch(f"/api/items/{item['id']}", content=b"not json").status_code == 400
    assert client.patch("/api/items/nothing", json={"color": "navy"}).status_code == 404


def test_a_photo_of_several_pieces_is_kept_off_the_event_loop(client, monkeypatch):
    real, seen = sources.create, []

    def create(*args, **kwargs):
        seen.append(on_event_loop())
        return real(*args, **kwargs)
    monkeypatch.setattr(sources, "create", create)
    r = client.post("/api/sources", files={"photo": ("pile.png", pile_bytes(), "image/png")}, data={"client_key": "s1"})
    assert r.status_code == 201 and seen == [False]
