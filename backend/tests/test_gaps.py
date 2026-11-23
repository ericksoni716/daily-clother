import json
import random
import re
from datetime import date, timedelta

from closet import gaps, life
from closet.config import bundle_dir

from .conftest import upload


def item(id, category, color="navy", formality=None, season="all", pattern="solid", **kw):
    return {"id": id, "name": kw.pop("name", f"{color} {category}".replace("_", " ")), "category": category, "color": color,
            "color_hex": None, "pattern": pattern, "formality": formality, "season": season,
            "silhouette": kw.pop("silhouette", {}), "material": kw.pop("material", None), "rating": kw.pop("rating", None),
            "status": kw.pop("status", "active"), "location": kw.pop("location", "closet"), **kw}


def full_closet():
    """A closet with every basic, two of each smart thing and a rain coat."""
    return [
        item("tee_white", "tee", "white", "casual", name="White tee"),
        item("tee_grey", "tee", "grey", "casual", name="Grey tee"),
        item("tee_navy", "tee", "navy", "casual", "warm", name="Navy linen tee", material="linen"),
        item("polo_navy", "polo", "navy", "smart_casual", "warm", name="Navy polo"),
        item("ocbd_white", "shirt", "white", "smart_casual", name="White oxford shirt"),
        item("ocbd_blue", "shirt", "light_blue", "smart_casual", name="Blue oxford shirt"),
        item("dress_white", "shirt", "white", "business", name="White dress shirt", material="poplin"),
        item("dress_blue", "shirt", "light_blue", "business", name="Blue dress shirt", material="poplin"),
        item("sweater_navy", "sweater", "navy", "smart_casual", "cool", name="Navy merino sweater"),
        item("sweater_grey", "sweater", "grey", "business", "cool", name="Grey merino sweater"),
        item("jacket_navy", "jacket", "navy", "smart_casual", name="Navy blazer", material="wool"),
        item("coat_grey", "coat", "grey", "business", "cool", name="Grey overcoat"),
        item("coat_navy", "coat", "navy", "smart_casual", "cool", name="Navy peacoat"),
        item("trench", "coat", "tan", "smart_casual", name="Tan trench coat"),
        item("jeans_dark", "jeans", "navy", "casual", name="Dark jeans"),
        item("jeans_black", "jeans", "black", "casual", name="Black jeans"),
        item("chinos_tan", "trousers", "tan", "smart_casual", name="Tan chinos"),
        item("chinos_navy", "trousers", "navy", "smart_casual", name="Navy chinos"),
        item("trousers_grey", "trousers", "grey", "business", name="Grey trousers", material="tropical wool"),
        item("trousers_navy", "trousers", "navy", "business", name="Navy trousers"),
        item("shorts_tan", "shorts", "tan", "casual", "warm", name="Tan shorts"),
        item("shorts_navy", "shorts", "navy", "casual", "warm", name="Navy shorts"),
        item("sneakers_white", "sneakers", "white", "casual", name="White leather sneakers"),
        item("sneakers_grey", "sneakers", "grey", "casual", name="Grey sneakers"),
        item("boots_brown", "boots", "brown", "smart_casual", name="Brown boots"),
        item("boots_black", "boots", "black", "smart_casual", name="Black boots"),
        item("shoes_brown", "dress_shoes", "brown", "business", name="Brown derbies"),
        item("shoes_black", "dress_shoes", "black", "business", name="Black oxfords"),
        item("belt_brown", "belt", "brown", name="Brown belt"),
    ]


def without(*ids, closet=None):
    return [i for i in (closet or full_closet()) if i["id"] not in ids]


def all_gaps(items, wears=()):
    return gaps.find_gaps(items, wears, {"max_gaps": 50})


def gap_by(answer, category, way=None):
    found = [g for g in answer["gaps"] if g["look_for"]["category"] == category and (way is None or way in g["found_by"])]
    return found[0] if found else None


def demo_items():
    return json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))["items"]


