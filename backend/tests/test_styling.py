"""Outfits chosen by Claude: the brief the stylist reads and the check of its answer (closet/styling.py), the question
itself (closet/tagger/stylist.py) and the developer tool that tries it on the demo closet (tools/style_demo_days.py).
Claude is always stood in for."""
import dataclasses
import importlib.util
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from closet import day, outfits, styling
from closet.tagger import correcting, stylist, taxonomy
from closet.tagger.tagging import RouteUnavailable, TaggingError, Unreachable

TOOL = Path(__file__).resolve().parents[2] / "tools" / "style_demo_days.py"
TUESDAY = date(2026, 11, 17)


def item(id, name, category, **more):
    """A closet row shaped like `today.closet_rows` gives it."""
    row = {"id": id, "name": name, "category": category, "color": "navy", "pattern": "solid", "formality": None,
           "season": "all", "status": "active", "laundry": "clean", "silhouette": {}, "rating": None, "notes": None,
           "fit_notes": None, "material": None, "kind": None, "location": "closet", "condition": "good"}
    row.update(more)
    return row


def closet():
    # numbered: base 1 blue oxford, 2 white tee; mid 3; outer 4; bottoms 5 chinos, 6 dark jeans; shoes 7 boots,
    # 8 sneakers; accessories 9 black belt, 10 brown belt, 11 wool scarf
    return [
        item("t1", "White tee", "tee", color="white"),
        item("t2", "Blue oxford", "shirt", color="light_blue"),
        item("m1", "Grey sweater", "sweater", color="grey"),
        item("o1", "Navy coat", "coat"),
        item("b1", "Dark jeans", "jeans", color="blue"),
        item("b2", "Chinos", "trousers", color="tan"),
        item("s1", "White sneakers", "sneakers", color="white"),
        item("s2", "Brown boots", "boots", color="brown"),
        item("a1", "Brown belt", "belt", color="brown"),
        item("a2", "Wool scarf", "scarf", color="grey"),
        item("a3", "Black belt", "belt", color="black"),
    ]


def context(**req):
    return outfits.parse_request({"low_c": 5, "high_c": 12, **req})[0]


def look(base=2, mid=0, outer=0, bottom=6, shoes=8, accessories=(), why="", watch=""):
    return {"base": base, "mid": mid, "outer": outer, "bottom": bottom, "shoes": shoes,
            "accessories": list(accessories), "why": why, "watch": watch}


def hour(h, temp, feels=None, chance=0, mm=0.0, wind=5.0, gust=10.0, humidity=50.0, uv=1.0, summary="cloudy"):
    return {"hour": h, "temp_c": temp, "feels_c": temp if feels is None else feels, "rain_chance": chance,
            "rain_mm": mm, "wind_kmh": wind, "gust_kmh": gust, "humidity": humidity, "uv": uv, "summary": summary}


def a_day(**change):
    """A cool November day: 2° at night, 9° at three in the afternoon."""
    temps = [2, 2, 1, 1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 8, 9, 9, 8, 7, 6, 5, 5, 4, 3, 3]
    hours = [hour(h, float(t)) for h, t in enumerate(temps)]
    for h, fields in change.items():
        hours[int(h[1:])].update(fields)
    return hours


# ------------------------------------------------------------------ the numbered closet
def test_pieces_are_numbered_from_one_by_place_then_by_name():
    listing = styling.listed(closet(), context())
    assert listing.ids == ("t2", "t1", "m1", "o1", "b2", "b1", "s2", "s1", "a3", "a1", "a2")
    assert [listing.number(i) for i in listing.ids] == list(range(1, 12))
    assert listing.number("nope") is None
    assert [line.split(" | ")[0] for line in listing.lines[:3]] == ["1. Blue oxford", "2. White tee", "3. Grey sweater"]
    assert listing.names["t1"] == "White tee" and set(listing.pieces) == set(listing.ids)


@pytest.mark.parametrize("change", [{"laundry": "dirty"}, {"location": "laundry"}, {"status": "archived"},
                                    {"condition": "needs_repair"}, {"rating": "dislike"}, {"kind": "robe"},
                                    {"category": "dress"}, {"category": None}])
def test_a_piece_that_cannot_be_worn_today_is_never_listed(change):
    rows = closet()
    rows[0].update(change)
    assert "t1" not in styling.listed(rows, context()).ids


def test_a_piece_left_out_today_is_not_listed():
    assert "t1" not in styling.listed(closet(), context(leave_out=["t1"])).ids


def test_swim_trunks_are_never_listed_for_the_stylist_even_on_a_hot_day():
    rows = closet() + [item("b3", "Blue swim trunks", "shorts", color="blue", season="warm", kind="swim_trunks")]
    listing = styling.listed(rows, context(low_c=24, high_c=31))
    assert "b3" not in listing.ids and "b1" in listing.ids
    assert "b3" in styling.listed(rows, context(low_c=24, high_c=31, build_around="b3")).ids   # unless built around


def test_tennis_shoes_kept_from_an_outfit_worn_again_are_listed_for_the_stylist():
    # the engine keeps them in the outfit worn again (today.again_of); Claude is told it must, so it must see them
    rows = closet() + [item("s3", "Tennis shoes", "sneakers", color="white", kind="tennis_shoe"),
                       item("s4", "Worn sneakers", "sneakers", color="white", condition="needs_repair")]
    assert "s3" not in styling.listed(rows, context()).ids
    again = dataclasses.replace(context(), keep=("t1", "s3", "s4"))
    assert "s3" in styling.listed(rows, again).ids and "s4" not in styling.listed(rows, again).ids


def test_tennis_shoes_are_never_listed_for_the_stylist_even_for_an_athletic_day():
    rows = closet() + [item("s3", "White tennis shoes", "sneakers", color="white", formality="athletic", kind="tennis_shoe")]
    listing = styling.listed(rows, context(occasion="athletic"))
    assert "s3" not in listing.ids and "s1" in listing.ids
    assert "s3" in styling.listed(rows, context(occasion="athletic", build_around="s3")).ids   # unless built around


def test_a_piece_built_around_is_listed_even_in_the_laundry():
    rows = closet()
    rows[0]["laundry"] = "dirty"
    assert "t1" in styling.listed(rows, context(build_around="t1")).ids
    assert "t1" not in styling.listed(rows, context(build_around="b1")).ids


def test_the_places_of_each_kind_of_piece():
    def places(category):
        return styling.places_of(outfits._piece(item("x", "X", category)))
    assert places("tee") == ["base"] and places("shirt") == ["base", "mid"] and places("sweater") == ["mid"]
    assert places("coat") == ["outer"] and places("jeans") == ["bottom"] and places("boots") == ["shoes"]
    assert places("belt") == places("scarf") == places("hat") == places("bag") == ["accessory"]


