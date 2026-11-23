"""What the demo closet comes with (closet/demo.py, made by tools/make_demo.py): no real photos beyond the seven
open-licence ones, nothing sent to Claude, nothing looked up."""
import json
import shutil
from datetime import timedelta

from closet import db, demo, illustrations, shop, wears
from closet.config import bundle_dir

from .same_drawing import same

ACCESSORIES = {"belt", "bag", "hat", "scarf"}


def data():
    return json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))


def rows(cfg, sql, *args):
    conn = db.connect(cfg.db_path("demo"))
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def test_the_demo_shows_what_the_app_can_do():
    items = data()["items"]
    assert 38 <= len(items) <= 55 and len({i["id"] for i in items}) == len(items)
    assert sum(1 for i in items if i.get("photo")) == 7   # the open-licence photos; the rest are drawings
    garments = {i["answer"]["details"].get("garment") for i in items}
    assert {"fleece_pullover", "parka", "joggers", "lounge_pants"} <= garments
    shoes = {i["answer"]["details"].get("shoe_style") for i in items}
    assert {"loafer", "oxford", "derby"} <= shoes
    assert ACCESSORIES <= {i["category"] for i in items}
    assert {"plaid", "stripe", "floral", "graphic"} <= {i["pattern"] for i in items}
    fleece = next(i for i in items if i["answer"]["details"].get("garment") == "fleece_pullover")
    assert fleece["answer"]["details"]["trim_color"] and fleece["answer"]["secondary_colors"]
    chinos = next(i for i in items if i["name"] == "Stone pleated chinos")["answer"]["details"]
    assert chinos["trouser_front"] == "single_pleat" and chinos["hem_finish"] == "turn_up" and chinos["crease"]
    assert chinos["waistband"] == "side_adjusters" and chinos["trouser_pockets"] and chinos["back_details"]
    # the drawn plaid and floral come from made-up pattern tiles, kept as the app keeps a measured pattern; the
    # photographed plaids keep the pattern measured from their photo, as the app keeps it
    tiles = [i for i in items if (i.get("pattern_fill") or {}).get("kind") == "tile"]
    assert all(i["pattern_fill"]["colors"] for i in tiles)
    assert {i["pattern"] for i in tiles if not i.get("photo")} == {"plaid", "floral"}
    plaids = [i for i in items if i.get("photo") and i["pattern"] == "plaid"]
    assert len(plaids) == 2 and all(i in tiles for i in plaids)


def test_the_demo_overcoat_is_drawn_as_a_coat_not_a_blazer():
    from closet.tagger.schema import ItemTags, drawing_for
    coat = next(i for i in data()["items"] if i["name"] == "Black overcoat")
    assert coat["answer"]["details"]["garment"] == "overcoat"
    _, p, _, _ = drawing_for(ItemTags.model_validate(coat["answer"]))   # what the outfit as worn draws it from
    assert p["block"] == "coat" and p["length"] == "knee"


def test_a_new_demo_closet_has_its_patterns_and_is_never_sent_to_claude(client, cfg):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    stored = rows(cfg, "SELECT * FROM items")
    assert all(r["tag_route"] == "demo" and r["tag_state"] == "done" and r["tag_model"] is None for r in stored)
    assert not [r for r in stored if r["pattern_state"] in ("waiting", "working")]
    tartan = next(r for r in stored if r["name"] == "Tartan lounge pants")
    assert json.loads(tartan["pattern_fill"])["kind"] == "tile" and tartan["pattern_state"] == "done"
    shown = client.get(f"/api/items/{tartan['id']}").json()
    assert shown["pattern"] == "plaid" and shown["illustration_svg"].startswith("<svg")
    # each drawing made from tags is the one the app makes now, so it is kept until the drawing code changes
    from_tags = {i["id"] for i in data()["items"] if i.get("wave") == 2}
    for r in stored:
        if r["id"] in from_tags or r["pattern_fill"]:
            assert same(illustrations.make(r).svg, r["illustration_svg"]), r["name"]


