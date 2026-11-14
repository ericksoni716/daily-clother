"""What an item is: its kind from the owner's taxonomy, the group it is shown in, and the category that follows.

Claude is never called: `FakeClaude` (conftest) describes every upload as a navy polo.
"""
import json
from pathlib import Path

import pytest

from closet import db, details, kinds, today, vocab
from closet.drawing.item import BOTTOMS, SHOES, TOPS

from .conftest import upload
from .test_corrections import described, history, svg

TAXONOMY = json.loads((Path(__file__).resolve().parents[2] / "docs" / "menswear-taxonomy.json").read_text(encoding="utf-8"))
GARMENTS = TAXONOMY["garments"]


# ---- the catalogue

def test_the_kinds_are_the_taxonomys_garments_in_its_order():
    assert list(kinds.KINDS) == list(GARMENTS)
    for kind, (category, signature) in kinds.KINDS.items():
        assert GARMENTS[kind]["category"] == category and GARMENTS[kind].get("signature", "") == signature
    for kind, axes in kinds.TOP_AXES_OF.items():
        for axis, values in axes.items():
            assert tuple(GARMENTS[kind][axis]) == values, (kind, axis)
    assert kinds.ACCESSORIES == {k: g["app_category"] for k, g in GARMENTS.items() if g["category"] == "accessory"}


def test_each_kinds_group_comes_from_its_taxonomy_category():
    by_group = {}
    for k in kinds.catalogue()["kinds"]:
        by_group.setdefault(k["group"], set()).add(GARMENTS[k["id"]]["category"])
    assert by_group == {"shirts": {"woven_shirt"}, "tees": {"knit_top"}, "knitwear": {"knitwear", "sweatshirt"},
                        "jackets": {"outerwear"}, "tailoring": {"tailoring"}, "trousers": {"bottoms"},
                        "activewear": {"activewear"}, "loungewear": {"loungewear"}, "shoes": {"footwear"},
                        "accessories": {"accessory"}}
    assert kinds.group("fleece_pullover") == "activewear"   # where the taxonomy puts it
    assert [g["title"] for g in kinds.catalogue()["groups"]][:3] == ["Shirts", "Tees & polos", "Knitwear & mid layers"]


@pytest.mark.parametrize("kind", list(GARMENTS))
def test_every_kind_sets_a_category_of_its_own_sort(kind):
    category = kinds.category_for(kind)
    assert category in vocab.CATEGORY
    taxonomy = GARMENTS[kind]["category"]
    if taxonomy == "footwear":
        assert category in SHOES
    elif taxonomy == "accessory":
        assert category == GARMENTS[kind]["app_category"]
    elif GARMENTS[kind].get("app_category"):
        assert category == GARMENTS[kind]["app_category"]
    else:
        assert category in TOPS + BOTTOMS
    # a set (pyjamas, a sweatsuit) keeps a top's or a bottom's category; anything else ignores the item's own
    for current in ("trousers", "tee", "boots"):
        again = kinds.category_for(kind, current)
        assert again == (current if kind in kinds.SET_CATEGORY and current in TOPS + BOTTOMS else category)
    # and is drawn, unless it is an accessory
    assert (kinds.drawing(kind) is None) == (taxonomy == "accessory")


def test_some_categories_by_name():
    assert [kinds.category_for(k) for k in ("ocbd", "henley", "fleece_pullover", "joggers", "chelsea_boot", "penny_loafer",
                                            "canvas_low_top", "slide", "beanie", "parka", "blazer")] == \
        ["shirt", "tee", "sweater", "trousers", "boots", "dress_shoes", "sneakers", "sandals", "hat", "coat", "jacket"]


def test_names_and_search_words():
    assert kinds.name("fleece_pullover") == "Fleece pullover" and kinds.name("t_shirt") == "T-shirt"
    assert kinds.name("chukka") == "Chukka boot"
    assert details.words("garment", "ocbd") == "oxford button-down"   # the history says it the same way
    assert "snaps" in kinds.search_words("western_shirt") and "trainers" in kinds.search_words("running_shoe")
    assert "activewear" in kinds.search_words("fleece_pullover")


def test_a_kind_of_top_has_only_its_own_details():
    tee = details.names_for("tee", "t_shirt")
    assert "neckline" in tee and "cuff" not in tee and "placket" not in tee and "collar" not in tee
    assert "fabric" in tee and "sleeve_length" in tee and "garment" in tee   # the cut and cloth stay for every kind
    assert details.names_for("tee") == details.names_for("tee", None)
    assert "cuff" in details.names_for("jacket", "parka")   # a kind that names no construction keeps them all
    assert details.names_for("boots", "chelsea_boot") == details.names_for("boots")


# ---- choosing a kind

def _rows(cfg):
    conn = db.connect(cfg.db_path("main"))
    try:
        return {r["id"]: r for r in today.closet_rows(conn)}
    finally:
        conn.close()


def test_choosing_a_kind_sets_the_category_and_the_drawing_and_survives_describe_it_again(client, services, claude, cfg):
    item = described(client, services, claude)
    assert item["kind"] is None and item["group"] == "tees"   # Claude said a polo, but no kind
    before = svg(client, item)
    r = client.put(f"/api/items/{item['id']}/kind", json={"kind": "fleece_pullover"})
    assert r.status_code == 200
    chosen = r.json()
    assert chosen["kind"] == "fleece_pullover" and chosen["kind_name"] == "Fleece pullover"
    assert chosen["kind_by"] == "owner" and chosen["group"] == "activewear"
    assert chosen["category"] == "sweater" and chosen["source"]["category"] == "user"
    assert chosen["own_details"] == {"garment": "fleece_pullover"}
    assert svg(client, chosen) != before
    assert _rows(cfg)[item["id"]]["category"] == "sweater"   # what the outfit engine and What's missing read
    assert _rows(cfg)[item["id"]]["kind"] == "fleece_pullover"
    listed = next(i for i in client.get("/api/items").json()["items"] if i["id"] == item["id"])
    assert (listed["kind"], listed["kind_name"], listed["group"]) == ("fleece_pullover", "Fleece pullover", "activewear")

    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    again = client.get(f"/api/items/{item['id']}").json()
    assert again["kind"] == "fleece_pullover" and again["category"] == "sweater"
    assert svg(client, again) == svg(client, chosen)


