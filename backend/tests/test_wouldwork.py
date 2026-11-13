"""Would this work? The check by rule (`wouldwork.py`): pure, so the demo closet is read straight from its file."""
import json
from datetime import date, timedelta

import pytest

from closet import gaps, wouldwork
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
