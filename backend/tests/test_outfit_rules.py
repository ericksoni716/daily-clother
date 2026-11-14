"""The outfit engine follows the owner's outfit rules in docs/menswear-taxonomy.json (#150)."""
import copy
import json
from contextlib import contextmanager

from closet import outfit_rules, outfits
from closet.tagger import taxonomy

from .test_outfits import check_outfit, day, item

CORE = ("base", "mid", "outer", "bottom", "shoes")


def owner_file():
    return copy.deepcopy(taxonomy.load()["outfit"]), copy.deepcopy(taxonomy.load()["colors"])


@contextmanager
def rules_from(outfit, colors):
    """The engine chooses by a changed copy of the owner's file, then by the real one again."""
    old = outfit_rules.use(outfit_rules.parse(outfit, colors))
    try:
        yield outfits.rules()
    finally:
        outfit_rules.use(old)


def pieces(*items):
    return [outfits._piece(i) for i in items]


def worn(result, items):
    by_id = {i["id"]: i for i in items}
    for o in result["outfits"]:
        check_outfit(o, items)
    return [[by_id[o["pieces"][k]] for k in CORE if o["pieces"][k]] for o in result["outfits"]]


# ====================================================================== reading the file
def test_the_engine_reads_the_owners_file():
    outfit, colors = owner_file()
    r = outfits.rules()
    assert r == outfit_rules.parse(outfit, colors)
    assert [b.high_min for b in r.bands] == sorted((e["high_min"] for e in outfit["temperature_bands_c"]), reverse=True)
    assert set(r.neutrals) == {c for c in colors["families"]["neutral"]}
    assert ("navy", "grey") in r.pairings
    assert r.reach == 1 and r.same_type_never and r.rain_outer_must
    # what the engine cannot express is listed, not silently dropped
    unread = {text for _, text, _ in r.unread}
    assert {"watch", "eyewear", "gloves"} <= unread
    assert any("tuck" in t for t in unread)


def test_a_block_missing_from_the_file_keeps_the_old_rules():
    r = outfit_rules.parse({}, {})
    assert [(b.high_min, b.mid, b.outer) for b in r.bands] == [(24, "no", "no"), (9, "may", "may"), (5, "may", "must"),
                                                              (-99, "may", "must")]
    assert r.neutrals == outfit_rules.FALLBACK_NEUTRALS
    assert r.reach == 1 and not r.rain_outer_must
    assert r.place_categories("base") == ("tee", "shirt", "polo")


def test_what_the_parser_does_not_understand_is_listed():
    outfit, colors = owner_file()
    outfit["color_rules"].append("wear purple on Tuesdays")
    r = outfit_rules.parse(outfit, colors)
    assert ("color_rules", "wear purple on Tuesdays", "not understood") in r.unread


# ====================================================================== temperature bands decide layering
def layered_closet():
    return [
        item("tee", "tee", "white", "casual", rating="love"),
        item("sweater", "sweater", "grey", "casual", rating="love"),
        item("jacket", "jacket", "navy", "casual", weight_class="midweight", rating="love"),
        item("coat", "coat", "navy", "smart_casual", weight_class="heavyweight"),
        item("jeans", "jeans", "navy", "casual"),
        item("shorts", "shorts", "tan", "casual", season="warm"),
        item("sneakers", "sneakers", "white", "casual"),
        item("boots", "boots", "brown", "casual"),
    ]


def test_the_hot_band_from_the_file_means_the_base_only():
    items = layered_closet()
    res = outfits.suggest(items, day(24, 28))
    assert res["outfits"]
    for o in res["outfits"]:
        assert o["pieces"]["mid"] is None and o["pieces"]["outer"] is None


def test_the_cold_band_from_the_file_means_mid_and_outer():
    items = layered_closet()
    res = outfits.suggest(items, day(2, 7))   # the 4 °C band: base + mid + warm outer
    assert res["outfits"]
    for o in res["outfits"]:
        assert o["pieces"]["mid"] and o["pieces"]["outer"]


