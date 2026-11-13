"""What the outfit engine and the gap analysis are told about each item's cloth (`today.cloth`, `today.closet_rows`)."""
import json

import pytest

from closet import app as app_module
from closet import db, outfits, today

from .conftest import upload


def row(id="x", category="shirt", name=None, material=None, source=None, answer=None, silhouette=None, **kw):
    """An item as the items table stores it (JSON as text)."""
    return {"id": id, "name": name, "category": category, "color": "navy", "color_hex": None, "pattern": "solid",
            "formality": "casual", "season": kw.pop("season", "all"), "material": material, "rating": None,
            "status": "active", "location": "closet", "laundry": "clean",
            "silhouette": json.dumps(silhouette or {}), "source": json.dumps(source or {}), "confidence": "{}",
            "illustration_svg": None,
            "tag_answer": answer if answer is None or isinstance(answer, str) else json.dumps(answer), **kw}


def answer(**details):
    return {"category": "shirt", "details": {"weight": "unknown", "knit_gauge": "na", "sleeve_length": "na", **details}}


def engine_row(r):
    return {**{k: v for k, v in r.items() if k not in today.LEFT_OUT}, **today.cloth(r)}


def weight(r):
    return outfits.WEIGHT_CLASSES[outfits._piece(engine_row(r)).weight]


# ------------------------------------------------------------------ the order of trust
def test_1_the_owners_own_words_win_over_the_answer():
    assert weight(row(name="Flannel shirt", source={"name": "user"}, answer=answer(weight="lightweight"))) == "heavyweight"
    assert weight(row(material="linen", source={"material": "user"}, answer=answer(weight="heavyweight"))) == "lightweight"


def test_1_a_bare_fibre_from_the_owner_does_not_overrule_the_answer():
    assert weight(row(material="wool", source={"material": "user"}, answer=answer(weight="lightweight"))) == "lightweight"
    assert weight(row(material="100% cotton", source={"material": "user"}, answer=answer(weight="heavyweight"))) == "heavyweight"


def test_2_the_answer_wins_over_words_the_owner_did_not_set():
    # a name the demo or the tagger gave, a material the tagger filled in
    assert weight(row(name="Linen shirt", answer=answer(weight="heavyweight"))) == "heavyweight"
    assert weight(row(name="Grey shirt", material="linen", source={"material": "ai"},
                      answer=answer(weight="super_heavy"))) == "super_heavy"


@pytest.mark.parametrize("gauge,expected", sorted(today.KNIT_GAUGE_WEIGHT.items()))
def test_2_a_knit_gauge_gives_the_weight_when_the_answer_has_none(gauge, expected):
    assert weight(row(category="sweater", name="Navy sweater", answer=answer(knit_gauge=gauge))) == expected


def test_2_the_answers_weight_wins_over_its_knit_gauge():
    assert weight(row(category="sweater", answer=answer(weight="midweight", knit_gauge="super_chunky"))) == "midweight"


def test_3_an_unknown_weight_falls_through_to_the_words():
    assert weight(row(name="Linen shirt", answer=answer())) == "lightweight"
    assert weight(row(category="sweater", name="Burgundy cable sweater", answer=answer())) == "heavyweight"


def test_4_then_to_the_category():
    assert weight(row(name="Grey shirt", answer=answer())) == "midweight"
    assert weight(row(category="coat", name="Black coat", answer=answer())) == "super_heavy"
    assert weight(row(category="tee", name="Grey tee", season="warm", answer=answer())) == "lightweight"


def test_the_sleeve_comes_from_the_answer_when_the_silhouette_does_not_say():
    tee = row(category="tee", name="Grey tee")
    assert outfits._piece(engine_row(tee)).long_sleeve is False   # the category's usual sleeve
    long_tee = row(category="tee", name="Grey tee", answer=answer(sleeve_length="long"))
    assert today.cloth(long_tee)["silhouette"] == {"sleeve": "long"}
    assert outfits._piece(engine_row(long_tee)).long_sleeve is True
    short = row(name="Grey shirt", answer=answer(sleeve_length="short"))
    assert outfits._piece(engine_row(short)).long_sleeve is False
    # what the silhouette says (the owner's, or the answer's copied there) wins
    owned = row(name="Grey shirt", silhouette={"sleeve": "short", "fit": "slim"}, source={"silhouette": "user"},
                answer=answer(sleeve_length="long"))
    assert today.cloth(owned)["silhouette"] == {"sleeve": "short", "fit": "slim"}
    assert outfits._piece(engine_row(owned)).long_sleeve is False


@pytest.mark.parametrize("stored", [None, "", "{nope", "[1, 2]", "null", "42", '{"details": "heavy"}', '{"details": null}',
                                    '{"details": {"weight": ["heavyweight"], "knit_gauge": {}, "sleeve_length": 3}}',
                                    '{"details": {"weight": "very heavy", "knit_gauge": "huge", "sleeve_length": "none"}}'])
