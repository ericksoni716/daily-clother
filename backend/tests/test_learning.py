"""The outfit engine learning from rated outfits (`outfits.feedback_from` and `suggest(..., feedback)`)."""
from closet import outfits

from .test_outfits import basic_closet, day, demo_items, item


def closet():
    # two white tees the engine cannot tell apart: without ratings it takes tee1
    return basic_closet() + [item("tee2", "tee", "white", "casual", "warm", silhouette={"sleeve": "short"})]


def rated(worn_on, rating, reasons=(), low=None, high=None, occasion="casual", **pieces):
    places = {pl: pieces.get(pl) for pl in outfits.PLACES}
    return {"id": f"o-{worn_on}", "worn_on": worn_on, "rating": rating, "rating_reasons": list(reasons),
            "pieces": {**places, "accessories": []},
            "context": None if low is None else {"low_c": low, "high_c": high, "rain": False, "occasion": occasion, "mood": None}}


def suggest(items, ctx, history, count=5):
    return outfits.suggest(items, ctx, count, outfits.feedback_from(history, items, ctx))


def first(result):
    p = result["outfits"][0]["pieces"]
    return (p["base"], p["mid"], p["outer"], p["bottom"], p["shoes"])


def test_no_ratings_give_exactly_what_the_engine_gives_without_feedback():
    for items in (closet(), demo_items()):
        for ctx in (day(22), day(3, 9), day(14, rain=True, occasion="business"), day(28, mood="relaxed")):
            plain = outfits.suggest(items, ctx, 5)
            assert outfits.suggest(items, ctx, 5, outfits.Feedback()) == plain
            assert suggest(items, ctx, []) == plain
            # outfits worn but not rated, or rated "fine" with nothing to say, teach nothing either
            idle = [rated("2026-11-03", None, base="tee2", bottom="jeans1", shoes="sneakers1"),
                    rated("2026-11-04", "fine", base="tee2", bottom="jeans1", shoes="sneakers1")]
            assert suggest(items, ctx, idle) == plain


def test_a_loved_set_is_preferred_when_otherwise_equal_and_says_so():
    items, ctx = closet(), day(22)
    assert first(outfits.suggest(items, ctx, 5)) == ("tee1", None, None, "jeans1", "sneakers1")
    loved = [rated("2026-11-03", "loved", base="tee2", bottom="jeans1", shoes="sneakers1")]
    result = suggest(items, ctx, loved)
    assert first(result) == ("tee2", None, None, "jeans1", "sneakers1")
    assert "You loved this outfit on 3 November." in result["outfits"][0]["reasons"]
    # part of a loved outfit is named piece by piece
    part = [rated("2026-11-03", "loved", base="tee2", mid="hoodie1", bottom="jeans1", shoes="dshoes1")]
    reasons = [r for o in suggest(items, ctx, part)["outfits"] for r in o["reasons"]]
    assert any(r.startswith("You loved the white tee tee2 and the blue jeans jeans1 together on 3 November") for r in reasons)
    # compliments count as liked too
    praised = [rated("2026-11-05", "fine", ["compliments"], base="tee2", bottom="jeans1", shoes="sneakers1")]
    result = suggest(items, ctx, praised)
    assert first(result) == ("tee2", None, None, "jeans1", "sneakers1")
    assert "You got compliments for this outfit on 5 November." in result["outfits"][0]["reasons"]


def test_a_loved_set_is_only_a_little_more_likely():
    # a loved outfit that is wrong for the day (a coat at 30°C) does not beat what suits the day
    items, ctx = closet(), day(30)
    loved = [rated("2026-11-03", "loved", base="tee2", outer="coat1", bottom="trousers1", shoes="dshoes1")]
    assert suggest(items, ctx, loved)["outfits"][0]["pieces"]["outer"] is None
    assert outfits.LOVED_MAX_BONUS < outfits.PIECE_PROBLEM_PENALTY


