import itertools
import json
import random
from pathlib import Path

import pytest

from closet import outfits
from closet.config import bundle_dir

from .conftest import upload

CORE = ("base", "mid", "outer", "bottom", "shoes")
BOTTOMS = ("jeans", "trousers", "shorts")
SHOES = ("sneakers", "boots", "dress_shoes", "sandals")


def item(id, category, color="navy", formality=None, season="all", pattern="solid", **kw):
    return {"id": id, "name": kw.pop("name", f"{color} {category} {id}"), "category": category, "color": color,
            "color_hex": None, "pattern": pattern, "formality": formality, "season": season,
            "silhouette": kw.pop("silhouette", {}), "material": kw.pop("material", None), "rating": kw.pop("rating", None),
            "status": kw.pop("status", "active"), "location": kw.pop("location", "closet"), **kw}


def day(low, high=None, **kw):
    return outfits.Context(low_c=low, high_c=low if high is None else high, **kw)


def demo_items():
    return json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))["items"]


def basic_closet():
    return [
        item("tee1", "tee", "white", "casual", "warm", silhouette={"sleeve": "short"}),
        item("shirt1", "shirt", "light_blue", "smart_casual", silhouette={"sleeve": "long"}),
        item("dress1", "shirt", "white", "business", silhouette={"sleeve": "long"}),
        item("sweater1", "sweater", "grey", "smart_casual", "cool"),
        item("hoodie1", "hoodie", "grey", "casual", "cool"),
        item("jacket1", "jacket", "navy", "casual", "cool"),
        item("coat1", "coat", "black", "business", "cool"),
        item("jeans1", "jeans", "blue", "casual"),
        item("trousers1", "trousers", "grey", "business"),
        item("shorts1", "shorts", "tan", "casual", "warm"),
        item("sneakers1", "sneakers", "white", "casual"),
        item("dshoes1", "dress_shoes", "brown", "business"),
    ]


def ids_of(outfit):
    p = outfit["pieces"]
    return [p[k] for k in CORE if p[k]] + list(p["accessories"])


def check_outfit(outfit, items):
    """The structural rules every outfit must keep."""
    by_id = {i["id"]: i for i in items}
    ids = ids_of(outfit)
    assert len(ids) == len(set(ids)), "a piece is used twice"
    cats = [by_id[i]["category"] for i in ids]
    assert sum(c in BOTTOMS for c in cats) == 1
    assert sum(c in SHOES for c in cats) == 1
    p = outfit["pieces"]
    for place in CORE:
        if p[place]:
            assert by_id[p[place]]["category"] in outfits.PLACE_CATEGORIES[place]
    assert 0 <= outfit["score"] <= 100 and isinstance(outfit["score"], int)
    assert outfit["reasons"] and all(isinstance(r, str) and r.endswith(".") for r in outfit["reasons"] + outfit["warnings"])
    for i in ids:
        assert by_id[i].get("status") != "archived" and by_id[i].get("location") != "laundry"


DAYS = [day(-5), day(2, rain=True, occasion="business"), day(8, 14), day(15), day(20, mood="sharp"),
        day(28, occasion="casual"), day(31, mood="relaxed"), day(10, occasion="formal"), day(18, occasion="athletic")]


@pytest.mark.parametrize("ctx", DAYS, ids=lambda c: f"{c.low_c}-{c.high_c}-{c.occasion}-{c.mood}")
def test_every_outfit_has_one_bottom_and_shoes(ctx):
    for items in (basic_closet(), demo_items()):
        result = outfits.suggest(items, ctx, 5)
        assert result["outfits"] and result["missing"] == []
        for o in result["outfits"]:
            check_outfit(o, items)


def test_build_around_item_is_in_every_outfit():
    items = demo_items() + [item("scarf1", "scarf", "grey"), item("belt1", "belt", "brown")]
    for target in items:
        if target.get("location") == "laundry":
            continue
        for ctx in (day(2), day(15), day(28)):
            ctx = outfits.Context(**{**ctx.__dict__, "build_around": target["id"]})
            result = outfits.suggest(items, ctx, 3)
            if target.get("category") == "other":
                # accessories (ties, watches...) have no place in an outfit yet: the owner is told so
                assert not result["outfits"] and "no category an outfit can use" in result["missing"][0]
                continue
            assert result["outfits"], (target["name"], ctx, result["missing"])
            for o in result["outfits"]:
                assert target["id"] in ids_of(o)
                check_outfit(o, items)


