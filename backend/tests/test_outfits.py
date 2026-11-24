import itertools
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from closet import gaps, outfit_rules, outfits, wouldwork
from closet.config import bundle_dir

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


def test_a_piece_worn_lately_is_said_plainly_when_you_asked_for_it():
    tee = item("tee1", "tee", "white", "casual", "warm", name="white tee", silhouette={"sleeve": "short"})
    items = [i for i in basic_closet() if i["id"] != "tee1"] + [tee,
             item("tee2", "tee", "grey", "casual", "warm", name="grey tee", silhouette={"sleeve": "short"})]
    worn = {"tee1": 1}
    said = lambda found: [w for o in found for w in o["warnings"] if w.startswith("You wore the white tee")]  # noqa: E731
    # chosen by Nines with nothing better to offer: it says so, as before
    only = outfits.suggest([i for i in items if i["category"] not in ("tee", "shirt", "polo") or i["id"] == "tee1"],
                           day(27, worn_days_ago=worn), 3)["outfits"]
    assert "You wore the white tee yesterday; nothing else suited as well." in said(only)
    # built around it, or kept from an outfit worn again: you asked for it, so only what is true is said
    for ctx in (day(27, worn_days_ago=worn, build_around="tee1"), day(27, worn_days_ago=worn, keep=("tee1",))):
        found = outfits.suggest(items, ctx, 3)["outfits"]
        assert found and all("tee1" in ids_of(o) for o in found)
        assert said(found) and set(said(found)) == {"You wore the white tee yesterday."}


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


def test_loungewear_and_pieces_waiting_to_be_mended_are_not_suggested():
    # the owner's loungewear and sleepwear is for home; Today's occasions are all for going out
    items = basic_closet() + [
        item("lounge", "trousers", "red", "casual", kind="lounge_pants", pattern="plaid"),
        item("robe", "coat", "grey", "casual", "cool", kind="robe"),
        item("smoking", "jacket", "burgundy", "smart_casual", kind="smoking_jacket"),
    ]
    items[7]["condition"] = "needs_repair"   # jeans1, with its hole
    seen = set()
    for low, high in ((-2, 6), (8, 14), (15, 21), (24, 31)):
        for o in outfits.suggest(items, day(low, high), 5)["outfits"]:
            seen.update(ids_of(o))
    assert not seen & {"lounge", "robe", "jeans1"}
    assert "trousers1" in seen
    # still there when asked for by name
    built = outfits.suggest(items, day(15, 21, build_around="lounge"), 3)
    assert built["outfits"] and all("lounge" in ids_of(o) for o in built["outfits"])
    # with nothing else to wear, it says why
    only = [i for i in basic_closet() if i["category"] not in BOTTOMS] + [item("lounge", "trousers", "red", "casual", kind="lounge_pants")]
    assert outfits.suggest(only, day(15), 3)["missing"] == [
        "None of your trousers, jeans or shorts can be worn today: 1 for wearing at home."]


def test_swim_trunks_are_never_in_an_everyday_outfit():
    # the owner, 22 November: swim trunks are "mostly used for trips", which pack them for swimming; Today never offers them
    items = basic_closet() + [item("trunks", "shorts", "blue", "casual", "warm", kind="swim_trunks")]
    seen = set()
    for low, high in ((15, 21), (20, 27), (24, 31), (28, 35)):
        for occasion in ("casual", "athletic"):
            for o in outfits.suggest(items, day(low, high, occasion=occasion), 5)["outfits"]:
                seen.update(ids_of(o))
    assert "trunks" not in seen and "shorts1" in seen
    # still there when the owner builds an outfit around them
    built = outfits.suggest(items, day(24, 31, build_around="trunks"), 3)
    assert built["outfits"] and all("trunks" in ids_of(o) for o in built["outfits"])
    # with nothing else to wear, it says why
    only = [i for i in basic_closet() if i["category"] not in BOTTOMS] + [item("trunks", "shorts", "blue", kind="swim_trunks")]
    assert outfits.suggest(only, day(24, 31), 3)["missing"] == [
        "None of your trousers, jeans or shorts can be worn today: 1 for swimming."]


SPORT = [item("tennis", "sneakers", "white", "athletic", kind="tennis_shoe"),
         item("golf", "sneakers", "white", "athletic", kind="golf_shoe"),
         item("cleats", "sneakers", "black", "athletic", kind="cleats")]


def test_shoes_for_a_sport_are_never_in_an_everyday_outfit_not_even_an_athletic_one():
    # the owner, 22 November: "shoes I play tennis or golf in"; a day does not say which sport, so Today never offers them
    items = basic_closet() + SPORT + [item("runner", "sneakers", "grey", "athletic", kind="running_shoe")]
    seen = set()
    for low, high in ((2, 8), (15, 21), (24, 31)):
        for occasion in ("casual", "athletic"):
            for o in outfits.suggest(items, day(low, high, occasion=occasion), 5)["outfits"]:
                seen.update(ids_of(o))
    assert not seen & {"tennis", "golf", "cleats"} and "runner" in seen   # running shoes are worn every day
    # still there when the owner builds an outfit around a pair
    for pair in ("tennis", "golf", "cleats"):
        built = outfits.suggest(items, day(15, 21, occasion="athletic", build_around=pair), 3)
        assert built["outfits"] and all(pair in ids_of(o) for o in built["outfits"])
    # with nothing else to wear, it says what each pair is for
    only = [i for i in basic_closet() if i["category"] not in SHOES] + SPORT
    assert outfits.suggest(only, day(15, 21), 3)["missing"] == [
        "None of your shoes can be worn today: 1 for golf, 1 for sport and 1 for tennis."]