def test_a_not_again_outfit_is_not_offered_again_as_it_was():
    items, ctx = closet(), day(22)
    top = first(outfits.suggest(items, ctx, 10))
    base, mid, outer, bottom, shoes = top
    history = [rated("2026-11-02", "not_again", base=base, mid=mid, outer=outer, bottom=bottom, shoes=shoes)]
    result = suggest(items, ctx, history, 10)
    offered = {(o["pieces"]["base"], o["pieces"]["mid"], o["pieces"]["outer"], o["pieces"]["bottom"], o["pieces"]["shoes"])
               for o in result["outfits"]}
    assert top not in offered and result["outfits"]
    # with no reason, its pieces are less likely together: an outfit holding two of them says why
    together = [o for o in result["outfits"] if len({base, bottom, shoes} & set(first({"outfits": [o]}))) >= 2]
    assert all(any("you said not again to on 2 November" in w for w in o["warnings"]) for o in together)


def test_not_again_for_a_reason_only_avoids_the_pieces_that_were_the_problem():
    items = closet()
    ctx = day(22)
    known = {p.id: p for p in (outfits._piece(i) for i in items)}
    ids = frozenset({"tee1", "dress1", "jeans1", "sneakers1"})
    # too dressed up on a casual day: the dress shirt with the rest, not the tee with the jeans
    pairs = outfits._problem_pairs(ids, {"too_dressy"}, known, True)
    assert pairs and all("dress1" in p for p in pairs)
    # on another kind of day it says nothing about the pieces
    assert outfits._problem_pairs(ids, {"too_dressy"}, known, False) == frozenset()
    # too cold says nothing about which pieces go together
    assert outfits._problem_pairs(ids, {"too_cold"}, known, True) == frozenset()
    history = [rated("2026-11-02", "not_again", ["too_cold"], base="tee1", bottom="jeans1", shoes="sneakers1", low=20, high=24)]
    fb = outfits.feedback_from(history, items, ctx)
    assert fb.avoided == () and ("tee1", "", "", "jeans1", "sneakers1") in fb.not_again


def test_only_a_not_again_outfit_left_says_so():
    items = [item("t", "tee", "white", "casual"), item("j", "jeans", "blue", "casual"), item("s", "sneakers", "white", "casual")]
    history = [rated("2026-11-02", "not_again", base="t", bottom="j", shoes="s")]
    result = suggest(items, day(22), history)
    assert result == {"outfits": [], "missing": [NOT_AGAIN_ONLY.format("2 November")]}


NOT_AGAIN_ONLY = ("The only outfit that suits today is one you said not again to on {}. "
                  "Change its rating on the Worn screen to have it offered again.")


def test_a_not_again_outfit_is_never_the_reason_a_rule_breaking_outfit_is_offered():
    # at 8°C only the tee, jeans and sneakers suit the day; shorts break a rule
    items = [item("t", "tee", "white", "casual"), item("j", "jeans", "blue", "casual"),
             item("sh", "shorts", "tan", "casual", "warm"), item("s", "sneakers", "white", "casual")]
    assert [o["pieces"]["bottom"] for o in outfits.suggest(items, day(8), 5)["outfits"]] == ["j"]
    history = [rated("2026-11-02", "not_again", base="t", bottom="j", shoes="s")]
    result = suggest(items, day(8), history)
    assert result == {"outfits": [], "missing": [NOT_AGAIN_ONLY.format("2 November")]}


def test_an_outfit_with_a_piece_no_longer_in_the_closet_teaches_nothing():
    # the sweater was deleted after tee, sweater, jeans and sneakers were rated "not again" (or loved):
    # what is left is an outfit that was never worn, so the rating must not move onto it
    items, ctx = closet(), day(22)
    for rating in ("not_again", "loved"):
        history = [rated("2026-11-02", rating, ["too_cold"], low=20, high=24,
                         base="tee1", mid="gone-sweater", bottom="jeans1", shoes="sneakers1")]
        assert outfits.feedback_from(history, items, ctx) == outfits.Feedback()
        assert suggest(items, ctx, history) == outfits.suggest(items, ctx, 5)


