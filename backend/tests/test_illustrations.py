"""Every item's drawing, kept up to date (closet/illustrations.py): made when tagging finishes, made again when the
owner changes a field it shows or the drawing code is newer, the owner's fields winning, never failing an item.

Claude is never called: `FakeClaude` (conftest) stands in for both routes.
"""
import json
import sqlite3

from closet import db, drawing, illustrations
from closet.config import bundle_dir
from closet.drawing import item as draw
from closet.tagger.schema import NAMED_HEX

from .conftest import ANSWER, upload

ANSWER_JSON = ANSWER.model_dump(mode="json")


def cut(services):
    services.worker.is_ready = lambda: True
    return services.worker.drain()


def tagged(client, services, claude, key="k1"):
    """An item added, cut out and described by the stand-in for Claude (a navy polo)."""
    item = upload(client, key=key).json()
    cut(services)
    claude.mode = "answers"
    assert services.tag_worker.drain() == 1
    return client.get(f"/api/items/{item['id']}").json()


def stored(cfg, item_id, profile="main"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def set_columns(cfg, item_id, **values):
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in values)} WHERE id = ?", [*values.values(), item_id])
    finally:
        conn.close()


def test_a_drawing_is_made_when_tagging_finishes(client, services, claude, cfg):
    item = upload(client).json()
    cut(services)
    waiting = client.get(f"/api/items/{item['id']}").json()
    assert waiting["tag_state"] == "waiting" and waiting["illustration_url"] is None   # nothing known to draw yet
    assert client.get(f"/api/items/{item['id']}/illustration.svg").status_code == 404

    body = tagged(client, services, claude)
    want = draw.svg_from_answer(ANSWER_JSON, NAMED_HEX["navy"], uid=item["id"][:8])
    assert body["illustration_svg"] == want and body["has_illustration"] and body["illustration_url"]
    assert stored(cfg, item["id"])["illustration_version"] == drawing.DRAWING_VERSION
    r = client.get(body["illustration_url"])
    assert r.status_code == 200 and r.text == want and r.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/api/items").json()["items"][0]["illustration_url"] == body["illustration_url"]
    assert body["seen_not_drawn"] == ["embroidered chest logo"] and isinstance(body["drawing_notes"], list)


def test_it_changes_with_a_field_it_shows_and_not_with_one_it_does_not(client, services, claude):
    body = tagged(client, services, claude)
    url, svg = body["illustration_url"], body["illustration_svg"]
    for change in ({"name": "Club polo"}, {"notes": "from the market"}, {"rating": "love"}, {"brand": "Sample & Co"},
                   {"formality": "casual"}, {"location": "drawer"}):
        after = client.patch(f"/api/items/{body['id']}", json=change).json()
        assert (after["illustration_url"], after["illustration_svg"]) == (url, svg), change

    # the colour, as the item page sends it (the word and its swatch)
    red = client.patch(f"/api/items/{body['id']}", json={"color": "red", "color_hex": "#b33a3a"}).json()
    assert red["illustration_url"] != url and "#b33a3a" in red["illustration_svg"] and NAMED_HEX["navy"] not in red["illustration_svg"]
    assert client.get(red["illustration_url"]).text == red["illustration_svg"]
    listed = client.get("/api/items").json()["items"][0]
    assert listed["illustration_url"] == red["illustration_url"]

    # the shape
    long = client.patch(f"/api/items/{body['id']}", json={"silhouette": {"sleeve": "long"}}).json()
    assert long["illustration_svg"] != red["illustration_svg"]

    # a pattern is not drawn yet: the drawing stays, and says what it leaves out
    plaid = client.patch(f"/api/items/{body['id']}", json={"pattern": "plaid"}).json()
    assert plaid["illustration_svg"] == long["illustration_svg"]
    assert "the plaid: the drawing shows only the colour for now" in plaid["drawing_notes"]


