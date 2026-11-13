"""Worn outfits: recorded with the wears or by hand, rated, listed, removed, and what Today does with them."""
from datetime import date, timedelta

import pytest

from closet import db, wears, weather

from .conftest import photo_bytes, upload

TODAY = date(2026, 11, 12)
DAY = {"low_c": 9, "high_c": 16}


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)

    def no_network(url):
        raise AssertionError(f"tests never ask the internet ({url})")

    monkeypatch.setattr(weather, "fetch", no_network)


def item_in(client, key, category, color=(10, 20, 30), name=None):
    r = upload(client, key=key, data=photo_bytes(color=color), name=name)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert client.patch(f"/api/items/{iid}", json={"category": category}).status_code == 200
    return iid


def small(client):
    return {"tee": item_in(client, "t", "tee", (10, 20, 30)), "jacket": item_in(client, "j", "jacket", (40, 50, 60)),
            "jeans": item_in(client, "b", "jeans", (70, 80, 90)), "shoes": item_in(client, "s", "sneakers", (100, 110, 120))}


def offered(ids, mid=None):
    return {"pieces": {"base": ids["tee"], "mid": mid, "outer": ids["jacket"], "bottom": ids["jeans"], "shoes": ids["shoes"],
                       "accessories": []},
            "context": {"low_c": 9, "high_c": 16, "rain": False, "occasion": "casual", "mood": "usual"},
            "score": 77, "reasons": ["Two layers for 12°C."], "warnings": []}


def all_ids(ids):
    return [ids["tee"], ids["jacket"], ids["jeans"], ids["shoes"]]