def test_in_rain_a_rain_proof_jacket_is_not_forced_onto_a_warm_day():
    # the owner's rule restricts the outer layer to rain-proof ones; one is required only where the day's band asks
    # for an outer layer anyway (the owner, 17 November: a rain jacket is not required on warm days)
    items = basic_closet() + [item("waxed", "jacket", "olive", "casual", "cool", name="olive waxed jacket",
                                   material="waxed cotton", weight_class="heavyweight")]
    warm = outfits.suggest(items, day(19, 26, rain=True), 3)["outfits"]
    assert warm and not all("waxed" in ids_of(o) for o in warm)
    for o in warm:   # any outer layer worn is still the rain-proof one
        assert o["pieces"]["outer"] in (None, "waxed")
    cold = outfits.suggest(items, day(2, 7, rain=True), 3)["outfits"]   # an outer layer is a must: it is the waxed one
    assert cold and all(o["pieces"]["outer"] == "waxed" for o in cold)


def test_build_around_an_item_in_the_laundry_explains_why_not():
    items = basic_closet()
    items[0]["laundry"] = "laundry"
    result = outfits.suggest(items, day(20, build_around="tee1"), 3)
    assert result["outfits"] == [] and "in the laundry" in result["missing"][0]
    assert outfits.suggest(items, day(20, build_around="nope"), 3)["missing"] == ["The item to build around is not in this closet."]


@pytest.mark.parametrize("changes, why", [
    ({}, None),
    ({"condition": "needs_repair"}, None),                    # waiting to be mended: Today builds around it
    ({"kind": "lounge_pants"}, None),                         # never chosen by itself, but built around when asked
    ({"category": "belt"}, None),                             # an accessory goes with the outfit's accessories
    ({"category": None}, "no_category"),                      # not described yet, and no kind chosen
    ({"category": "other"}, "not_in_outfits"),                # a tie or a watch: no outfit has a place for it
    ({"status": "archived"}, "archived"),
    ({"laundry": "laundry"}, "laundry"),
    ({"location": "laundry"}, "laundry"),
    ({"away": "cleaner", "away_until": "2026-11-27"}, "away"),
    ({"away": "lent", "laundry": "laundry"}, "away"),         # said where it is first, as Today says it
])
def test_why_today_cannot_build_around_a_piece(changes, why):
    piece = {**item("p", "trousers", "grey", "casual"), **changes}
    assert outfits.cannot_build_around(piece) == why
    # the same rule as Today itself: a piece it refuses gives no outfit and says why, any other gives outfits around it
    closet = [i for i in basic_closet() if i["category"] != "trousers"] + [item("t2", "trousers", "stone", "casual"), piece]
    result = outfits.suggest(closet, day(15, 21, build_around="p"), 3)
    if why is None:
        assert result["outfits"] and all("p" in ids_of(o) for o in result["outfits"])
    else:
        assert result["outfits"] == [] and result["missing"]


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


def test_today_answers_with_outfits_for_the_open_closet(client):
    """The answer's shape at the API, the day given so the weather is not looked up (moved from the removed
    `POST /api/outfits/suggest`; logging in, plain-word errors and the two closets are checked in test_weather.py)."""
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"]}
    r = client.post("/api/outfits/today", json={**DAY, "count": 4, "leave_out": [], "mood": "sharp"})
    assert r.status_code == 200
    body = r.json()
    assert body["missing"] == [] and len(body["outfits"]) == 4
    for o in body["outfits"]:
        assert set(o) == {"pieces", "score", "reasons", "warnings"}
        assert set(o["pieces"]) == {"base", "mid", "outer", "bottom", "shoes", "accessories"}
        assert set(ids_of(o)) <= demo_ids and o["pieces"]["outer"]
    # build around an item of the demo closet
    shirt = next(i["id"] for i in client.get("/api/items", params={"q": "oxford"}).json()["items"])
    r = client.post("/api/outfits/today", json={**DAY, "build_around": shirt})
    assert r.status_code == 200 and all(shirt in ids_of(o) for o in r.json()["outfits"])


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