def test_a_field_the_owner_set_wins_over_the_answer(client, services, claude):
    item = upload(client).json()
    # set before Claude answers: the answer leaves them alone, and so does the drawing
    client.patch(f"/api/items/{item['id']}", json={"category": "shirt", "color": "olive", "color_hex": "#6f7550",
                                                   "silhouette": {"sleeve": "long"}})
    cut(services)
    claude.mode = "answers"
    services.tag_worker.drain()
    body = client.get(f"/api/items/{item['id']}").json()
    assert (body["category"], body["color"], body["silhouette"]["sleeve"]) == ("shirt", "olive", "long")
    mine = {**ANSWER_JSON, "category": "shirt", "color": "olive",
            "silhouette": {**ANSWER_JSON["silhouette"], "sleeve": "long"},
            "details": {**ANSWER_JSON["details"], "sleeve_length": "na"}}   # the owner's sleeve, not the answer's
    assert body["illustration_svg"] == draw.svg_from_answer(mine, "#6f7550", uid=item["id"][:8])
    assert body["illustration_svg"] != draw.svg_from_answer(ANSWER_JSON, "#6f7550", uid=item["id"][:8])
    # the answer's details are still drawn: it is not the plain drawing of the owner's fields
    assert body["illustration_svg"] != draw.svg_from_fields("shirt", "#6f7550", None, body["silhouette"], uid=item["id"][:8])


def test_a_colour_word_chosen_by_the_owner_wins_over_the_answers_colour(client, services, claude):
    body = tagged(client, services, claude)
    after = client.patch(f"/api/items/{body['id']}", json={"color": "burgundy"}).json()   # the word alone, no swatch
    assert NAMED_HEX["burgundy"] in after["illustration_svg"] and NAMED_HEX["navy"] not in after["illustration_svg"]


def test_an_item_without_an_answer_is_drawn_from_its_fields(client):
    item = upload(client).json()
    body = client.patch(f"/api/items/{item['id']}", json={"category": "jeans", "color": "blue", "color_hex": "#4a6fa5",
                                                          "silhouette": {"leg": "wide"}}).json()
    assert body["tag_state"] == "none"
    assert body["illustration_svg"] == draw.svg_from_fields("jeans", "#4a6fa5", None, {"leg": "wide"}, uid=item["id"][:8])
    bag = client.patch(f"/api/items/{item['id']}", json={"category": "bag"}).json()
    assert bag["illustration_svg"] is None and bag["illustration_url"] is None   # no shape for it: the photo shows it


def test_an_older_drawing_is_made_again_when_asked_for_and_not_before(client, services, claude, cfg):
    one = tagged(client, services, claude, key="one")
    two = tagged(client, services, claude, key="two")
    for it in (one, two):
        set_columns(cfg, it["id"], illustration_svg="<svg>old</svg>", illustration_version=0)
    # nothing is redrawn by itself (a restart included)
    services.tag_worker.drain()
    assert stored(cfg, one["id"])["illustration_version"] == 0 and stored(cfg, two["id"])["illustration_version"] == 0

    body = client.get(f"/api/items/{one['id']}").json()
    assert body["illustration_svg"] == one["illustration_svg"]
    assert stored(cfg, one["id"])["illustration_version"] == drawing.DRAWING_VERSION
    assert stored(cfg, two["id"])["illustration_svg"] == "<svg>old</svg>"   # only the one asked for

    # the drawing itself, asked for by its address, is drawn again too
    r = client.get(f"/api/items/{two['id']}/illustration.svg")
    assert r.text == two["illustration_svg"] and stored(cfg, two["id"])["illustration_version"] == drawing.DRAWING_VERSION


def test_newer_drawing_code_redraws_an_item_the_first_time_the_closet_is_listed(client, services, claude, cfg, monkeypatch):
    body = tagged(client, services, claude)
    monkeypatch.setattr(drawing, "DRAWING_VERSION", drawing.DRAWING_VERSION + 1)
    set_columns(cfg, body["id"], illustration_svg="<svg>made by the older code</svg>")
    listed = client.get("/api/items").json()["items"][0]
    assert listed["illustration_url"] == body["illustration_url"]   # same drawing as before the old one was put back
    assert stored(cfg, body["id"])["illustration_version"] == drawing.DRAWING_VERSION


def test_an_answer_the_templates_cannot_draw_falls_back_to_the_plainest_drawing(client, services, claude, monkeypatch):
    real = draw.drawing_for

    def fussy(tags):
        if tags.details != draw.Details.plain():
            raise RuntimeError("cannot draw this")
        return real(tags)

    monkeypatch.setattr(draw, "drawing_for", fussy)
    body = tagged(client, services, claude)
    assert body["tag_state"] == "done"
    assert body["illustration_svg"] == draw.svg_from_fields("polo", NAMED_HEX["navy"], uid=body["id"][:8])
    assert draw.FELL_BACK in body["drawing_notes"]