def test_an_outfit_is_remembered_with_its_wears_and_undone_with_them(client):
    ids = small(client)
    client.post(f"/api/items/{ids['shoes']}/wears")   # already worn today on its own
    r = client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": offered(ids)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recorded"] == [ids["tee"], ids["jacket"], ids["jeans"]]
    o = body["outfit"]
    assert o["worn_on"] == TODAY.isoformat() and o["recorded_by"] == "today" and o["rating"] is None
    assert o["pieces"] == {**offered(ids)["pieces"]}
    assert o["context"] == offered(ids)["context"] and o["score"] == 77 and o["reasons"] == ["Two layers for 12°C."]
    listed = client.get("/api/outfits/worn").json()
    assert [x["id"] for x in listed["outfits"]] == [o["id"]] and listed["next"] is None

    undone = client.post("/api/wears/remove", json={"item_ids": body["recorded"], "worn_on": body["worn_on"], "outfit_id": o["id"]})
    assert undone.status_code == 200 and undone.json()["outfit_removed"] is True
    assert undone.json()["removed"] == body["recorded"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []
    assert client.get(f"/api/items/{ids['shoes']}").json()["wear_count"] == 1   # its own wear stays
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0

    # an outfit whose wears were all there already is still remembered, and undone with no items
    r = client.post("/api/wears", json={"item_ids": [ids["shoes"], ids["tee"]],
                                        "outfit": {"pieces": {"base": ids["tee"], "shoes": ids["shoes"]}}})
    first = r.json()["outfit"]
    again = client.post("/api/wears", json={"item_ids": [ids["shoes"], ids["tee"]],
                                            "outfit": {"pieces": {"base": ids["tee"], "shoes": ids["shoes"]}}})
    assert again.status_code == 201 and again.json()["recorded"] == []
    gone = client.post("/api/wears/remove", json={"item_ids": [], "worn_on": TODAY.isoformat(), "outfit_id": again.json()["outfit"]["id"]})
    assert gone.status_code == 200 and gone.json()["outfit_removed"] is True
    assert [x["id"] for x in client.get("/api/outfits/worn").json()["outfits"]] == [first["id"]]
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 1


def test_what_is_sent_with_an_outfit_is_checked_and_nothing_is_kept_on_a_mistake(client):
    ids = small(client)
    good = offered(ids)
    bad = [
        ({**good, "pieces": {**good["pieces"], "hat": ids["tee"]}}, "not places"),
        ({**good, "pieces": {**good["pieces"], "base": ids["jeans"]}}, "each once"),
        ({**good, "pieces": {**good["pieces"], "outer": None}}, "items being worn"),
        ({**good, "context": {**good["context"], "occasion": "party"}}, "not an occasion"),
        ({**good, "context": {**good["context"], "low_c": "cold"}}, "Celsius"),
        ({**good, "context": {**good["context"], "wind": 3}}, "only"),
        ({**good, "score": 101}, "0 to 100"),
        ({**good, "reasons": "nice"}, "sentences"),
        ({**good, "extra": 1}, "Give the outfit"),
    ]
    for outfit, words in bad:
        r = client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": outfit})
        assert r.status_code == 422 and words in r.json()["detail"], (outfit, r.text)
    assert client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": "outfit"}).status_code == 422
    r = client.post("/api/wears", json={"item_ids": all_ids(ids), "worn_on": days_ago(-1), "outfit": good})
    assert r.status_code == 422 and "future" in r.json()["detail"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []
    assert all(client.get(f"/api/items/{i}").json()["wear_count"] == 0 for i in all_ids(ids))
    r = client.post("/api/wears/remove", json={"item_ids": [], "worn_on": TODAY.isoformat(), "outfit_id": "nope"})
    assert r.status_code == 200 and r.json()["outfit_removed"] is False


def test_an_outfit_is_recorded_by_hand_with_its_pieces_in_their_places(client):
    ids = small(client)
    sweater = item_in(client, "w", "sweater", (130, 140, 150))
    client.post(f"/api/items/{ids['jeans']}/wears", json={"worn_on": days_ago(3)})
    r = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["shoes"], sweater, ids["jeans"], ids["tee"]],
                                               "worn_on": days_ago(3)})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["recorded_by"] == "hand" and o["worn_on"] == days_ago(3) and o["context"] is None and o["score"] is None
    assert o["pieces"] == {"base": ids["tee"], "mid": sweater, "outer": ids["jacket"], "bottom": ids["jeans"],
                           "shoes": ids["shoes"], "accessories": []}
    assert client.get(f"/api/items/{ids['tee']}").json()["last_worn"] == days_ago(3)
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1

    # removing it takes away the wears it added, not the one that was there before
    assert client.delete(f"/api/outfits/worn/{o['id']}").status_code == 204
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0
    assert client.delete(f"/api/outfits/worn/{o['id']}").status_code == 404

    for chosen, words in (([ids["tee"]], "at least 2"), ([ids["shoes"], ids["shoes"]], "at least 2"),
                          ([ids["tee"], ids["jeans"], item_in(client, "b2", "trousers", (4, 5, 6))], "one thing for your legs"),
                          ([ids["tee"], ids["shoes"], item_in(client, "s2", "boots", (1, 2, 3))], "one pair of shoes"),
                          ([ids["tee"], "nope"], "")):
        r = client.post("/api/outfits/worn", json={"item_ids": chosen})
        assert r.status_code in (404, 422) and words in r.json()["detail"], chosen
    uncategorised = upload(client, key="u", data=photo_bytes(color=(5, 6, 7))).json()["id"]
    r = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], uncategorised]})
    assert r.status_code == 422 and "category" in r.json()["detail"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []


def test_two_outfits_the_same_day_share_a_piece_and_removing_one_keeps_its_wear(client):
    ids = small(client)
    a = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    b = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"]]}).json()
    client.delete(f"/api/outfits/worn/{a['id']}")
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0
    assert [x["id"] for x in client.get("/api/outfits/worn").json()["outfits"]] == [b["id"]]


def test_rating_an_outfit_and_changing_it(client):
    ids = small(client)
    o = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids)}).json()
    url = f"/api/outfits/worn/{o['id']}/rating"
    r = client.put(url, json={"rating": "not_again", "reasons": ["uncomfortable", "too_cold", "too_cold"]})
    assert r.status_code == 200
    assert (r.json()["rating"], r.json()["rating_reasons"]) == ("not_again", ["too_cold", "uncomfortable"]) and r.json()["rated_at"]
    r = client.put(url, json={"rating": "loved", "reasons": ["compliments", "other"], "note": "  wore it to a party  "})
    assert (r.json()["rating"], r.json()["rating_reasons"], r.json()["rating_note"]) == ("loved", ["compliments", "other"], "wore it to a party")
    assert client.get("/api/outfits/worn").json()["outfits"][0]["rating"] == "loved"
    for body, words in (({"rating": "great"}, "one of"), ({"rating": "fine", "reasons": ["itchy"]}, "Reasons come from"),
                        ({"rating": "fine", "note": "hm"}, "goes with"), ({"rating": None, "reasons": ["too_cold"]}, "before giving"),
                        ({"rating": "fine", "note": "x" * 301}, "300")):
        r = client.put(url, json=body)
        assert r.status_code == 422 and words in r.json()["detail"], body
    assert client.put(url, json={"rating": "fine", "extra": 1}).status_code == 422
    cleared = client.put(url, json={"rating": None}).json()
    assert (cleared["rating"], cleared["rating_reasons"], cleared["rating_note"], cleared["rated_at"]) == (None, [], None, None)
    assert client.put("/api/outfits/worn/nope/rating", json={"rating": "fine"}).status_code == 404


def test_the_list_is_newest_first_and_comes_in_pages(client):
    ids = small(client)
    made = []
    for n in (5, 1, 3, 1, 8):
        made.append((days_ago(n), client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]],
                                                                          "worn_on": days_ago(n)}).json()["id"]))
    page = client.get("/api/outfits/worn", params={"limit": 2}).json()
    seen = [o["id"] for o in page["outfits"]]
    while page["next"]:
        page = client.get("/api/outfits/worn", params={"limit": 2, "before": page["next"]}).json()
        seen += [o["id"] for o in page["outfits"]]
    assert seen == [made[3][1], made[1][1], made[2][1], made[0][1], made[4][1]]
    assert client.get("/api/outfits/worn", params={"limit": 0}).status_code == 422
    assert client.get("/api/outfits/worn", params={"limit": 101}).status_code == 422
    assert client.get("/api/outfits/worn", params={"before": "nonsense"}).status_code == 422


