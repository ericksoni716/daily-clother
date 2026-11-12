import copy
import json
from itertools import combinations
from pathlib import Path

import pytest

from closet import outfits


def item(id, category, **fields):
    return {"id": id, "name": id, "category": category, "color": "navy", "pattern": "solid",
            "formality": "casual", "season": "all", "status": "active", "silhouette": {}, **fields}


def context(temp=15, **fields):
    return {"low_c": temp, "high_c": temp, "rain": False, "occasion": "casual", "mood": "usual", **fields}


def wardrobe():
    return [item("top-a", "shirt"), item("top-b", "shirt"), item("pants-a", "jeans"),
            item("pants-b", "trousers"), item("shoes-a", "sneakers"), item("shoes-b", "boots"),
            item("knit", "sweater"), item("coat", "coat")]


def ids(outfit):
    return {v for k, v in outfit["places"].items() if k != "accessories" and v} | set(outfit["places"]["accessories"])


def test_places_determinism_and_no_mutation():
    clothes, day = wardrobe(), context()
    before = copy.deepcopy((clothes, day))
    result = outfits.suggest(clothes, day, 3)
    assert result == outfits.suggest(list(reversed(clothes)), day, 3)
    assert (clothes, day) == before
    assert len(result["outfits"]) == 3
    scores = [o["score"] for o in result["outfits"]]
    assert scores == sorted(scores, reverse=True)
    for o in result["outfits"]:
        assert 0 <= o["score"] <= 100
        assert o["reasons"]
        assert o["places"]["base_top"] and o["places"]["bottom"] and o["places"]["shoes"]
        chosen = [i for i in clothes if i["id"] in ids(o)]
        assert sum(i["category"] in {"jeans", "trousers", "shorts"} for i in chosen) == 1
        assert sum(i["category"] in {"sneakers", "boots", "dress_shoes", "sandals"} for i in chosen) == 1
    for a, b in combinations(result["outfits"], 2):
        assert max(len(ids(a) - ids(b)), len(ids(b) - ids(a))) >= 2


@pytest.mark.parametrize("category", ["shirt", "sweater", "coat", "trousers", "boots", "scarf"])
def test_build_around_every_place(category):
    clothes = wardrobe() + [item("anchor", category)]
    result = outfits.suggest(clothes, context(2, build_around="anchor"), 3)
    assert result["outfits"]
    assert all("anchor" in ids(o) for o in result["outfits"])


@pytest.mark.parametrize("fields", [
    {"rating": "dislike"}, {"status": "archived"}, {"location": "laundry"},
    {"laundry_state": "laundry"}, {"laundry_state": "dirty"}, {"laundry_state": "washing"},
])
def test_unavailable_items_never_used_even_as_anchor(fields):
    clothes = wardrobe() + [item("bad", "shirt", **fields)]
    assert all("bad" not in ids(o) for o in outfits.suggest(clothes, context(), 10)["outfits"])
    result = outfits.suggest(clothes, context(build_around="bad"), 3)
    assert result["outfits"] == []
    assert result["messages"]


def test_exclusions_and_unknown_anchor():
    result = outfits.suggest(wardrobe(), context(exclude=["top-a"]), 3)
    assert all("top-a" not in ids(o) for o in result["outfits"])
    for anchor in ("top-a", "not-here"):
        result = outfits.suggest(wardrobe(), context(build_around=anchor, exclude=["top-a"]), 3)
        assert not result["outfits"] and result["messages"]


def test_weather_layers_and_missing_warmth():
    cold = outfits.suggest(wardrobe(), context(2), 3)["outfits"]
    assert all(o["places"]["outer_layer"] == "coat" for o in cold)
    hot = outfits.suggest(wardrobe(), context(28), 3)["outfits"]
    assert all(o["places"]["outer_layer"] is None and o["places"]["mid_layer"] is None for o in hot)
    thin = [i for i in wardrobe() if i["id"] != "coat"] + [item("shell", "jacket", weight_class="lightweight")]
    result = outfits.suggest(thin, context(2), 1)
    assert result["outfits"][0]["places"]["outer_layer"] == "shell"
    assert any("warm" in r.lower() for r in result["outfits"][0]["reasons"])


def test_cold_layers_hot_build_around_and_temperature_swing():
    cold = outfits.suggest(wardrobe(), context(2), 3)["outfits"]
    assert all(o["places"]["mid_layer"] for o in cold)
    hot = outfits.suggest(wardrobe(), context(28, build_around="coat"), 3)
    assert not hot["outfits"] and hot["messages"]
    swing = outfits.suggest(wardrobe(), context(2, high_c=28), 1)["outfits"][0]
    assert swing["places"]["outer_layer"]
    assert any("28°C" in r and "remove" in r for r in swing["reasons"])


def test_explicit_weight_overrides_material():
    clothes = [item("shirt", "shirt", material="heavy flannel", weight_class="lightweight"),
               item("jacket", "jacket", material="linen", weight_class="heavyweight"),
               item("pants", "trousers"), item("shoes", "boots")]
    assert outfits.suggest(clothes, context(2), 1)["outfits"][0]["places"]["outer_layer"] == "jacket"


def test_mood_changes_target_without_changing_occasion_rules():
    clothes = [item("top", "shirt", formality="smart_casual"),
               item("pants", "trousers", formality="smart_casual"),
               item("shoes", "boots", formality="smart_casual")]
    scores = [outfits.suggest(clothes, context(28, mood=mood), 1)["outfits"][0]["score"]
              for mood in ("relaxed", "usual", "sharp")]
    assert scores[0] < scores[1] < scores[2]