def test_undo_gives_back_the_kind_and_category_before(client, services, claude, cfg):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/kind", json={"kind": "henley"})
    second = client.put(f"/api/items/{item['id']}/kind", json={"kind": "chelsea_boot"}).json()
    assert second["category"] == "boots" and second["kind"] == "chelsea_boot"
    latest = history(client, item["id"])[0]
    names = {p["name"] for p in latest["parts"]}
    assert {"category", "garment"} <= names
    r = client.post(f"/api/items/{item['id']}/history/{latest['id']}/undo")
    assert r.status_code == 200
    back = r.json()["item"]
    assert back["kind"] == "henley" and back["category"] == "tee"
    assert _rows(cfg)[item["id"]]["category"] == "tee"
    assert _rows(cfg)[item["id"]]["kind"] == "henley"


def test_undo_of_the_first_kind_gives_back_claudes_category(client, services, claude):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/kind", json={"kind": "penny_loafer"})
    latest = history(client, item["id"])[0]
    back = client.post(f"/api/items/{item['id']}/history/{latest['id']}/undo").json()["item"]
    assert back["kind"] is None and back["category"] == "polo" and back["source"].get("category") != "user"
    assert back["own_details"] == {}


def test_details_the_kind_does_not_have_are_hidden_not_deleted(client, services, claude):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"cuff": "open_hem", "placket_buttons": 2}})
    tee = client.put(f"/api/items/{item['id']}/kind", json={"kind": "t_shirt"}).json()
    assert tee["own_details"] == {"cuff": "open_hem", "placket_buttons": 2, "garment": "t_shirt"}   # kept
    shown = {d["name"] for g in client.get(f"/api/items/{item['id']}/details").json()["groups"] for d in g["details"]}
    assert "cuff" not in shown and "placket_buttons" not in shown and "neckline" in shown
    assert client.get(f"/api/items/{item['id']}/details/cuff").status_code == 404
    assert client.put(f"/api/items/{item['id']}/details", json={"details": {"cuff": "barrel_1"}}).status_code == 422
    # a kind that has them shows them again, with the owner's values
    polo = client.put(f"/api/items/{item['id']}/kind", json={"kind": "polo"}).json()
    found = {d["name"]: d for g in client.get(f"/api/items/{item['id']}/details").json()["groups"] for d in g["details"]}
    assert found["cuff"]["own"] and found["cuff"]["value"] == "open_hem" and found["placket_buttons"]["value"] == 2
    assert polo["category"] == "polo"


def test_a_kind_must_be_one_of_the_list(client, services, claude):
    item = described(client, services, claude)
    for bad in ({"kind": "toga"}, {"kind": "unknown"}, {"kind": 3}, {}):
        r = client.put(f"/api/items/{item['id']}/kind", json=bad)
        assert r.status_code == 422, bad
        assert isinstance(r.json()["detail"], str)
    assert client.put("/api/items/nope/kind", json={"kind": "polo"}).status_code == 404
    assert len(history(client, item["id"])) == 1


def test_claudes_kind_and_what_else_it_thought(client, services, claude, cfg):
    item = described(client, services, claude)
    conn = db.connect(cfg.db_path("main"))
    try:
        answer = json.loads(conn.execute("SELECT tag_answer FROM items WHERE id = ?", (item["id"],)).fetchone()[0])
        answer["details"]["garment"] = "rugby_shirt"
        conn.execute("UPDATE items SET tag_answer = ? WHERE id = ?", (json.dumps(answer), item["id"]))
    finally:
        conn.close()
    said = client.get(f"/api/items/{item['id']}").json()
    assert said["kind"] == "rugby_shirt" and said["kind_by"] == "claude" and said["kind_confidence"] == answer["details_confidence"]
    assert "rugby_shirt" not in said["kind_alternatives"] and "polo" in said["kind_alternatives"]   # a polo collar and placket
    mine = client.put(f"/api/items/{item['id']}/kind", json={"kind": "polo"}).json()
    assert mine["kind_alternatives"][0] == "rugby_shirt" and mine["kind_confidence"] is None


def test_the_catalogue_and_the_drawings(client):
    found = client.get("/api/kinds").json()
    assert len(found["kinds"]) == len(GARMENTS) and len(found["groups"]) == 10
    assert client.get("/api/vocab").json()["kind_groups"] == found["groups"]
    r = client.get("/api/kinds/fleece_pullover.svg?color=%23336699")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and "#336699" in r.text.lower()
    assert client.get("/api/kinds/beanie.svg").status_code == 404
    assert client.get("/api/kinds/toga.svg").status_code == 404
    assert client.get("/api/kinds/polo.svg?color=red").status_code == 404


def test_a_sentence_changing_the_category_drops_a_kind_it_no_longer_is(client, services, claude, cfg):
    item = upload(client, key="k9").json()
    client.put(f"/api/items/{item['id']}/kind", json={"kind": "henley"})
    changed = client.patch(f"/api/items/{item['id']}", json={"category": "shirt"}).json()
    assert changed["own_details"] == {} and changed["kind"] is None