def test_an_answer_with_values_the_drawing_does_not_know_is_drawn_from_the_rest(client, services, claude, cfg):
    body = tagged(client, services, claude)
    odd = json.loads(json.dumps(ANSWER_JSON))
    odd["details"]["placket"] = "laced"   # not in the vocabulary: left out, the rest is drawn
    set_columns(cfg, body["id"], tag_answer=json.dumps(odd), illustration_version=0)
    after = client.get(f"/api/items/{body['id']}").json()
    assert after["illustration_svg"] and after["illustration_svg"] != body["illustration_svg"]
    assert draw.DROPPED in after["drawing_notes"]


def test_drawing_never_fails_an_item(client, services, claude, monkeypatch):
    body = tagged(client, services, claude)
    monkeypatch.setattr(draw, "drawing_from_answer", lambda *a, **k: 1 / 0)
    r = client.patch(f"/api/items/{body['id']}", json={"color": "red", "color_hex": "#b33a3a"})
    assert r.status_code == 200 and r.json()["illustration_svg"] is None and r.json()["drawing_notes"] == [draw.NOT_MADE]
    assert client.get(f"/api/items/{body['id']}/illustration.svg").status_code == 404


def test_a_busy_closet_still_shows_the_new_drawing(client, services, claude, cfg, monkeypatch):
    body = tagged(client, services, claude)
    set_columns(cfg, body["id"], illustration_version=0)

    def busy(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(illustrations, "_store", busy)
    assert client.get(f"/api/items/{body['id']}").json()["illustration_svg"] == body["illustration_svg"]
    assert stored(cfg, body["id"])["illustration_version"] == 0   # kept the next time it is asked for


def test_the_demo_closets_drawings_are_the_ones_made_in_advance(client, cfg):
    data = json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))
    # after a change to the drawings, raise DRAWING_VERSION and regenerate the demo closet with `tools/make_demo.py`
    assert data["drawing_version"] == drawing.DRAWING_VERSION
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    listed = {i["id"]: i for i in client.get("/api/items").json()["items"]}
    assert len(listed) == len(data["items"])
    for it in data["items"]:
        body = client.get(f"/api/items/{it['id']}").json()
        assert body["illustration_svg"] == it["illustration_svg"], it["name"]
        assert listed[it["id"]]["illustration_url"] == body["illustration_url"]
        assert client.get(body["illustration_url"]).text == it["illustration_svg"]
        assert stored(cfg, it["id"], "demo")["illustration_version"] == drawing.DRAWING_VERSION
    # changing a field the drawing shows draws that item from its answer, like any other
    polo = next(it for it in data["items"] if it["name"] == "Navy polo")
    red = client.patch(f"/api/items/{polo['id']}", json={"color": "red", "color_hex": "#b33a3a"}).json()
    assert red["illustration_svg"] != polo["illustration_svg"] and "#b33a3a" in red["illustration_svg"]


def test_the_migration_keeps_the_drawings_made_before_it(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = sqlite3.connect(path)
    for version, file in db.migration_files():
        if version <= 6:   # a closet made by the previous version
            old.executescript(file.read_text(encoding="utf-8") + f"\nPRAGMA user_version = {version};")
    old.execute("INSERT INTO items (id, category, illustration_svg, cutout_state, created_at, updated_at) "
                "VALUES ('a', 'shirt', '<svg>made in advance</svg>', 'none', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    old.execute("INSERT INTO items (id, category, cutout_state, created_at, updated_at) "
                "VALUES ('b', 'tee', 'none', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    old.commit()
    old.close()
    result = db.migrate(path, cfg.local_backups_dir)
    assert result["from"] == 6 and 7 in result["applied"]
    conn = db.connect(path)
    try:
        rows = {r["id"]: r for r in conn.execute("SELECT * FROM items")}
        assert rows["a"]["illustration_version"] == 1 and rows["b"]["illustration_version"] is None
        assert illustrations.current(conn, rows["a"])["illustration_svg"] == "<svg>made in advance</svg>"   # kept
        assert illustrations.current(conn, rows["b"])["illustration_svg"] == draw.svg_from_fields("tee", None, uid="b")
    finally:
        conn.close()
