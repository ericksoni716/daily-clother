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


def test_an_outfit_is_worn_and_undone_in_one_call(client):
    a, b, c = (upload(client, key=k, data=photo_bytes(color=col)).json()["id"] for k, col in
               (("a", (10, 20, 30)), ("b", (40, 50, 60)), ("c", (70, 80, 90))))
    # c was already worn today on its own: wearing the outfit leaves it as it is, and undoing the outfit too
    client.post(f"/api/items/{c}/wears")
    r = client.post("/api/wears", json={"item_ids": [a, b, c, a]})
    assert r.status_code == 201
    body = r.json()
    assert body["worn_on"] == TODAY.isoformat() and body["recorded"] == [a, b]
    assert [i["id"] for i in body["items"]] == [a, b, c]
    assert all((i["wear_count"], i["last_worn"], i["wears_since_wash"]) == (1, TODAY.isoformat(), 1) for i in body["items"])
    again = client.post("/api/wears", json={"item_ids": [a, b]})
    assert again.status_code == 200 and again.json()["recorded"] == []

    undone = client.post("/api/wears/remove", json={"item_ids": body["recorded"], "worn_on": body["worn_on"]})
    assert undone.status_code == 200
    assert undone.json()["removed"] == [a, b]
    assert [(i["wear_count"], i["last_worn"]) for i in undone.json()["items"]] == [(0, None), (0, None)]
    assert client.get(f"/api/items/{c}").json()["wear_count"] == 1
    # nothing left to remove that day is not an error
    assert client.post("/api/wears/remove", json={"item_ids": [a], "worn_on": TODAY.isoformat()}).json()["removed"] == []

    # another day can be given
    worn = client.post("/api/wears", json={"item_ids": [a], "worn_on": days_ago(2)}).json()
    assert worn["worn_on"] == days_ago(2) and worn["items"][0]["last_worn"] == days_ago(2)


def test_an_outfit_wear_is_all_or_nothing_and_checks_what_it_is_given(client):
    a = upload(client).json()["id"]
    r = client.post("/api/wears", json={"item_ids": [a, "nope"]})
    assert r.status_code == 404
    assert client.get(f"/api/items/{a}").json()["wear_count"] == 0
    for body, words in (({"item_ids": []}, "list of item ids"), ({"item_ids": [""]}, "list of item ids"),
                        ({"item_ids": [a], "worn_on": (TODAY + timedelta(days=1)).isoformat()}, "future"),
                        ({"item_ids": [a], "worn_on": "yesterday"}, "YYYY-MM-DD"),
                        ({"item_ids": [f"x{n}" for n in range(21)]}, "at most 20")):
        r = client.post("/api/wears", json=body)
        assert r.status_code == 422 and words in r.json()["detail"], body
    assert client.post("/api/wears", json={"item_ids": [a], "extra": 1}).status_code == 422
    assert client.post("/api/wears/remove", json={"item_ids": [a]}).status_code == 422
    assert client.post("/api/wears/remove", json={"item_ids": [a], "worn_on": "12/11/2026"}).status_code == 422
    assert client.post("/api/wears/remove", json={"item_ids": [a, "nope"], "worn_on": TODAY.isoformat()}).status_code == 404
    assert client.get(f"/api/items/{a}").json()["wear_count"] == 0


def test_removing_an_outfit_wear_after_a_wash_keeps_the_count_right(client):
    a = upload(client).json()["id"]
    client.post("/api/wears", json={"item_ids": [a]})
    client.post(f"/api/items/{a}/laundry", json={"state": "clean"})
    after = client.post("/api/wears/remove", json={"item_ids": [a], "worn_on": TODAY.isoformat()}).json()["items"][0]
    assert (after["wear_count"], after["wears_since_wash"]) == (0, 0)


def test_outfit_wears_need_login(anon):
    assert anon.post("/api/wears", json={"item_ids": ["x"]}).status_code == 401
    assert anon.post("/api/wears/remove", json={"item_ids": ["x"], "worn_on": TODAY.isoformat()}).status_code == 401


def test_demo_has_a_recent_history_and_is_separate_from_the_main_closet(client):
    mine = upload(client, name="Mine").json()
    client.post(f"/api/items/{mine['id']}/wears")
    client.post("/api/profile", json={"profile": "demo"})
    listed = client.get("/api/items").json()["items"]
    worn = [i for i in listed if i["last_worn"]]
    assert len(worn) >= 8 and all(days_ago(21) <= i["last_worn"] < TODAY.isoformat() for i in worn)
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


# ------------------------------------------------------------------ laundry that keeps itself (17 November)
def test_what_is_in_the_laundry_keeps_its_place_through_migration_30(tmp_path, monkeypatch):
    # pieces already in the laundry are dated from their last change, so the first laundry day washes them
    path, backups = tmp_path / "closet.db", tmp_path / "bk"
    real = db.migration_files()
    monkeypatch.setattr(db, "migration_files", lambda: [(v, p) for v, p in real if v < 30])
    db.migrate(path, backups)
    conn = db.connect(path)
    for item_id, state in (("a", "laundry"), ("b", "clean")):
        conn.execute("INSERT INTO items (id, laundry, created_at, updated_at) VALUES (?, ?, '2026-11-01T09:00:00.000000Z', "
                     "'2026-11-02T09:00:00.000000Z')", (item_id, state))
    conn.close()
    monkeypatch.setattr(db, "migration_files", lambda: real)
    assert 30 in db.migrate(path, backups)["applied"]
    conn = db.connect(path)
    rows = {r["id"]: (r["laundry_at"], r["laundry_by"]) for r in conn.execute("SELECT id, laundry_at, laundry_by FROM items")}
    conn.close()
    assert rows == {"a": ("2026-11-02T09:00:00.000000Z", "owner"), "b": (None, None)}


