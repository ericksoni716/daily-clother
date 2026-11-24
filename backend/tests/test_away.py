"""Where a piece is (closet/away.py): away at the cleaner's, at the tailor's or lent out, left out like the laundry,
still owned, and back again. The rules first (outfits, trips, gaps, insights, what Claude is told), then the routes."""
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from closet import aboutyou, db, gaps, outfits, styling, trips, wears, wouldwork
from closet.tagger import stylist

from . import test_insights as ti
from .conftest import upload
from .test_gaps import all_gaps, full_closet
from .test_gaps import log as gap_log
from .test_outfits import basic_closet, day, ids_of
from .test_styling import TUESDAY
from .test_styling import closet as styling_closet
from .test_styling import context as styling_context
from .test_trips import days as trip_days

TODAY = date(2026, 11, 23)
SECRET = "keep-this-on-the-computer-7f3a"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    # Both clocks on TODAY: the day the app takes as today, and the time it stamps on what happens (a return is
    # shown as today's when its stamp falls on today). Moving only the first passed only on 23 November.
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(db, "now", lambda: datetime.combine(TODAY, datetime.now().time()).astimezone(UTC)
                        .strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def away(items, item_id, place="cleaner", until=None, note=None):
    for i in items:
        if i["id"] == item_id:
            i.update(away=place, away_since="2026-11-20", away_until=until, away_note=note)
    return items


# ---------------------------------------------------------------------- outfits
def test_an_away_piece_is_not_offered_and_is_said_as_the_reason_like_the_laundry():
    items = away(basic_closet(), "jeans1")
    seen = {i for low in (-2, 8, 15, 24) for o in outfits.suggest(items, day(low, low + 6), 5)["outfits"] for i in ids_of(o)}
    assert "jeans1" not in seen and "trousers1" in seen
    assert outfits._unavailable(items[7], day(15)) == "at the cleaner's"
    assert "at the cleaner's" in outfits.OWNED_REASONS and "lent out" in outfits.OWNED_REASONS
    # asked for by name: said with the day it is expected back, the way "in the laundry" is said
    away(items, "jeans1", until="2026-11-27")
    built = outfits.suggest(items, day(15, 21, build_around="jeans1"), 3)
    assert built["outfits"] == []
    assert built["missing"] == ["The blue jeans jeans1 are at the cleaner's until Friday 27 November, so there is nothing "
                                "to build around them."]
    away(items, "jeans1", place="lent", until="2026-11-27")
    assert "are lent out until Friday 27 November" in outfits.suggest(items, day(15, build_around="jeans1"), 3)["missing"][0]


def test_with_nothing_else_the_closet_says_how_many_are_away():
    items = [i for i in basic_closet() if i["category"] not in ("sneakers", "dress_shoes", "boots", "sandals")]
    items += [{**basic_closet()[10], "away": "lent"}]
    assert outfits.suggest(items, day(15), 3)["missing"] == ["None of your shoes can be worn today: 1 lent out."]


def test_wear_this_again_fills_the_place_of_an_away_piece():
    from closet import today
    rows = away(basic_closet(), "jeans1", "tailor")
    again = today.again_of({"id": "w1", "worn_on": "2026-11-20", "pieces": {"base": "tee1", "bottom": "jeans1",
                                                                            "shoes": "sneakers1"}}, rows, set())
    assert again["kept"] == ["tee1", "sneakers1"] and again["unavailable"] == ["jeans1"]


# ---------------------------------------------------------------------- trips
def test_a_trip_packs_an_away_piece_only_when_it_is_expected_back_before_the_first_day():
    first = trip_days(3)[0]["date"]   # 2026-12-01
    gone = away(basic_closet(), "coat1")
    plan = trips.plan(gone, trip_days(3), {"pin": ["coat1"]})
    assert "coat1" not in {p["id"] for p in plan["packed"]}
    assert any("is at the cleaner's, so it is not packed" in n for n in plan["notes"])
    on_the_day = trips.plan(away(gone, "coat1", until=first), trip_days(3), {"pin": ["coat1"]})
    assert "coat1" not in {p["id"] for p in on_the_day["packed"]}
    before = trips.plan(away(gone, "coat1", until="2026-11-27"), trip_days(3), {"pin": ["coat1"]})
    assert "coat1" in {p["id"] for p in before["packed"]}
    assert ("The black coat coat1 is at the cleaner's until Friday 27 November: this plan counts on it being back "
            "before you leave.") in before["notes"]


def test_back_from_the_tailors_before_the_trip_counts_as_mended():
    items = away(basic_closet(), "coat1", "tailor", until="2026-11-27")
    items[6]["condition"] = "needs_repair"
    assert "coat1" in {p["id"] for p in trips.plan(items, trip_days(3), {"pin": ["coat1"]})["packed"]}
    items[6]["away"] = None   # mending, at home: still not packed
    assert "coat1" not in {p["id"] for p in trips.plan(items, trip_days(3), {"pin": ["coat1"]})["packed"]}


def test_with_nothing_away_a_trip_is_planned_as_before():
    items = basic_closet()
    assert trips.plan([{**i, "away": None, "away_until": None} for i in items], trip_days(4)) == trips.plan(items, trip_days(4))


# ---------------------------------------------------------------------- still owned
def test_an_away_piece_is_still_owned_for_whats_missing_and_would_this_work():
    worn = gap_log({"tee_white": 3, "jeans_dark": 3})
    gone = away(full_closet(), "coat_navy", "lent")
    assert all_gaps(gone, worn)["gaps"] == all_gaps(full_closet(), worn)["gaps"]
    piece = {"category": "coat", "color": "navy", "weight_class": "heavyweight"}
    a, b = wouldwork.check(gone, worn, piece), wouldwork.check(full_closet(), worn, piece)
    assert (a["verdict"], a["reasons"]) == (b["verdict"], b["reasons"])


def test_an_away_piece_is_not_nudged_while_it_is_away():
    busy, log = ti.busy_log()
    coat = ti.item("coat", "coat", "Grey coat")
    found = ti.find([busy, coat], log, ti.TODAY)
    assert [i["id"] for i in found["never_worn"]["items"]] == ["coat"]
    gone = ti.find([busy, {**coat, "away": "cleaner"}], log, ti.TODAY)
    assert gone["never_worn"]["items"] == [] and gone["makeup"]["pieces"] == 2   # still yours, not nudged
    old = ti.worn("coat", 200)
    lately = ti.find([busy, coat], log + old, ti.TODAY)["not_worn_lately"]["items"]
    assert [i["id"] for i in lately] == ["coat"]
    assert ti.find([busy, {**coat, "away": "lent"}], log + old, ti.TODAY)["not_worn_lately"]["items"] == []
    # What's missing's own note of what was never worn leaves it out as well
    gone_gaps = gaps.find_gaps(away(full_closet(), "tee_grey"), gap_log({"tee_white": 12}), {"max_gaps": 50})
    never = [n for n in gone_gaps.get("notes", []) if n.get("kind") == "never_worn"]
    assert never and "tee_grey" not in never[0]["items"]


# ---------------------------------------------------------------------- the note stays on this computer
def test_the_note_is_never_in_anything_sent_to_claude():
    rows = styling_closet()
    rows[0].update(away="tailor", away_since="2026-11-20", away_until="2026-11-27", away_note=SECRET, notes="Soft cotton")
    for ctx in (styling_context(), styling_context(build_around="t1")):
        told, _ = styling.brief(rows, {"source": "given"}, ctx, TUESDAY, [], [])
        assert "piece" in told["closet"].lower() or told["closet"]
        assert SECRET not in stylist.prompt(told)
    block = aboutyou.about([{**r, "rating": "love"} for r in rows], [], [], {}, None)
    assert SECRET not in block


def test_only_the_away_module_reads_the_note_and_nothing_that_asks_claude_reads_where_a_piece_is():
    root = Path(__file__).resolve().parents[1] / "closet"
    readers = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py") if "away_note" in p.read_text(encoding="utf-8"))
    assert readers == ["away.py"]
    asking = [p.relative_to(root).as_posix() for p in (root / "tagger").rglob("*.py")
              if re.search(r"away_(note|since|until)|\[\"away\"\]|get\(\"away\"\)|AWAY", p.read_text(encoding="utf-8"))]
    assert asking == []


# ---------------------------------------------------------------------- the routes
def send(client, item_id, **body):
    return client.put(f"/api/items/{item_id}/away", json=body)


def test_send_a_piece_away_and_the_item_answer_carries_it(client):
    item = upload(client).json()
    r = send(client, item["id"], place="cleaner", until="2026-11-27", note=" for   the hem ")
    assert r.status_code == 200
    body = r.json()
    assert body["away"] == {"place": "cleaner", "since": TODAY.isoformat(), "until": "2026-11-27", "note": "for the hem"}
    listed = client.get("/api/items").json()["items"][0]
    assert listed["away"] == {"place": "cleaner", "since": TODAY.isoformat(), "until": "2026-11-27"}   # no note in the list
    # changing the day keeps the day it went; another place is a new going
    again = send(client, item["id"], place="cleaner", until="2026-11-30").json()
    assert again["away"]["since"] == TODAY.isoformat() and again["away"]["note"] is None
    assert [h["away"] for h in client.get(f"/api/items/{item['id']}/history").json() if h["kind"] == "away"] == [
        {"event": "went", "place": "cleaner", "by": "owner"}]


@pytest.mark.parametrize("body, words", [
    ({"place": "attic"}, "Say where it is"),
    ({"place": "lent", "until": "next week"}, "YYYY-MM-DD"),
    ({"place": "lent", "until": "2026-11-01"}, "can't be before the day it went"),
    ({"place": "lent", "since": "2026-12-25"}, "can't be in the future"),
    ({"place": "lent", "note": "x" * 121}, "120 characters"),
])
def test_a_choice_that_cannot_be_kept_is_refused_in_words(client, body, words):
    item = upload(client).json()
    r = send(client, item["id"], **body)
    assert r.status_code == 422 and words in r.json()["detail"]
    assert client.get(f"/api/items/{item['id']}").json()["away"] is None


def test_unknown_items_and_unknown_fields_are_refused(client):
    assert send(client, "nope", place="lent").status_code == 404
    assert client.post("/api/items/nope/back").status_code == 404
    item = upload(client).json()
    assert send(client, item["id"], place="lent", colour="red").status_code == 422
    assert client.post(f"/api/items/{item['id']}/back/undo").status_code == 409   # nothing to undo


def test_back_from_the_cleaners_is_clean_and_undo_puts_it_all_back(client):
    item = upload(client).json()
    i = item["id"]
    client.post(f"/api/items/{i}/wears", json={"worn_on": (TODAY - timedelta(days=3)).isoformat()})
    client.post(f"/api/items/{i}/laundry", json={"state": "laundry"})
    send(client, i, place="cleaner", note="the stain")
    back = client.post(f"/api/items/{i}/back").json()
    assert back["away"] is None and back["laundry"] == "clean" and back["wears_since_wash"] == 0
    assert back["came_back"] == {"from": "cleaner", "on": TODAY.isoformat(), "by": "owner", "mended": False}
    undone = client.post(f"/api/items/{i}/back/undo").json()
    assert undone["away"]["place"] == "cleaner" and undone["away"]["note"] == "the stain"
    assert undone["laundry"] == "laundry" and undone["wears_since_wash"] == 1 and undone["came_back"] is None
    # marking it clean does not bring it back
    assert client.post(f"/api/items/{i}/laundry", json={"state": "clean"}).json()["away"]["place"] == "cleaner"


def test_back_from_the_tailors_clears_needs_mending_and_lent_changes_nothing_else(client):
    item = upload(client).json()
    i = item["id"]
    client.patch(f"/api/items/{i}", json={"condition": "needs_repair"})
    client.post(f"/api/items/{i}/laundry", json={"state": "laundry"})
    send(client, i, place="tailor")
    back = client.post(f"/api/items/{i}/back").json()
    assert back["condition"] is None and back["laundry"] == "laundry" and back["came_back"]["mended"] is True
    assert client.post(f"/api/items/{i}/back/undo").json()["condition"] == "needs_repair"
    client.post(f"/api/items/{i}/back")
    send(client, i, place="lent")
    lent = client.post(f"/api/items/{i}/back").json()
    assert lent["laundry"] == "laundry" and lent["came_back"]["from"] == "lent"
    assert [(h["away"]["event"], h["away"]["place"]) for h in client.get(f"/api/items/{i}/history").json()
            if h["kind"] == "away"] == [("back", "lent"), ("went", "lent"), ("back", "tailor"), ("went", "tailor")]


def test_a_wear_today_brings_it_back_and_undoing_the_wear_sends_it_away_again(client):
    item = upload(client).json()
    i = item["id"]
    send(client, i, place="lent", until="2026-11-30")
    # a day already gone, filled in from memory, leaves it where it is
    assert client.post(f"/api/items/{i}/wears", json={"worn_on": (TODAY - timedelta(days=5)).isoformat()}).json()["away"]
    worn = client.post(f"/api/items/{i}/wears").json()
    assert worn["away"] is None and worn["came_back"]["by"] == "wear" and worn["wear_count"] == 2
    undone = client.delete(f"/api/items/{i}/wears/{TODAY.isoformat()}").json()
    assert undone["away"] == {"place": "lent", "since": TODAY.isoformat(), "until": "2026-11-30", "note": None}


def test_an_outfit_recorded_by_hand_for_today_brings_its_away_pieces_back(client):
    a, b = upload(client, key="a").json(), upload(client, key="b").json()
    client.patch(f"/api/items/{a['id']}", json={"category": "tee"})
    client.patch(f"/api/items/{b['id']}", json={"category": "jeans"})
    send(client, b["id"], place="cleaner")
    assert client.post("/api/outfits/worn", json={"item_ids": [a["id"], b["id"]]}).status_code == 201
    back = client.get(f"/api/items/{b['id']}").json()
    assert back["away"] is None and back["laundry"] == "clean" and back["wears_since_wash"] == 1