def test_full_closet_has_no_rain_shoe_or_basic_gap():
    answer = all_gaps(full_closet())
    assert answer["enough"] is True and answer["message"] is None
    assert not any("basic" in g["found_by"] for g in answer["gaps"])
    assert gap_by(answer, "dress_shoes") is None
    assert all(g["id"] != "outer-rain" or g["score"] < 10 for g in answer["gaps"])


def test_no_rain_layer_is_found_on_rainy_days():
    answer = all_gaps(without("trench"))
    g = next(g for g in answer["gaps"] if g["id"] == "outer-rain")
    assert {"days", "basic"} <= set(g["found_by"])
    assert g["name"] == "A rain-proof outer layer" and g["look_for"]["category"] == "coat"
    assert any("Nothing you own keeps the rain off" in w and "umbrella" in w for w in g["why"])
    assert g["evidence"]["days"] and all(d["rain"] for d in g["evidence"]["days"])
    assert g["score"] >= 50 and answer["gaps"][0] is g


def test_one_pair_of_smart_shoes_is_a_thin_place():
    answer = all_gaps(without("shoes_black"))
    g = gap_by(answer, "dress_shoes", "thin_place")
    assert g is not None and "shoes_brown" in g["evidence"]["items"]
    assert any("your brown derbies" in w and "nothing to change to" in w for w in g["why"])
    assert g["look_for"]["formality"] in ("business", "formal")


def test_an_orphan_asks_for_the_plain_piece_that_would_bring_it_into_use():
    closet = without("jeans_dark", "jeans_black", "chinos_tan", "chinos_navy", "trousers_grey", "trousers_navy",
                     "shorts_tan", "shorts_navy")
    closet += [item("chinos_red", "trousers", "red", "smart_casual"), item("chinos_purple", "trousers", "purple", "smart_casual"),
               item("jeans_red", "jeans", "red", "casual"),
               item("shirt_loud", "shirt", "orange", "smart_casual", pattern="plaid", name="Orange plaid shirt")]
    g = next(g for g in all_gaps(closet)["gaps"] if "orphan" in g["found_by"])
    assert g["look_for"]["category"] in ("trousers", "jeans") and "shirt_loud" in g["evidence"]["items"]
    assert any("Your orange plaid shirt is in almost no outfit" in w for w in g["why"])
    assert set(g["look_for"]["colors"]) <= {"navy", "grey", "tan", "black", "white", "brown", "beige", "olive", "cream",
                                            "charcoal", "khaki", "light_blue", "blue", "denim"}


def wears_for(counts):
    out, day = [], 1
    for item_id, n in counts.items():
        for _ in range(n):
            out.append({"item_id": item_id, "worn_on": f"2026-10-{day:02d}"})
            day += 1
    return out


def test_an_item_worn_far_more_than_the_rest_asks_for_a_second():
    wears = wears_for({"jeans_dark": 8, "jeans_black": 1, "tee_white": 2, "tee_grey": 2})
    g = gap_by(all_gaps(full_closet(), wears), "jeans", "worn_most")
    assert g is not None and g["name"] == "Another pair of jeans like your dark jeans"
    assert g["evidence"]["items"][0] == "jeans_dark" and "navy" in g["look_for"]["colors"]
    assert any("8 times" in w for w in g["why"])
    # too few wears in the log say nothing yet
    assert gap_by(all_gaps(full_closet(), wears_for({"jeans_dark": 6, "jeans_black": 1})), "jeans", "worn_most") is None
    # the same wear twice in a day counts once
    twice = wears + [{"item_id": "jeans_dark", "worn_on": "2026-10-01"}]
    assert all_gaps(full_closet(), twice) == all_gaps(full_closet(), wears)


def test_never_worn_items_are_a_note_not_a_gap():
    answer = all_gaps(full_closet(), wears_for({"jeans_dark": 4, "tee_white": 3, "sneakers_white": 3}))
    note = next(n for n in answer["notes"] if n["kind"] == "never_worn")
    assert "jeans_dark" not in note["items"] and "trench" in note["items"]
    assert "not gaps" in note["text"]
    assert all(g["found_by"] != ["worn_most"] or g["evidence"]["items"][0] not in note["items"] for g in answer["gaps"])


