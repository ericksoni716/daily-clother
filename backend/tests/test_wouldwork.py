"""Would this work? The check by rule (`wouldwork.py`): pure, so the demo closet is read straight from its file."""
import json
from datetime import date, timedelta

import pytest

from closet import gaps, life, wouldwork
from closet.config import bundle_dir

TODAY = date(2026, 11, 13)


def demo():
    items = json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))["items"]
    wears = [{"item_id": i["id"], "worn_on": (TODAY - timedelta(days=n)).isoformat()}
             for i in items for n in (i.get("history") or {}).get("worn", [])]
    return items, wears


@pytest.fixture(scope="module")
def closet():
    items, wears = demo()
    return items, wears, gaps.find_gaps(items, wears, {"max_gaps": wouldwork.ALL_GAPS})


def check(closet, piece):
    items, wears, before = closet
    return wouldwork.check(items, wears, piece, before)


def ids_of(closet, category):
    return {i["id"] for i in closet[0] if i["category"] == category}


def test_a_rain_proof_coat_fills_the_demo_closets_rain_gap(closet):
    a = check(closet, {"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True})
    assert a["verdict"] == "fills_gap" and a["verdict_words"] == "Fills a gap"
    rain = next(f for f in a["fills"] if f["gap_id"] == "outer-rain")
    assert rain["score_after"] < rain["score_before"] and rain["days"]
    assert all(d["rain"] for d in rain["days"])
    assert "rain-proof outer layer" in a["reasons"][0]
    assert a["goes_with"]["days"] >= wouldwork.GOOD_MIN_DAYS and a["goes_with"]["items"]
    assert 1 <= len(a["goes_with"]["examples"]) <= wouldwork.EXAMPLES_MAX
    owned = {i["id"] for i in closet[0]}
    assert set(a["goes_with"]["items"]) <= owned
    for ex in a["goes_with"]["examples"]:
        assert ex["pieces"]["outer"] == wouldwork.CANDIDATE_ID and ex["day"]["words"]


def test_a_fourth_pair_of_dark_jeans_is_one_you_have_already(closet):
    a = check(closet, {"category": "jeans", "color": "navy", "formality": "casual"})
    assert a["verdict"] == "have_it"
    jeans = ids_of(closet, "jeans")
    assert len(jeans) == 3 and {r["id"] for r in a["repeats"]["items"]} == jeans
    assert a["repeats"]["text"].startswith("You have three like it (your dark indigo jeans")
    assert "hardly worn" in a["repeats"]["text"] and a["reasons"][0] == a["repeats"]["text"]
    # the wear log's own gap ("another pair like your dark indigo jeans") is listed, not counted as a gap filled
    assert all(f["found_by"] == ["worn_most"] for f in a["fills"])


def test_a_piece_nothing_goes_with_is_hard_to_wear(closet):
    a = check(closet, {"category": "trousers", "color": "purple", "formality": "formal", "pattern": "plaid"})
    assert a["verdict"] == "hard_to_wear"
    assert a["goes_with"]["days"] == 0 and a["goes_with"]["examples"] == []
    assert a["holds_back"] and "formality" in a["holds_back"][0]
    assert a["reasons"][0].startswith("Nothing you own makes a good outfit with it")


def test_a_new_kind_of_piece_works_and_adds_something(closet):
    a = check(closet, {"category": "shirt", "color": "orange", "pattern": "floral", "formality": "casual"})
    assert a["verdict"] == "adds" and a["repeats"]["items"] == [] and a["fills"] == []
    assert a["reasons"][-1] == "Nothing you own does quite the same job."


def without(items, *categories):
    return [i for i in items if i["category"] not in categories]


def gap_in(answer, gap_id):
    return next((f for f in answer["fills"] if f["gap_id"] == gap_id), None)


def test_the_very_trousers_a_gap_asks_for_fill_it():
    # without its trousers the demo closet asks for "Smart trousers"; with grey business ones the gap analysis would
    # call them a thin place resting on the new trousers themselves, which is what having bought them looks like
    items, wears = demo()
    a = wouldwork.check(without(items, "trousers"), wears, {"category": "trousers", "color": "grey", "formality": "business"})
    assert a["verdict"] == "fills_gap"
    assert gap_in(a, "trousers-business")["filled"] and "Smart trousers" in a["reasons"][0]


def test_the_very_coat_a_gap_asks_for_fills_it():
    items, wears = demo()
    a = wouldwork.check(without(items, "coat"), wears, {"category": "coat", "color": "navy", "weight_class": "heavyweight"})
    assert a["verdict"] == "fills_gap"
    assert gap_in(a, "outer-warm")["gone"] and "A warm winter coat" in a["reasons"][0]


def test_another_pair_of_smart_trousers_raises_no_gap_of_its_own(closet):
    items, wears, before = closet
    a = check(closet, {"category": "trousers", "color": "navy", "formality": "business"})
    row = wouldwork.candidate_row(wouldwork.parse_piece({"category": "trousers", "color": "navy", "formality": "business"}))
    after = {g["name"]: g for g in wouldwork._after(gaps._closet(items + [row], wears))}
    was = {g["name"]: g["score"] for g in before["gaps"]}
    light = "Light smart trousers for hot days"
    assert light not in after or after[light]["score"] <= was.get(light, 0)
    assert all(wouldwork.CANDIDATE_ID not in g["evidence"]["items"] or "thin_place" not in g["found_by"]
               or len(g["found_by"]) > 1 for g in after.values())
    assert a["verdict"] in ("fills_gap", "have_it", "adds")


def test_a_closet_short_of_warm_layers_is_not_blamed_on_the_piece():
    items, wears = demo()
    bare = without(items, "sweater", "hoodie", "jacket", "coat")
    assert len(bare) == 22
    a = wouldwork.check(bare, wears, {"category": "polo", "color": "white", "weight_class": "lightweight"})
    assert a["verdict"] != "hard_to_wear"
    assert not any("heavier or bulkier than every layer" in h for h in a["holds_back"])
    short = [h for h in a["holds_back"] if h.endswith("that is what the closet lacks, not this piece.")]
    assert short and "short of warm" in short[0]


def test_hard_to_wear_names_the_rule_it_was_judged_on(closet):
    a = check(closet, {"category": "trousers", "color": "purple", "formality": "formal", "pattern": "plaid"})
    assert a["verdict"] == "hard_to_wear"
    assert "your other bottoms makes one" in a["reasons"][0]
    assert a["reasons"][1].startswith("On ") and "breaks a rule" in a["reasons"][1]


def test_what_partners_lack_is_said_of_as_many_as_it_is_true_of(closet):
    a = check(closet, {"category": "trousers", "color": "purple", "formality": "formal", "pattern": "plaid"})
    tops = next(h for h in a["holds_back"] if "tops go" in h)
    # several reasons, each counted: never "they are all ..." of the commonest reason alone
    assert "they are all" not in tops and "two have a strong colour" in tops


def test_the_days_it_would_cover_are_days_it_makes_a_good_outfit_on(closet):
    items, wears, _ = closet
    for piece in ({"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True},
                  {"category": "trousers", "color": "navy", "formality": "business"},
                  {"category": "dress_shoes", "color": "brown", "formality": "business"}):
        a = check(closet, piece)
        row = wouldwork.candidate_row(wouldwork.parse_piece(piece))
        c = gaps._closet(items + [row], wears)
        good = {wouldwork._day_key(r["day"].as_dict()) for r in wouldwork._try_days(c, c.by_id[wouldwork.CANDIDATE_ID])
                if r["good"]}
        for f in a["fills"]:
            assert {wouldwork._day_key(d) for d in f["days"]} <= good


def test_a_disliked_piece_doing_the_same_job_is_named(closet):
    items, wears, _ = closet
    orange = dict(next(i for i in items if i["category"] == "shirt"), id="dislikedorange", color="orange",
                  pattern="floral", formality="casual", rating="dislike", name="Orange floral shirt")
    a = wouldwork.check(items + [orange], wears, {"category": "shirt", "color": "orange", "pattern": "floral",
                                                  "formality": "casual"})
    assert a["verdict"] == "adds" and a["repeats"]["disliked"] == ["dislikedorange"]
    assert "Nothing you own does quite the same job." not in a["reasons"]
    assert any("your orange floral shirt" in r.lower() and "dislike" in r for r in a["reasons"])


def test_the_same_input_gives_the_same_answer(closet):
    piece = {"category": "dress_shoes", "color": "brown", "formality": "business"}
    first = check(closet, piece)
    items, wears, _ = closet
    again = wouldwork.check(list(reversed(items)), list(reversed(wears)), dict(reversed(list(piece.items()))))
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert first["verdict"] == "fills_gap" and first["fills"][0]["gap_id"] == "dress_shoes-business"


def test_the_check_does_not_change_what_the_gap_analysis_finds(closet):
    items, wears, before = closet
    check(closet, {"category": "coat", "color": "navy", "rain_proof": True})
    assert gaps.find_gaps(items, wears, {"max_gaps": wouldwork.ALL_GAPS}) == before
    assert all(i["id"] != wouldwork.CANDIDATE_ID for i in items)


# ------------------------------------------------------------------ how the owner lives (the demo's example answers)
@pytest.fixture(scope="module")
def lived():
    items, wears = demo()
    answers, home = life.example()
    return items, wears, life.analyse(items, wears, answers, home, wouldwork.ALL_GAPS), answers, home


def check_lived(lived, piece):
    items, wears, before, answers, home = lived
    return wouldwork.check(items, wears, piece, before, answers, home)


def test_a_piece_filling_a_gap_high_on_the_weighed_list_fills_it_and_says_for_whom(lived):
    a = check_lived(lived, {"category": "dress_shoes", "color": "black", "formality": "business"})
    assert a["weighed"] and a["verdict"] == "fills_gap"
    shoes = a["fills"][0]
    assert shoes["gap_id"] == "dress_shoes-business" and shoes["counts"] and not shoes["low"]
    assert shoes["rank"] <= wouldwork.RANK_MAX and shoes["situations"] == ["Work"]
    assert a["reasons"][0].startswith("It would fill “A pair of smart leather shoes” for work, covering")
    assert {"id": "work", "label": "Work"} in a["situations"] and a["situations_text"].startswith("It suits work")
    # never lounging: shoes are not worn at home
    assert all(s["id"] != "lounging" for s in a["situations"])


def test_a_piece_filling_only_a_gap_low_on_the_weighed_list_is_not_said_to_fill_a_gap(lived, monkeypatch):
    piece = {"category": "coat", "color": "black", "formality": "athletic", "rain_proof": True,
             "weight_class": "heavyweight"}
    a = check_lived(lived, piece)
    low = next(f for f in a["fills"] if f["gap_id"] == "outer-rain_active")
    assert low["filled"] and low["low"] and not low["counts"] and low["rank"] > wouldwork.RANK_MAX
    assert low["situations"] == ["Exercise"]
    assert not any(f["counts"] for f in a["fills"]) and a["verdict"] != "fills_gap"
    assert not any("would fill" in r for r in a["reasons"])
    # it is where the list ranks the gap that holds it back
    monkeypatch.setattr(wouldwork, "RANK_MAX", low["rank"])
    assert check_lived(lived, piece)["verdict"] == "fills_gap"


def test_the_weighed_check_works_out_the_list_itself_alike_and_leaves_it_unchanged(lived):
    items, wears, before, answers, home = lived
    piece = {"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True}
    given = check_lived(lived, piece)
    assert wouldwork.check(items, wears, piece, None, answers, home) == given
    assert given["verdict"] == "fills_gap" and given["fills"][0]["gap_id"] == "outer-rain"
    assert life.analyse(items, wears, answers, home, wouldwork.ALL_GAPS) == before


def test_unanswered_questions_give_the_plain_check(closet):
    items, wears, before = closet
    piece = {"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True}
    a = check(closet, piece)
    assert wouldwork.check(items, wears, piece) == a == wouldwork.check(items, wears, piece, before, None, None)
    assert not a["weighed"] and a["situations"] == [] and a["situations_text"] is None
    assert all(f["situations"] == [] and not f["low"] and f["counts"] == (f["filled"] and f["found_by"] != ["worn_most"])
               for f in a["fills"])
    assert all("situation" not in d for f in a["fills"] for d in f["days"])
    # no situation is named, as before
    assert a["verdict"] == "fills_gap" and a["reasons"][0].startswith("It would fill “A rain-proof outer layer”, covering")


def test_an_empty_or_tiny_closet_says_there_is_not_enough_to_say():
    empty = wouldwork.check([], [], {"category": "coat", "color": "navy"})
    assert empty["verdict"] == "too_small" and empty["enough"] is False
    assert empty["verdict_words"] == "Not enough in the closet to say"
    assert "empty" in empty["message"]
    tiny = wouldwork.check([{"id": "a", "category": "tee", "color": "white"},
                            {"id": "b", "category": "jeans", "color": "blue"}], [], {"category": "tee", "color": "white"})
    assert tiny["verdict"] == "too_small" and "two pieces of clothing" in tiny["message"]
    assert tiny["repeats"]["items"][0]["id"] == "a"   # what it repeats is still said


def test_wrong_descriptions_are_refused_in_plain_words():
    for bad, words in [({}, "what kind of piece"), ({"category": "cape", "color": "navy"}, "not a kind of piece"),
                       ({"category": "coat"}, "main colour"), ({"category": "coat", "color": "navy", "season": "x"},
                                                                "not a season"),
                       ({"category": "coat", "color": "navy", "rain_proof": "yes"}, "true or false"),
                       ({"category": "coat", "color": "navy", "price": 3}, "not part of a description"),
                       ({"category": "other", "color": "navy"}, "not a kind of piece"), ("coat", "as an object")]:
        with pytest.raises(wouldwork.PieceError, match=words):
            wouldwork.parse_piece(bad)


def test_a_description_is_filled_in_and_read_back():
    p = wouldwork.parse_piece({"category": "coat", "color": "navy", "rain_proof": True, "weight_class": "heavyweight"})
    assert p["formality"] == "smart_casual" and p["season"] == "all" and p["pattern"] == "solid"
    assert wouldwork.describe(p) == "Navy coat, smart casual, all year, heavyweight, keeps the rain off"
    assert "waterproof" in wouldwork.candidate_row(p)["material"]
