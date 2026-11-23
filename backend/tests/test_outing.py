"""Give it an outing: who is a candidate, the rhythm, the outfit built around the piece, and turning it down
(`closet/outing.py`, pure)."""
from datetime import date

import pytest

from closet import outfits, outing

from .test_outfits import basic_closet, check_outfit, day, item

TODAY = date(2026, 11, 23)
ADDED = "2026-01-05T09:00:00.000000Z"
COOL = day(8, 14)            # a cool day: a jacket over a top


def closet(*extra):
    """The basic closet with a second tee and chinos (three outfits on a cool day), all added in January, and a tweed
    jacket you love; `extra` items replace those with the same id."""
    rows = [*basic_closet(), item("tee2", "tee", "grey", "casual"), item("chinos1", "trousers", "tan", "casual"),
            item("tweed", "jacket", "olive", "casual", "cool", rating="love", name="Tweed jacket")]
    by_id = {r["id"]: {"created_at": ADDED, **r} for r in rows}
    for r in extra:
        by_id[r["id"]] = {"created_at": ADDED, **r}
    return list(by_id.values())


def worn_lately(rows, but=("tweed",), on="2026-11-20"):
    """Every piece worn three days ago, but those named."""
    return {r["id"]: on for r in rows if r["id"] not in but}


def without(rows, *ids, ctx=COOL):
    """Today's three outfits as the rules would offer them without these pieces: the loved pieces the rules already
    favour stay out of them, as a neglected piece does."""
    return outfits.suggest([r for r in rows if r["id"] not in ids], ctx, 3)["outfits"]


def choose(rows, ctx=COOL, *, last_worn=None, history=(), dressed=(), shown=None, today=TODAY):
    shown = outfits.suggest(rows, ctx, 3)["outfits"] if shown is None else shown
    return outing.choose(rows, ctx, shown=shown, today=today, last_worn=worn_lately(rows) if last_worn is None else last_worn,
                         dressed=list(dressed), history=list(history))


def test_a_loved_piece_not_worn_for_four_weeks_gets_an_outing():
    rows = closet()
    found = choose(rows, last_worn={**worn_lately(rows), "tweed": "2026-10-02"})
    assert found["item_id"] == "tweed" and found["rating"] == "love"
    assert found["since"] == "2026-10-02" and found["never_worn"] is False and found["new"] is True
    assert found["outfit"]["pieces"]["outer"] == "tweed"


def test_a_piece_never_worn_counts_from_the_day_it_was_added():
    found = choose(closet())
    assert found["item_id"] == "tweed" and found["since"] == "2026-01-05" and found["never_worn"] is True


# ------------------------------------------------------------------ who is not a candidate, one condition each
@pytest.mark.parametrize("why, change", [
    ("worn three weeks ago", {"last_worn": "2026-11-02"}),
    ("added a fortnight ago, never worn", {"created_at": "2026-11-09T10:00:00Z"}),
    ("rated meh", {"rating": "meh"}),
    ("not rated", {"rating": None}),
    ("rated dislike", {"rating": "dislike"}),
    ("in the laundry", {"laundry": "dirty"}),
    ("at the cleaner's", {"away": "cleaner"}),
    ("waiting to be mended", {"condition": "needs_repair"}),
    ("archived", {"status": "archived"}),
    ("left out today", {"left_out": True}),
    ("too warm for today", {"season": "cool", "day": day(24, 30)}),
    ("too casual for the occasion", {"formality": "casual", "day": day(8, 14, occasion="business")}),
    ("loungewear", {"category": "trousers", "kind": "lounge_pants", "id_place": "bottom"}),
    ("swimwear", {"category": "shorts", "kind": "swim_trunks", "season": "warm", "day": day(24, 30)}),
    ("sport clothes on an ordinary day", {"category": "jacket", "kind": "track_jacket"}),
    ("an accessory", {"category": "scarf"}),
])
def test_who_is_not_a_candidate(why, change):
    change = dict(change)
    ctx = change.pop("day", COOL)
    last = change.pop("last_worn", None)
    if change.pop("left_out", False):
        ctx = outfits.Context(**{**ctx.__dict__, "leave_out": ("tweed",)})
    change.pop("id_place", None)
    rows = closet({**next(r for r in closet() if r["id"] == "tweed"), **change})
    lw = {**worn_lately(rows), **({"tweed": last} if last else {})}
    found = choose(rows, ctx, last_worn=lw)
    assert found is None or found["item_id"] != "tweed", why
    if last is None and "created_at" not in change:   # not a matter of time: not wearable as an outing
        tweed = next(r for r in rows if r["id"] == "tweed")
        assert not outing.wearable_today(tweed, outfits._piece(tweed), ctx), why