def test_a_line_says_everything_known_about_the_piece_in_words():
    row = item("x", "Linen  shirt", "shirt", kind="camp_collar_shirt", color="cream", pattern="stripe",
               material="linen", weight_class="lightweight", formality="smart_casual", season="warm",
               silhouette={"fit": "regular", "sleeve": "short", "neck": "collar"}, rating="love", location="storage",
               wear_notes="Open  over a tee", notes="x" * 300, fit_notes="Runs\n big")
    line = styling.listed([row], context(worn_days_ago={"x": 3})).lines[0]
    assert line == ("1. Linen shirt | camp collar shirt (base or mid layer) | cream, stripe | linen, lightweight | "
                    "smart casual | warm season | regular fit, short sleeve, collar neck | loved | worn 3 days ago | "
                    f"put away in storage | how I wear it: “Open over a tee” | my note: “{'x' * styling.MAX_NOTE}” | "
                    "fit: “Runs big”")


def test_a_plain_line_leaves_out_what_is_not_worth_saying():
    line = styling.listed([item("x", "Loafers", "dress_shoes", color="brown")], context()).lines[0]
    assert line.startswith("1. Loafers | dress shoes (shoes) | brown | ")
    assert "season" not in line and "solid" not in line and "“" not in line and "storage" not in line
    assert "loved" not in line and "liked" not in line and line.endswith("never worn")


def test_a_piece_between_two_levels_of_formality_is_listed_with_both():
    rows = [item("a", "Loafers", "dress_shoes", color="burgundy", formality="business", formality_also="smart_casual"),
            item("b", "Runners", "sneakers", color="grey", formality="athletic")]
    lines = styling.listed(rows, context()).lines
    assert "| smart casual to business |" in lines[0] and "| athletic |" in lines[1]


def test_the_rating_and_when_it_was_last_worn_are_in_words():
    rows = [item("a", "A tee", "tee", rating="like"), item("b", "B tee", "tee", rating="meh"), item("c", "C tee", "tee")]
    lines = styling.listed(rows, context(worn_days_ago={"a": 0, "b": 1, "c": 12})).lines
    assert "| liked | worn today" in lines[0] and "| meh | worn yesterday" in lines[1]
    assert lines[2].endswith("| worn 12 days ago")


def test_an_accessorys_place_is_accessory():
    line = styling.listed([item("a", "Brown belt", "belt", color="brown")], context()).lines[0]
    assert "belt (accessory)" in line


# ------------------------------------------------------------------ the guide
def test_the_guide_has_a_heading_for_every_part_of_the_owners_outfit_notes():
    text = styling.guide()
    parts = taxonomy.load()["outfit"]
    for key in parts:
        assert f"{key.replace('_', ' ').capitalize()}:" in text
    assert "{" not in text and "}" not in text


def test_the_guide_reads_dicts_lists_and_lists_of_dicts_as_plain_lines(tmp_path):
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps({"garments": {"ignored": True}, "outfit": {
        "places": {"base": ["tee", "shirt"], "max_layers": 3},
        "color_pairings": [{"top": "navy", "bottom_colour": "grey"}, "white with anything"],
        "rain": "Wear boots",
    }}), encoding="utf-8")
    assert styling.guide(path).splitlines() == [
        "Places:", "- base:", "  - tee, shirt", "- max layers: 3",
        "Color pairings:", "- top navy; bottom colour grey", "- white with anything",
        "Rain:", "- Wear boots",
    ]


# ------------------------------------------------------------------ the day
def test_the_day_from_the_forecast_hours_in_words():
    hours = a_day(**{f"h{h}": {"rain_chance": 70, "rain_mm": 1.0, "summary": "rain"} for h in (14, 15)},
                  h13={"wind_kmh": 30.0, "gust_kmh": 50.4, "uv": 6.4})
    detail = day.read(hours)
    text = styling.day_words({"place": "Lisbon, Portugal", "detail": detail}, context(occasion="smart_casual"), TUESDAY)
    lines = text.splitlines()
    assert lines[0] == "Date: Tuesday 17 November 2026. Place: Lisbon, Portugal."
    assert lines[1] == "Hours dressed for: 7am to 10pm."
    assert lines[2] == "Temperature: 3°C to 9°C; it feels like 3°C to 9°C."
    assert lines[3] == f"Rain: {detail['rain']['words']} (70% chance, about 2.0 mm)."
    assert lines[4] == f"Wind: up to 30 km/h, gusts 50 ({detail['wind']['words']})."
    assert lines[5] == "Sun: UV index up to 6."
    assert lines[-1] == "Occasion: smart casual. Mood: usual."


def test_a_dry_humid_day_and_rain_with_nothing_known_of_it():
    hot = day.read([hour(h, 29.0, feels=33.0, humidity=80.0, uv=9.0) for h in range(24)])
    text = styling.day_words({"detail": hot}, context(), TUESDAY)
    assert "Rain: none expected in those hours." in text and "Sun: UV index up to 9. Humid." in text
    assert "Place:" not in text
    hot["rain"] = {"words": "showers", "chance": None, "mm": None}
    assert "Rain: showers." in styling.day_words({"detail": hot}, context(), TUESDAY).splitlines()


def test_wind_with_no_gusts_and_no_word():
    detail = day.read(a_day())
    detail["wind"] = {"kmh": 12.2, "gust_kmh": None, "words": None}
    assert "Wind: up to 12 km/h." in styling.day_words({"detail": detail}, context(), TUESDAY).splitlines()


@pytest.mark.parametrize("source, how", [("mild", "no forecast could be had, so a mild day is assumed"),
                                         ("given", "typed by the owner"), ("forecast", "the whole day's forecast"),
                                         (None, "the whole day's forecast")])
def test_without_the_hours_the_low_and_high_are_said_with_where_they_came_from(source, how):
    text = styling.day_words({"source": source}, context(rain=True), TUESDAY)
    assert f"Temperature: 5°C to 12°C; rain ({how})." in text.splitlines()
    dry = styling.day_words({"source": source}, context(), TUESDAY)
    assert f"Temperature: 5°C to 12°C; no rain ({how})." in dry.splitlines()


def test_the_owners_note_is_quoted_with_what_was_taken_from_it_only_when_it_counts():
    note = {"active": True, "text": "At a  fair all afternoon", "words": ["outside noon to 6pm", "at a fair"]}
    text = styling.day_words({"note": note}, context(), TUESDAY)
    assert "The owner's note about the day: “At a fair all afternoon” (read as: outside noon to 6pm; at a fair)." in text
    assert "note" not in styling.day_words({"note": {**note, "active": False}}, context(), TUESDAY)


def test_the_occasion_and_mood_are_in_plain_words():
    text = styling.day_words({}, context(occasion="smart_casual", mood="sharp"), TUESDAY)
    assert text.splitlines()[-1] == "Occasion: smart casual. Mood: sharp."


# ------------------------------------------------------------------ what was worn
NAMES = {"t1": "White tee", "b1": "Dark jeans", "s1": "White sneakers", "o1": "Navy coat"}


