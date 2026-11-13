import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import backup, db, gaps, shopping

from .test_gaps import full_closet

GAP = {
    "id": "coat-smart_casual-warm", "name": "A warm coat",
    "look_for": {"category": "coat", "formality": "smart_casual", "season": "cool",
                 "weight_class": "heavyweight", "colors": ["navy"], "pattern": None, "material": "wool"},
    "why": ["A warm coat would help on cold days."], "score": 65, "found_by": ["days"],
    "evidence": {"days": [], "items": []},
}
HIDDEN = f"/api/gaps/{GAP['id']}/hidden"


@pytest.fixture
def analysis(monkeypatch):
    """Keep persistence tests small; real-engine integration is checked separately."""
    calls = []

    def find(rows, wears):
        answer = {"enough": True, "message": None,
                  "gaps": [] if any(r["name"] == "No gaps" for r in rows) else [copy.deepcopy(GAP)],
                  "notes": [], "checked": {"items": len(rows), "wears": len(wears), "days": 40}}
        calls.append(answer)
        return answer

    monkeypatch.setattr(app_module, "find_gaps", find)
    return calls


def insert_item(cfg, name="A synthetic shirt"):
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("INSERT INTO items (id, name, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("synthetic-shirt", name, "shirt", db.now(), db.now()))
    finally:
        conn.close()


def flags(client):
    return client.get("/api/gaps").json()["gaps"][0]


def test_hidden_choices_survive_changes_restart_and_do_not_change_analysis(client, services, cfg, analysis):
    before = client.get("/api/gaps").json()
    assert flags(client) == {**GAP, "hidden": False, "hidden_reason": None, "wished": False}
    hidden = client.put(HIDDEN, json={"reason": "not_my_style"})
    assert hidden.status_code == 200 and hidden.json()["hidden_reason"] == "not_my_style"
    assert flags(client)["hidden"] is True
    assert len(analysis) == 1 and analysis[0]["gaps"] == [GAP]
    insert_item(cfg)
    changed = flags(client)
    assert changed["hidden"] and changed["hidden_reason"] == "not_my_style"
    assert len(analysis) == 2
    assert {k: v for k, v in changed.items() if k not in ("hidden", "hidden_reason", "wished")} == GAP
    assert analysis[1]["gaps"] == [GAP]
    assert before["gaps"][0]["hidden"] is False
    restarted = TestClient(app_module.create_app(services))
    restarted.cookies.update(client.cookies)
    assert flags(restarted)["hidden"] is True
    assert restarted.delete(HIDDEN).status_code == 204
    assert restarted.delete(HIDDEN).status_code == 204
    assert client.get("/api/gaps/hidden").json() == {"gaps": []}
    assert flags(client)["hidden"] is False
    assert flags(client)["hidden_reason"] is None


@pytest.mark.parametrize("reason", [None, *shopping.REASONS])
def test_hide_reasons_and_repeat_update(client, analysis, reason):
    assert client.put(HIDDEN, json={"reason": reason}).status_code == 200
    assert client.get("/api/gaps/hidden").json()["gaps"][0]["hidden_reason"] == reason
    assert client.put(HIDDEN, json={}).json()["hidden_reason"] is None
    assert len(client.get("/api/gaps/hidden").json()["gaps"]) == 1


def test_snapshot_survives_disappearance_and_can_be_wished_or_hidden_again(client, cfg, analysis):
    saved = client.put(HIDDEN, json={"reason": "other"}).json()
    insert_item(cfg, "No gaps")
    assert client.get("/api/gaps").json()["gaps"] == []
    assert client.get("/api/gaps/hidden").json() == {"gaps": [saved]}
    wish = client.post("/api/wishlist", json={"gap_id": GAP["id"]})
    assert wish.status_code == 201
    assert wish.json()["name"] == GAP["name"] and wish.json()["look_for"] == GAP["look_for"]
    assert client.get("/api/gaps/hidden").json() == {"gaps": []}
    assert client.put(HIDDEN, json={}).status_code == 409
    assert client.delete("/api/wishlist/" + wish.json()["id"]).status_code == 204
    assert client.put(HIDDEN, json={}).status_code == 200
    assert client.delete(HIDDEN).status_code == 204
    assert client.get("/api/gaps/hidden").json() == {"gaps": []}


def test_gap_wish_lifecycle_and_current_flags(client, cfg, analysis):
    assert client.put(HIDDEN, json={"reason": "too_expensive"}).status_code == 200
    created = client.post("/api/wishlist", json={"gap_id": GAP["id"]})
    wish = created.json()
    assert created.status_code == 201
    assert set(wish) == {"id", "gap_id", "name", "look_for", "details", "note", "created_at"}
    assert wish["details"] == wish["note"] == ""
    assert flags(client)["wished"] and not flags(client)["hidden"]
    assert flags(client)["hidden_reason"] is None
    assert client.put(HIDDEN, json={}).status_code == 409
    assert not flags(client)["hidden"]
    path = "/api/wishlist/" + wish["id"]
    changed = client.patch(path, json={"note": "Try a navy one."})
    assert changed.status_code == 200 and changed.json()["note"] == "Try a navy one."
    again = client.post("/api/wishlist", json={"gap_id": GAP["id"]})
    assert again.status_code == 200 and again.json() == changed.json()
    insert_item(cfg)
    assert flags(client)["wished"]
    assert client.get("/api/wishlist").json() == {"wishes": [changed.json()]}
    assert client.post(path + "/bought").status_code == 204
    assert client.get("/api/wishlist").json() == {"wishes": []}
    assert flags(client)["wished"] is False
    assert client.patch(path, json={"note": "Too late"}).status_code == 404
    second = client.post("/api/wishlist", json={"gap_id": GAP["id"]})
    assert second.status_code == 201 and second.json()["id"] != wish["id"]
    assert client.delete("/api/wishlist/" + second.json()["id"]).status_code == 204
    assert flags(client)["wished"] is False
    assert len(analysis) == 2


def test_manual_wishlist(client, analysis):
    first = client.post("/api/wishlist", json={"name": "  A travel bag  ", "details": "Fits a weekend.", "note": "Olive"})
    assert first.status_code == 201
    wish = first.json()
    assert wish["name"] == "A travel bag" and wish["gap_id"] is None and wish["look_for"] is None
    assert wish["details"] == "Fits a weekend." and wish["note"] == "Olive"
    second = client.post("/api/wishlist", json={"name": "A travel bag"})
    assert second.status_code == 201 and second.json()["id"] != wish["id"]
    assert second.json()["note"] == second.json()["details"] == ""
    assert not analysis  # manual wishes never need the engine
    path = "/api/wishlist/" + wish["id"]
    assert client.patch(path, json={"note": ""}).json()["note"] == ""
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 404
    assert client.post("/api/wishlist/" + second.json()["id"] + "/bought").status_code == 204
    assert client.get("/api/wishlist").json() == {"wishes": []}


@pytest.mark.parametrize("body", [
    {}, [], None, {"name": ""}, {"name": "  "}, {"name": 3}, {"name": None}, {"name": "x" * 201},
    {"name": "Bag", "details": None}, {"name": "Bag", "details": "x" * 4001},
    {"name": "Bag", "note": False}, {"name": "Bag", "note": "x" * 2001},
    {"gap_id": None}, {"gap_id": []}, {"gap_id": ""}, {"gap_id": "x" * 201},
    {"gap_id": GAP["id"], "name": "Spoofed"}, {"gap_id": GAP["id"], "look_for": {}},
    {"name": "Bag", "bought_at": "yesterday"},
])
def test_wishlist_creation_validation(client, analysis, body):
    response = client.post("/api/wishlist", content=json.dumps(body), headers={"content-type": "application/json"})
    assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.get("/api/wishlist").json() == {"wishes": []}


@pytest.mark.parametrize("body", [{}, {"note": None}, {"note": []}, {"note": 1}, {"note": "x" * 2001},
                                      {"note": "", "name": "Cannot rename"}, []])
def test_note_validation(client, body):
    wish = client.post("/api/wishlist", json={"name": "Bag", "note": "Keep me"}).json()
    response = client.patch("/api/wishlist/" + wish["id"], json=body)
    assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.get("/api/wishlist").json()["wishes"][0]["note"] == "Keep me"


@pytest.mark.parametrize("body", [{"reason": "unknown"}, {"reason": []}, {"reason": 2}, {"snapshot": GAP}, []])
def test_hide_validation(client, analysis, body):
    assert client.put(HIDDEN, json=body).status_code == 422
    assert client.get("/api/gaps/hidden").json() == {"gaps": []}


@pytest.mark.parametrize("method,path", [("put", HIDDEN), ("post", "/api/wishlist"), ("patch", "/api/wishlist/missing")])
def test_json_and_body_limits(client, method, path):
    request = getattr(client, method)
    assert request(path, content="{").status_code == 400
    assert request(path, content=b"\xff").status_code == 400
    assert request(path, content="x" * (shopping.BODY_LIMIT + 1)).status_code == 413


def test_unknown_ids(client, analysis):
    assert client.put("/api/gaps/unknown/hidden", json={}).status_code == 404
    assert client.delete("/api/gaps/unknown/hidden").status_code == 204
    assert client.post("/api/wishlist", json={"gap_id": "unknown"}).status_code == 404
    assert client.patch("/api/wishlist/unknown", json={"note": ""}).status_code == 404
    assert client.post("/api/wishlist/unknown/bought").status_code == 404
    assert client.delete("/api/wishlist/unknown").status_code == 404
    for method, suffix in [("delete", ""), ("post", "/bought")]:
        assert getattr(client, method)("/api/wishlist/" + "x" * 201 + suffix).status_code == 422
    assert client.delete("/api/gaps/" + "x" * 201 + "/hidden").status_code == 422


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/gaps", None), ("get", "/api/gaps/hidden", None),
    ("put", HIDDEN, {}), ("delete", HIDDEN, None), ("get", "/api/wishlist", None),
    ("post", "/api/wishlist", {"name": "Bag"}), ("patch", "/api/wishlist/id", {"note": ""}),
    ("post", "/api/wishlist/id/bought", None), ("delete", "/api/wishlist/id", None),
])
def test_all_shopping_routes_require_login(anon, method, path, body):
    assert anon.request(method, path, json=body).status_code == 401