# ---- formality between two levels (a penny loafer, smart casual or business)
def test_a_piece_between_two_levels_counts_as_either_and_is_measured_from_its_nearer_end():
    loafers = outfits._piece(item("loafers", "dress_shoes", "burgundy", "smart_casual", formality_also="business"))
    knit = outfits._piece(item("polo", "polo", "navy", "smart_casual", formality_also="casual"))
    oxfords = outfits._piece(item("oxfords", "dress_shoes", "black", "business"))
    assert outfits.span(loafers) == (2, 3) and outfits.span(knit) == (1, 2) and outfits.span(oxfords) == (3, 3)
    for level, steps in ((2, 0), (3, 0), (2.5, 0), (1, 1), (4, 1), (0.5, 1.5)):
        assert outfits.steps_from(loafers, level) == steps, level
    assert outfits.steps_from(oxfords, 2.5) == 0.5   # one level: as far as it ever was
    for occasion, off in (("athletic", 1), ("casual", 0), ("smart_casual", 0), ("business", 0), ("formal", 0)):
        assert outfits._formality_off(loafers, "shoes", occasion) == off, occasion
    assert outfits._formality_off(outfits._piece(item("o", "dress_shoes", "black", "smart_casual")), "shoes", "formal") == -1
    assert outfits.share_a_level(loafers, oxfords) and outfits.share_a_level(loafers, knit)
    assert not outfits.share_a_level(knit, oxfords)
    assert outfits.level_words(loafers) == "smart casual to business" and outfits.level_words(knit) == "casual to smart casual"
    # in the score it loses nothing on either kind of day
    for occasion in ("smart_casual", "business"):
        ctx = day(20, occasion=occasion)
        alone = outfits._piece(item("loafers", "dress_shoes", "burgundy", occasion))
        assert outfits._piece_score(loafers, "shoes", ctx, 20) == outfits._piece_score(alone, "shoes", ctx, 20)


def test_pieces_are_as_far_apart_in_formality_as_their_closest_levels():
    tee, jeans = item("tee", "tee", "white", "casual"), item("jeans", "jeans", "blue", "casual")
    loafers = item("loafers", "dress_shoes", "burgundy", "smart_casual", formality_also="business")
    oxfords = item("oxfords", "dress_shoes", "black", "business")

    def clash(*rows):
        return outfits._formality_clash([outfits._piece(r) for r in rows], None, "casual")

    assert clash(tee, jeans, oxfords) is not None   # business shoes with a tee and jeans, two levels apart
    assert clash(tee, jeans, loafers) is None        # loafers that can be smart casual are one level away
    dinner = item("dinner", "shirt", "white", "formal")
    assert clash(dinner, loafers) is None and clash(dinner, tee, loafers) is not None


def test_an_outfit_with_a_piece_between_two_levels_reads_at_the_days_level():
    loafers = item("loafers", "dress_shoes", "burgundy", "smart_casual", formality_also="business")
    rest = [item("dress1", "shirt", "white", "business", silhouette={"sleeve": "long"}),
            item("trousers1", "trousers", "grey", "business")]
    o = outfits.suggest(rest + [loafers], day(20, occasion="business"), 1)["outfits"][0]
    assert "Everything is business, right for a business day." in o["reasons"]
    # on a formal occasion the loafers count as business, close enough; as smart casual alone they would not be
    formal = outfits.suggest(rest + [loafers], day(20, occasion="formal"), 1)["outfits"][0]
    assert not any("more casual" in w for w in formal["warnings"]), formal["warnings"]
    single = outfits.suggest(rest + [{**loafers, "formality_also": None}], day(20, occasion="formal"), 1)["outfits"][0]
    assert any("loafers" in w and "more casual" in w for w in single["warnings"]), single["warnings"]
    # sporty pieces go only with what can be casual: a polo that can be casual too breaks no hard rule with them
    runners = outfits._piece(item("runners", "sneakers", "grey", "athletic"))
    polo = outfits._piece(item("polo", "polo", "navy", "smart_casual"))
    knit = outfits._piece(item("polo", "polo", "navy", "smart_casual", formality_also="casual"))
    assert any(isinstance(s, outfits._Hard) for s in outfits._outfit_problems([runners, polo], [runners, polo]))
    assert not any(isinstance(s, outfits._Hard) for s in outfits._outfit_problems([runners, knit], [runners, knit]))


# ---------------------------------------------------------------- the logic review of 23 November: sentences that must
# be true of the outfit shown, and outfits a person would wear (findings 13 to 25 of the review)
def small_closet(*more):
    return [item("tee", "tee", "white", "casual", name="White tee"), item("jeans", "jeans", "navy", "casual", name="Dark jeans"),
            item("sneakers", "sneakers", "white", "casual", name="White sneakers"), *more]


def cold_closet():
    return [item("henley", "tee", "cream", "casual", "cool", name="Oatmeal henley", silhouette={"sleeve": "long"}),
            item("fleece", "sweater", "grey", "casual", "cool", name="Grey fleece pullover", weight_class="heavyweight"),
            item("parka", "coat", "tan", "casual", "cool", name="Khaki parka", weight_class="super_heavy"),
            item("jeans", "jeans", "navy", "casual", name="Dark jeans", weight_class="heavyweight"),
            item("boots", "boots", "brown", "casual", name="Brown boots"),
            item("beanie", "hat", "yellow", "casual", "cool", name="Mustard beanie"),
            item("scarf", "scarf", "orange", "casual", "cool", name="Rust wool scarf")]