def test_a_liked_piece_is_a_candidate_after_the_loved_ones():
    rows = closet(item("cords", "trousers", "brown", "casual", rating="like", name="Brown cords"))
    first = choose(rows, last_worn=worn_lately(rows, but=("tweed", "cords")), shown=without(rows, "tweed", "cords"))
    assert first["item_id"] == "tweed"
    rows = closet(item("cords", "trousers", "brown", "casual", rating="like", name="Brown cords"),
                  {**next(r for r in closet() if r["id"] == "tweed"), "rating": None})
    second = choose(rows, last_worn=worn_lately(rows, but=("cords",)), shown=without(rows, "tweed", "cords"))
    assert second["item_id"] == "cords" and second["rating"] == "like"


def test_among_loved_pieces_the_longest_passed_over_comes_first():
    rows = closet(item("cords", "trousers", "brown", "casual", rating="love", name="Brown cords"))
    lw = {**worn_lately(rows, but=("tweed", "cords")), "tweed": "2026-10-20", "cords": "2026-09-01"}
    assert choose(rows, last_worn=lw, shown=without(rows, "tweed", "cords"))["item_id"] == "cords"


def test_a_piece_in_the_outfits_that_stay_is_not_offered_again():
    rows = closet()
    shown = outfits.suggest(rows, COOL, 3)["outfits"]
    shown[0] = {**shown[0], "pieces": {**shown[0]["pieces"], "outer": "tweed"}}
    assert choose(rows, shown=shown) is None


def test_days_whose_weather_did_not_suit_it_do_not_count():
    # a winter coat last worn in March, the summer recorded day by day as too warm for it: not neglected at the frost
    coat = item("tweed", "coat", "black", "casual", "cool", rating="love", name="Wool coat")
    rows = closet(coat)
    ctx = day(2, 7)
    lw = {**worn_lately(rows), "tweed": "2026-10-01"}
    warm = [{"day": f"2026-{m:02d}-{d:02d}", "low_c": 18, "high_c": 27, "rain": False}
            for m, d in [(10, n) for n in range(2, 31)] + [(11, n) for n in range(1, 8)]]
    shown = without(rows, "tweed", ctx=ctx)
    assert choose(rows, ctx, last_worn=lw, dressed=warm, shown=shown) is None
    assert choose(rows, ctx, last_worn=lw, shown=shown)["item_id"] == "tweed"   # with no days recorded, every day counts


def test_passed_over_counts_a_day_recorded_twice_once():
    p = outfits._piece(item("c", "coat", "black", "business", "cool"))
    hot = {"low_c": 22, "high_c": 30, "rain": False}
    dressed = [{"day": "2026-11-10", **hot}, {"day": "2026-11-10", **hot}, {"day": "2026-11-11", **hot}]
    assert outing.passed_over(p, date(2026, 11, 1), TODAY, dressed) == 22 - 2


# ------------------------------------------------------------------ the outfit
def test_the_outing_outfit_obeys_the_rules_every_outfit_keeps():
    rows = closet()
    found = choose(rows)
    o = found["outfit"]
    check_outfit(o, rows)
    assert outing.good(o) and not o["warnings"] and o["score"] >= outing.MIN_SCORE
    assert not any(r.startswith("Built around") for r in o["reasons"])   # the outing's own sentence says why