def kind(client, category, key):
    item = upload(client, key=key).json()
    assert client.patch(f"/api/items/{item['id']}", json={"category": category}).status_code == 200
    return item["id"]


def laundry(client, item_id):
    return client.get(f"/api/items/{item_id}").json()["laundry"]


def wear(client, item_id, n):
    assert client.post(f"/api/items/{item_id}/wears", json={"worn_on": days_ago(n)}).status_code in (200, 201)


def test_worn_clothes_go_in_the_laundry_by_themselves_after_their_count(client):
    # "Before it needs washing": tops after 1 wear, trousers after 3, jackets and coats and shoes never
    tee, trousers, jacket, shoes = (kind(client, c, c) for c in ("tee", "trousers", "jacket", "sneakers"))
    wear(client, tee, 0)
    assert laundry(client, tee) == "laundry"
    for n in (3, 2):
        wear(client, trousers, n)
    assert laundry(client, trousers) == "clean"
    wear(client, trousers, 1)
    assert laundry(client, trousers) == "laundry"
    for n in range(6):
        wear(client, jacket, n)
        wear(client, shoes, n)
    assert laundry(client, jacket) == laundry(client, shoes) == "clean"
    # the owner's own count wins: trousers after one wear
    assert client.put("/api/settings", json={"rewear": {"bottoms": 1}}).status_code == 200
    other = kind(client, "jeans", "jeans")
    wear(client, other, 0)
    assert laundry(client, other) == "laundry"


def test_undoing_the_wear_that_put_it_in_takes_it_back_out_but_never_one_put_in_by_hand(client):
    tee, shirt = kind(client, "tee", "t"), kind(client, "shirt", "s")
    wear(client, tee, 0)
    assert laundry(client, tee) == "laundry"
    assert client.delete(f"/api/items/{tee}/wears/{days_ago(0)}").status_code == 200
    assert laundry(client, tee) == "clean"
    # an outfit undone as one does the same
    worn = client.post("/api/wears", json={"item_ids": [tee, shirt]}).json()
    assert {i["laundry"] for i in worn["items"]} == {"laundry"}
    client.post("/api/wears/remove", json={"item_ids": [tee, shirt], "worn_on": worn["worn_on"]})
    assert laundry(client, tee) == laundry(client, shirt) == "clean"
    # put in by hand: undoing a wear leaves it where the owner put it
    client.post(f"/api/items/{shirt}/laundry", json={"state": "laundry"})
    wear(client, shirt, 2)
    client.delete(f"/api/items/{shirt}/wears/{days_ago(2)}")
    assert laundry(client, shirt) == "laundry"


def test_the_laundry_day_washes_what_went_in_before_it(client, cfg, monkeypatch):
    # TODAY is a Thursday; with Sunday as the laundry day, what went in before last Sunday is clean, the rest waits
    assert client.put("/api/settings", json={"laundry": {"auto": True, "day": 6}}).status_code == 200
    old, new, undated = kind(client, "tee", "o"), kind(client, "shirt", "n"), kind(client, "polo", "u")
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = '2026-11-06T10:00:00.000000Z', laundry_by = 'auto', "
                     "wears_since_wash = 1 WHERE id = ?", (old,))
        conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = '2026-11-10T10:00:00.000000Z', laundry_by = 'auto' "
                     "WHERE id = ?", (new,))
        conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = NULL WHERE id = ?", (undated,))   # the demo's kind
    finally:
        conn.close()
    wears._caught_up.clear()
    listed = {i["id"]: i for i in client.get("/api/items").json()["items"]}
    assert listed[old]["laundry"] == "clean" and listed[old]["wears_since_wash"] == 0
    assert listed[new]["laundry"] == "laundry" and listed[undated]["laundry"] == "laundry"
    # a week on, the next Sunday has washed the other one too
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=4))
    assert laundry(client, new) == "clean"
    assert wears.last_laundry_day(6, TODAY) == date(2026, 11, 8) and wears.next_laundry_day(6, TODAY) == date(2026, 11, 15)


def test_the_laundry_setting_can_be_turned_off_and_is_checked(client):
    assert client.get("/api/settings").json()["laundry"] == {"auto": True, "day": 6}
    assert client.put("/api/settings", json={"laundry": {"auto": False}}).status_code == 200
    tee = kind(client, "tee", "t")
    wear(client, tee, 0)
    assert laundry(client, tee) == "clean"   # off: nothing goes in by itself
    assert client.get("/api/settings").json()["laundry"] == {"auto": False, "day": 6}
    for bad in ({"auto": "yes"}, {"day": 7}, {"day": True}, {"when": 1}, "sunday"):
        r = client.put("/api/settings", json={"laundry": bad})
        assert r.status_code == 422, bad
    assert client.put("/api/settings", json={"laundry": {"auto": True, "day": None}}).status_code == 200


def test_undoing_the_wear_takes_it_out_even_when_its_count_was_already_reached(client, cfg):
    # the demo's pieces carry counts from their history: clean, yet already worn as often as their kind allows
    tee = kind(client, "tee", "t")
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("UPDATE items SET wears_since_wash = 1 WHERE id = ?", (tee,))
    finally:
        conn.close()
    wear(client, tee, 0)
    assert laundry(client, tee) == "laundry"
    client.delete(f"/api/items/{tee}/wears/{days_ago(0)}")
    assert laundry(client, tee) == "clean"
