from datetime import date, timedelta
from pathlib import Path

import pytest

from closet import db, wears

from .conftest import photo_bytes, upload

TODAY = date(2026, 11, 12)


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)


def test_a_wear_defaults_to_today_and_there_is_one_per_day(client):
    item = upload(client).json()
    assert (item["wear_count"], item["last_worn"], item["wears_since_wash"], item["laundry"]) == (0, None, 0, "clean")
    first = client.post(f"/api/items/{item['id']}/wears")
    assert first.status_code == 201
    body = first.json()
    assert (body["wear_count"], body["last_worn"], body["wears_since_wash"]) == (1, TODAY.isoformat(), 1)
    assert body["recent_wears"] == [TODAY.isoformat()]
    again = client.post(f"/api/items/{item['id']}/wears", json={"worn_on": TODAY.isoformat()})
    assert again.status_code == 200 and again.json()["wear_count"] == 1 and again.json()["wears_since_wash"] == 1


def test_a_wear_in_the_future_or_a_bad_date_is_refused(client):
    item = upload(client).json()
    future = client.post(f"/api/items/{item['id']}/wears", json={"worn_on": (TODAY + timedelta(days=1)).isoformat()})
    assert future.status_code == 422 and "future" in future.json()["detail"]
    for bad in ("12/11/2026", "2026-13-01", "yesterday", "20261111"):
        r = client.post(f"/api/items/{item['id']}/wears", json={"worn_on": bad})
        assert r.status_code == 422 and "YYYY-MM-DD" in r.json()["detail"]
    assert client.post("/api/items/nope/wears").status_code == 404
    assert client.get(f"/api/items/{item['id']}").json()["wear_count"] == 0


def test_counts_last_worn_listing_and_removing(client):
    item = upload(client).json()
    url = f"/api/items/{item['id']}/wears"
    for n in (5, 1, 9):
        assert client.post(url, json={"worn_on": days_ago(n)}).status_code == 201
    listed = client.get(url).json()["wears"]
    assert [w["worn_on"] for w in listed] == [days_ago(1), days_ago(5), days_ago(9)]
    summary = client.get("/api/items").json()["items"][0]
    assert (summary["wear_count"], summary["last_worn"], summary["wears_since_wash"]) == (3, days_ago(1), 3)

    after = client.delete(f"{url}/{days_ago(1)}")
    assert after.status_code == 200
    assert (after.json()["wear_count"], after.json()["last_worn"], after.json()["wears_since_wash"]) == (2, days_ago(5), 2)
    assert client.delete(f"{url}/{days_ago(1)}").status_code == 404
    assert client.delete(f"{url}/not-a-date").status_code == 422
    assert [w["worn_on"] for w in client.get(url).json()["wears"]] == [days_ago(5), days_ago(9)]


def test_laundry_state_and_marking_clean_resets_the_count(client):
    item = upload(client).json()
    url = f"/api/items/{item['id']}"
    client.post(f"{url}/wears", json={"worn_on": days_ago(3)})
    client.post(f"{url}/wears", json={"worn_on": days_ago(2)})
    dirty = client.post(f"{url}/laundry", json={"state": "laundry"})
    assert dirty.status_code == 200 and dirty.json()["laundry"] == "laundry" and dirty.json()["wears_since_wash"] == 2
    clean = client.post(f"{url}/laundry", json={"state": "clean"}).json()
    assert (clean["laundry"], clean["wears_since_wash"], clean["wear_count"]) == ("clean", 0, 2)
    # a wear from before the wash, removed afterwards, does not make the count go below what was worn since
    client.post(f"{url}/wears")
    assert client.delete(f"{url}/wears/{days_ago(2)}").json()["wears_since_wash"] == 1
    assert client.delete(f"{url}/wears/{TODAY.isoformat()}").json()["wears_since_wash"] == 0
    assert client.post(f"{url}/laundry", json={"state": "dirty"}).status_code == 422
    assert client.post("/api/items/nope/laundry", json={"state": "clean"}).status_code == 404