def test_a_missing_empty_or_broken_answer_is_nothing_known(stored):
    r = row(name="Linen shirt", answer=stored)
    assert today.cloth(r) == {"weight_class": None, "silhouette": {}}
    assert weight(r) == "lightweight"   # the old guess from the words


def test_broken_source_and_silhouette_are_nothing_known():
    r = {**row(name="Flannel shirt", answer=answer(weight="lightweight")), "source": "{nope", "silhouette": "[1]"}
    assert today.cloth(r) == {"weight_class": "lightweight", "silhouette": {}}


# ------------------------------------------------------------------ the engine
def layering_closet(shirt_answer):
    rows = [row("shirt", name="Grey shirt", answer=shirt_answer, silhouette={"sleeve": "long"}),
            row("sweater", "sweater", name="Navy sweater", answer=answer(weight="lightweight")),
            row("jeans", "jeans", name="Blue jeans"), row("sneakers", "sneakers", name="White sneakers")]
    return [engine_row(r) for r in rows]


def worn_together(rows):
    found = outfits.suggest(rows, outfits.Context(low_c=10, high_c=14), 5)
    assert found["outfits"]
    return {(o["pieces"]["base"], o["pieces"]["mid"]) for o in found["outfits"]}


def test_a_shirt_tagged_heavyweight_is_not_put_under_a_lightweight_sweater():
    assert ("shirt", "sweater") not in worn_together(layering_closet(answer(weight="heavyweight")))
    # the same shirt with no stored answer is guessed midweight from its category, and goes under anything
    assert ("shirt", "sweater") in worn_together(layering_closet(None))


# ------------------------------------------------------------------ through the API
def set_answer(cfg, profile, item_id, stored):
    conn = db.connect(cfg.db_path(profile))
    try:
        conn.execute("UPDATE items SET tag_answer = ? WHERE id = ?", (json.dumps(stored), item_id))
    finally:
        conn.close()


def make_item(client, key, **fields):
    created = upload(client, key=key).json()
    assert client.patch(f"/api/items/{created['id']}", json=fields).status_code == 200
    return created["id"]


def test_todays_outfits_use_the_stored_answer(client, cfg):
    ids = {
        "shirt": make_item(client, "a", name="Grey shirt", category="shirt", color="grey", formality="casual",
                           silhouette={"sleeve": "long"}),
        "sweater": make_item(client, "b", name="Navy sweater", category="sweater", color="navy", formality="casual"),
        "jeans": make_item(client, "c", name="Blue jeans", category="jeans", color="blue", formality="casual"),
        "sneakers": make_item(client, "d", name="White sneakers", category="sneakers", color="white", formality="casual"),
    }

    def pairs():
        r = client.post("/api/outfits/today", json={"low_c": 10, "high_c": 14, "count": 5})
        assert r.status_code == 200, r.text
        return {(o["pieces"]["base"], o["pieces"]["mid"]) for o in r.json()["outfits"]}

    assert (ids["shirt"], ids["sweater"]) in pairs()
    set_answer(cfg, "main", ids["shirt"], answer(weight="heavyweight"))
    set_answer(cfg, "main", ids["sweater"], answer(weight="lightweight"))
    assert (ids["shirt"], ids["sweater"]) not in pairs()


def warm_coat_score(body):
    return next(g["score"] for g in body["gaps"] if g["id"] == "outer-warm")


def test_the_gaps_use_the_stored_answer_and_a_new_one_is_not_served_from_the_cache(client, cfg, monkeypatch):
    runs = []
    original = app_module.life.analyse
    monkeypatch.setattr(app_module.life, "analyse", lambda *a: runs.append(1) or original(*a))
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    coat_id = next(i["id"] for i in client.get("/api/items").json()["items"] if i["category"] == "coat")
    before = client.get("/api/gaps").json()
    conn = db.connect(cfg.db_path("demo"))
    try:
        stored = json.loads(conn.execute("SELECT tag_answer FROM items WHERE id = ?", (coat_id,)).fetchone()[0])
    finally:
        conn.close()
    assert stored["details"]["weight"] == "super_heavy"
    # the only coat turns out to be a light one: a warm coat is missed more than before
    set_answer(cfg, "demo", coat_id, {**stored, "details": {**stored["details"], "weight": "lightweight"}})
    light = client.get("/api/gaps").json()
    assert light != before and warm_coat_score(light) > warm_coat_score(before)
    # and back again
    set_answer(cfg, "demo", coat_id, stored)
    assert client.get("/api/gaps").json() == before
    assert len(runs) == 3
    # a new answer that only changes what the engine does not read (and when it was given) is served from the cache
    set_answer(cfg, "demo", coat_id, {**stored, "details": {**stored["details"], "placket_buttons": 9}})
    conn = db.connect(cfg.db_path("demo"))
    try:
        conn.execute("UPDATE items SET tagged_at = '2030-01-01T00:00:00Z', tag_route = 'plan' WHERE id = ?", (coat_id,))
    finally:
        conn.close()
    assert client.get("/api/gaps").json() == before
    assert len(runs) == 3