def test_a_missing_basic_is_named():
    g = gap_by(all_gaps(without("belt_brown")), "belt", "basic")
    assert g is not None and g["name"] == "A leather belt" and g["found_by"] == ["basic"]
    assert any("You have none" in w for w in g["why"])
    # a basic the owner dislikes is still missing, and the reason says so
    disliked = without("belt_brown") + [item("belt_x", "belt", "brown", rating="dislike", name="Brown belt")]
    g = gap_by(all_gaps(disliked), "belt", "basic")
    assert g is not None and any("rated dislike" in w for w in g["why"])


def test_gaps_that_say_the_same_thing_are_merged():
    answer = all_gaps(without("shoes_black", "shoes_brown"))
    ids = [g["id"] for g in answer["gaps"]]
    assert len(ids) == len(set(ids))
    shoes = [g for g in answer["gaps"] if g["look_for"]["category"] == "dress_shoes"]
    assert len(shoes) == 1
    g = shoes[0]
    assert {"days", "basic"} <= set(g["found_by"]) and len(g["why"]) >= 2
    assert len(g["evidence"]["days"]) > 1 and len(g["evidence"]["items"]) >= 3


def test_gaps_are_ranked_and_kept_short():
    items = without("trench", "shoes_black", "belt_brown", "coat_grey", "trousers_navy", "dress_blue", "tee_grey")
    long = all_gaps(items)["gaps"]
    assert len(long) > gaps.MAX_GAPS
    scores = [g["score"] for g in long]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
    short = gaps.find_gaps(items, [])["gaps"]
    assert short == long[:gaps.MAX_GAPS]
    assert gaps.find_gaps(items, [], gaps.Options(max_gaps=3))["gaps"] == long[:3]


def test_same_inputs_give_the_same_answer_in_any_order():
    items = without("trench", "shoes_black")
    wears = wears_for({"jeans_dark": 8, "jeans_black": 1, "tee_white": 2, "tee_grey": 2})
    first = gaps.find_gaps(items, wears)
    rng = random.Random(7)
    for _ in range(2):
        shuffled_items, shuffled_wears = items[:], wears[:]
        rng.shuffle(shuffled_items)
        rng.shuffle(shuffled_wears)
        assert gaps.find_gaps(shuffled_items, shuffled_wears) == first


def test_a_tiny_closet_gets_a_plain_answer():
    answer = gaps.find_gaps(full_closet()[:5], [])
    assert answer["enough"] is False and answer["gaps"] == []
    assert str(gaps.MIN_ITEMS) in answer["message"]
    # accessories and archived items do not count
    belts = [item(f"belt{i}", "belt", "brown") for i in range(10)]
    archived = [item(f"old{i}", "tee", "white", "casual", status="archived") for i in range(10)]
    assert gaps.find_gaps(full_closet()[:5] + belts + archived, [])["enough"] is False


def test_an_empty_closet_says_so():
    answer = gaps.find_gaps([], [])
    assert answer["enough"] is False and answer["gaps"] == [] and "empty" in answer["message"]
    assert answer["checked"] == {"items": 0, "wears": 0, "days": 0}


def test_the_laundry_is_ignored():
    closet = full_closet()
    for i in closet:
        if i["id"] in ("trench", "shoes_black", "coat_navy"):
            i.update(laundry="laundry")
    assert gaps.find_gaps(closet, []) == gaps.find_gaps(full_closet(), [])


def test_swim_trunks_are_not_counted_as_everyday_shorts():
    # they are for swimming on a trip: never a pair of shorts What's missing counts, compares or calls unused
    no_shorts = without("shorts_tan", "shorts_navy")
    trunks = item("trunks", "shorts", "blue", "casual", "warm", name="Blue swim trunks", kind="swim_trunks")
    wears = wears_for({"trunks": 12, "tee_white": 3})
    assert all_gaps(no_shorts + [trunks], wears) == all_gaps(no_shorts, wears)
    # the same pair, as plain shorts, is counted
    assert all_gaps(no_shorts + [{**trunks, "kind": None}], wears) != all_gaps(no_shorts, wears)