def test_build_around_item_out_of_season_is_used_with_a_warning():
    items = basic_closet()
    result = outfits.suggest(items, day(3, build_around="shorts1"), 3)
    assert all(o["pieces"]["bottom"] == "shorts1" for o in result["outfits"])
    assert any("too cold for shorts" in w for w in result["outfits"][0]["warnings"])


def test_cold_day_gets_an_outer_layer_and_a_hot_day_none():
    for items in (basic_closet(), demo_items()):
        for o in outfits.suggest(items, day(2), 5)["outfits"]:
            assert o["pieces"]["outer"]
        for o in outfits.suggest(items, day(28), 5)["outfits"]:
            assert o["pieces"]["outer"] is None and o["pieces"]["mid"] is None


def test_hot_day_prefers_short_sleeves_and_no_cool_season_pieces():
    items = demo_items()
    by_id = {i["id"]: i for i in items}
    for o in outfits.suggest(items, day(28), 5)["outfits"]:
        for i in ids_of(o):
            assert by_id[i]["season"] != "cool"


def test_formal_occasion_gets_no_hoodie_or_sneakers_when_alternatives_exist():
    items = basic_closet()
    by_id = {i["id"]: i for i in items}
    for ctx in (day(10, occasion="formal"), day(10, occasion="business"), day(25, occasion="business", mood="relaxed")):
        result = outfits.suggest(items, ctx, 5)
        assert result["outfits"]
        for o in result["outfits"]:
            cats = {by_id[i]["category"] for i in ids_of(o)}
            assert not cats & {"hoodie", "sneakers", "shorts"}, (ctx, cats)


def test_without_alternatives_a_casual_piece_is_used_with_a_warning():
    items = [item("dress1", "shirt", "white", "business"), item("trousers1", "trousers", "grey", "business"),
             item("sneakers1", "sneakers", "white", "casual")]
    result = outfits.suggest(items, day(20, occasion="business"), 3)
    assert len(result["outfits"]) == 1
    assert any("more casual than a business day" in w for w in result["outfits"][0]["warnings"])


def test_disliked_item_is_never_chosen():
    items = demo_items()
    loved = {"Blue oxford shirt", "Tan chore jacket", "Dark indigo jeans", "White canvas sneakers", "Breton striped tee"}
    for i in items:
        if i["name"] in loved:
            i["rating"] = "dislike"
    disliked = {i["id"] for i in items if i["rating"] == "dislike"}
    for ctx in DAYS:
        for o in outfits.suggest(items, ctx, 5)["outfits"]:
            assert not disliked & set(ids_of(o))


def test_item_worn_yesterday_is_passed_over_for_an_equal_one():
    items = basic_closet() + [item("tee2", "tee", "white", "casual", "warm", silhouette={"sleeve": "short"})]
    for worn, other in (("tee1", "tee2"), ("tee2", "tee1")):
        result = outfits.suggest(items, day(27, worn_days_ago={worn: 1}), 3)
        assert result["outfits"][0]["pieces"]["base"] == other
        assert worn not in ids_of(result["outfits"][0])


def test_nothing_is_worn_over_something_heavier_or_bulkier():
    items = [
        item("tee1", "tee", "white", "casual"),
        item("flannel1", "shirt", "green", "casual", pattern="plaid", weight_class="heavyweight"),
        item("bomber1", "jacket", "navy", "casual", weight_class="lightweight"),
        item("hoodie1", "hoodie", "grey", "casual", silhouette={"fit": "oversized"}),
        item("jeans1", "jeans", "blue", "casual"),
        item("sneakers1", "sneakers", "white", "casual"),
    ]
    for t in (2, 8, 12, 16):
        for o in outfits.suggest(items, day(t), 10)["outfits"]:
            p = o["pieces"]
            assert not (p["mid"] in ("flannel1", "hoodie1") and p["outer"] == "bomber1"), (t, p)
    # an oversized base top does not go under a thinner jacket either
    baggy = [item("tee2", "tee", "white", "casual", weight_class="lightweight", silhouette={"fit": "oversized"}),
             item("bomber1", "jacket", "navy", "casual", weight_class="lightweight"),
             item("jeans1", "jeans", "blue", "casual"), item("sneakers1", "sneakers", "white", "casual")]
    for o in outfits.suggest(baggy, day(12, 14), 10)["outfits"]:
        assert o["pieces"]["outer"] is None
    # and the general rule on the demo closet, with weights the engine works out from category, material and name
    pieces = {i["id"]: outfits._piece(i) for i in demo_items()}
    for ctx in DAYS:
        for o in outfits.suggest(demo_items(), ctx, 5)["outfits"]:
            stack = [pieces[o["pieces"][k]] for k in ("base", "mid", "outer") if o["pieces"][k]]
            for inner, outer in itertools.pairwise(stack):
                if inner is stack[0] and inner.weight <= outfits.BASE_UNDER_ANYTHING_MAX and inner.bulk == inner.weight:
                    continue  # a thin, close-fitting base top goes under anything
                assert inner.weight <= outer.weight and inner.bulk <= outer.bulk