def test_the_laundry_filter(client):
    a = upload(client, key="a", name="Shirt").json()
    upload(client, photo_bytes(color=(20, 90, 160)), key="b", name="Jeans")   # another photo: the same one is not added twice
    client.post(f"/api/items/{a['id']}/laundry", json={"state": "laundry"})
    names = lambda **p: sorted(i["name"] for i in client.get("/api/items", params=p).json()["items"])  # noqa: E731
    assert names(laundry="laundry") == ["Shirt"]
    assert names(laundry="clean") == ["Jeans"]
    assert names() == ["Jeans", "Shirt"]
    assert client.get("/api/items", params={"laundry": "wet"}).status_code == 422


def test_the_laundry_is_not_a_location_any_more(client):
    item = upload(client).json()
    assert "laundry" not in client.get("/api/vocab").json()["location"]
    r = client.patch(f"/api/items/{item['id']}", json={"location": "laundry"})
    assert r.status_code == 422 and "Put in the laundry" in r.json()["detail"]
    assert client.patch(f"/api/items/{item['id']}", json={"location": "drawer"}).json()["location"] == "drawer"


def test_wears_need_login(anon):
    assert anon.get("/api/items/x/wears").status_code == 401
    assert anon.post("/api/items/x/wears").status_code == 401
    assert anon.delete(f"/api/items/x/wears/{TODAY.isoformat()}").status_code == 401
    assert anon.post("/api/items/x/laundry", json={"state": "clean"}).status_code == 401


def test_demo_has_a_recent_history_and_is_separate_from_the_main_closet(client):
    mine = upload(client, name="Mine").json()
    client.post(f"/api/items/{mine['id']}/wears")
    client.post("/api/profile", json={"profile": "demo"})
    listed = client.get("/api/items").json()["items"]
    worn = [i for i in listed if i["last_worn"]]
    assert len(worn) >= 8 and all(days_ago(14) <= i["last_worn"] < TODAY.isoformat() for i in worn)
    assert 2 <= sum(i["laundry"] == "laundry" for i in listed) <= 5
    assert all(i["wears_since_wash"] <= i["wear_count"] for i in listed)
    assert client.get(f"/api/items/{mine['id']}/wears").status_code == 404
    jeans = next(i for i in listed if i["name"] == "Dark indigo jeans")
    client.post(f"/api/items/{jeans['id']}/wears")
    client.post("/api/profile", json={"profile": "main"})
    assert client.get(f"/api/items/{jeans['id']}/wears").status_code == 404
    assert [(i["name"], i["wear_count"]) for i in client.get("/api/items").json()["items"]] == [("Mine", 1)]


def test_the_migration_runs_on_a_closet_made_by_the_previous_version(tmp_path, monkeypatch):
    path, backups = tmp_path / "closet.db", tmp_path / "bk"
    real = db.migration_files()
    previous = [(v, p) for v, p in real if v < 4]
    monkeypatch.setattr(db, "migration_files", lambda: previous)
    db.migrate(path, backups)
    conn = db.connect(path)
    t = db.now()
    for item_id, location in (("a", "laundry"), ("b", "drawer"), ("c", None)):
        conn.execute("INSERT INTO items (id, location, created_at, updated_at) VALUES (?, ?, ?, ?)", (item_id, location, t, t))
    conn.close()

    monkeypatch.setattr(db, "migration_files", lambda: real)
    result = db.migrate(path, backups)
    assert 4 in result["applied"] and result["backup"] and Path(result["backup"]).exists()
    conn = db.connect(path)
    rows = {r["id"]: (r["location"], r["laundry"], r["wears_since_wash"])
            for r in conn.execute("SELECT id, location, laundry, wears_since_wash FROM items")}
    assert rows == {"a": (None, "laundry", 0), "b": ("drawer", "clean", 0), "c": (None, "clean", 0)}
    conn.execute("INSERT INTO wears (item_id, worn_on, created_at) VALUES ('a', '2026-11-01', ?)", (t,))
    with pytest.raises(Exception, match="UNIQUE"):
        conn.execute("INSERT INTO wears (item_id, worn_on, created_at) VALUES ('a', '2026-11-01', ?)", (t,))
    conn.execute("DELETE FROM items WHERE id = 'a'")
    assert conn.execute("SELECT COUNT(*) FROM wears").fetchone()[0] == 0
    conn.close()
    # the copy taken first is the closet as the previous version left it
    old = db.connect(Path(result["backup"]))
    assert old.execute("SELECT location FROM items WHERE id = 'a'").fetchone()[0] == "laundry"
    old.close()