def worn_outfit(on="2026-11-16", **more):
    o = {"worn_on": on, "pieces": {"base": "t1", "mid": None, "outer": None, "bottom": "b1", "shoes": "s1",
                                   "accessories": []}, "context": {}, "rating": None, "rating_reasons": [],
         "rating_note": None}
    o.update(more)
    return o


def test_a_worn_outfit_is_told_by_its_pieces_names_with_its_day_and_what_the_owner_said():
    o = worn_outfit(pieces={"base": "t1", "outer": "o1", "bottom": "b1", "shoes": "s1", "accessories": ["gone"]},
                    context={"low_c": 4.6, "high_c": 9, "rain": True, "occasion": "smart_casual"},
                    rating="not_again", rating_reasons=["too_cold", "colours_clashed", "made_up"],
                    rating_note=" Felt   cold ")
    assert styling.history_words([o], NAMES) == (
        "- 2026-11-16 (5°C to 9°C, rain, smart casual): White tee, Navy coat, Dark jeans, White sneakers, "
        "a piece no longer in the closet. The owner: not again, too cold, the colours clashed, “Felt cold”.")


def test_an_unrated_and_a_loved_outfit():
    lines = styling.history_words([worn_outfit(context={"low_c": 10, "high_c": 15}),
                                   worn_outfit("2026-11-15", rating="loved", rating_reasons=["compliments"])],
                                  NAMES).splitlines()
    assert lines[0].endswith("(10°C to 15°C): White tee, Dark jeans, White sneakers. The owner: not rated.")
    assert lines[1].endswith("The owner: loved it, got compliments.")
    assert "fine." in styling.history_words([worn_outfit(rating="fine")], NAMES)


def test_the_owners_note_on_a_worn_outfit_is_cut_short():
    text = styling.history_words([worn_outfit(rating_note="y" * 500)], NAMES)
    assert f"“{'y' * styling.MAX_NOTE}”" in text and "y" * (styling.MAX_NOTE + 1) not in text


def test_only_the_newest_worn_outfits_are_told():
    worn = [worn_outfit(f"2026-10-{30 - i:02d}") for i in range(styling.HISTORY + 3)]
    lines = styling.history_words(worn, NAMES).splitlines()
    assert len(lines) == styling.HISTORY and lines[0].startswith("- 2026-10-30")
    assert f"2026-10-{30 - styling.HISTORY:02d}" not in "\n".join(lines)


def test_nothing_worn_and_outfits_with_no_pieces():
    assert styling.history_words([], NAMES) == "- Nothing has been recorded as worn yet."
    empty = [worn_outfit(pieces={}), worn_outfit(pieces=None), worn_outfit(pieces={"accessories": []})]
    assert styling.history_words(empty, NAMES) == "- Nothing has been recorded as worn yet."
    assert len(styling.history_words([*empty, worn_outfit()], NAMES).splitlines()) == 1


# ------------------------------------------------------------------ the rules' shortlist
def test_the_shortlist_gives_the_numbers_by_place():
    listing = styling.listed(closet(), context())
    engine = [{"pieces": {"base": "t1", "mid": "gone", "outer": "o1", "bottom": "b1", "shoes": "s1",
                          "accessories": ["a1", "gone", "a2"]}},
              {"pieces": {"base": "t2", "mid": "m1", "outer": None, "bottom": "b2", "shoes": "s2", "accessories": []}}]
    assert styling.shortlist_words(engine, listing).splitlines() == [
        "- base 2; outer layer 4; bottom 6; shoes 8; accessories 10, 11",
        "- base 1; mid layer 3; bottom 5; shoes 7",
    ]


def test_the_shortlist_is_cut_short_and_says_so_when_the_rules_found_nothing():
    listing = styling.listed(closet(), context())
    engine = [{"pieces": {"base": "t1", "bottom": "b1", "shoes": "s1"}}] * (styling.SHORTLIST + 4)
    assert len(styling.shortlist_words(engine, listing).splitlines()) == styling.SHORTLIST
    assert styling.shortlist_words([], listing) == "- The rules found no outfit."
    assert styling.shortlist_words([{"pieces": {"base": "gone"}}], listing) == "- The rules found no outfit."


# ------------------------------------------------------------------ the brief
def make_brief(ctx=None, profile=None, rows=None, worn=()):
    return styling.brief(rows or closet(), {"source": "given"}, ctx or context(), TUESDAY, list(worn), [], profile)


def test_the_brief_has_its_seven_blocks():
    blocks, listing = make_brief()
    assert set(blocks) == {"guide", "profile", "closet", "day", "worn", "shortlist", "must"}
    assert blocks["guide"] == styling.guide() and blocks["closet"] == "\n".join(listing.lines)
    assert blocks["day"].startswith("Date: Tuesday 17 November 2026.") and blocks["must"] == ""
    assert blocks["shortlist"] == "- The rules found no outfit."


def test_the_brief_uses_the_owners_profile_or_the_default():
    assert make_brief()[0]["profile"] == styling.DEFAULT_PROFILE
    assert make_brief(profile="   \n ")[0]["profile"] == styling.DEFAULT_PROFILE
    assert make_brief(profile="  Mostly dark colours.\n")[0]["profile"] == "Mostly dark colours."


def test_a_worn_piece_now_in_the_laundry_is_still_told_by_name():
    rows = closet()
    rows[0]["laundry"] = "dirty"
    blocks, listing = make_brief(rows=rows, worn=[worn_outfit()])
    assert "t1" not in listing.ids and "White tee, Dark jeans" in blocks["worn"]


def test_the_brief_says_what_every_outfit_must_hold():
    assert make_brief(context(build_around="o1"))[0]["must"] == (
        "Every outfit must include piece 4: the owner wants to build around it.")
    kept = outfits.Context(5, 12, keep=("t1", "b1", "gone"))
    assert make_brief(kept)[0]["must"] == (
        "Every outfit must include pieces 2, 6: the owner is wearing an outfit again.")
    both = outfits.Context(5, 12, build_around="a1", keep=("t1",))
    assert make_brief(both)[0]["must"].splitlines() == [
        "Every outfit must include piece 10: the owner wants to build around it.",
        "Every outfit must include pieces 2: the owner is wearing an outfit again."]


# ------------------------------------------------------------------ the check of the answer
def check(looks, ctx=None, not_again=None, rows=None):
    ctx = ctx or context()
    return styling.check(looks, styling.listed(rows or closet(), ctx), ctx, not_again)


def test_a_good_outfit_comes_back_in_the_engines_shape():
    kept, problems = check([look(2, 3, 4, 6, 8, [10], why="  Warm and\n easy. ", watch="Mind the rain.")])
    assert problems == []
    assert kept == [{"pieces": {"base": "t1", "mid": "m1", "outer": "o1", "bottom": "b1", "shoes": "s1",
                                "accessories": ["a1"]},
                     "score": None, "reasons": ["Warm and easy."], "warnings": ["Mind the rain."], "by": "claude"}]


