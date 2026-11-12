import threading

import pytest

from closet import outfits

DAY = {"low_c": 15, "high_c": 20, "rain": False, "occasion": "casual"}
URL = "/api/outfits/suggest"


def test_login_required(anon):
    assert anon.post(URL, json=DAY).status_code == 401


def test_shape_and_profile_isolation(client):
    main = client.post(URL, json=DAY)
    assert main.status_code == 200
    assert main.json()["outfits"] == []
    assert main.json()["messages"]
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    response = client.post(URL, json={**DAY, "count": 3})
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"outfits", "messages"}
    assert len(result["outfits"]) == 3
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"]}
    for outfit in result["outfits"]:
        assert set(outfit) == {"places", "score", "reasons"}
        assert set(outfit["places"]) == {"base_top", "mid_layer", "outer_layer", "bottom", "shoes", "accessories"}
        for place, value in outfit["places"].items():
            if place == "accessories":
                assert set(value) <= demo_ids
            elif value is not None:
                assert value in demo_ids
        assert 0 <= outfit["score"] <= 100
        assert all(isinstance(r, str) for r in outfit["reasons"])
    anchor = result["outfits"][0]["places"]["base_top"]
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.post(URL, json={**DAY, "build_around": anchor}).json()["outfits"] == []
    assert client.get("/api/items").json()["items"] == []


@pytest.mark.parametrize("body", [
    [], None, {}, {**DAY, "low_c": 30}, {**DAY, "high_c": "hot"}, {**DAY, "low_c": True},
    {**DAY, "high_c": 10**400}, {**DAY, "low_c": -61}, {**DAY, "high_c": 61},
    {**DAY, "rain": "no"}, {**DAY, "occasion": "wedding"}, {**DAY, "mood": "wild"},
    {**DAY, "count": 0}, {**DAY, "count": 11}, {**DAY, "count": True},
    {**DAY, "exclude": "abc"}, {**DAY, "exclude": [1]}, {**DAY, "build_around": 5},
    {**DAY, "days_since_worn": {"abc": -1}}, {**DAY, "days_since_worn": {"abc": True}},
    {**DAY, "days_since_worn": []}, {**DAY, "typo": 1},
])
def test_readable_validation(client, body):
    response = client.post(URL, json=body)
    assert response.status_code in (400, 422)
    assert isinstance(response.json()["detail"], str)


def test_invalid_json_and_nonfinite_temperature(client):
    for body in ('{"broken"', '{"low_c": NaN, "high_c": 15, "rain": false, "occasion": "casual"}'):
        response = client.post(URL, content=body, headers={"content-type": "application/json"})
        assert response.status_code in (400, 422)
        assert isinstance(response.json()["detail"], str)


def test_engine_runs_off_event_loop(client, monkeypatch):
    def check_thread(*args):
        assert threading.current_thread().name == "AnyIO worker thread"
        return {"outfits": [], "messages": ["Checked the worker thread."]}

    monkeypatch.setattr(outfits, "suggest", check_thread)
    assert client.post(URL, json=DAY).status_code == 200
