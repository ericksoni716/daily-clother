import json
from datetime import date, timedelta

import pytest

from closet import db, wears

from .conftest import photo_bytes, upload

TODAY = date(2026, 11, 12)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)


@pytest.fixture
def item_ids(client):
    first = upload(client, key="shirt").json()["id"]
    second = upload(client, photo_bytes(color=(20, 90, 160)), key="jeans").json()["id"]
    return [first, second]


def undo(client, item_ids, day=TODAY.isoformat()):
    return client.request("DELETE", "/api/wears", json={"item_ids": item_ids, "worn_on": day})


def current_items(client, item_ids):
    return [client.get(f"/api/items/{item_id}").json() for item_id in item_ids]


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_batch_wears_require_login(anon, method):
    response = anon.request(method, "/api/wears", json={"item_ids": ["unknown"], "worn_on": TODAY.isoformat()})
    assert response.status_code == 401


def test_record_outfit_on_one_local_day_and_repeat_without_changes(client, item_ids, monkeypatch):
    calls = []

    def clock():
        calls.append(True)
        return TODAY + timedelta(days=len(calls) - 1)

    monkeypatch.setattr(wears, "today", clock)
    response = client.post("/api/wears", json={"item_ids": item_ids})
    assert response.status_code == 201
    result = response.json()
    assert result["worn_on"] == TODAY.isoformat()
    assert result["created_ids"] == item_ids
    assert len(calls) == 1
    assert [item["id"] for item in result["items"]] == item_ids
    for item in result["items"]:
        assert (item["wear_count"], item["wears_since_wash"], item["last_worn"]) == (1, 1, TODAY.isoformat())
        assert item["recent_wears"] == [TODAY.isoformat()]
        assert item["laundry"] == "clean"
        assert "photos" in item and "silhouette" in item
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    repeated = client.post("/api/wears", json={"item_ids": item_ids})
    assert repeated.status_code == 200
    assert repeated.json() == {**result, "created_ids": []}


def test_undo_only_new_wears_preserves_preexisting_and_retries_after_midnight(client, item_ids, monkeypatch):
    first, second = item_ids
    original = client.post(f"/api/items/{first}/wears").json()
    result = client.post("/api/wears", json={"item_ids": item_ids}).json()
    assert result["created_ids"] == [second]
    assert result["items"][0] == original
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=1))
    removed = undo(client, result["created_ids"], result["worn_on"])
    assert removed.status_code == 200
    assert removed.json()["worn_on"] == TODAY.isoformat()
    assert [item["id"] for item in removed.json()["items"]] == [second]
    assert removed.json()["items"][0]["wear_count"] == 0
    assert removed.json()["items"][0]["wears_since_wash"] == 0
    assert undo(client, result["created_ids"], result["worn_on"]).json() == removed.json()
    assert current_items(client, [first]) == [original]


def test_undo_updates_last_worn_and_respects_wash_and_laundry(client, item_ids):
    first, second = item_ids
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    client.post(f"/api/items/{first}/wears", json={"worn_on": yesterday})
    client.post(f"/api/items/{second}/laundry", json={"state": "laundry"})
    added = client.post("/api/wears", json={"item_ids": item_ids})
    assert added.status_code == 201
    assert [item["wears_since_wash"] for item in added.json()["items"]] == [2, 1]
    client.post(f"/api/items/{first}/laundry", json={"state": "clean"})
    # A wear recorded after washing still counts, even when its calendar day is older.
    older = (TODAY - timedelta(days=2)).isoformat()
    client.post(f"/api/items/{first}/wears", json={"worn_on": older})
    removed = undo(client, item_ids)
    assert removed.status_code == 200
    a, b = removed.json()["items"]
    assert (a["wear_count"], a["wears_since_wash"], a["last_worn"]) == (2, 1, yesterday)
    assert a["recent_wears"] == [yesterday, older]
    assert (b["wear_count"], b["wears_since_wash"], b["last_worn"], b["laundry"]) == (0, 0, None, "laundry")
    assert undo(client, [first], older).json()["items"][0]["wears_since_wash"] == 0
    assert undo(client, [first], yesterday).json()["items"][0]["wears_since_wash"] == 0