def test_none_for_the_empty_layers_and_empty_lists_for_no_words():
    kept, _ = check([look(1, 0, 0, 5, 7, why="  ", watch="")])
    assert kept[0]["pieces"] == {"base": "t2", "mid": None, "outer": None, "bottom": "b2", "shoes": "s2",
                                 "accessories": []}
    assert kept[0]["reasons"] == [] and kept[0]["warnings"] == []


@pytest.mark.parametrize("change, words", [
    ({"base": 99}, "99 is not a piece in the list"),
    ({"base": 12}, "12 is not a piece in the list"),
    ({"bottom": -1}, "-1 is not a piece in the list"),
    ({"shoes": True}, "True is not a piece in the list"),
    ({"mid": "3"}, "3 is not a piece in the list"),
    ({"outer": 4.0}, "4.0 is not a piece in the list"),
    ({"base": 6}, "piece 6 cannot be worn as the base"),
    ({"shoes": 2}, "piece 2 cannot be worn as the shoes"),
    ({"base": 3}, "piece 3 cannot be worn as the base"),
    ({"outer": 11}, "piece 11 cannot be worn as the outer layer"),
    ({"base": 0}, "it has no base"),
    ({"bottom": 0}, "it has no bottom"),
    ({"shoes": 0, "base": 0}, "it has no base or shoes"),
    ({"base": 1, "mid": 1}, "the same piece is in two places"),
])
def test_an_outfit_that_cannot_be_worn_is_left_out_and_said(change, words):
    kept, problems = check([{**look(), **change}])
    assert kept == [] and problems == [f"Outfit 1 was left out: {words}."]


def test_an_outfit_with_nothing_in_it_is_left_out():
    kept, problems = check([{}])
    assert kept == [] and problems == ["Outfit 1 was left out: it has no base or bottom or shoes."]


def test_an_outfit_must_hold_the_piece_built_around():
    ctx = context(build_around="o1")
    kept, problems = check([look(), look(1, 0, 4, 5, 7)], ctx)
    assert problems == ["Outfit 1 was left out: it leaves out the piece to build around."]
    assert [k["pieces"]["outer"] for k in kept] == ["o1"]
    # an accessory to build around counts when it is among the accessories
    kept, problems = check([look(accessories=[10])], context(build_around="a1"))
    assert problems == [] and kept[0]["pieces"]["accessories"] == ["a1"]


def test_an_outfit_must_hold_every_piece_kept_from_an_outfit_worn_again():
    ctx = outfits.Context(5, 12, keep=("t1", "b1"))
    kept, problems = check([look(2, 0, 0, 5, 8), look(2, 0, 0, 6, 7)], ctx)
    assert problems == ["Outfit 1 was left out: it leaves out a piece kept from the outfit worn before."]
    assert len(kept) == 1 and kept[0]["pieces"]["bottom"] == "b1"


def test_an_outfit_the_owner_said_not_again_to_is_left_out():
    not_again = {("t1", "", "", "b1", "s1"): "2026-11-10"}
    kept, problems = check([look(), look(2, 0, 0, 6, 8, [10]), look(2, 3, 0, 6, 8)], not_again=not_again)
    assert problems == ["Outfit 1 was left out: the owner said “not again” to it on 2026-11-10.",
                        "Outfit 2 was left out: the owner said “not again” to it on 2026-11-10."]
    assert [k["pieces"]["mid"] for k in kept] == ["m1"]   # the same with a layer more is another outfit


def test_the_same_outfit_twice_in_one_answer_is_kept_once():
    kept, problems = check([look(why="first"), look(accessories=[9], why="second")])
    assert [k["reasons"] for k in kept] == [["first"]]
    assert problems == ["Outfit 2 was left out: it is the same as an outfit before it."]


@pytest.mark.parametrize("accessories, kept_ids", [
    ([99, 0, -2, True, "10"], []),      # not in the list
    ([2, 6, 8], []),                    # not accessories
    ([10, 9, 11], ["a1", "a2"]),        # a second belt
    ([10, 10], ["a1"]),                 # the same one twice
    ([11, 9], ["a2", "a3"]),
])
def test_a_wrong_accessory_is_dropped_and_the_outfit_stands(accessories, kept_ids):
    kept, problems = check([look(accessories=accessories)])
    assert problems == [] and kept[0]["pieces"]["accessories"] == kept_ids


def test_good_outfits_after_a_bad_one_are_kept_in_order():
    kept, problems = check([look(why="a"), look(base=99), look(1, 0, 0, 5, 7, why="c"), look(6), look(2, 3, 0, 5, 8,
                                                                                                 why="e")])
    assert [k["reasons"] for k in kept] == [["a"], ["c"], ["e"]]
    assert problems == ["Outfit 2 was left out: 99 is not a piece in the list.",
                        "Outfit 4 was left out: piece 6 cannot be worn as the base."]


def test_nothing_asked_nothing_kept():
    assert check([]) == ([], [])


# ------------------------------------------------------------------ the question to Claude
def test_the_prompt_holds_every_block_under_its_heading():
    blocks = {"guide": "GUIDE-TEXT", "profile": "PROFILE-TEXT", "closet": "CLOSET-TEXT", "day": "DAY-TEXT",
              "worn": "WORN-TEXT", "shortlist": "SHORTLIST-TEXT", "must": ""}
    text = stylist.prompt(blocks, 4)
    for heading, key in (("# How the owner dresses", "profile"), ("# The guide", "guide"),
                         ("# The closet: what can be worn today", "closet"), ("# Today", "day"),
                         ("# What the owner wore lately", "worn"), ("# A start from the app's rules", "shortlist")):
        assert heading in text and text.index(heading) < text.index(blocks[key])
    assert "4 outfits for today" in text and "3 outfits" not in text
    assert "It wins over the guide below." in text and "preferences to weigh, never rules" in text
    assert "Every outfit must" not in text
    assert stylist.prompt({**blocks, "must": "Every outfit must include piece 4."}).count(
        "Every outfit must include piece 4.") == 1
    assert f"{stylist.COUNT} outfits for today" in stylist.prompt(blocks)


def test_the_answers_outfits_go_through_the_check():
    answer = stylist.Looks(read="A cold day.", outfits=[
        stylist.Look(base=2, mid=3, outer=4, bottom=6, shoes=8, accessories=[10], why="Warm.", watch=""),
        stylist.Look(base=1, mid=0, outer=0, bottom=5, shoes=7, accessories=[], why="Light.", watch="Rain.")])
    plain = stylist.looks(answer)
    assert plain[0] == look(2, 3, 4, 6, 8, [10], why="Warm.")
    kept, problems = check(plain)
    assert problems == [] and [k["pieces"]["base"] for k in kept] == ["t1", "t2"]