def test_too_cold_on_similar_days_dresses_warmer_within_its_bound():
    items, ctx = closet(), day(14)
    cold = [rated(f"2026-10-{n:02d}", "fine", ["too_cold"], base="tee1", bottom="jeans1", shoes="sneakers1", low=12, high=17)
            for n in range(1, 11)]
    fb = outfits.feedback_from(cold[:1], items, ctx)
    assert fb.warmth_shift == outfits.WARMTH_SHIFT_PER_RATING and fb.warmth_day == "2026-10-01"
    fb = outfits.feedback_from(cold, items, ctx)
    assert fb.warmth_shift == outfits.WARMTH_SHIFT_MAX and fb.warmth_day == "2026-10-10"
    # a day far from today does not count, nor does an outfit with no day recorded
    far = [rated("2026-08-01", "fine", ["too_cold"], base="tee1", bottom="jeans1", shoes="sneakers1", low=28, high=33),
           rated("2026-08-02", "fine", ["too_cold"], base="tee1", bottom="jeans1", shoes="sneakers1")]
    assert outfits.feedback_from(far, items, ctx).warmth_shift == 0
    # too warm pulls the other way, and they cancel
    warm = [rated("2026-10-20", "loved", ["too_warm"], base="tee1", bottom="jeans1", shoes="sneakers1", low=12, high=17)]
    assert outfits.feedback_from(warm, items, ctx).warmth_shift == -outfits.WARMTH_SHIFT_PER_RATING
    assert outfits.feedback_from(cold[:1] + warm, items, ctx).warmth_shift == 0

    def warmth(result):
        pieces = {i["id"]: outfits._piece(i) for i in items}
        return [sum(outfits._warmth(pieces[o["pieces"][pl]], pl) for pl in ("base", "mid", "outer") if o["pieces"][pl])
                for o in result["outfits"]]

    plain = outfits.suggest(items, ctx, 5)
    warmer = suggest(items, ctx, cold)
    assert warmer != plain and warmth(warmer)[0] > warmth(plain)[0]
    assert any("Dressed a little warmer than usual: you were cold on a day like this on 10 October." in o["reasons"]
               for o in warmer["outfits"])
    # the bound holds however many times it was said
    assert outfits.feedback_from(cold * 5, items, ctx).warmth_shift == outfits.WARMTH_SHIFT_MAX
    lighter = suggest(items, ctx, warm)
    assert any("Dressed a little lighter than usual: you were too warm on a day like this on 20 October." in o["reasons"]
               for o in lighter["outfits"])


def test_the_same_ratings_give_the_same_outfits():
    items = demo_items()
    by_name = {i["name"]: i["id"] for i in items}
    history = [rated("2026-11-01", "loved", ["compliments"], base=by_name["White tee"], mid=by_name["Burgundy cable sweater"],
                     outer=by_name["Tan chore jacket"], bottom=by_name["Brown corduroy trousers"], shoes=by_name["Brown boots"],
                     low=4, high=10, occasion="smart_casual"),
               rated("2026-11-04", "not_again", ["colours_clashed", "too_cold"], base=by_name["Plaid flannel shirt"],
                     bottom=by_name["Black jeans"], shoes=by_name["White canvas sneakers"], low=6, high=11)]
    for ctx in (day(5, 11), day(18), day(8, 12, occasion="smart_casual")):
        once = suggest(items, ctx, history)
        assert suggest(items, ctx, list(reversed(history))) == once == suggest(items, ctx, history)
        assert once["outfits"]


def test_odd_ratings_never_crash():
    items, ctx = closet(), day(15)
    odd = [None, 3, {}, {"rating": "loved"}, {"rating": "loved", "pieces": "x"}, {"rating": "wow", "pieces": {"base": "tee1"}},
           {"rating": "not_again", "rating_reasons": ["nope", None], "pieces": {"base": "gone", "bottom": "jeans1"}, "worn_on": None},
           {"rating": "fine", "rating_reasons": ["too_cold"], "context": {"low_c": True, "high_c": "x"}, "pieces": {}}]
    assert suggest(items, ctx, odd)["outfits"]
    assert outfits._date_words("2026-11-03") == "3 November" and outfits._date_words("soon") == "soon"