def test_shoes_for_a_sport_are_not_counted_as_everyday_sneakers():
    # for their sport only: never the sneakers What's missing counts, compares or calls unused
    no_sneakers = without("sneakers_white", "sneakers_grey")
    tennis = item("tennis", "sneakers", "white", "casual", name="White tennis shoes", kind="tennis_shoe")
    wears = wears_for({"tennis": 12, "tee_white": 3})
    assert all_gaps(no_sneakers + [tennis], wears) == all_gaps(no_sneakers, wears)
    # golf shoes and cleats are left out of the closet it judges in the same way; the same pair as plain sneakers is in it
    pairs = [{**tennis, "id": kind, "kind": kind} for kind in ("golf_shoe", "cleats")]
    assert set(gaps._closet(no_sneakers + pairs, wears).by_id) == set(gaps._closet(no_sneakers, wears).by_id)
    assert "tennis" in gaps._closet(no_sneakers + [{**tennis, "kind": None}], wears).by_id


def test_odd_item_data_never_crashes():
    odd = full_closet() + [{"id": "x1"}, {"id": "x2", "category": "cape"}, None, "nonsense",
                           item("x3", "shirt", "chartreuse", "black_tie", "monsoon", pattern="?")]
    wears = [None, {"item_id": "x1"}, {"item_id": "nope", "worn_on": "2026-10-01"}, {"worn_on": 5}]
    assert gaps.find_gaps(odd, wears)["enough"] is True


def test_demo_closet_gaps_name_real_items():
    items = demo_items()
    ids = {i["id"] for i in items}
    answer = gaps.find_gaps(items, [])
    assert answer["enough"] is True and answer["gaps"]
    assert 1 <= len(answer["gaps"]) <= gaps.MAX_GAPS
    for g in answer["gaps"]:
        assert g["name"] and g["why"] and g["found_by"] and 0 <= g["score"] <= 100
        assert g["evidence"]["items"] and set(g["evidence"]["items"]) <= ids


# ---------------------------------------------------------------------------- API
def test_gaps_answers_for_the_open_closet(client):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    # every demo item but the small accessories (category "other"), which outfits leave out, and what is worn at home
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"] if i["category"] != "other" and gaps.everyday(i)}
    r = client.get("/api/gaps")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"enough", "message", "gaps", "notes", "checked", "context"}
    assert body["enough"] is True and body["gaps"] and body["checked"]["items"] == len(demo_ids)
    assert body["checked"]["wears"] > 0 and body["checked"]["days"] == sum(
        len(life.days_for(key, life.DEMO_LIFE, life.DEMO_CLIMATE)) for key in life.SITUATIONS)
    for g in body["gaps"]:
        assert set(g) == {"id", "name", "look_for", "why", "score", "found_by", "evidence", "state",
                          "hidden_reason", "wish_id", "situations"}
        assert set(g["evidence"]) == {"days", "items"} and set(g["evidence"]["items"]) <= demo_ids
        assert set(g["found_by"]) <= {"days", "thin_place", "orphan", "worn_most", "basic"}
        assert g["look_for"]["category"]
    # a second call gives the same answer, and so does one after a wash
    assert client.get("/api/gaps").json() == body
    some = sorted(demo_ids)[0]
    assert client.post(f"/api/items/{some}/laundry", json={"state": "laundry"}).status_code == 200
    assert client.get("/api/gaps").json() == body
    # a change to the closet is seen
    assert client.patch(f"/api/items/{some}", json={"status": "archived"}).status_code == 200
    assert client.get("/api/gaps").json()["checked"]["items"] == len(demo_ids) - 1


def test_gaps_demo_and_main_closets_are_separate(client):
    main_item = upload(client).json()
    r = client.get("/api/gaps").json()
    assert r["enough"] is False and r["gaps"] == [] and r["checked"]["items"] <= 1
    client.post("/api/profile", json={"profile": "demo"})
    demo = client.get("/api/gaps").json()
    assert demo["enough"] is True
    assert all(main_item["id"] not in g["evidence"]["items"] for g in demo["gaps"])
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/gaps").json() == r