def test_the_answers_form_refuses_anything_extra_or_loose():
    good = {"base": 1, "mid": 0, "outer": 0, "bottom": 5, "shoes": 7, "accessories": [], "why": "", "watch": ""}
    stylist.Look(**good)
    with pytest.raises(ValidationError):
        stylist.Look(**good, colour="navy")
    with pytest.raises(ValidationError):
        stylist.Look(**{**good, "base": "1"})
    with pytest.raises(ValidationError):
        stylist.Looks.model_validate({"read": "", "outfits": [good], "extra": 1})
    with pytest.raises(ValidationError):
        stylist.Looks.model_validate({"read": "", "outfits": [{**good, "extra": 1}]})


def test_claude_is_asked_once_in_text_on_the_stylists_model(monkeypatch):
    blocks, _ = make_brief(context(build_around="o1"))
    seen = []

    def fake_ask(text, images, routes, **kw):
        seen.append((text, images, routes, kw))
        return correcting.CorrectionResult(stylist.Looks(read="", outfits=[]), "plan", kw["model"])
    monkeypatch.setattr(stylist.correcting, "ask", fake_ask)
    result = stylist.ask(blocks, ("api", "plan"))
    assert result.route == "plan" and result.answer.outfits == []
    text, images, routes, kw = seen[0]
    assert text == stylist.prompt(blocks, stylist.COUNT) and images == [] and routes == ("api", "plan")
    for key in ("profile", "closet", "day", "worn", "shortlist", "must"):
        assert blocks[key] in text
    assert kw["answer_model"] is stylist.Looks and kw["system"] == stylist.SYSTEM
    assert (kw["model"], kw["effort"], kw["max_tokens"]) == (stylist.MODEL, stylist.EFFORT, stylist.MAX_TOKENS)
    assert kw["client"] is None and kw["exe"] is None and kw["meter"] is None
    meter, client = object(), object()
    stylist.ask(blocks, ("plan",), client=client, exe="claude", meter=meter, model="claude-x", effort="high", count=5)
    text, _, _, kw = seen[1]
    assert "5 outfits for today" in text
    assert (kw["model"], kw["effort"], kw["client"], kw["exe"], kw["meter"]) == ("claude-x", "high", client, "claude",
                                                                               meter)


@pytest.mark.parametrize("error", [RouteUnavailable("no route"), Unreachable("offline"), TaggingError("bad answer")])
def test_when_claude_cannot_answer_the_error_comes_through(monkeypatch, error):
    def fake_ask(*a, **kw):
        raise error
    monkeypatch.setattr(stylist.correcting, "ask", fake_ask)
    with pytest.raises(type(error)):
        stylist.ask(make_brief()[0], ("plan",))