def test_ratings_shape_today_and_wear_again_keeps_the_clean_pieces(client):
    client.post("/api/profile", json={"profile": "demo"})
    listed = client.get("/api/outfits/worn").json()["outfits"]
    assert len(listed) == 5 and listed[0]["worn_on"] == days_ago(1) and listed[0]["rating"] is None
    assert sum(o["rating"] is not None for o in listed) == 4
    by_name = {i["name"]: i["id"] for i in client.get("/api/items").json()["items"]}

    # the loved outfit of six days ago: its pieces are clean, so they come back in their places
    loved = next(o for o in listed if o["worn_on"] == days_ago(6))
    r = client.post("/api/outfits/today", json={**DAY, "again": loved["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    again = body["context"]["again"]
    assert again["id"] == loved["id"] and again["worn_on"] == days_ago(6)
    assert by_name["White tee"] in again["unavailable"]   # in the laundry
    kept = [loved["pieces"][pl] for pl in ("mid", "outer", "bottom", "shoes")]
    assert sorted(again["kept"]) == sorted(kept)
    assert body["outfits"]
    for o in body["outfits"]:
        assert set(kept) <= {o["pieces"][pl] for pl in ("base", "mid", "outer", "bottom", "shoes")} and o["pieces"]["bottom"] == loved["pieces"]["bottom"]
        assert o["pieces"]["base"] != by_name["White tee"]
    assert any("You loved" in r for o in body["outfits"] for r in o["reasons"])

    r = client.post("/api/outfits/today", json={**DAY, "again": "nope"})
    assert r.status_code == 422 and "no longer" in r.json()["detail"]
    assert client.post("/api/outfits/today", json={**DAY, "again": 3}).status_code == 422
    # without "again" nothing is left out
    assert "again" not in client.post("/api/outfits/today", json=DAY).json()["context"]


def test_demo_and_main_closets_keep_their_own_worn_outfits(client):
    ids = small(client)
    mine = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    client.post("/api/profile", json={"profile": "demo"})
    demo_ids = {o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]}
    assert mine["id"] not in demo_ids and len(demo_ids) == 5
    assert client.put(f"/api/outfits/worn/{mine['id']}/rating", json={"rating": "fine"}).status_code == 404
    client.post("/api/profile", json={"profile": "main"})
    assert [o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]] == [mine["id"]]


def test_the_demo_outfits_match_its_wears(client):
    client.post("/api/profile", json={"profile": "demo"})
    for o in client.get("/api/outfits/worn").json()["outfits"]:
        for pid in [v for k, v in o["pieces"].items() if k != "accessories" and v]:
            assert o["worn_on"] in [w["worn_on"] for w in client.get(f"/api/items/{pid}/wears").json()["wears"]]


def test_worn_outfits_need_login(anon):
    assert anon.get("/api/outfits/worn").status_code == 401
    assert anon.post("/api/outfits/worn", json={"item_ids": ["a", "b"]}).status_code == 401
    assert anon.put("/api/outfits/worn/x/rating", json={"rating": "fine"}).status_code == 401
    assert anon.delete("/api/outfits/worn/x").status_code == 401
    assert anon.post("/api/wears", json={"item_ids": ["x"], "outfit": {}}).status_code == 401


def test_the_migration_runs_on_a_closet_made_by_the_previous_version(tmp_path, monkeypatch):
    path, backups = tmp_path / "closet.db", tmp_path / "bk"
    real = db.migration_files()
    monkeypatch.setattr(db, "migration_files", lambda: [(v, p) for v, p in real if v < 7])
    db.migrate(path, backups)
    conn = db.connect(path)
    t = db.now()
    for item_id in ("a", "b"):
        conn.execute("INSERT INTO items (id, category, created_at, updated_at) VALUES (?, 'tee', ?, ?)", (item_id, t, t))
    conn.execute("INSERT INTO wears (item_id, worn_on, created_at) VALUES ('a', '2026-11-01', ?)", (t,))
    conn.close()

    monkeypatch.setattr(db, "migration_files", lambda: real)
    result = db.migrate(path, backups)
    assert result["applied"][0] == 7 and result["backup"]
    conn = db.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM wears").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM worn_outfits").fetchone()[0] == 0
    conn.execute("INSERT INTO worn_outfits (id, worn_on, recorded_by, created_at, updated_at) VALUES ('o', '2026-11-01', 'hand', ?, ?)", (t, t))
    conn.execute("INSERT INTO worn_outfit_pieces (outfit_id, item_id, place, position, added_wear) VALUES ('o', 'a', 'base', 0, 0)")
    with pytest.raises(Exception, match="CHECK"):
        conn.execute("UPDATE worn_outfits SET rating = 'great' WHERE id = 'o'")
    conn.execute("DELETE FROM items WHERE id = 'a'")   # a deleted item leaves the outfit, without that piece
    assert conn.execute("SELECT COUNT(*) FROM worn_outfit_pieces").fetchone()[0] == 0
    conn.execute("DELETE FROM worn_outfits WHERE id = 'o'")
    conn.close()