def test_one_layer_is_not_called_enough_on_a_day_it_is_too_cold_for():
    # with no sweater or coat to offer at 0 to 6°C the card said "A single layer on top is enough" under a warning
    # that it will be cold; nor is a middle layer said to be missing when the closet has none
    o = outfits.suggest(small_closet(), day(0, 6), 1)["outfits"][0]
    assert any("this will be cold" in w for w in o["warnings"])
    assert not any("is enough" in r for r in o["reasons"])
    assert not any("middle layer" in w for w in o["warnings"])
    # on a day it is true, it is still said
    mild = outfits.suggest(small_closet(), day(20, 23), 1)["outfits"][0]
    assert "A single layer on top is enough for 20°C to 23°C." in mild["reasons"]


def test_suede_boots_are_not_said_to_stand_up_to_the_rain():
    boots = item("boots", "boots", "brown", "casual", name="Suede chukka boots")
    closet = [i for i in small_closet(boots, item("jacket", "jacket", "navy", "casual", name="Navy jacket")) if i["id"] != "sneakers"]
    o = outfits.suggest(closet, day(12, 18, rain=True), 1)["outfits"][0]
    assert any("which the rain spoils" in w for w in o["warnings"])
    assert not any("stand up to the rain" in r for r in o["reasons"])
    leather = [{**i, "name": "Brown leather boots"} if i["id"] == "boots" else i for i in closet]
    o = outfits.suggest(leather, day(12, 18, rain=True), 1)["outfits"][0]
    assert "The brown leather boots stand up to the rain." in o["reasons"]


def test_all_neutral_colours_is_not_said_of_an_outfit_with_a_mustard_beanie():
    # the colour sentence was worked out before the hat and scarf were added and never looked at them
    o = outfits.suggest(cold_closet(), day(-8, -2), 1)["outfits"][0]
    assert "beanie" in o["pieces"]["accessories"]
    assert "All neutral colours, so everything goes together." not in o["reasons"]
    assert not any(r.startswith("One colour") for r in o["reasons"]), o["reasons"]


def test_the_scarf_is_worn_on_a_freezing_day_that_is_short_of_warm():
    # the hat was chosen first and a rust scarf "competed" with a mustard beanie, so the warmer of the two stayed home;
    # on a day short of warm both go on, and the card says why their colours were let be (at -8 to -2°C the scarf now
    # makes the outfit warm enough, so the day is taken a little colder to show it still short with both)
    o = outfits.suggest(cold_closet(), day(-12, -6), 1)["outfits"][0]
    assert any("No coat warm enough" in w for w in o["warnings"])
    assert sorted(o["pieces"]["accessories"]) == ["beanie", "scarf"]
    assert any("for the cold" in r for r in o["reasons"]), o["reasons"]
    # on a day warm enough the colour rule still holds: one accent, not two
    warm_enough = cold_closet() + [item("down", "coat", "black", "casual", "cool", name="Black down coat",
                                        weight_class="super_heavy", material="down")]
    for x in warm_enough:
        if x["id"] == "henley":
            x["weight_class"] = "heavyweight"
    o = outfits.suggest(warm_enough, day(2, 3), 1)["outfits"][0]
    assert not {"beanie", "scarf"} <= set(o["pieces"]["accessories"]), (o["pieces"], o["warnings"])


def test_a_freezing_wet_day_gets_the_parka_not_the_thin_mac():
    # snow counts as rain; the mac was the only outer layer the rain rule let in, and the fleece went with the parka
    closet = cold_closet() + [item("mac", "coat", "navy", "smart_casual", name="Navy mac", weight_class="lightweight")]
    o = outfits.suggest(closet, day(-8, -2, rain=True), 1)["outfits"][0]
    assert o["pieces"]["outer"] == "parka" and o["pieces"]["mid"] == "fleece", o["warnings"]
    assert any("umbrella" in w for w in o["warnings"])
    # where the mac is warm enough for the day it is still the only outer layer offered in rain
    mild = outfits.suggest(closet, day(12, 17, rain=True), 3)["outfits"]
    assert mild and all(x["pieces"]["outer"] in ("mac", None) for x in mild)


