"""Give it an outing on Today (what closet/today.py does with closet/outing.py): the outing takes the last place and
says what the sentence needs, the day's piece is kept, "Not this piece" ends it, no outing on a day ahead, a trip day,
or over a piece built around, and with Claude choosing the rules' outing keeps the last place and nothing more is
sent. The whole day is given, so no forecast is looked up; Claude is stood in for."""
import json
from datetime import date, timedelta

from closet import db

from . import test_stylejobs
from .test_plans import add_trip
from .test_stylejobs import DAY, TODAY, make_item, today

fixed_today = test_stylejobs.fixed_today   # the stylist's fixtures: today's date, and Claude stood in for
styled = test_stylejobs.styled

LONG_AGO = "2026-08-01T09:00:00.000000Z"


def wardrobe(c) -> dict[str, str]:
    """A small closet for a cool day, three outfits' worth, and a tweed jacket you like, added in August, never worn;
    everything else was worn six days ago."""
    ids = {
        "tee": make_item(c, "tee", "White tee", "tee", "white", formality="casual"),
        "tee2": make_item(c, "tee2", "Grey tee", "tee", "grey", formality="casual"),
        "shirt": make_item(c, "shirt", "Blue oxford", "shirt", "light_blue", formality="casual"),
        "hoodie": make_item(c, "hoodie", "Grey hoodie", "hoodie", "grey", formality="casual"),
        "jacket": make_item(c, "jacket", "Navy jacket", "jacket", "navy", formality="casual", rating="love"),
        "chinos": make_item(c, "chinos", "Tan chinos", "trousers", "tan", formality="casual"),
        "jeans": make_item(c, "jeans", "Dark jeans", "jeans", "navy", formality="casual"),
        "sneakers": make_item(c, "sneakers", "White sneakers", "sneakers", "white", formality="casual"),
        "tweed": make_item(c, "tweed", "Tweed jacket", "jacket", "olive", formality="casual", season="cool", rating="like"),
    }
    worn_on = (TODAY - timedelta(days=6)).isoformat()
    r = c.post("/api/wears", json={"item_ids": [v for k, v in ids.items() if k != "tweed"], "worn_on": worn_on})
    assert r.status_code == 201, r.text
    return ids


def backdate(cfg, profile, item_id):
    conn = db.connect(cfg.db_path(profile))
    conn.execute("UPDATE items SET created_at = ? WHERE id = ?", (LONG_AGO, item_id))
    conn.close()


def outings(cfg, profile="owner"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return [dict(r) for r in conn.execute("SELECT day, item_id, since, never_worn, turned_down FROM outings")]
    finally:
        conn.close()


def closet_with_outing(styled):
    ids = wardrobe(styled.c)
    backdate(styled.cfg, styled.sv.state.get("profile"), ids["tweed"])
    return ids


def off(styled):
    assert styled.c.put("/api/settings", json={"stylist_on": False}).status_code == 200


def test_the_outing_takes_the_last_place_and_says_what_the_sentence_needs(styled):
    off(styled)
    ids = closet_with_outing(styled)
    body = today(styled.c)
    *rest, last = body["outfits"]
    assert len(body["outfits"]) == 3 and all("outing" not in o for o in rest)
    assert last["outing"] == {"item_id": ids["tweed"], "rating": "like", "since": "2026-08-01", "never_worn": True,
                              "plural": False}
    assert ids["tweed"] in last["pieces"].values() and not last["warnings"]
    assert all(ids["tweed"] not in o["pieces"].values() for o in rest)
    assert outings(styled.cfg, styled.sv.state.get("profile")) == [
        {"day": TODAY.isoformat(), "item_id": ids["tweed"], "since": "2026-08-01", "never_worn": 1, "turned_down": 0}]
    assert today(styled.c)["outfits"] == body["outfits"]   # a reload gives the same


def test_not_this_piece_on_the_outing_gives_an_ordinary_outfit_back_for_the_day(styled):
    off(styled)
    ids = closet_with_outing(styled)
    before = today(styled.c)
    body = today(styled.c, leave_out=[ids["tweed"]])
    assert len(body["outfits"]) == 3 and not any("outing" in o for o in body["outfits"])
    assert body["outfits"][:2] == before["outfits"][:2]
    assert outings(styled.cfg, styled.sv.state.get("profile"))[0]["turned_down"] == 1
    # turned down for the day, whatever the page asks next
    assert not any("outing" in o for o in today(styled.c)["outfits"])


def test_a_day_ahead_a_trip_day_and_a_piece_built_around_carry_no_outing(styled):
    off(styled)
    ids = closet_with_outing(styled)
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert not any("outing" in o for o in today(styled.c, day=tomorrow)["outfits"])
    assert not any("outing" in o for o in today(styled.c, build_around=ids["shirt"])["outfits"])
    assert outings(styled.cfg, styled.sv.state.get("profile")) == []
    add_trip(styled.sv, TODAY, TODAY + timedelta(days=3))
    assert not any("outing" in o for o in today(styled.c)["outfits"])
    assert outings(styled.cfg, styled.sv.state.get("profile")) == []


def test_wearing_the_outing_records_the_wear(styled):
    off(styled)
    ids = closet_with_outing(styled)
    last = today(styled.c)["outfits"][-1]
    pieces = [v for k, v in last["pieces"].items() if k != "accessories" and v]
    r = styled.c.post("/api/wears", json={"item_ids": pieces, "outfit": {
        "pieces": last["pieces"], "score": last["score"], "reasons": last["reasons"], "warnings": last["warnings"],
        "context": {**DAY, "occasion": "casual", "mood": "usual"}}})
    assert r.status_code == 201, r.text
    assert styled.c.get(f"/api/items/{ids['tweed']}").json()["last_worn"] == TODAY.isoformat()


def test_with_claude_choosing_the_rules_outing_keeps_the_last_place_and_nothing_more_is_sent(styled):
    ids = closet_with_outing(styled)
    first = today(styled.c)
    assert first["context"]["stylist"]["state"] == "working" and first["outfits"][-1]["outing"]["item_id"] == ids["tweed"]
    styled.held.pop()()
    body = today(styled.c)
    assert body["context"]["stylist"]["state"] == "ready"
    assert body["outfits"][0]["by"] == "claude"
    assert body["outfits"][-1]["outing"]["item_id"] == ids["tweed"] and "by" not in body["outfits"][-1]
    [(brief, _)] = styled.stand_in.calls
    assert "outing" not in json.dumps(brief).lower()   # Claude is told nothing about it
    # the owner writes about the outfits: Claude is told the outing is the rules', in the last place, as shown
    styled.c.post("/api/outfits/today", json={**DAY, "say": "Why the tweed?", "looking_at": 2})
    styled.held.pop()()
    talk = styled.stand_in.calls[-1][0]["talk"]
    assert "Outfit 3 (from the app's rules)" in talk
    assert date.fromisoformat(outings(styled.cfg, styled.sv.state.get("profile"))[0]["day"]) == TODAY
