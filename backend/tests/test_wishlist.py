"""Hiding gaps and the wishlist (closet/wishlist.py, migration 0007)."""
import sqlite3

import pytest

from closet import db, gaps

from .conftest import upload


@pytest.fixture
def demo(client):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    return client


def gap_list(client) -> list[dict]:
    r = client.get("/api/gaps")
    assert r.status_code == 200
    return r.json()["gaps"]


def by_id(client) -> dict[str, dict]:
    return {g["id"]: g for g in gap_list(client)}


def test_every_gap_is_marked_open_at_first(demo):
    gs = gap_list(demo)
    assert gs and len(gs) <= gaps.MAX_GAPS
    for g in gs:
        assert g["state"] == "open" and g["hidden_reason"] is None and g["wish_id"] is None
    assert [g["score"] for g in gs] == sorted((g["score"] for g in gs), reverse=True)


def test_the_gap_ids_are_the_same_when_the_analysis_runs_again(demo):
    first = [g["id"] for g in gap_list(demo)]
    before = demo.get("/api/gaps").json()["checked"]["wears"]
    jeans = next(i for i in demo.get("/api/items").json()["items"] if i["name"] == "Black jeans")
    assert demo.post(f"/api/items/{jeans['id']}/wears").status_code == 201   # the closet changes: analysed again
    assert demo.get("/api/gaps").json()["checked"]["wears"] == before + 1
    again = [g["id"] for g in gap_list(demo)]
    assert again == first


def test_hide_and_bring_back(demo):
    gid = gap_list(demo)[0]["id"]
    r = demo.post(f"/api/gaps/{gid}/hide", json={"reason": "too_expensive"})
    assert r.status_code == 200 and r.json()["reason"] == "too_expensive" and r.json()["gap_id"] == gid
    g = by_id(demo)[gid]
    assert g["state"] == "hidden" and g["hidden_reason"] == "too_expensive"
    # hiding again changes the reason; no reason is fine too
    assert demo.post(f"/api/gaps/{gid}/hide").json()["reason"] is None
    assert by_id(demo)[gid]["hidden_reason"] is None
    assert demo.delete(f"/api/gaps/{gid}/hide").status_code == 204
    assert by_id(demo)[gid]["state"] == "open"
    assert demo.delete(f"/api/gaps/{gid}/hide").status_code == 404


def test_hide_refuses_an_unknown_reason_or_gap(demo):
    gid = gap_list(demo)[0]["id"]
    assert demo.post(f"/api/gaps/{gid}/hide", json={"reason": "ugly"}).status_code == 422
    r = demo.post("/api/gaps/no-such-gap/hide", json={})
    assert r.status_code == 404 and "no longer" in r.json()["detail"]


def test_a_hidden_gap_does_not_push_a_new_one_off_the_list(demo):
    everything = demo.get("/api/gaps").json()
    assert len(everything["gaps"]) == gaps.MAX_GAPS   # the demo closet has more gaps than the list shows
    shown = [g["id"] for g in everything["gaps"]]
    demo.post(f"/api/gaps/{shown[0]}/hide", json={})
    after = gap_list(demo)
    assert [g["id"] for g in after if g["state"] == "open"][:gaps.MAX_GAPS - 1] == shown[1:]
    assert len([g for g in after if g["state"] == "open"]) == gaps.MAX_GAPS   # the next one moved up
    assert after[0]["id"] == shown[0] and after[0]["state"] == "hidden"       # and the hidden one keeps its place


def test_a_hidden_gap_stays_hidden_after_the_closet_changes(demo):
    gid = gap_list(demo)[0]["id"]
    demo.post(f"/api/gaps/{gid}/hide", json={"reason": "have_one"})
    items = demo.get("/api/items").json()["items"]
    tee = next(i for i in items if i["name"] == "Black tee")
    assert demo.post(f"/api/items/{tee['id']}/wears").status_code == 201
    assert demo.patch(f"/api/items/{items[-1]['id']}", json={"status": "archived"}).status_code == 200
    g = by_id(demo)[gid]
    assert g["state"] == "hidden" and g["hidden_reason"] == "have_one"