def test_an_athletic_day_is_not_dressed_in_jeans_and_called_right_for_sport():
    # What's missing holds that jeans and a button-up shirt are not exercise clothes (`life.eligible`); Today agrees
    from closet import life
    closet = [item("tee", "tee", "white", "casual", name="White tee"), item("shirt", "shirt", "light_blue", "casual", name="Blue oxford shirt"),
              item("jeans", "jeans", "navy", "casual", name="Dark jeans"),
              item("joggers", "trousers", "grey", "athletic", name="Grey joggers", kind="joggers", laundry="laundry"),
              item("runners", "sneakers", "grey", "athletic", name="Grey runners", kind="running_shoe")]
    by_id = {i["id"]: i for i in closet}
    assert not life.eligible(by_id["jeans"], "exercise")
    found = outfits.suggest(closet, day(15, 21, occasion="athletic"), 3)["outfits"]
    assert found
    for o in found:
        worn_ = [by_id[i] for i in o["pieces"].values() if isinstance(i, str)]
        makeshift = [i["name"] for i in worn_ if not life.eligible(i, "exercise")]
        assert makeshift and any("not made for sport" in w for w in o["warnings"]), (makeshift, o["warnings"])
        assert not any("right for sport" in r for r in o["reasons"]), o["reasons"]
    assert found[0]["pieces"]["base"] == "tee"   # the tee is for sport; the oxford shirt is not
    # with the joggers clean, the outfit is right for sport and says so
    clean = [{**i, "laundry": "clean"} for i in closet]
    o = outfits.suggest(clean, day(15, 21, occasion="athletic"), 1)["outfits"][0]
    assert o["pieces"]["bottom"] == "joggers" and not any("not made for sport" in w for w in o["warnings"])
    assert any("right for sport" in r for r in o["reasons"])


def test_no_leather_belt_is_added_to_joggers():
    # joggers, sweatpants and lounge pants are filed as trousers, but have a drawstring waist and no belt loops
    closet = small_closet(item("joggers", "trousers", "grey", "athletic", name="Heather grey joggers", kind="joggers"),
                          item("belt", "belt", "brown", name="Brown leather belt"))
    o = outfits.suggest(closet, day(15, 21, build_around="joggers"), 1)["outfits"][0]
    assert o["pieces"]["bottom"] == "joggers" and o["pieces"]["accessories"] == []
    named = small_closet(item("sweats", "trousers", "grey", "casual", name="Grey sweatpants"), item("belt", "belt", "brown"))
    assert outfits.suggest(named, day(15, 21, build_around="sweats"), 1)["outfits"][0]["pieces"]["accessories"] == []
    o = outfits.suggest(closet, day(15, 21), 1)["outfits"][0]   # jeans still get the belt
    assert o["pieces"]["bottom"] == "jeans" and o["pieces"]["accessories"] == ["belt"]


def test_the_warmest_you_have_is_not_said_of_a_jacket_once_the_parka_is_set_aside():
    # the parka was only set aside for today ("Not this piece"), or is waiting to be mended
    closet = cold_closet() + [item("bomber", "jacket", "navy", "casual", "cool", name="Navy bomber jacket")]
    o = outfits.suggest(closet, day(-8, -2, leave_out=("parka",)), 1)["outfits"][0]
    assert o["pieces"]["outer"] == "bomber"
    assert not any("is the warmest you have" in w for w in o["warnings"]), o["warnings"]
    assert "No coat warm enough for -8°C to -2°C; the navy bomber jacket is the warmest you can wear today." in o["warnings"]
    mending = [{**i, "condition": "needs_repair"} if i["id"] == "parka" else i for i in closet]
    o = outfits.suggest(mending, day(-8, -2), 1)["outfits"][0]
    assert any("is the warmest you can wear today" in w for w in o["warnings"]), o["warnings"]


def test_plural_pieces_are_spoken_of_as_plural():
    # "The dark jeans is more casual than a formal occasion calls for."
    closet = [item("shirt", "shirt", "white", "business", name="White dress shirt"), item("jeans", "jeans", "navy", "casual", name="Dark jeans"),
              item("shoes", "dress_shoes", "black", "business", name="Black oxfords")]
    o = outfits.suggest(closet, day(15, 21, occasion="formal"), 1)["outfits"][0]
    said = " ".join(o["warnings"])
    assert "The dark jeans are more casual than a formal occasion calls for." in said
    assert "jeans is " not in said
    tee = outfits._piece(item("tee", "tee", "white", "casual", name="White tee"))
    oxfords = outfits._piece(closet[2])
    assert outfits._outfit_problems([tee, oxfords], [tee, oxfords]) == [
        "The black oxfords are a lot dressier than the white tee."]
    laundry = small_closet(item("joggers", "trousers", "grey", "athletic", name="Heather grey joggers", laundry="laundry"))
    assert outfits.suggest(laundry, day(15, 21, build_around="joggers"))["missing"] == [
        "The heather grey joggers are in the laundry, so there is nothing to build around them."]


def test_the_kinds_without_belt_loops_are_the_taxonomys_elastic_waists():
    garments = json.loads((Path(__file__).parents[2] / "docs" / "menswear-taxonomy.json").read_text(encoding="utf-8"))["garments"]
    elastic = {k for k, g in garments.items() if g.get("app_category", "trousers") in ("trousers", "shorts")
               and any(v in ("elastic_drawcord_waist", "elastic_waist", "elastic_drawcord")
                       for vs in g.values() if isinstance(vs, list) for v in vs)}
    assert elastic - set(outfits.LOUNGE_KINDS) <= outfits.NO_BELT_KINDS, elastic - outfits.NO_BELT_KINDS


# ---------------------------------------------------------------- decided, then changed on 23 November
def wide_closet():
    return small_closet(item("shorts", "shorts", "tan", "casual", "warm", name="Tan shorts"),
                        item("overshirt", "jacket", "olive", "casual", "cool", name="Olive overshirt", weight_class="midweight"),
                        item("parka", "coat", "tan", "casual", "cool", name="Khaki parka", weight_class="super_heavy"))