def test_insufficient_variety_is_explained_without_duplicates():
    clothes = [item("a", "tee"), item("b", "tee"), item("pants", "shorts"), item("shoes", "sneakers")]
    result = outfits.suggest(clothes, context(28), 3)
    assert len(result["outfits"]) == 2
    assert result["messages"]
    assert ids(result["outfits"][0]) != ids(result["outfits"][1])


def test_unknown_tags_and_hex_only_colours():
    clothes = [item("top", "tee", color=None, color_hex="#ff0000", pattern=None, season=None, formality=None),
               item("clash", "trousers", color=None, color_hex="#00ff00"),
               item("neutral", "trousers", color=None, color_hex="#808080"),
               item("shoes", "sneakers")]
    result = outfits.suggest(clothes, context(28), 3)
    assert result["outfits"]
    assert all("clash" not in ids(o) for o in result["outfits"])
    assert any("missing" in r for r in result["outfits"][0]["reasons"])


def test_no_compatible_combination_is_not_an_error():
    clothes = [item("top", "tee", pattern="graphic"), item("pants", "shorts", pattern="camo"),
               item("shoes", "sneakers")]
    result = outfits.suggest(clothes, context(28), 3)
    assert result["outfits"] == []
    assert "pattern" in " ".join(result["messages"])


def test_formal_alternatives_and_internal_formality():
    clothes = wardrobe() + [item("dress-shirt", "shirt", formality="formal"),
                            item("dress-pants", "trousers", formality="formal"),
                            item("dress-shoes", "dress_shoes", formality="formal"),
                            item("hoodie", "hoodie")]
    result = outfits.suggest(clothes, context(28, occasion="formal"), 3)
    assert result["outfits"]
    for o in result["outfits"]:
        assert ids(o) == {"dress-shirt", "dress-pants", "dress-shoes"}


def test_preference_and_recent_wear():
    clothes = [item("a", "shirt", rating="love"), item("b", "shirt", rating="love"),
               item("c", "shirt"), item("pants", "trousers"), item("shoes", "boots")]
    assert outfits.suggest(clothes, context(28), 1)["outfits"][0]["places"]["base_top"] == "a"
    day = context(28, days_since_worn={"a": 1})
    assert outfits.suggest(clothes, day, 1)["outfits"][0]["places"]["base_top"] == "b"


@pytest.mark.parametrize("inner,outer", [
    ({"weight_class": "heavyweight"}, {"weight_class": "lightweight"}),
    ({"silhouette": {"fit": "oversized"}}, {"silhouette": {"fit": "slim"}}),
    ({"material": "heavy wool flannel"}, {"material": "linen"}),
])
def test_no_heavier_or_bulkier_underlayer(inner, outer):
    clothes = [item("shirt", "shirt", **inner), item("jacket", "jacket", **outer),
               item("pants", "trousers"), item("shoes", "boots")]
    result = outfits.suggest(clothes, context(2), 3)
    assert result["outfits"]
    assert all(o["places"]["outer_layer"] is None for o in result["outfits"])
    assert any("layer" in r.lower() for r in result["outfits"][0]["reasons"])


def test_colours_patterns_and_tonal_exception():
    clothes = [item("red", "shirt", color="red", pattern="graphic"),
               item("green", "trousers", color="green", pattern="plaid"),
               item("tonal", "trousers", color="burgundy"), item("plain", "trousers"),
               item("shoes", "boots")]
    result = outfits.suggest(clothes, context(28, build_around="red"), 10)
    assert result["outfits"]
    assert all("green" not in ids(o) for o in result["outfits"])
    assert any("tonal" in ids(o) for o in result["outfits"])


def test_season_and_rain():
    clothes = [item("warm", "shirt", season="warm"), item("cool", "shirt", season="cool"),
               item("pants", "trousers"), item("suede", "boots", material="suede"),
               item("leather", "boots", material="leather"),
               item("raincoat", "coat", material="waxed cotton")]
    cold = outfits.suggest(clothes, context(2, rain=True), 1)["outfits"][0]
    assert cold["places"]["base_top"] == "cool"
    assert cold["places"]["shoes"] == "leather"
    assert any("rain" in r.lower() for r in cold["reasons"])
    hot = outfits.suggest(clothes, context(28), 1)["outfits"][0]
    assert hot["places"]["base_top"] == "warm"


@pytest.mark.parametrize("clothes,missing", [
    ([], "top"), ([item("top", "tee"), item("pants", "shorts")], "shoes"),
    ([item("top", "tee", laundry_state="dirty")], "clean"),
])
def test_incomplete_closets(clothes, missing):
    result = outfits.suggest(clothes, context(), 3)
    assert result["outfits"] == []
    assert missing in " ".join(result["messages"]).lower()


@pytest.mark.parametrize("temp,occasion,rain", [(2, "business", True), (15, "casual", False), (28, "casual", False)])
def test_demo_three_distinct_outfits(temp, occasion, rain):
    clothes = json.loads((Path(__file__).parents[1] / "closet/demo_data/items.json").read_text())["items"]
    result = outfits.suggest(clothes, context(temp, occasion=occasion, rain=rain), 3)
    assert len(result["outfits"]) == 3
    for a, b in combinations(result["outfits"], 2):
        assert max(len(ids(a) - ids(b)), len(ids(b) - ids(a))) >= 2