# ---------------------------------------------------------------------------- what is worn at home (review, 23 November)
def sentences(answer) -> str:
    return " ".join(s for g in answer["gaps"] for s in [g["name"], *g["why"]])


def log(counts, first="2026-11-01"):
    """A wear log: each item worn on that many days running from `first`."""
    start = date.fromisoformat(first)
    return [{"item_id": i, "worn_on": (start + timedelta(days=n)).isoformat()} for i, k in counts.items() for n in range(k)]


LOUNGE = item("lounge", "trousers", "red", "casual", "cool", "plaid", name="Tartan lounge pants", kind="lounge_pants")
ONE_PAIR = ("jeans_black", "chinos_tan", "chinos_navy", "trousers_grey", "trousers_navy", "shorts_tan", "shorts_navy")


def test_lounge_pants_worn_at_home_do_not_ask_for_another_pair_of_trousers():
    # the demo's "Another pair of trousers like your tartan lounge pants": nothing is suggested from clothes for home
    worn = log({"lounge": 6, "chinos_tan": 2, "chinos_navy": 2, "trousers_grey": 1, "tee_white": 2, "sneakers_white": 3})
    assert "lounge pants" not in sentences(all_gaps(full_closet() + [LOUNGE], worn))


def test_lounge_pants_are_not_a_piece_a_suggestion_is_based_on():
    answer = all_gaps(without(*ONE_PAIR) + [LOUNGE], log({"lounge": 6, "jeans_dark": 3, "tee_white": 2}))
    assert "lounge" not in {i for g in answer["gaps"] for i in g["evidence"]["items"]}


def test_lounge_pants_are_not_a_second_pair_of_trousers_to_change_into():
    lounge = item("lounge", "trousers", "grey", "casual", name="Grey lounge pants", kind="lounge_pants")
    before, after = all_gaps(without(*ONE_PAIR)), all_gaps(without(*ONE_PAIR) + [lounge])

    def rests_on_jeans(answer):
        return [g["id"] for g in answer["gaps"] if "thin_place" in g["found_by"] and "jeans_dark" in g["evidence"]["items"]]

    assert rests_on_jeans(before)
    assert "lounge pants" not in sentences(after)
    assert rests_on_jeans(after) == rests_on_jeans(before)


def test_a_bath_robe_is_not_the_warmest_outer_layer():
    robe = item("robe", "coat", "white", "casual", "cool", name="White terry robe", kind="robe", weight_class="super_heavy")
    assert "robe" not in sentences(all_gaps(without("coat_grey", "coat_navy", "trench") + [robe]))


def test_pyjamas_do_not_count_as_owning_a_plain_tee():
    no_tees = without("tee_white", "tee_grey", "tee_navy")
    pyjamas = item("pj", "tee", "grey", "casual", name="Grey pyjamas", kind="pajama_set_knit")

    def basic_tee(answer):
        return [g for g in answer["gaps"] if g["look_for"]["category"] == "tee" and "basic" in g["found_by"]]

    assert basic_tee(all_gaps(no_tees))
    assert basic_tee(all_gaps(no_tees + [pyjamas]))


def test_clothes_for_home_are_judged_as_if_they_were_not_in_the_closet():
    # one rule for every kind worn at home: the answer is the closet's without them, whatever is recorded of them
    home = [LOUNGE, item("robe", "coat", "navy", "casual", "cool", name="Navy robe", kind="robe", weight_class="super_heavy"),
            item("pj", "tee", "grey", "casual", name="Grey pyjamas", kind="pajama_set_knit")]
    worn = log({"lounge": 8, "robe": 8, "pj": 8, "jeans_dark": 3, "tee_white": 2})
    assert all_gaps(full_closet() + home, worn) == all_gaps(full_closet(), worn)
    assert all(not gaps.everyday(i) for i in home)
    # the smoking jacket is worn out, so it is an everyday piece
    assert gaps.everyday(item("sj", "jacket", "red", "smart_casual", kind="smoking_jacket"))