def test_a_wide_day_carries_one_light_layer_for_the_cool_morning():
    # out from 5°C to 28°C: the band taken from the high alone forbade every layer while the card said to take one
    found = outfits.suggest(wide_closet(), day(5, 28), 3)["outfits"]
    layers = [[o["pieces"][k] for k in ("mid", "outer") if o["pieces"][k]] for o in found]
    assert layers[0] == ["overshirt"]
    for o, layer in zip(found, layers, strict=True):
        assert layer in (["overshirt"], [])   # never the parka, never two layers
        assert not any("take another layer" in w for w in o["warnings"]), o["warnings"]
    assert "The olive overshirt is for the cool morning; take it off as it warms up to 28°C." in found[0]["reasons"]
    # the edges: the owner's bands ask for a light layer under a high of 21°C ("base + light mid or light outer"), and
    # allow none from 27°C ("base only")
    assert outfits.wide(day(20.5, 28)) and not outfits.wide(day(21, 28)) and not outfits.wide(day(5, 26.5))
    assert all(not o["pieces"]["mid"] and not o["pieces"]["outer"] for o in outfits.suggest(wide_closet(), day(21, 28), 3)["outfits"])
    # a heavy layer is still not offered
    heavy = [i for i in wide_closet() if i["id"] != "overshirt"]
    bare = outfits.suggest(heavy, day(5, 28), 3)["outfits"]
    assert all(not o["pieces"]["mid"] and not o["pieces"]["outer"] for o in bare)
    assert ("This is light for the cool morning at 5°C, but anything warmer would be too hot once it reaches 28°C."
            in bare[0]["warnings"])


def test_a_hot_day_says_when_the_jeans_are_too_warm_and_puts_lighter_bottoms_first():
    loved = small_closet(item("chinos", "trousers", "tan", "casual", name="Tan linen trousers", material="linen"))
    loved[1].update(weight_class="heavyweight", rating="love")   # the dark jeans
    first = outfits.suggest(loved, day(24, 31), 3)["outfits"]
    assert first[0]["pieces"]["bottom"] == "chinos"
    jeans = next(o for o in first if o["pieces"]["bottom"] == "jeans")
    assert "The dark jeans are heavy for a high of 31°C; nothing lighter went with the rest." in jeans["warnings"]
    # under 30°C they are not said to be too warm
    cooler = outfits.suggest(loved, day(22, 29), 3)["outfits"]
    assert not any("heavy for a high" in w for o in cooler for w in o["warnings"])


# ====================================================================== remembered answers (23 November)
# The engine remembers its rule-only answers by value (`outfits._memo`). These tests hold the remembered answers equal
# to the plain ones over a wide sample, show that swapping the rules is followed at once, and count the work done so
# the repetition cannot come back unseen. They compare with the plain functions, not with recorded answers, so they
# stay true when the rules change.
def candidate_items():
    """Pieces across every category, formality, season, colour and pattern, with shapes, spans and materials."""
    rng = random.Random(1123)
    out = []
    for n, category in enumerate(outfits.CATEGORY_FORMALITY):
        for k in range(3):
            formality = rng.choice([None, *outfits.FORMALITY])
            also = None
            if formality and rng.random() < 0.3:
                i = outfits.FORMALITY.index(formality)
                also = outfits.FORMALITY[i + 1] if i + 1 < len(outfits.FORMALITY) else outfits.FORMALITY[i - 1]
            sil = {key: rng.choice(values) for key, values in outfits.vocab.SILHOUETTE.items() if rng.random() < 0.3}
            hex_value = rng.choice([None, "#1f2a44", "#c8102e", "#f5f5dc", "#556b2f", "#203050"])
            out.append(item(f"c{n:02d}{k}", category, rng.choice(outfits.vocab.COLOR), formality,
                            rng.choice(outfits.vocab.SEASON), rng.choice(outfits.vocab.PATTERN), silhouette=sil,
                            formality_also=also, color_hex=hex_value,
                            material=rng.choice([None, "linen", "suede", "wool flannel", "waxed cotton", "silk", "denim"]),
                            weight_class=rng.choice([None, *outfits.WEIGHT_CLASSES]),
                            rating=rng.choice([None, None, "love", "meh"])))
    return out


def sample_pieces():
    items = demo_items() + basic_closet() + candidate_items()
    return [p for p in (outfits._piece(i) for i in items) if p is not None]


def copy_of(p):
    """An equal piece that is not the same object, as the next day's `_piece` used to give."""
    return outfits.dataclasses.replace(p)


def test_pieces_compare_and_hash_by_value_and_a_colourless_copy_keeps_the_rest():
    for p in sample_pieces()[:40]:
        q = copy_of(p)
        assert q == p and hash(q) == hash(p) and q is not p
        assert outfits._one_of(q) is outfits._one_of(p)
        plain = outfits._neutral_copy(p)
        assert (plain.color, plain.hue, plain.rgb) == (None, None, None)
        assert {k: v for k, v in vars(plain).items() if k not in ("color", "hue", "rgb", "_hash")} == \
            {k: v for k, v in vars(p).items() if k not in ("color", "hue", "rgb", "_hash")}
    a = sample_pieces()[0]
    assert outfits.dataclasses.replace(a, label=a.label + " x") != a