def test_the_demo_has_worn_outfits_with_accessories_and_ratings(client):
    client.post("/api/profile", json={"profile": "demo"})
    worn = client.get("/api/outfits/worn").json()["outfits"]
    by_id = {i["id"]: i for i in client.get("/api/items").json()["items"]}
    accessories = {by_id[a]["category"] for o in worn for a in o["pieces"]["accessories"]}
    assert ACCESSORIES <= accessories
    assert {o["rating"] for o in worn} == {None, "loved", "fine", "not_again"}
    assert worn[0]["rating"] is None   # yesterday's, for Today to ask about


def test_the_demo_wishes_have_stand_in_finds_and_a_price_drop(client, cfg):
    client.post("/api/profile", json={"profile": "demo"})
    wished = client.get("/api/wishlist").json()["wishes"]
    assert len(wished) == 2 and all(w["gap_id"] is None and w["price_max"] for w in wished)
    conn = db.connect(cfg.db_path("demo"))
    try:
        finds = [f for w in wished for f in shop.list_finds(conn, w["id"])]
    finally:
        conn.close()
    assert finds and all(f["url"].startswith("https://shop.example/") and f["image_url"] is None for f in finds)
    assert all(f["verdict"] and f["reasons"] and len(f["history"]) >= 2 for f in finds)
    drops = [f["drop"] for f in finds if f["drop"]]
    assert drops and all(d["to"] < d["from"] for d in drops)
    # the demo closet cannot search: its finds are only shown
    assert client.post(f"/api/wishlist/{wished[0]['id']}/find").status_code in (403, 409)


def test_the_demo_has_a_saved_trip_planned_without_looking_anything_up(client):
    client.post("/api/profile", json={"profile": "demo"})
    listed = client.get("/api/trips").json()["trips"]
    assert len(listed) == 1 and listed[0]["first_day"] > wears.today().isoformat() and listed[0]["packed"] > 0
    trip = client.get(f"/api/trips/{listed[0]['id']}").json()
    assert {d["source"] for d in trip["weather"]} == {"given"} and trip["plan"]["uncovered"] == []
    assert trip["packed"] and all(line.startswith("basic:") for line in trip["packed"])


def test_the_demo_keeps_two_outfits_and_plans_a_day_a_few_days_ahead(client):
    client.post("/api/profile", json={"profile": "demo"})
    kept = client.get("/api/outfits/kept").json()["outfits"]
    assert [o["name"] for o in kept] == ["Lunch in the sun", None] and all(o["gone"] == [] for o in kept)
    planned = client.get("/api/plans").json()["plans"]
    assert [p["day"] for p in planned] == [(wears.today() + timedelta(days=3)).isoformat()]


def test_an_older_demo_closet_is_given_the_new_items_once(cfg, tmp_path, monkeypatch):
    full = data()
    older = {**{k: v for k, v in full.items() if k not in ("wishes", "trip")},
             "items": [i for i in full["items"] if i.get("wave") != 2]}
    old_bundle = tmp_path / "bundle"
    (old_bundle / "demo_data").mkdir(parents=True)
    (old_bundle / "demo_data" / "items.json").write_text(json.dumps(older), encoding="utf-8")
    shutil.copytree(bundle_dir() / "demo_data" / "images", old_bundle / "demo_data" / "images")
    monkeypatch.setattr(demo, "bundle_dir", lambda: old_bundle)
    assert demo.ensure(cfg) == len(older["items"])
    outfits_before = len(rows(cfg, "SELECT id FROM worn_outfits"))
    assert outfits_before < len(full["outfits"]) and not rows(cfg, "SELECT id FROM wishes")

    monkeypatch.undo()
    new = [i for i in full["items"] if i.get("wave") == 2]
    assert demo.ensure(cfg) == len(new)
    assert len(rows(cfg, "SELECT id FROM items")) == len(full["items"])
    assert len(rows(cfg, "SELECT id FROM worn_outfits")) == len(full["outfits"])
    assert len(rows(cfg, "SELECT id FROM wishes")) == 2 and len(rows(cfg, "SELECT id FROM trips")) == 1
    # once: what the owner removes afterwards is not brought back
    conn = db.connect(cfg.db_path("demo"))
    conn.execute("DELETE FROM items WHERE id = ?", (new[0]["id"],))
    conn.execute("DELETE FROM trips")
    conn.close()
    assert demo.ensure(cfg) == 0
    assert len(rows(cfg, "SELECT id FROM items")) == len(full["items"]) - 1 and not rows(cfg, "SELECT id FROM trips")