def test_demo_main_isolation(client, analysis):
    main = client.post("/api/wishlist", json={"gap_id": GAP["id"]}).json()
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    assert not flags(client)["wished"]
    assert client.get("/api/wishlist").json() == {"wishes": []}
    assert client.delete("/api/wishlist/" + main["id"]).status_code == 404
    assert client.put(HIDDEN, json={"reason": "already_owned"}).status_code == 200
    demo = client.post("/api/wishlist", json={"name": "Demo wish"}).json()
    client.post("/api/profile", json={"profile": "main"})
    assert flags(client)["wished"] and not flags(client)["hidden"]
    assert client.get("/api/gaps/hidden").json() == {"gaps": []}
    assert client.get("/api/wishlist").json() == {"wishes": [main]}
    client.post("/api/profile", json={"profile": "demo"})
    assert flags(client)["hidden"] and not flags(client)["wished"]
    assert client.get("/api/wishlist").json() == {"wishes": [demo]}


def test_concurrent_gap_wishes_are_idempotent(client, services, analysis):
    flags(client)  # populate the analysis cache before concurrent requests

    def add(_):
        session = TestClient(app_module.create_app(services))
        session.cookies.update(client.cookies)
        return session.post("/api/wishlist", json={"gap_id": GAP["id"]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(add, range(2)))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert len(client.get("/api/wishlist").json()["wishes"]) == 1


def test_migration_from_0006_preserves_items_and_takes_backup(tmp_path):
    path = tmp_path / "closet.db"
    conn = sqlite3.connect(path)
    try:
        for version, file in db.migration_files():
            if version <= 6:
                conn.executescript(file.read_text())
        conn.execute("PRAGMA user_version = 6")
        conn.execute("INSERT INTO items (id, name, created_at, updated_at) VALUES ('old', 'Old shirt', 'then', 'then')")
        conn.commit()
    finally:
        conn.close()
    result = db.migrate(path, tmp_path / "backups")
    assert result["from"] == 6 and result["to"] == 7 and result["applied"] == [7]
    assert Path(result["backup"]).is_file()
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT name FROM items WHERE id = 'old'").fetchone()[0] == "Old shirt"
        assert conn.execute("SELECT count(*) FROM gap_choices").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM wishes").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
    assert db.migrate(path, tmp_path / "backups")["applied"] == []


def test_backup_restore_preserves_shopping_and_excludes_demo(client, services, cfg, tmp_path, analysis):
    hidden = client.put(HIDDEN, json={"reason": "other"}).json()
    wish = client.post("/api/wishlist", json={"name": "Main bag", "note": "Keep this"}).json()
    folder = tmp_path / "backups"
    folder.mkdir()
    client.post("/api/profile", json={"profile": "demo"})
    client.post("/api/wishlist", json={"name": "Demo bag"})
    result = backup.run_backup(cfg, services.state, folder=folder)
    assert result["ok"]
    client.post("/api/profile", json={"profile": "main"})
    client.delete(HIDDEN)
    client.delete("/api/wishlist/" + wish["id"])
    services.stop()
    backup.restore(cfg, folder)
    assert client.get("/api/wishlist").json() == {"wishes": [wish]}
    assert client.get("/api/gaps/hidden").json() == {"gaps": [hidden]}


def test_real_analysis_identity_and_persisted_flags(client):
    client.post("/api/profile", json={"profile": "demo"})
    original = client.get("/api/gaps").json()["gaps"]
    first = original[0]
    assert client.put(f"/api/gaps/{first['id']}/hidden", json={}).status_code == 200
    second = original[1]
    assert client.post("/api/wishlist", json={"gap_id": second["id"]}).status_code == 201
    current = client.get("/api/gaps").json()["gaps"]
    assert [g["id"] for g in current] == [g["id"] for g in original]
    assert current[0]["hidden"] and current[1]["wished"]
    for before, after in zip(original, current, strict=True):
        assert {k: v for k, v in after.items() if k not in ("hidden", "hidden_reason", "wished")} == {
            k: v for k, v in before.items() if k not in ("hidden", "hidden_reason", "wished")}


def test_gap_identity_is_unchanged_by_names_or_input_order():
    closet = full_closet()
    original = gaps.find_gaps(closet)
    renamed = [{**item, "name": item["name"] + " (renamed)"} for item in reversed(closet)]
    assert {g["id"] for g in gaps.find_gaps(renamed)["gaps"]} == {g["id"] for g in original["gaps"]}