def test_remembered_rule_answers_equal_the_plain_ones_over_a_wide_sample():
    outfits.forget()
    pieces = sample_pieces()
    by_place = {pl: [p for p in pieces if outfits._fits(p, pl)] for pl in outfits.PLACES}
    rng = random.Random(23)
    occasions = [None, *outfits.FORMALITY]
    for _ in range(2500):
        chosen = rng.sample(pieces, rng.randint(1, 6))
        outer = rng.choice([None, None, *[p for p in chosen if p.category in ("jacket", "coat")]])
        clothes = [p for p in chosen if p is not outer] if rng.random() < 0.8 else []
        occasion = rng.choice(occasions)
        want = outfits._outfit_problems_plain(chosen, clothes, outer, occasion)
        for _ in range(2):   # worked out, then remembered; and asked with equal pieces that are other objects
            assert outfits._outfit_problems(chosen, clothes, outer, occasion) == want
            got = outfits._outfit_problems([copy_of(p) for p in chosen], [copy_of(p) for p in clothes],
                                           copy_of(outer) if outer else None, occasion)
            assert got == want and [type(x) for x in got] == [type(x) for x in want]   # a _Hard stays a _Hard
        five = [rng.choice([None, *by_place[pl]]) if pl in ("mid", "outer") else rng.choice(by_place[pl])
                for pl in outfits.PLACES]
        for explain in (False, True):
            want = outfits._style_plain(*five, explain=explain)
            assert outfits._style(*five, explain=explain) == want
            assert outfits._style(*[copy_of(p) if p else None for p in five], explain=explain) == want


def test_a_changed_answer_cannot_change_what_is_remembered():
    red, blue = outfits._piece(item("r", "tee", "red")), outfits._piece(item("b", "trousers", "blue"))
    first = outfits._outfit_problems([red, blue], [red, blue])
    first.append("changed by the caller")
    assert outfits._outfit_problems([red, blue], [red, blue]) == outfits._outfit_problems_plain([red, blue], [red, blue])


def suggest_plain(monkeypatch, *args):
    """`suggest` remembering nothing: every table is a new, empty one."""
    with monkeypatch.context() as m:
        m.setattr(outfits, "_memo", lambda name, limit=None: {})
        return outfits.suggest(*args)


GRID = [day(lo, hi, rain=rain, occasion=occ) for lo, hi in ((0, 6), (8, 14), (15, 21), (25, 31))
        for rain in (False, True) for occ in outfits.FORMALITY]   # the gap analysis's 40 kinds of day


def test_suggest_gives_the_same_outfits_remembering_as_without(monkeypatch):
    outfits.forget()
    extra = candidate_items()
    for n, cand in enumerate(extra[::3]):
        closet = basic_closet() + [cand]
        for ctx in GRID[n % 5::12] + [DAYS[n % len(DAYS)]]:
            for around in (None, cand["id"]):
                c = outfits.Context(**{**vars(ctx), "build_around": around})
                assert outfits.suggest(closet, c, 3) == suggest_plain(monkeypatch, closet, c, 3), (cand, c)
    worn = outfits.Context(**{**vars(DAYS[2]), "worn_days_ago": {"tee1": 0, "jeans1": 2}, "mood": "sharp"})
    for ctx in (DAYS[1], DAYS[3], worn):
        assert outfits.suggest(demo_items(), ctx, 10) == suggest_plain(monkeypatch, demo_items(), ctx, 10)


def pick_plain(found, count):
    """`_pick` as it was written before it kept each outfit's most shared places (23 November)."""
    found = sorted(found, key=lambda o: (-o.raw, o.ids()))
    chosen = []
    for need in (outfits.MIN_PIECES_DIFFERENT, 1):
        while len(chosen) < count:
            best, best_key = None, None
            for o in found:
                if any(o is c or outfits._different(o, c) < need for c in chosen):
                    continue
                key = o.raw - outfits.OVERLAP_PENALTY * max((outfits._shared(o, c) for c in chosen), default=0)
                if best_key is None or key > best_key:
                    best, best_key = o, key
            if best is None:
                break
            chosen.append(best)
    return chosen


def test_picking_the_outfits_that_differ_is_unchanged():
    pool = [p for p in (outfits._piece(i) for i in basic_closet() + candidate_items()[:30]) if p is not None]
    for ctx in GRID[::3]:
        t = outfits._design_temp(ctx)
        for strict in (True, False):
            found = outfits._search(pool, ctx, t, None, strict)
            for count in (1, 3, 10):
                assert outfits._pick(found, count) == pick_plain(found, count)
    for o in found:   # the ids `_search` gives an outfit are the ones its places hold
        assert o.ids() == tuple(x.piece.id if x else "" for x in (o.base, o.mid, o.outer, o.bottom, o.shoes))