def test_a_coat_waiting_to_be_mended_is_still_owned_like_one_in_the_wash():
    def closet(**state):
        return [dict(i, **state) if i["id"] == "coat_navy" else i for i in without("coat_grey", "trench")]

    def listed(answer):
        return [(g["id"], g["score"], g["why"]) for g in answer["gaps"]]

    assert listed(all_gaps(closet(condition="needs_repair"))) == listed(all_gaps(closet(laundry="laundry")))


def test_a_coat_worn_every_day_of_a_cold_week_does_not_ask_for_a_second_coat():
    answer = all_gaps(without("coat_navy", "trench"), log({"coat_grey": 6, "jeans_dark": 3, "jeans_black": 3, "tee_white": 2}))
    assert not [g for g in answer["gaps"] if "worn_most" in g["found_by"] and g["look_for"]["category"] == "coat"]
    # nor do boots worn daily, and never a fourth pair while two sit unworn
    three = full_closet() + [item("boots_tan", "boots", "tan", "smart_casual", name="Tan boots")]
    answer = all_gaps(three, log({"boots_brown": 8, "jeans_dark": 3, "tee_white": 2}))
    assert not [g for g in answer["gaps"] if "worn_most" in g["found_by"]]


def test_a_top_worn_far_more_is_not_doubled_while_one_of_its_kind_sits_unworn():
    worn = log({"tee_white": 6, "tee_grey": 1, "jeans_dark": 3, "sneakers_white": 2})
    assert gap_by(all_gaps(full_closet(), worn), "tee", "worn_most") is None   # the navy linen tee is never worn
    worn = log({"tee_white": 6, "tee_grey": 1, "tee_navy": 1, "jeans_dark": 3, "sneakers_white": 2})
    assert gap_by(all_gaps(full_closet(), worn), "tee", "worn_most") is not None


def test_a_heavy_puffer_jacket_is_a_warm_winter_coat():
    puffer = item("puffer", "jacket", "black", "casual", "cool", name="Black down puffer", kind="puffer",
                  weight_class="super_heavy")
    answer = all_gaps(without("coat_grey", "coat_navy") + [puffer])
    assert "A heavy coat is what keeps a cold day comfortable. You have none." not in sentences(answer)
    # a light jacket is still no winter coat
    light = item("bomber", "jacket", "black", "casual", name="Black bomber", weight_class="lightweight")
    assert "A heavy coat is what keeps a cold day comfortable. You have none." in sentences(
        all_gaps(without("coat_grey", "coat_navy") + [light]))


def test_whats_missing_does_not_speak_of_the_engine():
    said = sentences(all_gaps(without("trench", "belt_brown")))
    assert "umbrella" in said
    assert "engine" not in said
    assert not [b for b in gaps.BASICS if "engine" in b.why]


def test_whats_missing_speaks_of_one_and_of_pairs_correctly():
    closet = without("boots_black", "dress_blue", "trousers_navy", "shoes_brown", "tee_grey", "tee_navy")
    answer = all_gaps(closet, log({"tee_white": 5, "boots_brown": 2, "jeans_dark": 2, "sneakers_white": 2}))
    said = sentences(answer)
    assert "it is the only tee you have" in said and "only one outfit:" in said   # the sentences are there to judge
    assert "one outfit that differ:" not in said
    assert not re.search(r"is the only \w+ that suit\.", said)
    boots = gaps._wear_findings(gaps._closet(without("boots_black"), log({"boots_brown": 6, "jeans_dark": 4, "tee_white": 2})))
    assert boots == ([], boots[1])   # shoes are worn daily by nature: no second pair from wears


def test_whats_missing_writes_dates_as_the_rest_of_the_wardrobe_does():
    answer = all_gaps(without("tee_grey", "tee_navy"), log({"tee_white": 5, "jeans_dark": 3, "sneakers_white": 3}, "2026-11-03"))
    said = sentences(answer) + " ".join(n["text"] for n in answer["notes"])
    assert "between 3 and 7 November 2026" in said
    assert not re.search(r"\d{4}-\d\d-\d\d", said)