def test_weight_comes_from_the_weight_class_then_material_then_name_then_category():
    assert outfits._piece(item("a", "shirt", weight_class="super_heavy")).weight == 3
    assert outfits._piece(item("a", "shirt", material="linen")).weight == 0
    assert outfits._piece(item("a", "sweater", material="merino wool")).weight == 1
    assert outfits._piece(item("a", "shirt", name="Plaid flannel shirt")).weight == 2
    assert outfits._piece(item("a", "coat", name="Navy coat")).weight == 3
    assert outfits._piece(item("a", "tee", season="warm", name="Tee")).weight == 0


def test_same_inputs_give_the_same_outfits_in_the_same_order():
    items = demo_items()
    for ctx in DAYS:
        first = outfits.suggest(items, ctx, 5)
        shuffled = items[:]
        random.Random(7).shuffle(shuffled)
        assert outfits.suggest(items, ctx, 5) == first
        assert outfits.suggest(shuffled, ctx, 5) == first


def test_empty_closet_and_closet_without_shoes_say_what_is_missing():
    empty = outfits.suggest([], day(15), 3)
    assert empty["outfits"] == [] and "Add some clothes" in empty["missing"][0]
    no_shoes = [i for i in basic_closet() if i["category"] not in SHOES]
    result = outfits.suggest(no_shoes, day(15), 3)
    assert result["outfits"] == [] and result["missing"] == ["There are no shoes in this closet yet."]


def test_items_in_the_laundry_or_archived_are_never_used():
    items = basic_closet()
    for i in items:
        if i["category"] in SHOES:
            i["laundry"] = "laundry" if i["id"] == "sneakers1" else None
            i["status"] = "archived" if i["id"] == "dshoes1" else "active"
    result = outfits.suggest(items, day(15), 3)
    assert result["outfits"] == []
    assert result["missing"] == ["None of your shoes can be worn today: 1 archived and 1 in the laundry."]
    items[-1]["status"] = "active"
    items[0]["location"] = "laundry"
    for o in outfits.suggest(items, day(28), 5)["outfits"]:
        assert "tee1" not in ids_of(o) and "sneakers1" not in ids_of(o)


def test_build_around_an_item_in_the_laundry_explains_why_not():
    items = basic_closet()
    items[0]["laundry"] = "laundry"
    result = outfits.suggest(items, day(20, build_around="tee1"), 3)
    assert result["outfits"] == [] and "in the laundry" in result["missing"][0]
    assert outfits.suggest(items, day(20, build_around="nope"), 3)["missing"] == ["The item to build around is not in this closet."]


def test_at_most_one_strong_colour_unless_tonal_and_one_loud_pattern():
    items = [
        item("red", "tee", "red", "casual"), item("green", "tee", "green", "casual"),
        item("plaid", "shirt", "navy", "casual", pattern="plaid"), item("camo", "shorts", "olive", "casual", "warm", pattern="camo"),
        item("burg", "sweater", "burgundy", "casual"), item("jeans", "jeans", "blue", "casual"),
        item("yellow", "jeans", "yellow", "casual"), item("shoes", "sneakers", "white", "casual"),
    ]
    by_id = {i["id"]: i for i in items}
    for ctx in (day(15), day(26), day(5)):
        for o in outfits.suggest(items, ctx, 10)["outfits"]:
            chosen = [by_id[i] for i in ids_of(o)]
            strong = {i["color"] for i in chosen if i["color"] in ("red", "green", "yellow", "burgundy")}
            # the owner's families: red with green shares none, red with yellow is two brights; earth tones
            # (green, yellow, burgundy) go together
            assert not {"red", "green"} <= strong and not {"red", "yellow"} <= strong, strong
            assert sum(i["pattern"] in ("plaid", "camo") for i in chosen) <= 1
    # red under burgundy is tonal and allowed
    tonal = outfits.suggest(items, day(14, build_around="burg"), 10)["outfits"]
    assert any(o["pieces"]["base"] == "red" for o in tonal)


