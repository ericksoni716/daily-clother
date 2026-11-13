import pytest

from closet import trip_weather

from .test_trip_weather import PLACE, meteo  # noqa: F401

pytestmark = pytest.mark.usefixtures("meteo")
SPEC = {"place": PLACE, "first_day": "2026-11-14", "last_day": "2026-11-18", "occasion": "casual"}


@pytest.fixture(autouse=True)
def dry_trip(monkeypatch):
    original = trip_weather.lookup
    monkeypatch.setattr(trip_weather, "lookup", lambda *args: [{**d, "rain": False} for d in original(*args)])


@pytest.mark.parametrize("method,path", [
    ("post", "/api/trips/plan"), ("post", "/api/trips"), ("get", "/api/trips"),
    ("get", "/api/trips/no"), ("patch", "/api/trips/no"), ("delete", "/api/trips/no")])
def test_login(anon, method, path):
    assert getattr(anon, method)(path).status_code == 401


def test_routes_ticks_swaps_pins_and_profile_isolation(client):
    client.post("/api/profile", json={"profile": "demo"})
    assert client.post("/api/trips/plan", json=SPEC).status_code == 200
    assert client.get("/api/trips").json() == {"trips": []}
    r = client.post("/api/trips", json=SPEC)
    assert r.status_code == 201, r.text
    trip = r.json()
    url = f"/api/trips/{trip['id']}"
    assert client.get(url).json()["plan"] == trip["plan"]
    assert client.get("/api/trips").json()["trips"][0]["id"] == trip["id"]
    ticked = client.patch(url, json={"checked": {"basic:socks": True}, "revision": trip["revision"]})
    assert ticked.status_code == 200, ticked.text
    assert client.get(url).json()["checked"]["basic:socks"]
    assert client.patch(url, json={"revision": trip["revision"], "checked": {"basic:socks": False}}).status_code == 409
    pieces = [p for g in trip["plan"]["packing"].values() for p in g]
    assert pieces
    excluded = pieces[0]["id"]
    changed = client.patch(url, json={"leave_out": [excluded]}).json()
    assert excluded not in {p["id"] for g in changed["plan"]["packing"].values() for p in g}
    pinned = client.patch(url, json={"leave_out": [], "pins": [excluded]}).json()
    assert excluded in {p["id"] for g in pinned["plan"]["packing"].values() for p in g}
    assert client.patch(url, json={"replan": True}).status_code == 200
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/trips").json() == {"trips": []}
    for method in ("get", "patch", "delete"):
        assert getattr(client, method)(url, **({"json": {}} if method == "patch" else {})).status_code == 404
    client.post("/api/profile", json={"profile": "demo"})
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_changed_weather_offers_replan_without_mutating(client, monkeypatch):
    trip = client.post("/api/trips", json=SPEC).json()
    original = trip_weather.lookup

    def changed(*args):
        return [{**d, "high_c": d["high_c"] + 2} for d in original(*args)]

    monkeypatch.setattr(trip_weather, "lookup", changed)
    url = f"/api/trips/{trip['id']}"
    opened = client.get(url).json()
    assert opened["weather_changed"]
    assert opened["plan"] == trip["plan"] and opened["revision"] == trip["revision"]
    replanned = client.patch(url, json={"replan": True}).json()
    assert replanned["plan"]["days"][0]["weather"]["high_c"] == 22
    assert not client.get(url).json()["weather_changed"]


@pytest.mark.parametrize("changes,words", [
    ({"first_day": "2026-11-12"}, "today"), ({"last_day": "2027-01-01"}, "30"),
    ({"occasion": "party"}, "occasion"), ({"can_wash": "yes"}, "wash"),
    ({"pins": ["missing"]}, "closet"), ({"pins": ["a"], "leave_out": ["a"]}, "both"),
    ({"overrides": [{"date": "2026-11-25", "occasion": "business"}]}, "within"),
    ({"overrides": [{"date": [], "occasion": "business"}]}, "within"),
])
def test_wrong_input_in_plain_words(client, changes, words):
    r = client.post("/api/trips/plan", json={**SPEC, **changes})
    assert r.status_code == 422 and words in r.json()["detail"], r.text


def test_wrong_ticks_and_json(client):
    trip = client.post("/api/trips", json=SPEC).json()
    url = f"/api/trips/{trip['id']}"
    assert client.patch(url, json={"checked": {"invented": True}}).status_code == 422
    assert client.patch(url, json={"checked": {"basic:socks": "yes"}}).status_code == 422
    assert client.post("/api/trips/plan", content="bad json").status_code == 400


def test_tick_does_not_fetch_or_plan_and_replan_keeps_only_retained_lines(client, monkeypatch):
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=SPEC).json()
    url = f"/api/trips/{trip['id']}"
    piece = next(p for g in trip["plan"]["packing"].values() for p in g)
    with monkeypatch.context() as patch:
        patch.setattr(trip_weather, "lookup", lambda *args: pytest.fail("Ticking must not fetch weather"))
        r = client.patch(url, json={"checked": {"basic:socks": True, f"item:{piece['id']}": True}})
        assert r.status_code == 200 and r.json()["plan"] == trip["plan"]
    r = client.patch(url, json={"leave_out": [piece["id"]]})
    assert r.status_code == 200
    assert r.json()["checked"] == {"basic:socks": True}


def test_usual_days_become_forecast_without_changing_saved_plan(client, monkeypatch):
    from datetime import UTC, datetime

    from closet import weather

    trip = client.post("/api/trips", json={**SPEC, "first_day": "2026-11-29", "last_day": "2026-11-30"}).json()
    assert trip["plan"]["days"][0]["weather"]["source"] == "usual"
    monkeypatch.setattr(weather, "_now", lambda: datetime(2026, 11, 15, tzinfo=UTC).timestamp())
    opened = client.get(f"/api/trips/{trip['id']}").json()
    assert opened["weather_changed"]
    assert opened["latest_weather"][0]["source"] == "forecast"
    assert opened["plan"] == trip["plan"]