def test_a_band_changed_in_the_file_changes_the_layering():
    items = layered_closet()
    outfit, colors = owner_file()
    for band in outfit["temperature_bands_c"]:
        if band["high_min"] == 27:
            band["high_min"] = 35
        elif band["high_min"] == 21:
            band["outfit"] = "base + mid; optional light outer"
    with rules_from(outfit, colors):
        res = outfits.suggest(items, day(24, 28))
        assert res["outfits"]
        for o in res["outfits"]:
            assert o["pieces"]["mid"] is not None
    res = outfits.suggest(items, day(24, 28))
    assert all(o["pieces"]["mid"] is None for o in res["outfits"])


def test_the_coldest_band_adds_its_accessories():
    items = layered_closet() + [item("hat", "hat", "grey"), item("scarf", "scarf", "grey")]
    res = outfits.suggest(items, day(-5, 0))
    assert {"hat", "scarf"} <= set(res["outfits"][0]["pieces"]["accessories"])
    outfit, colors = owner_file()
    outfit["temperature_bands_c"][-1]["outfit"] = "warm base + warm mid + insulated outer; boots"
    with rules_from(outfit, colors):
        res = outfits.suggest(items, day(-5, 0))
        assert not {"hat", "scarf"} & set(res["outfits"][0]["pieces"]["accessories"])


# ====================================================================== places
def test_places_come_from_the_file():
    items = layered_closet()
    outfit, colors = owner_file()
    outfit["places"]["mid"] = [w for w in outfit["places"]["mid"] if w != "sweater"]
    with rules_from(outfit, colors):
        res = outfits.suggest(items, day(2, 7))
        assert all(o["pieces"]["mid"] != "sweater" for o in res["outfits"])


# ====================================================================== pattern
def test_two_patterns_of_the_same_type_are_never_suggested_even_when_loved():
    items = [
        item("shirt", "shirt", "navy", "smart_casual", pattern="stripe", rating="love"),
        item("sweater", "sweater", "grey", "smart_casual", pattern="stripe", rating="love"),
        item("sweater2", "sweater", "grey", "smart_casual", rating="dislike"),
        item("trousers", "trousers", "grey", "smart_casual"),
        item("shoes", "sneakers", "white", "smart_casual"),
    ]
    for ctx in (day(8, 14), day(8, 14, occasion="smart_casual")):
        res = outfits.suggest(items, ctx)
        assert res["outfits"]
        for o in res["outfits"]:
            assert not (o["pieces"]["base"] == "shirt" and o["pieces"]["mid"] == "sweater")


def test_the_pattern_rule_names_itself_and_follows_the_file():
    a, b = pieces(item("a", "shirt", "navy", pattern="stripe"), item("b", "sweater", "navy", pattern="stripe"))
    problems = outfits._outfit_problems([a, b], [a, b])
    assert any(isinstance(p, outfits._Hard) and "two stripe patterns" in p for p in problems)
    outfit, colors = owner_file()
    outfit["pattern_rules"] = [r for r in outfit["pattern_rules"] if "same type" not in r]
    with rules_from(outfit, colors):
        assert not any(isinstance(p, outfits._Hard) for p in outfits._outfit_problems([a, b], [a, b]))


def test_two_loud_patterns_are_named():
    a, b = pieces(item("a", "shirt", "navy", pattern="floral"), item("b", "shorts", "tan", pattern="camo"))
    assert any("two loud patterns" in p for p in outfits._outfit_problems([a, b], [a, b]))


# ====================================================================== colour
def test_a_recommended_pairing_scores_higher_and_says_so():
    base, bottom, shoes = pieces(item("t", "tee", "navy"), item("j", "trousers", "grey"), item("s", "sneakers", "navy"))
    with_pair, reasons, _ = outfits._style(base, None, None, bottom, shoes, explain=True)
    assert "Navy and grey go together." in reasons
    outfit, colors = owner_file()
    outfit["color_pairings"] = [p for p in outfit["color_pairings"] if set(p) != {"navy", "grey"}]
    with rules_from(outfit, colors):
        without, reasons, _ = outfits._style(base, None, None, bottom, shoes, explain=True)
        assert "Navy and grey go together." not in reasons
    assert with_pair > without