def test_cold_day_with_only_a_light_jacket_says_so():
    items = [item("tee1", "tee", "white", "casual"), item("jacket1", "jacket", "navy", "casual", weight_class="lightweight"),
             item("jeans1", "jeans", "blue", "casual"), item("sneakers1", "sneakers", "white", "casual")]
    o = outfits.suggest(items, day(2), 1)["outfits"][0]
    assert o["pieces"]["outer"] == "jacket1"
    assert "No coat warm enough for 2°C; the navy jacket jacket1 is the warmest you have." in o["warnings"]


def test_cold_day_uses_the_only_outer_layer_even_when_it_breaks_a_rule():
    base = [item("tee1", "tee", "white", "casual"), item("jeans1", "jeans", "blue", "casual"),
            item("sneakers1", "sneakers", "white", "casual")]
    for outer in (item("jacket1", "jacket", "navy", "casual", "warm"), item("coat1", "coat", "black", "formal")):
        result = outfits.suggest(base + [outer], day(2), 3)["outfits"]
        assert result and all(o["pieces"]["outer"] == outer["id"] for o in result), outer
        assert all(o["warnings"] for o in result)


def test_odd_item_data_never_crashes():
    odd = [item("x1", ["tee"]), item("x2", {"a": 1}), item("x3", "tee", rating=["love"]), item("x4", "tee", color_hex=5),
           item(7, "tee", silhouette="slim", weight_class=["heavy"], formality={"x": 1}), {"category": "tee"}, {"id": "x5"}]
    result = outfits.suggest(basic_closet() + odd, day(15), 3)
    assert result["outfits"]


def test_rain_keeps_sandals_and_canvas_away_when_there_is_a_choice():
    items = basic_closet() + [item("sandals1", "sandals", "brown", "casual", "warm"),
                              item("canvas1", "sneakers", "white", "casual", material="canvas", rating="love"),
                              item("boots1", "boots", "brown", "casual")]
    for o in outfits.suggest(items, day(22, rain=True), 5)["outfits"]:
        assert o["pieces"]["shoes"] not in ("sandals1",)
    first = outfits.suggest(items, day(12, rain=True), 1)["outfits"][0]
    assert first["pieces"]["shoes"] == "boots1"
    assert any("rain" in r for r in first["reasons"] + first["warnings"])


def test_accessories_follow_the_weather_and_the_shoes():
    items = basic_closet() + [item("scarf1", "scarf", "grey"), item("belt_black", "belt", "black"),
                              item("belt_brown", "belt", "brown")]
    cold = outfits.suggest(items, day(2, occasion="business"), 1)["outfits"][0]
    assert cold["pieces"]["shoes"] == "dshoes1" and cold["pieces"]["bottom"] == "trousers1"
    assert cold["pieces"]["accessories"] == ["belt_brown", "scarf1"]
    assert "The brown belt belt_brown matches the brown dress_shoes dshoes1." in cold["reasons"]
    warm = outfits.suggest(items, day(26), 3)["outfits"]
    assert all("scarf1" not in o["pieces"]["accessories"] for o in warm)