def test_a_wished_gap_is_marked_and_not_offered_again(demo):
    g = gap_list(demo)[1]
    r = demo.post("/api/wishlist", json={"gap_id": g["id"]})
    assert r.status_code == 201
    wish = r.json()
    assert wish["gap_id"] == g["id"] and wish["name"] == g["name"] and wish["look_for"] == g["look_for"]
    assert wish["note"] == "" and wish["bought_at"] is None
    marked = by_id(demo)[g["id"]]
    assert marked["state"] == "wished" and marked["wish_id"] == wish["id"]
    # asking again gives the same wish
    again = demo.post("/api/wishlist", json={"gap_id": g["id"]})
    assert again.status_code == 200 and again.json()["id"] == wish["id"]
    assert len(demo.get("/api/wishlist").json()["wishes"]) == 1
    # a wished gap cannot be hidden; it is removed from the list first
    assert demo.post(f"/api/gaps/{g['id']}/hide", json={}).status_code == 409
    # still marked after the closet changes
    tee = next(i for i in demo.get("/api/items").json()["items"] if i["name"] == "White tee")
    demo.post(f"/api/items/{tee['id']}/wears")
    assert by_id(demo)[g["id"]]["state"] == "wished"


def test_wishing_for_a_hidden_gap_brings_it_back(demo):
    gid = gap_list(demo)[0]["id"]
    demo.post(f"/api/gaps/{gid}/hide", json={"reason": "other"})
    assert demo.post("/api/wishlist", json={"gap_id": gid}).status_code == 201
    g = by_id(demo)[gid]
    assert g["state"] == "wished" and g["hidden_reason"] is None


def test_the_wishlist_routes(demo):
    assert demo.get("/api/wishlist").json() == {"wishes": []}
    gid = gap_list(demo)[0]["id"]
    from_gap = demo.post("/api/wishlist", json={"gap_id": gid, "note": "  navy if I can  "}).json()
    assert from_gap["note"] == "navy if I can"
    by_hand = demo.post("/api/wishlist", json={"name": " Brown suede chelsea boots ", "note": "size 10"})
    assert by_hand.status_code == 201
    hand = by_hand.json()
    assert hand["name"] == "Brown suede chelsea boots" and hand["gap_id"] is None and hand["look_for"] is None
    # newest first
    assert [w["id"] for w in demo.get("/api/wishlist").json()["wishes"]] == [hand["id"], from_gap["id"]]

    # change the note (and the name)
    changed = demo.patch(f"/api/wishlist/{hand['id']}", json={"note": "size 10, not too pointed"})
    assert changed.status_code == 200 and changed.json()["note"] == "size 10, not too pointed"
    assert changed.json()["name"] == "Brown suede chelsea boots"
    assert demo.patch(f"/api/wishlist/{hand['id']}", json={"name": "Chelsea boots"}).json()["name"] == "Chelsea boots"
    assert demo.patch(f"/api/wishlist/{hand['id']}", json={"name": "  "}).status_code == 422
    assert demo.patch(f"/api/wishlist/{hand['id']}", json={"note": "x" * 1001}).status_code == 422
    assert demo.patch("/api/wishlist/nope", json={"note": "x"}).status_code == 404

    # bought: off the list, and the gap is offered again while the analysis still finds it
    r = demo.post(f"/api/wishlist/{from_gap['id']}/bought")
    assert r.status_code == 200 and r.json()["bought_at"]
    assert [w["id"] for w in demo.get("/api/wishlist").json()["wishes"]] == [hand["id"]]
    assert by_id(demo)[gid]["state"] == "open"
    assert demo.post("/api/wishlist/nope/bought").status_code == 404

    # remove
    assert demo.delete(f"/api/wishlist/{hand['id']}").status_code == 204
    assert demo.get("/api/wishlist").json() == {"wishes": []}
    assert demo.delete(f"/api/wishlist/{hand['id']}").status_code == 404