def test_with_no_good_outfit_around_the_first_candidate_the_next_is_tried():
    # loafers you love, but too dressy for anything else casual: nothing good is built around them; the tweed is next
    rows = closet(item("loafers", "dress_shoes", "black", "formal", rating="love", name="Patent shoes"))
    lw = {**worn_lately(rows, but=("tweed", "loafers")), "loafers": "2026-08-01"}
    found = choose(rows, last_worn=lw)
    assert found["item_id"] == "tweed"


def test_no_outing_when_fewer_than_two_outfits():
    rows = closet()
    shown = outfits.suggest(rows, COOL, 1)["outfits"]
    assert choose(rows, shown=shown) is None


def test_place_puts_it_last_and_keeps_the_count():
    rows = closet()
    shown = outfits.suggest(rows, COOL, 3)["outfits"]
    found = choose(rows, shown=shown)
    placed = outing.place(shown, found)
    assert len(placed) == 3 and placed[:2] == shown[:2]
    assert placed[2]["outing"] == {"item_id": "tweed", "rating": "love", "since": "2026-01-05", "never_worn": True,
                                  "plural": False}


def test_place_leaves_the_outfits_alone_when_the_piece_is_already_in_one_of_them():
    rows = closet()
    shown = outfits.suggest(rows, COOL, 3)["outfits"]
    found = choose(rows, shown=shown)
    claude = [{**shown[1], "pieces": {**shown[1]["pieces"], "outer": "tweed"}, "by": "claude"}, shown[0], shown[2]]
    assert outing.place(claude, found) == claude


# ------------------------------------------------------------------ the rhythm, and turning it down
def offered(days_ago, item_id="jacket1", turned_down=0):
    d = date.fromordinal(TODAY.toordinal() - days_ago).isoformat()
    return {"day": d, "item_id": item_id, "since": "2026-09-01", "never_worn": 0, "turned_down": turned_down}


@pytest.mark.parametrize("days_ago, any_outing", [(1, False), (4, False), (5, True), (12, True)])
def test_at_most_one_outing_day_in_five(days_ago, any_outing):
    assert (choose(closet(), history=[offered(days_ago)]) is not None) is any_outing


@pytest.mark.parametrize("days_ago, again", [(6, False), (20, False), (21, True)])
def test_a_piece_offered_waits_three_weeks(days_ago, again):
    found = choose(closet(), history=[offered(days_ago, "tweed")])
    assert (found is not None and found["item_id"] == "tweed") is again


def test_the_choice_is_the_same_for_the_same_day():
    rows = closet(item("cords", "trousers", "brown", "casual", rating="love", name="Brown cords"))
    lw = worn_lately(rows, but=("tweed", "cords"))
    assert choose(rows, last_worn=lw) == choose(list(reversed(rows)), last_worn=lw)


def test_the_days_outing_is_kept_through_the_day():
    rows = closet(item("cords", "trousers", "brown", "casual", rating="love", name="Brown cords"))
    lw = {**worn_lately(rows, but=("tweed", "cords")), "cords": "2026-09-01"}   # the cords would come first now
    kept = {**offered(0, "tweed"), "since": "2026-10-02"}
    found = choose(rows, last_worn=lw, history=[kept], shown=without(rows, "tweed", "cords"))
    assert found["item_id"] == "tweed" and found["since"] == "2026-10-02" and found["new"] is False


def test_turned_down_ends_the_days_outing():
    rows = closet(item("cords", "trousers", "brown", "casual", rating="love", name="Brown cords"))
    ctx = outfits.Context(**{**COOL.__dict__, "leave_out": ("tweed",)})
    assert choose(rows, ctx, history=[offered(0, "tweed", turned_down=1)]) is None
    # and the next days it counts as offered: the cords may come after the rhythm's five days, the tweed after three weeks
    later = date.fromordinal(TODAY.toordinal() + 5)
    found = choose(rows, today=later, history=[offered(0, "tweed", turned_down=1)], shown=without(rows, "tweed", "cords"),
                   last_worn=worn_lately(rows, but=("tweed", "cords")))
    assert found["item_id"] == "cords"