@pytest.mark.parametrize("temp", [2, 15, 28])
def test_demo_closet_gives_three_different_outfits(temp):
    result = outfits.suggest(demo_items(), day(temp), 3)
    assert len(result["outfits"]) == 3
    for a, b in itertools.combinations(result["outfits"], 2):
        differ = sum(a["pieces"][k] != b["pieces"][k] for k in CORE)
        assert differ >= 2
    scores = [o["score"] for o in result["outfits"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("body,words", [
    ({}, "low temperature"),
    ({"low_c": 5}, "high temperature"),
    ({"low_c": "cold", "high_c": 5}, "number of degrees"),
    ({"low_c": 10, "high_c": 5}, "above the high"),
    ({"low_c": 5, "high_c": 8, "occasion": "party"}, "not an occasion"),
    ({"low_c": 5, "high_c": 8, "mood": "grumpy"}, "not a mood"),
    ({"low_c": 5, "high_c": 8, "rain": "yes"}, "true or false"),
    ({"low_c": 5, "high_c": 8, "worn_days_ago": {"a": -1}}, "days ago"),
    ({"low_c": 5, "high_c": 8, "leave_out": "a"}, "list of item ids"),
    ({"low_c": 5, "high_c": 8, "build_around": "a", "leave_out": ["a"]}, "also in the list"),
    ({"low_c": 5, "high_c": 8, "count": 0}, "Count"),
    ({"low_c": 5, "high_c": 8, "colour": "red"}, "not part of a day"),
    ([], "as an object"),
])
def test_requests_are_checked_in_plain_words(body, words):
    with pytest.raises(outfits.ContextError, match=words):
        outfits.parse_request(body)


# ---------------------------------------------------------------------- API
DAY = {"low_c": 2, "high_c": 6, "rain": True, "occasion": "business"}


def test_suggest_needs_login(anon):
    assert anon.post("/api/outfits/suggest", json=DAY).status_code == 401


def test_suggest_answers_with_outfits_for_the_open_closet(client):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"]}
    r = client.post("/api/outfits/suggest", json={**DAY, "count": 4, "worn_days_ago": {}, "leave_out": [], "mood": "sharp"})
    assert r.status_code == 200
    body = r.json()
    assert body["missing"] == [] and len(body["outfits"]) == 4
    for o in body["outfits"]:
        assert set(o) == {"pieces", "score", "reasons", "warnings"}
        assert set(o["pieces"]) == {"base", "mid", "outer", "bottom", "shoes", "accessories"}
        assert set(ids_of(o)) <= demo_ids and o["pieces"]["outer"]
    # build around an item of the demo closet
    shirt = next(i["id"] for i in client.get("/api/items", params={"q": "oxford"}).json()["items"])
    r = client.post("/api/outfits/suggest", json={**DAY, "build_around": shirt})
    assert r.status_code == 200 and all(shirt in ids_of(o) for o in r.json()["outfits"])


def test_suggest_validation_errors_are_plain_words(client):
    r = client.post("/api/outfits/suggest", json={"low_c": 10, "high_c": 4})
    assert r.status_code == 422 and r.json()["detail"] == "The low temperature is above the high one."
    r = client.post("/api/outfits/suggest", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    r = client.post("/api/outfits/suggest", json={**DAY, "build_around": "missing"})
    assert r.status_code == 422 and r.json()["detail"] == "The item to build around is not in this closet."


def test_demo_and_main_closets_are_separate(client):
    main_item = upload(client).json()
    for field, value in (("category", "tee"), ("color", "white")):
        client.patch(f"/api/items/{main_item['id']}", json={field: value})
    r = client.post("/api/outfits/suggest", json=DAY).json()
    assert r["outfits"] == [] and any("shoes" in m for m in r["missing"])
    client.post("/api/profile", json={"profile": "demo"})
    r = client.post("/api/outfits/suggest", json=DAY).json()
    assert r["outfits"] and all(main_item["id"] not in ids_of(o) for o in r["outfits"])
    r = client.post("/api/outfits/suggest", json={**DAY, "build_around": main_item["id"]})
    assert r.status_code == 422


def test_colour_families_come_from_the_owners_taxonomy():
    from closet.tagger.taxonomy import COLOR_FAMILIES
    taxonomy = json.loads((Path(__file__).resolve().parents[2] / "docs" / "menswear-taxonomy.json").read_text())
    assert {k: list(v) for k, v in COLOR_FAMILIES.items()} == taxonomy["colors"]["families"]
    # read live from the owner's rules (outfit_rules), so compared as tuples
    assert tuple(outfits.NEUTRALS) == COLOR_FAMILIES["neutral"] and tuple(outfits.BRIGHTS) == COLOR_FAMILIES["bright"]
    def piece(c):
        return outfits._piece(item(c, "tee", c, "casual"))
    # earth tones go together; so do cool colours; two brights compete even in one family; no shared family competes
    assert outfits._go_together(piece("green"), piece("yellow"))
    assert outfits._go_together(piece("light_blue"), piece("purple"))
    assert not outfits._go_together(piece("red"), piece("yellow"))
    assert not outfits._go_together(piece("red"), piece("green"))
    # the reason names the owner's family
    items = [item("rust", "tee", "orange", "casual"), item("forest", "trousers", "green", "casual"),
             item("shoes", "sneakers", "white", "casual")]
    o = outfits.suggest(items, day(22, build_around="rust"), 1)["outfits"][0]
    assert any(r.startswith("Earth tones together") for r in o["reasons"]), o["reasons"]
