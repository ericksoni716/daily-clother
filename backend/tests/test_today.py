"""Today's own rules beside the engine's (`closet/today.py`): which pieces of an outfit worn before come back."""
import dataclasses

from closet import outfits, today


def item(id, category, color="navy", formality=None, season="all", **kw):
    return {"id": id, "name": kw.pop("name", f"{color} {category}"), "category": category, "color": color,
            "color_hex": None, "pattern": "solid", "formality": formality, "season": season, "silhouette": {},
            "material": None, "rating": kw.pop("rating", None), "status": kw.pop("status", "active"),
            "location": "closet", **kw}


def small_closet(*more):
    return [item("tee", "tee", "white", "casual", name="White tee"), item("jeans", "jeans", "navy", "casual", name="Dark jeans"),
            item("sneakers", "sneakers", "white", "casual", name="White sneakers"), *more]


def worn_outfit(**pieces):
    return {"id": "o1", "worn_on": "2026-11-01", "pieces": {"base": None, "mid": None, "outer": None, "bottom": None,
                                                           "shoes": None, "accessories": [], **pieces}}


def wear_again(rows, before, ctx=None):
    """What Today does with `again` (today.suggest): the pieces that can still be worn keep their places."""
    ctx = ctx or outfits.Context(15, 21)
    again = today.again_of(before, rows, set(ctx.leave_out))
    return again, outfits.suggest(rows, dataclasses.replace(ctx, keep=tuple(again["kept"])))


def test_wear_this_again_fills_in_for_a_piece_that_is_waiting_to_be_mended():
    # as for a piece in the wash: keep the rest, fill the place, and name what was left out (Today showed no outfit,
    # "The pieces kept from that outfit do not make an outfit for today.")
    rows = small_closet(item("chinos", "trousers", "tan", "casual", name="Tan chinos"))
    rows[1]["condition"] = "needs_repair"   # the jeans
    again, answer = wear_again(rows, worn_outfit(base="tee", bottom="jeans", shoes="sneakers"))
    assert answer["outfits"], answer["missing"]
    assert again["unavailable"] == ["jeans"] and again["kept"] == ["tee", "sneakers"]
    assert answer["outfits"][0]["pieces"]["bottom"] == "chinos"


def test_wear_this_again_works_for_what_was_worn_to_tennis():
    # tennis shoes, swim trunks and lounge pants are never chosen by Nines, but the owner wore them and asks for that
    # outfit again by name, as when building around a piece
    rows = small_closet(item("shorts", "shorts", "navy", "casual", "warm", name="Navy shorts"),
                        item("tennis", "sneakers", "white", "athletic", name="Tennis shoes", kind="tennis_shoe"))
    again, answer = wear_again(rows, worn_outfit(base="tee", bottom="shorts", shoes="tennis"), outfits.Context(22, 26))
    assert again["kept"] == ["tee", "shorts", "tennis"] and again["unavailable"] == []
    assert answer["outfits"], answer["missing"]
    assert all(o["pieces"]["shoes"] == "tennis" for o in answer["outfits"])
    # they still do not come into an outfit that is not the one worn again
    assert all(o["pieces"]["shoes"] != "tennis" for o in outfits.suggest(rows, outfits.Context(22, 26))["outfits"])
    # lounge pants worn at home come back too
    rows.append(item("lounge", "trousers", "red", "casual", name="Tartan lounge pants", kind="lounge_pants"))
    again, answer = wear_again(rows, worn_outfit(base="tee", bottom="lounge", shoes="sneakers"))
    assert again["kept"] == ["tee", "lounge", "sneakers"] and answer["outfits"][0]["pieces"]["bottom"] == "lounge"