@pytest.mark.parametrize("removing", [False, True])
def test_unknown_item_is_checked_before_any_wear_changes(client, item_ids, removing, monkeypatch):
    if removing:
        client.post("/api/wears", json={"item_ids": item_ids})
    before = current_items(client, item_ids)

    def unexpected_write(*args, **kwargs):
        pytest.fail("Every item must be checked before the first wear changes")

    monkeypatch.setattr(wears, "_remove" if removing else "_add", unexpected_write)
    ids = [*item_ids, "unknown"]
    response = undo(client, ids) if removing else client.post("/api/wears", json={"item_ids": ids})
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert current_items(client, item_ids) == before


@pytest.mark.parametrize("removing", [False, True])
def test_unexpected_failure_rolls_back_wears_and_counters(client, item_ids, cfg, monkeypatch, removing):
    if removing:
        client.post("/api/wears", json={"item_ids": item_ids})
    before = current_items(client, item_ids)
    helper = "_remove" if removing else "_add"
    original = getattr(wears, helper)
    calls = []

    def fail_second(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("Simulated interruption")
        return result

    monkeypatch.setattr(wears, helper, fail_second)
    body = {"item_ids": item_ids}
    if removing:
        body["worn_on"] = TODAY.isoformat()
    conn = db.connect(cfg.db_path("main"))
    try:
        with pytest.raises(RuntimeError, match="Simulated interruption"):
            wears.batch(conn, body, removing=removing)
        assert not conn.in_transaction
    finally:
        conn.close()
    assert current_items(client, item_ids) == before


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize("ids", [None, "one", {}, 1, True, [None], [1], [True], [[]], [{}], [""], ["  "], ["x" * 129], ["x", "x"], ["x"] * 51])
def test_batch_rejects_bad_lists_with_readable_error(client, method, ids):
    body = {"item_ids": ids}
    if method == "DELETE":
        body["worn_on"] = TODAY.isoformat()
    response = client.request(method, "/api/wears", json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize("body", [None, [], "items", 1, {}, {"item_ids": ["x"], "extra": True}])
def test_batch_rejects_bad_bodies_with_readable_error(client, method, body):
    # Send JSON null explicitly; httpx's json=None otherwise means no body.
    response = client.request(method, "/api/wears", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_batch_rejects_invalid_json(client, method):
    response = client.request(method, "/api/wears", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json() == {"detail": "The request was not valid JSON."}


@pytest.mark.parametrize("day", [None, 20261112, True, [], "", "yesterday", "20261112", "2026-02-30", "2026-11-12\n", "2026-11-12T00:00:00"])
def test_undo_rejects_bad_date_without_removing_wears(client, item_ids, day):
    client.post("/api/wears", json={"item_ids": item_ids})
    response = undo(client, item_ids, day)
    assert response.status_code == 422
    assert "YYYY-MM-DD" in response.json()["detail"]
    assert [item["wear_count"] for item in current_items(client, item_ids)] == [1, 1]


def test_required_fields_and_empty_undo(client, item_ids):
    assert client.post("/api/wears", json={"item_ids": []}).status_code == 422
    assert client.post("/api/wears", json={"item_ids": item_ids, "worn_on": TODAY.isoformat()}).status_code == 422
    assert client.request("DELETE", "/api/wears", json={"item_ids": item_ids}).status_code == 422
    response = undo(client, [])
    assert response.status_code == 200
    assert response.json() == {"items": [], "worn_on": TODAY.isoformat()}


def test_batch_uses_only_open_closet(client, item_ids):
    client.post("/api/profile", json={"profile": "demo"})
    demo_ids = [item["id"] for item in client.get("/api/items").json()["items"][:2]]
    assert client.post("/api/wears", json={"item_ids": item_ids}).status_code == 404
    assert client.post("/api/wears", json={"item_ids": demo_ids}).status_code == 201
    client.post("/api/profile", json={"profile": "main"})
    assert undo(client, demo_ids).status_code == 404
    assert [item["wear_count"] for item in current_items(client, item_ids)] == [0, 0]