def test_swapping_the_rules_is_followed_at_once_with_nothing_stale_served():
    red, blue = outfits._piece(item("r", "tee", "red")), outfits._piece(item("b", "trousers", "blue"))
    navy, grey = outfits._piece(item("n", "tee", "navy")), outfits._piece(item("g", "trousers", "grey"))
    closet = [item("r", "tee", "red"), item("b", "trousers", "blue"), item("s", "sneakers", "white")]
    competing = outfits._outfit_problems([red, blue], [red, blue])
    paired = outfits._style(navy, None, None, grey, None)
    worn = outfits.suggest(closet, day(18), 1)["outfits"][0]
    assert competing and any("compete" in w for w in worn["warnings"]) and paired[0] > 0
    old = outfit_rules.use(outfits.dataclasses.replace(outfits.rules(), max_accents=2, max_brights=None, pairings=()))
    try:
        assert outfits._outfit_problems([red, blue], [red, blue]) == []
        assert outfits._style(navy, None, None, grey, None)[0] == paired[0] - outfits.PAIRING_BONUS
        assert not any("compete" in w for w in outfits.suggest(closet, day(18), 1)["outfits"][0]["warnings"])
        outfit_rules.RULES = outfits.dataclasses.replace(outfits.rules())   # set by hand: followed as well
        assert outfits._outfit_problems([red, blue], [red, blue]) == []
    finally:
        outfit_rules.use(old)
    assert outfits._outfit_problems([red, blue], [red, blue]) == competing
    assert outfits.suggest(closet, day(18), 1)["outfits"][0] == worn


def test_the_tables_stay_bounded_and_answer_the_same_when_emptied(monkeypatch):
    outfits.forget()
    monkeypatch.setattr(outfits, "MEMO_MAX", 50)
    monkeypatch.setattr(outfits, "PIECES_MAX", 10)
    closet = basic_closet() + candidate_items()[:6]
    for ctx in GRID[::8]:
        assert outfits.suggest(closet, ctx, 3) == suggest_plain(monkeypatch, closet, ctx, 3)
        tables = outfits._memo_state[1]
        assert all(len(t) <= 50 for t in tables.values()) and len(tables["pieces"]) <= 10


def test_threads_asking_at_once_get_the_answers_one_thread_gets(monkeypatch):
    closets = [basic_closet() + candidate_items()[k::9] for k in range(4)]
    asks = [(c, ctx) for c in closets for ctx in GRID[1::7]]
    want = [suggest_plain(monkeypatch, c, ctx, 3) for c, ctx in asks]
    outfits.forget()
    with ThreadPoolExecutor(4) as pool:
        got = list(pool.map(lambda a: outfits.suggest(a[0], a[1], 3), asks * 2))
    assert got == want * 2


def counting_closet():
    return basic_closet() + [
        item("tee2", "tee", "grey", "casual"), item("polo1", "polo", "white", "smart_casual"),
        item("chinos1", "trousers", "tan", "smart_casual"), item("boots1", "boots", "brown", "smart_casual"),
        item("jacket2", "jacket", "olive", "smart_casual", material="waxed cotton"),
        item("sweater2", "sweater", "navy", "smart_casual"), item("jeans2", "jeans", "black", "casual"),
        item("scarf1", "scarf", "grey"), item("belt1", "belt", "brown")]


def test_the_closets_own_grid_is_not_worked_out_again_for_each_piece_checked():
    """Counted, not timed: the engine is pure and the closet fixed, so these counts are the same on every machine.

    Each check runs the gap analysis again with the piece in the closet: 40 kinds of day, most of whose outfits are
    the closet's own, which the closet's analysis has already judged. Without the remembered answers each check worked
    out more than the closet's whole analysis (about 13,000 rule answers here against 3,000); with them, a check works
    out only what holds the new piece, under half as much. A second, equal round works out nothing."""
    outfits.forget()
    outfits.MEMO_WORKED_OUT.clear()
    closet = counting_closet()
    before = gaps.find_gaps(closet, [], {"max_gaps": wouldwork.ALL_GAPS})
    grid = sum(outfits.MEMO_WORKED_OUT.values())
    assert grid == sum(len(t) for name, t in outfits._memo_state[1].items() if name != "pieces")   # none twice
    pieces = [{"category": "shirt", "color": "white"}, {"category": "coat", "color": "tan", "rain_proof": True}]
    answers = []
    for piece in pieces:
        start = sum(outfits.MEMO_WORKED_OUT.values())
        answers.append(wouldwork.check(closet, [], piece, before))
        assert sum(outfits.MEMO_WORKED_OUT.values()) - start < grid / 2, piece
    start = sum(outfits.MEMO_WORKED_OUT.values())
    assert gaps.find_gaps(closet, [], {"max_gaps": wouldwork.ALL_GAPS}) == before
    assert [wouldwork.check(closet, [], piece, before) for piece in pieces] == answers
    assert sum(outfits.MEMO_WORKED_OUT.values()) == start