def test_a_new_wish_needs_a_name_or_a_gap(demo):
    assert demo.post("/api/wishlist", json={}).status_code == 422
    assert demo.post("/api/wishlist", json={"name": ""}).status_code == 422
    assert demo.post("/api/wishlist", json={"name": "x" * 121}).status_code == 422
    assert demo.post("/api/wishlist", json={"name": "A", "gap_id": "outer-rain"}).status_code == 422
    assert demo.post("/api/wishlist", json={"gap_id": "no-such-gap"}).status_code == 404
    assert demo.post("/api/wishlist", json={"name": "A", "colour": "red"}).status_code == 422


def test_demo_and_main_closets_keep_their_own(client):
    upload(client)
    assert client.post("/api/wishlist", json={"name": "A good umbrella"}).status_code == 201
    client.post("/api/profile", json={"profile": "demo"})
    assert client.get("/api/wishlist").json() == {"wishes": []}
    gid = gap_list(client)[0]["id"]
    client.post(f"/api/gaps/{gid}/hide", json={})
    client.post("/api/wishlist", json={"name": "Demo wish"})
    client.post("/api/profile", json={"profile": "main"})
    assert [w["name"] for w in client.get("/api/wishlist").json()["wishes"]] == ["A good umbrella"]
    client.post("/api/profile", json={"profile": "demo"})
    assert by_id(client)[gid]["state"] == "hidden"
    assert [w["name"] for w in client.get("/api/wishlist").json()["wishes"]] == ["Demo wish"]


def test_hidden_gaps_and_the_wishlist_are_in_the_closets_database(client, cfg):
    client.post("/api/wishlist", json={"name": "A good umbrella"})
    conn = db.connect(cfg.db_path("main"))
    assert [r["name"] for r in conn.execute("SELECT name FROM wishes")] == ["A good umbrella"]
    conn.close()
    assert not cfg.db_path("demo").exists() or not db.connect(cfg.db_path("demo")).execute("SELECT * FROM wishes").fetchall()


@pytest.mark.parametrize("method,path", [
    ("post", "/api/gaps/outer-rain/hide"), ("delete", "/api/gaps/outer-rain/hide"), ("get", "/api/wishlist"),
    ("post", "/api/wishlist"), ("patch", "/api/wishlist/x"), ("post", "/api/wishlist/x/bought"), ("delete", "/api/wishlist/x"),
])
def test_login_is_required(anon, method, path):
    assert getattr(anon, method)(path).status_code == 401


def test_the_migration_runs_on_a_closet_made_by_the_previous_version(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = sqlite3.connect(path)
    for version, file in db.migration_files():
        if version <= 6:   # a closet made by the previous version
            old.executescript(file.read_text(encoding="utf-8") + f"\nPRAGMA user_version = {version};")
    old.execute("INSERT INTO items (id, name, category, cutout_state, created_at, updated_at) "
                "VALUES ('a', 'Old shirt', 'shirt', 'ready', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    old.commit()
    old.close()
    result = db.migrate(path, cfg.local_backups_dir)
    assert result["from"] == 6 and result["applied"][0] == 7 and result["backup"]   # and any later ones
    conn = db.connect(path)
    assert conn.execute("SELECT name FROM items").fetchone()[0] == "Old shirt"
    assert conn.execute("SELECT COUNT(*) FROM wishes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM hidden_gaps").fetchone()[0] == 0
    t = db.now()
    conn.execute("INSERT INTO wishes (id, gap_id, name, created_at, updated_at) VALUES ('w1', 'outer-rain', 'Rain coat', ?, ?)", (t, t))
    with pytest.raises(sqlite3.IntegrityError):   # one wish still wanted per gap
        conn.execute("INSERT INTO wishes (id, gap_id, name, created_at, updated_at) VALUES ('w2', 'outer-rain', 'Rain coat', ?, ?)", (t, t))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO hidden_gaps (gap_id, name, reason, hidden_at) VALUES ('g', 'G', 'ugly', ?)", (t,))
    conn.close()