# ------------------------------------------------------------------ the developer tool
@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("style_demo_days", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tools_hours_hold_each_temperature_until_the_next(tool):
    hours = tool.hours({5: (10, 9), 9: (14, 12)}, h3={"uv": 7.0}, h12={"rain_chance": 80})
    assert [h["hour"] for h in hours] == list(range(24))
    assert (hours[0]["temp_c"], hours[0]["feels_c"]) == (10, 9)   # before the first given hour: the first one
    assert hours[8]["temp_c"] == 10 and hours[9]["temp_c"] == 14 and hours[23]["feels_c"] == 12
    assert hours[3]["uv"] == 7.0 and hours[4]["uv"] == 2.0 and hours[12]["rain_chance"] == 80


def test_every_made_up_day_reads(tool):
    for key, spec in tool.DAYS.items():
        outside = tuple(spec["note"]["outside"]) if spec["note"] and spec["note"].get("outside") else None
        detail = day.read(spec["hours"], outside, now_hour=7)
        assert detail is not None, key
        ctx = context(occasion=spec["occasion"])
        assert styling.day_words({"detail": detail, "note": spec["note"]}, ctx, TUESDAY)
    assert day.read(tool.DAYS["cold"]["hours"], now_hour=7)["wet"] is True
    assert day.read(tool.DAYS["mild"]["hours"], now_hour=7)["wet"] is False


def test_the_tool_names_an_outfit_by_its_pieces(tool):
    names = {"a": "White tee", "b": "Dark jeans", "c": "Boots", "d": "Belt"}
    assert tool.name_of(names, {"base": "a", "mid": None, "bottom": "b", "shoes": "c", "accessories": ["d"]}) == (
        "White tee, Dark jeans, Boots, Belt")


def test_the_tool_refuses_an_unknown_day(tool):
    with pytest.raises(SystemExit):
        tool.main(["--days", "tuesday"])
    with pytest.raises(SystemExit):
        tool.main(["--days", ","])


def first_of(closet_text: str, place: str) -> tuple[int, str]:
    """The number and name of the first piece in the brief's closet that can take a place."""
    for line in closet_text.splitlines():
        head, kind = line.split(" | ")[:2]
        if f"({place}" in kind or f" {place})" in kind:
            n, name = head.split(". ", 1)
            return int(n), name
    raise AssertionError(f"no {place} in the demo closet")


def test_the_tool_prints_claudes_outfits_by_name(tool, monkeypatch, capsys):
    chosen = []

    def fake_ask(brief, routes, **kw):
        base, bottom, shoes = (first_of(brief["closet"], p) for p in ("base", "bottom", "shoes"))
        chosen.append((base[1], bottom[1], shoes[1]))
        answer = stylist.Looks(read="A mild day.", outfits=[stylist.Look(
            base=base[0], mid=0, outer=0, bottom=bottom[0], shoes=shoes[0], accessories=[], why="Easy.", watch="")])
        return SimpleNamespace(answer=answer, route="plan", output_tokens=400)
    monkeypatch.setattr(tool.stylist, "ask", fake_ask)
    assert tool.main(["--days", "mild"]) == 0
    out = capsys.readouterr().out
    assert len(chosen) == 1 and "Claude on the day: A mild day." in out
    assert f"1. {', '.join(chosen[0])}" in out and "Why: Easy." in out and "1 of 1 answered" in out


def test_the_tool_says_when_claude_gave_no_answer(tool, monkeypatch, capsys):
    def fake_ask(brief, routes, **kw):
        raise TaggingError("no usable answer")
    monkeypatch.setattr(tool.stylist, "ask", fake_ask)
    assert tool.main(["--days", "mild"]) == 1
    assert "No answer: TaggingError: no usable answer" in capsys.readouterr().out


def test_an_outfit_with_nothing_known_of_its_day_has_no_empty_brackets():
    # found by review: an outfit recorded with no temperatures or occasion read "2026-11-16 (): …"
    names = {"a": "White tee", "b": "Blue jeans", "c": "White sneakers"}
    for context in ({}, None, {"low_c": None, "high_c": None, "rain": False, "occasion": None}):
        worn = [{"worn_on": "2026-11-16", "pieces": {"base": "a", "bottom": "b", "shoes": "c"}, "context": context}]
        assert styling.history_words(worn, names) == \
            "- 2026-11-16: White tee, Blue jeans, White sneakers. The owner: not rated."


# ------------------------------------------------------------------ the conversation (styling.talk_words, keeps)
def shown_outfits():
    return [{"pieces": {"base": "t1", "mid": None, "outer": None, "bottom": "b1", "shoes": "s1", "accessories": ["a1"]},
             "reasons": ["  Easy and\n warm. "], "by": "claude"},
            {"pieces": {"base": "t2", "mid": "m1", "outer": None, "bottom": "b2", "shoes": "s2", "accessories": []},
             "reasons": ["The rules liked it."], "score": 80}]


def test_nothing_said_is_no_talk():
    listing = styling.listed(closet(), context())
    assert styling.talk_words([], listing) == ""
    assert styling.talk_words([], listing, shown_outfits()) == ""   # the outfits are only told with a message
    assert styling.talk_words([{"said": "  ", "reply": "Hello."}, {"said": None, "reply": None}], listing) == ""


def test_the_talk_tells_the_outfits_shown_by_their_numbers_then_what_was_said():
    listing = styling.listed(closet(), context())
    turns = [{"said": "Too  dressy.", "reply": " Plainer\n it is. "}]
    assert styling.talk_words(turns, listing, shown_outfits(), "  Swap the\n boots ").splitlines() == [
        "The outfits on the owner's screen now, in order (the owner may call them the first, the second and so on):",
        "- Outfit 1 (yours): base 2; bottom 6; shoes 8; accessories 10. You said: “Easy and warm.”",
        "- Outfit 2 (from the app's rules): base 1; mid layer 3; bottom 5; shoes 7.",
        "What was said today, oldest first:",
        "- The owner: “Too dressy.”",
        "- You: “Plainer it is.”",
        "- The owner, just now: “Swap the boots”",
    ]


def test_without_a_message_the_talk_is_only_what_was_said():
    listing = styling.listed(closet(), context())
    turns = [{"said": "Too dressy.", "reply": "Plainer it is."}]
    assert styling.talk_words(turns, listing, shown_outfits()) == (
        "What was said today, oldest first:\n- The owner: “Too dressy.”\n- You: “Plainer it is.”")
    assert styling.talk_words(turns, listing) == styling.talk_words(turns, listing, shown_outfits())


def test_a_turn_with_no_answer_says_it_did_not_reach_the_owner():
    listing = styling.listed(closet(), context())
    for reply in (None, "", "  "):
        assert styling.talk_words([{"said": "Too dressy.", "reply": reply}], listing).splitlines()[-1] == (
            "- (your answer did not reach them)")


def test_only_the_newest_talk_turns_are_told():
    listing = styling.listed(closet(), context())
    turns = [{"said": f"Message {i}.", "reply": f"Answer {i}."} for i in range(styling.TALK_TURNS + 3)]
    lines = styling.talk_words(turns, listing).splitlines()
    assert len(lines) == 1 + 2 * styling.TALK_TURNS
    assert lines[1] == "- The owner: “Message 3.”" and lines[-1] == f"- You: “Answer {styling.TALK_TURNS + 2}.”"
    assert "Message 2." not in "\n".join(lines)


@pytest.mark.parametrize("looking_at, said", [(0, ", with outfit 1 in front of them"),
                                              (1, ", with outfit 2 in front of them"),
                                              (2, ""), (-1, ""), (True, ""), (None, ""), ("0", "")])
def test_the_outfit_in_front_of_the_owner_is_told_only_when_it_is_on_the_screen(looking_at, said):
    listing = styling.listed(closet(), context())
    text = styling.talk_words([], listing, shown_outfits(), "Not this one.", looking_at)
    assert text.splitlines()[-1] == f"- The owner, just now{said}: “Not this one.”"
    assert "in front of them" not in styling.talk_words([], listing, None, "Not this one.", 0)


def test_things_to_remember_are_kept_with_where_they_would_go():
    listing = styling.listed(closet(), context())   # piece 2 is the white tee
    got = styling.keeps([{"about": 0, "text": "  I like   navy. "}, {"about": 2, "text": "Only under a layer."}], listing)
    assert got == [
        {"kind": "style", "item_id": None, "name": None, "text": "I like navy.", "state": "offered"},
        {"kind": "piece", "item_id": "t1", "name": "White tee", "text": "Only under a layer.", "state": "offered"},
    ]
    assert styling.keeps([{"text": "No about is my style."}, {"about": None, "text": "Nor is None."}], listing) == [
        {"kind": "style", "item_id": None, "name": None, "text": "No about is my style.", "state": "offered"},
        {"kind": "style", "item_id": None, "name": None, "text": "Nor is None.", "state": "offered"}]
    assert styling.STYLE == "style" and styling.PIECE == "piece" and styling.MAX_KEEPS == 2


@pytest.mark.parametrize("thing", [{"about": 12, "text": "No such piece."}, {"about": -1, "text": "Below."},
                                   {"about": True, "text": "A yes."}, {"about": "2", "text": "Words."},
                                   {"about": 2.0, "text": "A float."}, {"about": 0, "text": ""},
                                   {"about": 0, "text": "   "}, {"about": 0, "text": 5}, {"about": 0}, "I like navy.",
                                   None, 3])
def test_a_thing_with_no_text_or_about_no_piece_is_dropped(thing):
    assert styling.keeps([thing], styling.listed(closet(), context())) == []


def test_things_to_remember_must_be_a_list():
    listing = styling.listed(closet(), context())
    for offered in (None, {"about": 0, "text": "I like navy."}, "I like navy.", 3):
        assert styling.keeps(offered, listing) == []


def test_a_thing_offered_twice_is_kept_once_and_at_most_max_keeps():
    listing = styling.listed(closet(), context())
    got = styling.keeps([{"about": 0, "text": "One."}, {"about": 0, "text": " One. "}, {"about": 2, "text": "One."},
                         {"about": 0, "text": "Two."}], listing)
    assert [(k["item_id"], k["text"]) for k in got] == [(None, "One."), ("t1", "One.")]
    assert len(styling.keeps([{"about": 0, "text": f"Thing {i}."} for i in range(5)], listing)) == styling.MAX_KEEPS


def test_a_thing_to_remember_is_cut_to_max_note():
    got = styling.keeps([{"about": 0, "text": "z" * 500}], styling.listed(closet(), context()))
    assert got[0]["text"] == "z" * styling.MAX_NOTE


# ------------------------------------------------------------------ the conversation in the question to Claude
BLOCKS = {"guide": "GUIDE-TEXT", "profile": "PROFILE-TEXT", "closet": "CLOSET-TEXT", "day": "DAY-TEXT",
          "worn": "WORN-TEXT", "shortlist": "SHORTLIST-TEXT", "must": ""}
HOLDS = "What the owner told you earlier today (the conversation above) still holds: keep to it."


def test_a_plain_prompt_asks_for_outfits_and_a_line_about_the_day_with_no_conversation():
    text = stylist.prompt(BLOCKS)
    assert "# What to give" in text and "`read`" in text
    assert "# The conversation" not in text and HOLDS not in text and "`reply`" not in text
    assert "`remember`" not in text and text.endswith("- `read`: one sentence on what about today shaped your choices.")


def test_a_plain_prompt_after_a_conversation_tells_it_and_says_it_still_holds():
    text = stylist.prompt({**BLOCKS, "talk": "TALK-TEXT"})
    assert "# The conversation with the owner today\nTALK-TEXT" in text
    assert text.index("SHORTLIST-TEXT") < text.index("TALK-TEXT") < text.index("# What to give")
    assert HOLDS in text and "`read`" in text and "`reply`" not in text
    assert f"{stylist.COUNT} outfits for today" in text


def test_a_prompt_with_a_message_asks_for_a_reply_outfits_and_things_to_remember_not_a_read():
    text = stylist.prompt({**BLOCKS, "talk": "TALK-TEXT", "say": "Too dressy."})
    assert "# The conversation with the owner today\nTALK-TEXT" in text
    assert "`reply`" in text and "`outfits`" in text and "`remember`" in text
    assert f"give {stylist.COUNT} outfits again" in text
    assert "`read`" not in text and HOLDS not in text and "outfits for today, the best first" not in text
    assert "Every outfit must" not in text
    must = "Every outfit must include piece 4: the owner wants to build around it."
    assert stylist.prompt({**BLOCKS, "talk": "T", "say": "Too dressy.", "must": must}).count(must) == 1
    assert "give 5 outfits again" in stylist.prompt({**BLOCKS, "talk": "T", "say": "Too dressy."}, 5)


def test_a_message_is_asked_with_the_reply_form_and_more_room(monkeypatch):
    seen = []

    def fake_ask(text, images, routes, **kw):
        seen.append((text, kw))
        model = kw["answer_model"]
        answer = (stylist.Reply(reply="Plainer.", outfits=[], remember=[]) if model is stylist.Reply
                  else stylist.Looks(read="", outfits=[]))
        return correcting.CorrectionResult(answer, "api", kw["model"])
    monkeypatch.setattr(stylist.correcting, "ask", fake_ask)
    talking = {**BLOCKS, "talk": "TALK-TEXT", "say": "Too dressy."}
    assert stylist.ask(talking, ("api",)).answer.reply == "Plainer."
    text, kw = seen[-1]
    assert text == stylist.prompt(talking, stylist.COUNT)
    assert kw["answer_model"] is stylist.Reply and kw["max_tokens"] == stylist.TALK_MAX_TOKENS
    assert kw["system"] == stylist.SYSTEM and (kw["model"], kw["effort"]) == (stylist.MODEL, stylist.EFFORT)
    for brief in ({**BLOCKS, "talk": "TALK-TEXT"}, {**BLOCKS, "talk": "TALK-TEXT", "say": ""}):
        stylist.ask(brief, ("api",))
        assert seen[-1][1]["answer_model"] is stylist.Looks and seen[-1][1]["max_tokens"] == stylist.MAX_TOKENS
    assert stylist.TALK_MAX_TOKENS > stylist.MAX_TOKENS


def test_given_turns_a_plain_answer_into_what_the_job_takes():
    one = stylist.Look(base=1, mid=0, outer=0, bottom=2, shoes=3, accessories=[], why="Warm.", watch="")
    result = correcting.CorrectionResult(stylist.Looks(read="Cold.", outfits=[one]), "plan", "m", 10, 5)
    assert stylist.given(result) == {"looks": [one.model_dump()], "read": "Cold.", "reply": None, "remember": [],
                                     "route": "plan", "model": "m", "input_tokens": 10, "output_tokens": 5}


def test_given_turns_a_reply_into_what_the_job_takes():
    one = stylist.Look(base=1, mid=0, outer=0, bottom=2, shoes=3, accessories=[4], why="Plainer.", watch="")
    answer = stylist.Reply(reply="Plainer it is.", outfits=[one],
                           remember=[stylist.Keep(about=0, text="I don't wear a blazer on weekends.")])
    result = correcting.CorrectionResult(answer, "api", "m", 20, 8)
    assert stylist.given(result) == {"looks": [one.model_dump()], "read": None, "reply": "Plainer it is.",
                                     "remember": [{"about": 0, "text": "I don't wear a blazer on weekends."}],
                                     "route": "api", "model": "m", "input_tokens": 20, "output_tokens": 8}


def test_the_reply_form_refuses_anything_extra_or_loose():
    stylist.Reply.model_validate({"reply": "Yes.", "outfits": [], "remember": [{"about": 0, "text": "I like navy."}]})
    with pytest.raises(ValidationError):
        stylist.Reply.model_validate({"reply": "Yes.", "outfits": [], "remember": [], "read": "Cold."})
    with pytest.raises(ValidationError):
        stylist.Reply.model_validate({"reply": "Yes.", "outfits": []})
    with pytest.raises(ValidationError):
        stylist.Reply.model_validate({"reply": "Yes.", "outfits": [], "remember": [{"about": 0, "text": "x", "why": 1}]})
    with pytest.raises(ValidationError):
        stylist.Keep.model_validate({"about": "0", "text": "I like navy."})
    with pytest.raises(ValidationError):
        stylist.Keep.model_validate({"about": 0, "text": "I like navy.", "kind": "style"})


# ------------------------------------------------------------------ the look at the outfits as drawn
LOOK_BLOCKS = {**BLOCKS, "chosen": "CHOSEN-TEXT"}


def test_the_look_prompt_has_the_day_the_profile_the_closet_and_the_outfits_chosen_under_their_headings():
    text = stylist.look_prompt(LOOK_BLOCKS, 3)
    for heading, key in (("# Today", "day"), ("# How the owner dresses", "profile"),
                         ("# The closet: what can be worn today", "closet"), ("# The outfits you chose", "chosen")):
        assert heading in text and text.index(heading) < text.index(LOOK_BLOCKS[key])
    assert "outfit-1.png is outfit 1" in text


def test_the_look_prompt_asks_for_outfits_and_what_was_seen_and_to_keep_an_outfit_unless_the_picture_shows_a_problem():
    text = stylist.look_prompt(LOOK_BLOCKS, 3)
    assert "`outfits`: the final 3 outfits" in text and "`saw`:" in text
    assert "Change an outfit only where the picture shows something you would really fix" in text
    assert "Otherwise keep it exactly as it is, with the same numbers." in text
    assert "`outfits`: the final 2 outfits" in stylist.look_prompt(LOOK_BLOCKS, 2)


def test_the_look_prompt_leaves_out_the_guide_the_worn_history_and_the_shortlist():
    text = stylist.look_prompt(LOOK_BLOCKS, 3)
    for left_out in ("GUIDE-TEXT", "WORN-TEXT", "SHORTLIST-TEXT", "# The guide", "# What the owner wore lately"):
        assert left_out not in text


def test_the_look_asks_claude_with_the_seen_form_one_named_picture_each_and_its_own_limits(monkeypatch):
    seen = []

    def fake_ask(text, images, routes, **kw):
        seen.append((text, images, routes, kw))
        return correcting.CorrectionResult(stylist.Seen(saw="", outfits=[]), "api", kw["model"])
    monkeypatch.setattr(stylist.correcting, "ask", fake_ask)
    pictures = ["first", "second", "third"]
    result = stylist.look(LOOK_BLOCKS, pictures, ("api", "plan"))
    assert result.route == "api" and result.answer.outfits == []
    text, images, routes, kw = seen[0]
    assert text == stylist.look_prompt(LOOK_BLOCKS, 3) and images == pictures and routes == ("api", "plan")
    assert kw["names"] == ["outfit-1.png", "outfit-2.png", "outfit-3.png"]
    assert kw["answer_model"] is stylist.Seen and kw["system"] == stylist.SYSTEM
    assert (kw["model"], kw["effort"], kw["max_tokens"], kw["timeout"]) == (
        stylist.MODEL, stylist.LOOK_EFFORT, stylist.LOOK_MAX_TOKENS, stylist.LOOK_TIMEOUT)
    assert kw["client"] is None and kw["exe"] is None and kw["meter"] is None
    meter, client = object(), object()
    stylist.look(LOOK_BLOCKS, ["one"], ("plan",), client=client, exe="claude", meter=meter, model="claude-x",
                 effort="high")
    text, _, _, kw = seen[1]
    assert "the final 1 outfits" in text and kw["names"] == ["outfit-1.png"]
    assert (kw["model"], kw["effort"], kw["client"], kw["exe"], kw["meter"]) == ("claude-x", "high", client, "claude",
                                                                               meter)


def test_the_look_is_asked_on_the_styling_model_at_low_effort_with_a_bound_on_time():
    assert stylist.MODEL == stylist.CONFIG["roles"]["styling"]
    assert stylist.LOOK_EFFORT == "low" and 0 < stylist.LOOK_TIMEOUT and 0 < stylist.LOOK_MAX_TOKENS
    assert stylist.PICTURE_WIDTH == 360


@pytest.mark.parametrize("error", [RouteUnavailable("no route"), Unreachable("offline"), TaggingError("bad answer")])
def test_when_the_look_cannot_be_answered_the_error_comes_through(monkeypatch, error):
    def fake_ask(*a, **kw):
        raise error
    monkeypatch.setattr(stylist.correcting, "ask", fake_ask)
    with pytest.raises(type(error)):
        stylist.look(LOOK_BLOCKS, ["p"], ("plan",))


def test_seen_turns_a_look_into_what_the_job_takes():
    one = stylist.Look(base=1, mid=0, outer=4, bottom=2, shoes=3, accessories=[5], why="Lighter.", watch="")
    result = correcting.CorrectionResult(stylist.Seen(saw="Too dark.", outfits=[one]), "plan", "m", 30, 9)
    assert stylist.seen(result) == {"looks": [one.model_dump()], "saw": "Too dark.", "route": "plan", "model": "m",
                                    "input_tokens": 30, "output_tokens": 9}


def test_the_seen_form_refuses_anything_extra_or_loose():
    good = look()
    stylist.Seen.model_validate({"saw": "", "outfits": [good]})
    with pytest.raises(ValidationError):
        stylist.Seen.model_validate({"saw": "", "outfits": [good], "read": "Cold."})
    with pytest.raises(ValidationError):
        stylist.Seen.model_validate({"saw": "", "outfits": [{**good, "extra": 1}]})
    with pytest.raises(ValidationError):
        stylist.Seen.model_validate({"outfits": [good]})
    with pytest.raises(ValidationError):
        stylist.Seen.model_validate({"saw": None, "outfits": []})


def test_the_outfits_chosen_are_told_by_number_with_their_pictures_and_why():
    listing = styling.listed(closet(), context())
    found = [{"pieces": {"base": "t1", "mid": "m1", "outer": "o1", "bottom": "b1", "shoes": "s2",
                         "accessories": ["a1", "a2"]}, "reasons": ["Warm  and\n easy."]},
             {"pieces": {"base": "t2", "mid": None, "outer": None, "bottom": "b2", "shoes": "s1", "accessories": []}},
             {"pieces": {"base": "t2", "bottom": "b1", "shoes": "s2"}, "reasons": []}]
    assert styling.chosen_words(found, listing) == (
        "- Outfit 1 (outfit-1.png): base 2; mid layer 3; outer layer 4; bottom 6; shoes 7; accessories 10, 11. "
        "Why you chose it: “Warm and easy.”\n"
        "- Outfit 2 (outfit-2.png): base 1; bottom 5; shoes 8.\n"
        "- Outfit 3 (outfit-3.png): base 1; bottom 6; shoes 7.")
    assert styling.chosen_words([], listing) == ""


def test_the_outfits_chosen_are_told_with_what_check_made_of_claudes_answer():
    ctx = context()
    listing = styling.listed(closet(), ctx)
    kept, _ = styling.check([look(base=1, outer=4, accessories=[9], why="Sharp."), look()], listing, ctx)
    assert styling.chosen_words(kept, listing).splitlines() == [
        "- Outfit 1 (outfit-1.png): base 1; outer layer 4; bottom 6; shoes 8; accessories 9. Why you chose it: “Sharp.”",
        "- Outfit 2 (outfit-2.png): base 2; bottom 6; shoes 8."]


# ------------------------------------------------------------------ the taxonomy file, where the program keeps it
def test_the_guide_is_read_where_the_packaged_program_keeps_the_taxonomy(tmp_path, monkeypatch):
    """The packaged program has no docs/ folder: it keeps the owner's taxonomy next to the tagger
    (packaging/closet.spec), and `taxonomy.load` looks in both places. The stylist's guide once built its own path
    to docs/, so every outfit asked of Claude failed on the owner's computer (FileNotFoundError)."""
    packaged = tmp_path / "closet" / "tagger" / "menswear-taxonomy.json"
    packaged.parent.mkdir(parents=True)
    packaged.write_text(json.dumps(taxonomy.load()), encoding="utf-8")
    monkeypatch.setattr(taxonomy, "TAXONOMY_FILES", (tmp_path / "docs" / "menswear-taxonomy.json", packaged))
    assert styling.guide() == styling.guide(packaged) and styling.guide()


def test_only_the_taxonomy_module_says_where_the_taxonomy_file_is():
    """Every reader goes through `taxonomy.load`, which knows where a source checkout and the packaged program keep
    the file; a path of its own to docs/ works from the repository and nowhere else."""
    import re
    from pathlib import Path

    import closet
    root = Path(closet.__file__).resolve().parent
    found = []
    for path in root.rglob("*.py"):
        if path == root / "tagger" / "taxonomy.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"""["']menswear-taxonomy\.json["']""", code):
                found.append(f"{path.relative_to(root)}:{n}")
    assert found == []