def test_the_owners_neutrals_decide_what_counts_as_an_accent():
    a, b, c = pieces(item("a", "tee", "light_blue"), item("b", "trousers", "burgundy"), item("c", "sneakers", "white"))
    assert any("two strong colours" in p for p in outfits._outfit_problems([a, b, c], [a, b, c]))
    outfit, colors = owner_file()
    colors["families"]["neutral"] = list(colors["families"]["neutral"]) + ["light_blue"]
    with rules_from(outfit, colors):
        assert not any("two strong colours" in p for p in outfits._outfit_problems([a, b, c], [a, b, c]))


def test_shoe_colour_rules_name_the_rule():
    s, t = pieces(item("s", "dress_shoes", "brown", "business"), item("t", "trousers", "black", "business"))
    problems = outfits._outfit_problems([s, t], [s, t])
    assert any("brown shoes go with everything but black" in p for p in problems)


# ====================================================================== formality
def test_athletic_pieces_never_go_to_business():
    items = [
        item("shirt", "shirt", "white", "business"),
        item("trousers", "trousers", "grey", "business"),
        item("joggers", "trousers", "grey", "athletic", name="joggers", rating="love"),
        item("shoes", "dress_shoes", "black", "business"),
        item("trainers", "sneakers", "white", "athletic", rating="love"),
    ]
    res = outfits.suggest(items, day(18, 22, occasion="business"))
    assert res["outfits"]
    for o in res["outfits"]:
        assert "joggers" not in o["pieces"].values() and "trainers" not in o["pieces"].values()


def test_the_formality_reach_follows_the_file():
    shirt, trousers = pieces(item("s", "shirt", "white", "casual"), item("j", "trousers", "grey", "business"))
    assert outfits._formality_clash([shirt, trousers], None, "business")
    assert outfits._reach() == 1
    outfit, colors = owner_file()
    outfit["formality_rules"] = ["every piece within two levels of the target"]
    with rules_from(outfit, colors):
        assert outfits._reach() == 2


# ====================================================================== rain
def test_in_rain_the_outer_layer_sheds_water_when_the_closet_has_one():
    items = layered_closet() + [item("shell", "jacket", "olive", "casual", name="rain shell")]
    res = outfits.suggest(items, day(12, 15, rain=True))
    assert res["outfits"]
    assert all(o["pieces"]["outer"] == "shell" for o in res["outfits"])
    outfit, colors = owner_file()
    outfit["rain"] = "avoid suede shoes"
    with rules_from(outfit, colors):
        res = outfits.suggest(items, day(12, 15, rain=True))
        assert any(o["pieces"]["outer"] != "shell" for o in res["outfits"])


# ====================================================================== proportions
def test_proportions_score_but_never_exclude():
    items = [
        item("tee", "tee", "white", "casual", silhouette={"fit": "oversized"}),
        item("jeans", "jeans", "navy", "casual", silhouette={"leg": "slim"}),
        item("shoes", "sneakers", "white", "casual"),
    ]
    res = outfits.suggest(items, day(22, 26))
    assert res["outfits"]
    good = pieces(item("t", "tee", "white", silhouette={"fit": "oversized"}), item("w", "jeans", "navy", silhouette={"leg": "wide"}))
    bad = pieces(item("t", "tee", "white", silhouette={"fit": "oversized"}), item("s", "jeans", "navy", silhouette={"leg": "slim"}))
    assert outfits._style(good[0], None, None, good[1], None)[0] > outfits._style(bad[0], None, None, bad[1], None)[0]


def test_the_rules_survive_a_round_trip_through_json():
    outfit, colors = owner_file()
    assert outfit_rules.parse(json.loads(json.dumps(outfit)), colors) == outfits.rules()
