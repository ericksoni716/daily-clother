import asyncio
import json
import xml.etree.ElementTree as ET

import pytest

from closet import app as app_module
from closet import db, illustrations
from closet.drawing import figure
from closet.drawing import item as draw
from closet.tagger.schema import NAMED_HEX

from .conftest import ANSWER

URL = "/api/outfits/figure"
PLACES = ("base", "mid", "outer", "bottom", "shoes")


def insert_item(cfg, item_id="top", profile="main", **fields):
    row = {"id": item_id, "category": "polo", "color": "navy", "color_hex": NAMED_HEX["navy"],
           "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z", **fields}
    for key in ("source", "silhouette", "tag_answer"):
        if isinstance(row.get(key), dict):
            row[key] = json.dumps(row[key])
    conn = db.connect(cfg.db_path(profile))
    try:
        conn.execute(f"INSERT INTO items ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def test_figure_requires_login(anon):
    assert anon.post(URL, json={}).status_code == 401


def test_figure_requires_login_after_setup(client):
    client.post("/api/logout")
    assert client.post(URL, json={}).status_code == 401


@pytest.mark.parametrize("body", [{}, dict.fromkeys(PLACES)])
def test_empty_or_nullable_places_return_a_private_svg(client, body):
    response = client.post(URL, json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "private, no-store"
    assert ET.fromstring(response.text).tag == "{http://www.w3.org/2000/svg}svg"
    assert response.text == figure.svg_from_pieces({})


@pytest.mark.parametrize("body", [
    {"accessories": []}, {"pieces": {}}, {"other": None}, {"base": 1}, {"mid": False},
    {"outer": []}, {"bottom": {}}, {"shoes": 3.5}, [], "top",
])
def test_request_shape_is_strict(client, body):
    assert client.post(URL, json=body).status_code == 422


@pytest.mark.parametrize("place", PLACES)
def test_unknown_items_are_rejected_in_every_place(client, place):
    response = client.post(URL, json={place: "not-an-item"})
    assert response.status_code == 422
    assert response.json()["detail"] == "A piece is not in the open closet."


def test_all_places_are_resolved_without_changing_the_closet(client, cfg):
    categories = ("tee", "sweater", "jacket", "trousers", "boots")
    rows = {place: insert_item(cfg, place, category=category) for place, category in zip(PLACES, categories, strict=True)}
    response = client.post(URL, json={place: row["id"] for place, row in rows.items()})
    assert response.status_code == 200
    assert response.text == figure.svg_from_pieces({place: illustrations.description(row) for place, row in rows.items()})
    conn = db.connect(cfg.db_path("main"))
    try:
        assert all(dict(row) == rows[row["id"]] for row in conn.execute("SELECT * FROM items"))
    finally:
        conn.close()


def test_figures_use_only_the_open_closet(client, cfg):
    insert_item(cfg, "main-only")
    insert_item(cfg, "shared", color_hex="#123456")
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo_row = insert_item(cfg, "shared", profile="demo", color_hex="#abcdef")
    insert_item(cfg, "demo-only", profile="demo")
    assert client.post(URL, json={"base": "main-only"}).status_code == 422
    response = client.post(URL, json={"base": "shared"})
    assert response.status_code == 200
    assert response.text == figure.svg_from_pieces({"base": illustrations.description(demo_row)})
    assert "#abcdef" in response.text and "#123456" not in response.text
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.post(URL, json={"base": "demo-only"}).status_code == 422
    response = client.post(URL, json={"base": "shared"})
    assert "#123456" in response.text and "#abcdef" not in response.text


@pytest.mark.parametrize("own_hex", [False, True])
def test_owner_corrections_and_remaining_details_reach_the_figure(client, cfg, monkeypatch, own_hex):
    source = {"category": "user", "color": "user", "silhouette": "user"}
    if own_hex:
        source["color_hex"] = "user"
    answer = ANSWER.model_dump(mode="json")
    row = insert_item(cfg, category="shirt", color="burgundy", color_hex="#123456", source=source,
                      silhouette={"sleeve": "long", "neck": "crew", "fit": "loose"}, tag_answer=answer)
    seen = {}
    render = figure.svg_from_pieces

    def capture(pieces):
        seen.update(pieces)
        return render(pieces)

    monkeypatch.setattr(figure, "svg_from_pieces", capture)
    response = client.post(URL, json={"base": row["id"]})
    assert response.status_code == 200
    description = seen["base"]
    assert description["category"] == "shirt" and description["color"] == "burgundy"
    assert description["silhouette"]["sleeve"] == "long"
    assert description["details"] == {**answer["details"], "sleeve_length": "na", "neckline": "na",
                                      "collar": "none", "fit_detail": "regular"}
    assert description["color_hex"] == ("#123456" if own_hex else None)
    assert ("#123456" if own_hex else NAMED_HEX["burgundy"]) in response.text
    expected = {**answer, "category": "shirt", "color": "burgundy",
                "silhouette": description["silhouette"], "details": description["details"]}
    assert illustrations.make(row) == draw.drawing_from_answer(expected, description["color_hex"], uid="top")
    assert json.loads(row["tag_answer"]) == answer


@pytest.mark.parametrize("tag_answer", [None, "{broken", "[]", "null"])
def test_coarse_fallback_retains_the_original_item_drawing(cfg, services, tag_answer):
    row = insert_item(cfg, category="jeans", color="red", color_hex="#abc", pattern="stripe",
                      silhouette={"leg": "wide"}, source={"color": "user"}, tag_answer=tag_answer)
    assert illustrations.description(row) == {"category": "jeans", "color": "red", "color_hex": "#abc",
                                             "pattern": "stripe", "silhouette": {"leg": "wide"}, "details": {}}
    assert illustrations.make(row) == draw.drawing_from_fields(
        "jeans", "#abc", "stripe", {"leg": "wide"}, color="red", uid="top")


def test_coarse_rows_and_invalid_swatches_are_safe(client, cfg):
    row = insert_item(cfg, color_hex='"><script>alert(1)</script>')
    response = client.post(URL, json={"base": row["id"]})
    assert response.status_code == 200
    ET.fromstring(response.text)
    assert "<script" not in response.text and NAMED_HEX["navy"] in response.text


@pytest.mark.parametrize("source", ["[]", "null", "true", '"unknown"', "12"])
def test_malformed_stored_source_uses_plain_fields_without_logging(client, cfg, caplog, source):
    row = insert_item(cfg, category="shirt", color="red", color_hex="#123456", source=source,
                      tag_answer=ANSWER.model_dump(mode="json"))
    insert_item(cfg, "legs", category="trousers", color_hex="#abcdef")
    assert illustrations.description(row) == {"category": "shirt", "color": "red", "color_hex": "#123456",
                                             "silhouette": {}, "details": {}}
    response = client.post(URL, json={"base": row["id"], "bottom": "legs"})
    assert response.status_code == 200
    assert "#123456" in response.text and "#abcdef" in response.text
    assert not [record for record in caplog.records if record.name == "closet.illustrations"]
    assert illustrations.make(row) == draw.Drawing(None, (draw.NOT_MADE,))


@pytest.mark.parametrize("details", [None, [], "unknown", {"sleeve_length": ["bad"], "placket_buttons": "bad"}])
def test_malformed_stored_details_do_not_break_the_outfit(client, cfg, details):
    answer = {**ANSWER.model_dump(mode="json"), "details": details}
    row = insert_item(cfg, tag_answer=answer, source={"silhouette": "user"}, silhouette={"sleeve": "long"})
    insert_item(cfg, "legs", category="trousers", color_hex="#abcdef")
    response = client.post(URL, json={"base": row["id"], "bottom": "legs"})
    assert response.status_code == 200
    ET.fromstring(response.text)
    assert "#abcdef" in response.text


def test_description_and_rendering_run_offloop_with_a_profile_snapshot(client, cfg, services, monkeypatch):
    row = insert_item(cfg, color_hex="#123456")
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    insert_item(cfg, profile="demo", color_hex="#abcdef")
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    dispatch = app_module.run_in_threadpool
    describe = illustrations.description
    render = figure.svg_from_pieces
    calls = []

    async def switch_before_work(work):
        services.state.update(profile="demo")
        return await dispatch(work)

    def offloop_describe(item):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        calls.append("describe")
        return describe(item)

    def offloop_render(pieces):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        calls.append("render")
        return render(pieces)

    monkeypatch.setattr(app_module, "run_in_threadpool", switch_before_work)
    monkeypatch.setattr(illustrations, "description", offloop_describe)
    monkeypatch.setattr(figure, "svg_from_pieces", offloop_render)
    response = client.post(URL, json={"base": row["id"]})
    assert response.status_code == 200
    assert calls == ["describe", "render"]
    assert "#123456" in response.text and "#abcdef" not in response.text