def test_two_demo_shoes_are_drawn_from_made_up_traces(client, cfg):
    traced = [i for i in data()["items"] if i.get("trace")]
    assert {i["name"] for i in traced} == {"Grey runners", "Brown boots"}
    assert all(not i.get("photo") for i in traced)   # traced from made-up photos, none kept
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    for it in traced:
        shown = client.get(f"/api/items/{it['id']}").json()
        assert shown["trace"]["state"] == "done" and shown["trace"]["drawn"] and shown["trace"]["parts"]
        assert 'id="traced-' in shown["illustration_svg"]
        # the drawing kept is the one the app makes from the trace now
        r = rows(cfg, "SELECT * FROM items WHERE id = ?", it["id"])[0]
        assert illustrations.make(r).svg == r["illustration_svg"] == it["illustration_svg"]
    runners = next(i for i in traced if i["name"] == "Grey runners")
    assert client.get(f"/api/items/{runners['id']}").json()["trace"]["marks"]   # the stripes, to fix
    # a fix works on a demo shoe as on any traced shoe
    r = client.post(f"/api/items/{runners['id']}/trace/fix", json={"mark": 0, "hide": True})
    assert r.status_code == 200 and r.json()["trace"]["marks"][0]["hidden"]
    # a shoe with no photo has nothing to trace: said to be boots, it is not left waiting to be traced
    tops = next(i for i in data()["items"] if i["name"] == "Black high-tops")
    shown = client.patch(f"/api/items/{tops['id']}", json={"category": "boots"}).json()
    assert shown["trace"]["state"] is None and shown["trace"]["message"] is None


def test_an_older_demo_closet_is_given_its_traced_shoes_once(cfg, tmp_path, monkeypatch):
    full = data()
    older = {**full, "items": [{k: v for k, v in i.items() if k not in ("trace", "trace_version")} for i in full["items"]]}
    old_bundle = tmp_path / "bundle"
    (old_bundle / "demo_data").mkdir(parents=True)
    (old_bundle / "demo_data" / "items.json").write_text(json.dumps(older), encoding="utf-8")
    shutil.copytree(bundle_dir() / "demo_data" / "images", old_bundle / "demo_data" / "images")
    monkeypatch.setattr(demo, "bundle_dir", lambda: old_bundle)
    demo.ensure(cfg)
    assert not rows(cfg, "SELECT id FROM items WHERE trace IS NOT NULL")
    boots = next(i for i in full["items"] if i["name"] == "Brown boots")
    conn = db.connect(cfg.db_path("demo"))
    conn.execute("UPDATE items SET trace_plain = 1 WHERE id = ?", (boots["id"],))   # the owner chose the plain drawing
    conn.close()

    monkeypatch.undo()
    demo.ensure(cfg)
    got = rows(cfg, "SELECT * FROM items WHERE trace IS NOT NULL")
    assert [r["name"] for r in got] == ["Grey runners"] and got[0]["trace_state"] == "done"
    assert 'id="traced-' in got[0]["illustration_svg"]
    conn = db.connect(cfg.db_path("demo"))
    conn.execute("UPDATE items SET trace_state = NULL, trace = NULL WHERE id = ?", (got[0]["id"],))
    conn.execute("UPDATE items SET trace_state = 'refused' WHERE id = ?", (got[0]["id"],))
    conn.close()
    demo.ensure(cfg)   # once: a shoe the demo has done something with since is left as it is
    assert not rows(cfg, "SELECT id FROM items WHERE trace IS NOT NULL")
