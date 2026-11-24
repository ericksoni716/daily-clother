"""Worn outfits: recorded with the wears or by hand, rated, listed, removed, and what Today does with them."""
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from closet import db, outfits, today, wears, weather, worn

from .conftest import photo_bytes, upload

TODAY = date(2026, 11, 12)
DAY = {"low_c": 9, "high_c": 16, "rain": False}   # the whole day given: the weather is not looked up


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)

    def no_network(url):
        raise AssertionError(f"tests never ask the internet ({url})")

    monkeypatch.setattr(weather, "fetch", no_network)


def item_in(client, key, category, color=(10, 20, 30), name=None):
    r = upload(client, key=key, data=photo_bytes(color=color), name=name)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert client.patch(f"/api/items/{iid}", json={"category": category}).status_code == 200
    return iid


def small(client):
    return {"tee": item_in(client, "t", "tee", (10, 20, 30)), "jacket": item_in(client, "j", "jacket", (40, 50, 60)),
            "jeans": item_in(client, "b", "jeans", (70, 80, 90)), "shoes": item_in(client, "s", "sneakers", (100, 110, 120))}


def offered(ids, mid=None):
    return {"pieces": {"base": ids["tee"], "mid": mid, "outer": ids["jacket"], "bottom": ids["jeans"], "shoes": ids["shoes"],
                       "accessories": []},
            "context": {"low_c": 9, "high_c": 16, "rain": False, "occasion": "casual", "mood": "usual"},
            "score": 77, "reasons": ["Two layers for 12°C."], "warnings": []}


def all_ids(ids):
    return [ids["tee"], ids["jacket"], ids["jeans"], ids["shoes"]]


def test_an_outfit_is_remembered_with_its_wears_and_undone_with_them(client):
    ids = small(client)
    client.post(f"/api/items/{ids['shoes']}/wears")   # already worn today on its own
    r = client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": offered(ids)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recorded"] == [ids["tee"], ids["jacket"], ids["jeans"]]
    o = body["outfit"]
    assert o["worn_on"] == TODAY.isoformat() and o["recorded_by"] == "today" and o["rating"] is None
    assert o["pieces"] == {**offered(ids)["pieces"]}
    assert o["context"] == offered(ids)["context"] and o["score"] == 77 and o["reasons"] == ["Two layers for 12°C."]
    listed = client.get("/api/outfits/worn").json()
    assert [x["id"] for x in listed["outfits"]] == [o["id"]] and listed["next"] is None

    undone = client.post("/api/wears/remove", json={"item_ids": body["recorded"], "worn_on": body["worn_on"], "outfit_id": o["id"]})
    assert undone.status_code == 200 and undone.json()["outfit_removed"] is True
    assert undone.json()["removed"] == body["recorded"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []
    assert client.get(f"/api/items/{ids['shoes']}").json()["wear_count"] == 1   # its own wear stays
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0

    # an outfit whose wears were all there already is still remembered, and undone with no items
    client.post(f"/api/items/{ids['tee']}/wears")
    r = client.post("/api/wears", json={"item_ids": [ids["shoes"], ids["tee"]],
                                        "outfit": {"pieces": {"base": ids["tee"], "shoes": ids["shoes"]}}})
    assert r.status_code == 201 and r.json()["recorded"] == []
    gone = client.post("/api/wears/remove", json={"item_ids": [], "worn_on": TODAY.isoformat(), "outfit_id": r.json()["outfit"]["id"]})
    assert gone.status_code == 200 and gone.json()["outfit_removed"] is True and gone.json()["removed"] == []
    assert client.get("/api/outfits/worn").json()["outfits"] == []
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 1   # its own wear stays


def test_the_same_outfit_recorded_twice_on_a_day_is_one_outfit(client):
    # "I'm wearing this" on the computer, then again on the phone: the second gives back the first
    ids = small(client)
    first = client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": offered(ids)}).json()
    second = client.post("/api/wears", json={"item_ids": list(reversed(all_ids(ids))), "outfit": offered(ids)})
    assert second.status_code == 201 and second.json()["recorded"] == []
    assert second.json()["outfit"]["id"] == first["outfit"]["id"]
    by_hand = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids)}).json()
    assert by_hand["id"] == first["outfit"]["id"]
    assert [o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]] == [first["outfit"]["id"]]
    # undone from the phone, which recorded no wear of its own: the outfit's wears go with it
    gone = client.post("/api/wears/remove", json={"item_ids": second.json()["recorded"], "worn_on": TODAY.isoformat(),
                                                  "outfit_id": second.json()["outfit"]["id"]}).json()
    assert gone["outfit_removed"] is True and sorted(gone["removed"]) == sorted(all_ids(ids))
    assert all(client.get(f"/api/items/{i}").json()["wear_count"] == 0 for i in all_ids(ids))
    # on another day the same pieces are another outfit
    a = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids), "worn_on": days_ago(1)}).json()
    b = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids), "worn_on": days_ago(2)}).json()
    assert a["id"] != b["id"]


@pytest.mark.parametrize("order", ["first_then_second", "second_then_first"])
def test_removing_outfits_that_share_pieces_leaves_the_wear_log_right_in_any_order(client, order):
    ids = small(client)
    a = client.post("/api/wears", json={"item_ids": [ids["tee"], ids["jeans"], ids["shoes"]],
                                        "outfit": {"pieces": {"base": ids["tee"], "bottom": ids["jeans"], "shoes": ids["shoes"]}}}).json()
    b = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"], ids["shoes"]]}).json()
    first, second = (a["outfit"]["id"], b["id"]) if order == "first_then_second" else (b["id"], a["outfit"]["id"])
    assert client.delete(f"/api/outfits/worn/{first}").status_code == 204
    left = [ids["jacket"], ids["jeans"], ids["shoes"]] if first == a["outfit"]["id"] else [ids["tee"], ids["jeans"], ids["shoes"]]
    assert all(client.get(f"/api/items/{i}").json()["wear_count"] == 1 for i in left)
    assert client.delete(f"/api/outfits/worn/{second}").status_code == 204
    assert all(client.get(f"/api/items/{i}").json()["wear_count"] == 0 for i in all_ids(ids))


@pytest.mark.parametrize("action", ["remove", "undo"])
def test_overlapping_outfit_removals_do_not_leave_shared_wears_behind(client, cfg, action):
    ids = small(client)
    first = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    second = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"], ids["shoes"]]}).json()
    conn = db.connect(cfg.db_path("main"))
    other = db.connect(cfg.db_path("main"))
    interleaved = []

    def before_lock(sql):
        if sql == "BEGIN IMMEDIATE" and not interleaved:
            interleaved.append(True)
            worn.remove(other, first["id"])

    try:
        conn.set_trace_callback(before_lock)
        if action == "remove":
            worn.remove(conn, second["id"])
        else:
            worn.undo(conn, [], TODAY.isoformat(), second["id"])
        assert interleaved
        assert conn.execute("SELECT COUNT(*) FROM worn_outfits").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM wears").fetchone()[0] == 0
        assert all(r[0] == 0 for r in conn.execute("SELECT wears_since_wash FROM items"))
    finally:
        conn.close()
        other.close()


def test_failed_outfit_removal_rolls_back_its_wears(client, cfg):
    ids = small(client)
    outfit = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("CREATE TEMP TRIGGER refuse_removal BEFORE DELETE ON worn_outfits "
                     "BEGIN SELECT RAISE(ABORT, 'test removal failed'); END")
        with pytest.raises(sqlite3.IntegrityError, match="test removal failed"):
            worn.remove(conn, outfit["id"])
        assert not conn.in_transaction
        assert worn.get(conn, outfit["id"])["pieces"] == outfit["pieces"]
        assert conn.execute("SELECT COUNT(*) FROM wears").fetchone()[0] == 2
        assert conn.execute("SELECT SUM(wears_since_wash) FROM items").fetchone()[0] == 2
    finally:
        conn.close()


def test_long_sentences_are_shortened_not_refused(client):
    ids = small(client)
    long = "The " + "very " * 400 + "long-named jacket keeps you warm."
    r = client.post("/api/wears", json={"item_ids": all_ids(ids),
                                        "outfit": {**offered(ids), "reasons": [long] * 40, "warnings": [long]}})
    assert r.status_code == 201, r.text
    o = r.json()["outfit"]
    assert len(o["reasons"]) == worn.MAX_REASONS_TEXT and len(o["warnings"]) == 1
    assert all(len(x) <= worn.MAX_SENTENCE and x.endswith("…") and x.startswith("The very") for x in o["reasons"] + o["warnings"])


def test_deleting_a_piece_keeps_the_outfit_as_it_was_and_it_stops_teaching(client, cfg):
    ids = small(client)
    sweater = item_in(client, "w", "sweater", (130, 140, 150))
    o = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], sweater, ids["jeans"], ids["shoes"]]}).json()
    client.put(f"/api/outfits/worn/{o['id']}/rating", json={"rating": "not_again"})
    conn = db.connect(cfg.db_path("main"))
    ctx = outfits.parse_request(DAY)[0]

    def feedback():
        return outfits.feedback_from(worn.rated(conn), today.closet_rows(conn), ctx)

    assert (ids["tee"], sweater, "", ids["jeans"], ids["shoes"]) in feedback().not_again
    assert client.delete(f"/api/items/{sweater}").status_code == 204
    listed = client.get("/api/outfits/worn").json()["outfits"]
    assert listed[0]["pieces"]["mid"] == sweater and listed[0]["gone"] == [sweater]   # still the outfit that was worn
    assert feedback() == outfits.Feedback()   # and it no longer teaches: tee, jeans and sneakers were never rated
    # an archived piece is still in the closet: the outfit still teaches, and is not "gone"
    other = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"]], "worn_on": days_ago(1)}).json()
    client.put(f"/api/outfits/worn/{other['id']}/rating", json={"rating": "loved"})
    client.patch(f"/api/items/{ids['jacket']}", json={"status": "archived"})
    listed = {x["id"]: x for x in client.get("/api/outfits/worn").json()["outfits"]}
    assert listed[other["id"]]["gone"] == [] and feedback().liked
    # an outfit with no piece left in the closet goes from the list with its last piece
    for i in (ids["tee"], ids["jeans"], ids["shoes"]):
        client.delete(f"/api/items/{i}")
    assert [x["id"] for x in client.get("/api/outfits/worn").json()["outfits"]] == [other["id"]]
    # and one with a piece gone can still be removed
    assert client.delete(f"/api/outfits/worn/{other['id']}").status_code == 204
    conn.close()


def test_what_is_sent_with_an_outfit_is_checked_and_nothing_is_kept_on_a_mistake(client):
    ids = small(client)
    good = offered(ids)
    bad = [
        ({**good, "pieces": {**good["pieces"], "hat": ids["tee"]}}, "not places"),
        ({**good, "pieces": {**good["pieces"], "base": ids["jeans"]}}, "each once"),
        ({**good, "pieces": {**good["pieces"], "outer": None}}, "items being worn"),
        ({**good, "context": {**good["context"], "occasion": "party"}}, "not an occasion"),
        ({**good, "context": {**good["context"], "low_c": "cold"}}, "Celsius"),
        ({**good, "context": {**good["context"], "wind": 3}}, "only"),
        ({**good, "score": 101}, "0 to 100"),
        ({**good, "reasons": "nice"}, "sentences"),
        ({**good, "extra": 1}, "Give the outfit"),
    ]
    for outfit, words in bad:
        r = client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": outfit})
        assert r.status_code == 422 and words in r.json()["detail"], (outfit, r.text)
    assert client.post("/api/wears", json={"item_ids": all_ids(ids), "outfit": "outfit"}).status_code == 422
    r = client.post("/api/wears", json={"item_ids": all_ids(ids), "worn_on": days_ago(-2), "outfit": good})   # the computer's tomorrow is a phone's today
    assert r.status_code == 422 and "future" in r.json()["detail"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []
    assert all(client.get(f"/api/items/{i}").json()["wear_count"] == 0 for i in all_ids(ids))
    r = client.post("/api/wears/remove", json={"item_ids": [], "worn_on": TODAY.isoformat(), "outfit_id": "nope"})
    assert r.status_code == 200 and r.json()["outfit_removed"] is False


def test_an_outfit_is_recorded_by_hand_with_its_pieces_in_their_places(client):
    ids = small(client)
    sweater = item_in(client, "w", "sweater", (130, 140, 150))
    client.post(f"/api/items/{ids['jeans']}/wears", json={"worn_on": days_ago(3)})
    r = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["shoes"], sweater, ids["jeans"], ids["tee"]],
                                               "worn_on": days_ago(3)})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["recorded_by"] == "hand" and o["worn_on"] == days_ago(3) and o["context"] is None and o["score"] is None
    assert o["pieces"] == {"base": ids["tee"], "mid": sweater, "outer": ids["jacket"], "bottom": ids["jeans"],
                           "shoes": ids["shoes"], "accessories": []}
    assert client.get(f"/api/items/{ids['tee']}").json()["last_worn"] == days_ago(3)
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1

    # removing it takes away the wears it added, not the one that was there before
    assert client.delete(f"/api/outfits/worn/{o['id']}").status_code == 204
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0
    assert client.delete(f"/api/outfits/worn/{o['id']}").status_code == 404

    for chosen, words in (([ids["tee"]], "at least 2"), ([ids["shoes"], ids["shoes"]], "at least 2"),
                          ([ids["tee"], ids["jeans"], item_in(client, "b2", "trousers", (4, 5, 6))], "one thing for your legs"),
                          ([ids["tee"], ids["shoes"], item_in(client, "s2", "boots", (1, 2, 3))], "one pair of shoes"),
                          ([ids["tee"], "nope"], "")):
        r = client.post("/api/outfits/worn", json={"item_ids": chosen})
        assert r.status_code in (404, 422) and words in r.json()["detail"], chosen
    uncategorised = upload(client, key="u", data=photo_bytes(color=(5, 6, 7))).json()["id"]
    r = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], uncategorised]})
    assert r.status_code == 422 and "category" in r.json()["detail"]
    assert client.get("/api/outfits/worn").json()["outfits"] == []


def test_an_outfit_recorded_by_hand_can_include_a_tie_or_a_watch(client):
    # "Record an outfit" lists every piece with a category, the tie and the watch among them (their category is
    # Other: there is none for a tie); they are worn with the outfit's accessories
    ids = small(client)
    tie, watch = item_in(client, "tie", "other", (120, 20, 40)), item_in(client, "watch", "other", (90, 90, 90))
    r = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"], ids["shoes"], tie, watch]})
    assert r.status_code == 201, r.json()
    o = r.json()
    assert o["pieces"]["accessories"] == [tie, watch] and o["pieces"]["base"] == ids["tee"]
    assert client.get(f"/api/items/{tie}").json()["wear_count"] == 1
    assert [x["id"] for x in client.get("/api/outfits/worn").json()["outfits"]] == [o["id"]]


def test_two_outfits_the_same_day_share_a_piece_and_removing_one_keeps_its_wear(client):
    ids = small(client)
    a = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    b = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"]]}).json()
    client.delete(f"/api/outfits/worn/{a['id']}")
    assert client.get(f"/api/items/{ids['jeans']}").json()["wear_count"] == 1
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0
    assert [x["id"] for x in client.get("/api/outfits/worn").json()["outfits"]] == [b["id"]]


def test_rating_an_outfit_and_changing_it(client):
    ids = small(client)
    o = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids)}).json()
    url = f"/api/outfits/worn/{o['id']}/rating"
    r = client.put(url, json={"rating": "not_again", "reasons": ["uncomfortable", "too_cold", "too_cold"]})
    assert r.status_code == 200
    assert (r.json()["rating"], r.json()["rating_reasons"]) == ("not_again", ["too_cold", "uncomfortable"]) and r.json()["rated_at"]
    r = client.put(url, json={"rating": "loved", "reasons": ["compliments", "other"], "note": "  wore it to a party  "})
    assert (r.json()["rating"], r.json()["rating_reasons"], r.json()["rating_note"]) == ("loved", ["compliments", "other"], "wore it to a party")
    assert client.get("/api/outfits/worn").json()["outfits"][0]["rating"] == "loved"
    for body, words in (({"rating": "great"}, "one of"), ({"rating": "fine", "reasons": ["itchy"]}, "Reasons come from"),
                        ({"rating": "fine", "note": "hm"}, "goes with"), ({"rating": None, "reasons": ["too_cold"]}, "before giving"),
                        ({"rating": "fine", "note": "x" * 301}, "300")):
        r = client.put(url, json=body)
        assert r.status_code == 422 and words in r.json()["detail"], body
    assert client.put(url, json={"rating": "fine", "extra": 1}).status_code == 422
    cleared = client.put(url, json={"rating": None}).json()
    assert (cleared["rating"], cleared["rating_reasons"], cleared["rating_note"], cleared["rated_at"]) == (None, [], None, None)
    assert client.put("/api/outfits/worn/nope/rating", json={"rating": "fine"}).status_code == 404


def tapped(days: int, at: str = "08:15:00") -> str:
    return f"{days_ago(days)}T{at}Z"


def test_an_outfit_kept_on_the_phone_is_recorded_for_the_day_tapped_and_once_when_sent_again(client):
    # tapped yesterday while Nines could not be reached, sent today, and sent again after the answer was lost
    ids = small(client)
    sent = {"item_ids": all_ids(ids), "worn_on": days_ago(1), "outfit": offered(ids), "tapped_at": tapped(1)}
    first = client.post("/api/wears", json=sent)
    assert first.status_code == 201, first.text
    assert first.json()["worn_on"] == days_ago(1) and first.json()["outfit"]["worn_on"] == days_ago(1)
    again = client.post("/api/wears", json=sent)
    assert again.status_code == 201 and again.json()["recorded"] == []
    assert again.json()["outfit"]["id"] == first.json()["outfit"]["id"]
    assert [o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]] == [first.json()["outfit"]["id"]]
    for i in all_ids(ids):
        assert client.get(f"/api/items/{i}/wears").json()["wears"] == [{"worn_on": days_ago(1), "created_at": first.json()["outfit"]["created_at"]}]


def test_an_outfit_sent_later_is_refused_when_the_day_or_its_pieces_changed_meanwhile(client):
    ids = small(client)
    other = client.post("/api/outfits/worn", json={"item_ids": [ids["jacket"], ids["jeans"]], "worn_on": days_ago(1)}).json()
    late = {"item_ids": all_ids(ids), "worn_on": days_ago(1), "outfit": offered(ids), "tapped_at": tapped(1)}
    r = client.post("/api/wears", json=late)
    assert r.status_code == 409 and "Another outfit was recorded for that day" in r.json()["detail"]
    assert [o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]] == [other["id"]]
    assert client.get(f"/api/items/{ids['tee']}").json()["wear_count"] == 0   # nothing kept from it
    # sent at once, a second outfit on a day is still recorded beside the first, as before
    assert client.post("/api/wears", json={**late, "tapped_at": None}).status_code == 201

    assert client.patch(f"/api/items/{ids['tee']}", json={"status": "archived", "name": "Plain tee"}).status_code == 200
    r = client.post("/api/wears", json={**late, "worn_on": days_ago(2), "tapped_at": tapped(2)})
    assert r.status_code == 409 and r.json()["detail"] == "Plain tee has been archived since."
    assert client.patch(f"/api/items/{ids['tee']}", json={"status": "active"}).status_code == 200
    assert client.delete(f"/api/items/{ids['jacket']}").status_code in (200, 204)
    r = client.post("/api/wears", json={**late, "worn_on": days_ago(3), "tapped_at": tapped(3)})
    assert r.status_code == 409 and "deleted since" in r.json()["detail"]
    for when in ("yesterday", "2026-11-11T08:15:00", "2999-01-01T00:00:00Z"):
        r = client.post("/api/wears", json={**late, "worn_on": days_ago(4), "tapped_at": when})
        assert r.status_code == 422, when
    r = client.post("/api/wears", json={"item_ids": all_ids(ids), "tapped_at": tapped(1)})
    assert r.status_code == 422 and "Only an outfit" in r.json()["detail"]


def test_a_rating_kept_on_the_phone_is_rated_as_of_the_tap_and_once_when_sent_again(client):
    ids = small(client)
    o = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids), "worn_on": days_ago(2)}).json()
    url = f"/api/outfits/worn/{o['id']}/rating"
    sent = {"rating": "loved", "reasons": ["compliments"], "tapped_at": "2026-11-11T09:30:00+01:00"}
    for _ in range(2):
        r = client.put(url, json=sent)
        assert r.status_code == 200, r.text
        assert (r.json()["rating"], r.json()["rating_reasons"], r.json()["rated_at"]) == ("loved", ["compliments"], "2026-11-11T08:30:00.000000Z")
    # changed on the computer after the tap: the phone's older word is refused, the newer one stays
    assert client.put(url, json={"rating": "not_again"}).status_code == 200
    r = client.put(url, json=sent)
    assert r.status_code == 409 and "somewhere else since" in r.json()["detail"]
    assert client.get("/api/outfits/worn").json()["outfits"][0]["rating"] == "not_again"
    assert client.put("/api/outfits/worn/nope/rating", json=sent).status_code == 404


def test_a_rating_taken_away_elsewhere_after_the_tap_refuses_the_phones_older_tap(client):
    """Review 2, finding 6. Your phone, out of reach of Nines, keeps a tap: "Loved it", two hours ago. Since then, on
    the computer, you rated the same outfit and then took the rating away. Taking it away is a change made after the
    tap, as setting one is: the phone's older tap is refused ("You changed how it went somewhere else since."), and
    the outfit stays unrated."""
    ids = small(client)
    o = client.post("/api/outfits/worn", json={"item_ids": all_ids(ids)}).json()
    tapped_at = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rating = f"/api/outfits/worn/{o['id']}/rating"
    assert client.put(rating, json={"rating": "not_again"}).status_code == 200
    assert client.put(rating, json={"rating": None}).status_code == 200
    late = client.put(rating, json={"rating": "loved", "tapped_at": tapped_at})
    assert late.status_code == 409, f"the tap from two hours ago was taken: {late.json().get('rating')}"
    assert late.json()["detail"] == "You changed how it went somewhere else since."
    assert client.get("/api/outfits/worn").json()["outfits"][0]["rating"] is None
    # a phone's own taking away, sent again after its answer was lost, is already so: not refused
    cleared = client.put(rating, json={"rating": None, "tapped_at": tapped_at})
    assert cleared.status_code == 200 and cleared.json()["rating"] is None


def test_the_list_is_newest_first_and_comes_in_pages(client):
    ids = small(client)
    made = []
    for n, legs in ((5, "jeans"), (1, "jeans"), (3, "jeans"), (1, "shoes"), (8, "jeans")):   # two outfits on one day
        made.append((days_ago(n), client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids[legs]],
                                                                          "worn_on": days_ago(n)}).json()["id"]))
    page = client.get("/api/outfits/worn", params={"limit": 2}).json()
    seen = [o["id"] for o in page["outfits"]]
    while page["next"]:
        page = client.get("/api/outfits/worn", params={"limit": 2, "before": page["next"]}).json()
        seen += [o["id"] for o in page["outfits"]]
    assert seen == [made[3][1], made[1][1], made[2][1], made[0][1], made[4][1]]
    assert client.get("/api/outfits/worn", params={"limit": 0}).status_code == 422
    assert client.get("/api/outfits/worn", params={"limit": 101}).status_code == 422
    assert client.get("/api/outfits/worn", params={"before": "nonsense"}).status_code == 422


def test_ratings_shape_today_and_wear_again_keeps_the_clean_pieces(client):
    client.post("/api/profile", json={"profile": "demo"})
    listed = client.get("/api/outfits/worn").json()["outfits"]
    assert len(listed) == 16 and listed[0]["worn_on"] == days_ago(1) and listed[0]["rating"] is None
    assert sum(o["rating"] is not None for o in listed) == 15
    by_name = {i["name"]: i["id"] for i in client.get("/api/items").json()["items"]}

    # the loved outfit of six days ago: its pieces are clean, so they come back in their places
    loved = next(o for o in listed if o["worn_on"] == days_ago(6))
    r = client.post("/api/outfits/today", json={**DAY, "again": loved["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    again = body["context"]["again"]
    assert again["id"] == loved["id"] and again["worn_on"] == days_ago(6)
    assert by_name["White tee"] in again["unavailable"]   # in the laundry
    kept = [loved["pieces"][pl] for pl in ("mid", "outer", "bottom", "shoes")]
    assert sorted(again["kept"]) == sorted(kept)
    assert body["outfits"]
    for o in body["outfits"]:
        assert set(kept) <= {o["pieces"][pl] for pl in ("base", "mid", "outer", "bottom", "shoes")} and o["pieces"]["bottom"] == loved["pieces"]["bottom"]
        assert o["pieces"]["base"] != by_name["White tee"]
    assert any("You loved" in r for o in body["outfits"] for r in o["reasons"])

    r = client.post("/api/outfits/today", json={**DAY, "again": "nope"})
    assert r.status_code == 422 and "no longer" in r.json()["detail"]
    assert client.post("/api/outfits/today", json={**DAY, "again": 3}).status_code == 422
    # without "again" nothing is left out
    assert "again" not in client.post("/api/outfits/today", json=DAY).json()["context"]


def test_demo_and_main_closets_keep_their_own_worn_outfits(client):
    ids = small(client)
    mine = client.post("/api/outfits/worn", json={"item_ids": [ids["tee"], ids["jeans"]]}).json()
    client.post("/api/profile", json={"profile": "demo"})
    demo_ids = {o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]}
    assert mine["id"] not in demo_ids and len(demo_ids) == 16
    assert client.put(f"/api/outfits/worn/{mine['id']}/rating", json={"rating": "fine"}).status_code == 404
    client.post("/api/profile", json={"profile": "main"})
    assert [o["id"] for o in client.get("/api/outfits/worn").json()["outfits"]] == [mine["id"]]


def test_the_demo_outfits_match_its_wears(client):
    client.post("/api/profile", json={"profile": "demo"})
    for o in client.get("/api/outfits/worn").json()["outfits"]:
        for pid in [v for k, v in o["pieces"].items() if k != "accessories" and v] + o["pieces"]["accessories"]:
            assert o["worn_on"] in [w["worn_on"] for w in client.get(f"/api/items/{pid}/wears").json()["wears"]]


def test_the_migration_runs_on_a_closet_made_by_the_previous_version(tmp_path, monkeypatch):
    path, backups = tmp_path / "closet.db", tmp_path / "bk"
    real = db.migration_files()
    monkeypatch.setattr(db, "migration_files", lambda: [(v, p) for v, p in real if v < 10])
    db.migrate(path, backups)
    conn = db.connect(path)
    t = db.now()
    for item_id in ("a", "b"):
        conn.execute("INSERT INTO items (id, category, created_at, updated_at) VALUES (?, 'tee', ?, ?)", (item_id, t, t))
    conn.execute("INSERT INTO wears (item_id, worn_on, created_at) VALUES ('a', '2026-11-01', ?)", (t,))
    conn.close()

    monkeypatch.setattr(db, "migration_files", lambda: real)
    result = db.migrate(path, backups)
    assert result["applied"][0] == 10 and result["backup"]   # and any later ones
    conn = db.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM wears").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM worn_outfits").fetchone()[0] == 0
    conn.execute("INSERT INTO worn_outfits (id, worn_on, recorded_by, created_at, updated_at) VALUES ('o', '2026-11-01', 'hand', ?, ?)", (t, t))
    conn.execute("INSERT INTO worn_outfit_pieces (outfit_id, item_id, place, position, added_wear) VALUES ('o', 'a', 'base', 0, 0)")
    with pytest.raises(Exception, match="CHECK"):
        conn.execute("UPDATE worn_outfits SET rating = 'great' WHERE id = 'o'")
    conn.execute("DELETE FROM items WHERE id = 'a'")   # a deleted item leaves the outfit, without that piece
    assert conn.execute("SELECT COUNT(*) FROM worn_outfit_pieces").fetchone()[0] == 0
    conn.execute("DELETE FROM worn_outfits WHERE id = 'o'")
    conn.close()


# ------------------------------------------------------------------ one piece's outfits, on its page
def _o(oid, ids, rating=None):
    pieces = {pl: None for pl in worn.PLACES} | {"accessories": []}
    for pl, i in zip(("base", "bottom", "shoes"), ids, strict=True):
        pieces[pl] = i
    return {"id": oid, "pieces": pieces, "gone": [], "rating": rating}


@pytest.mark.parametrize("days, outfit_on, rows", [
    ([], {}, []),
    (["d3"], {}, [(None, ["d3"], None)]),                                                   # a wear with no outfit
    (["d3", "d2", "d1"], {"d3": _o("a", "tjs"), "d1": _o("b", "jst", "loved")},             # the same pieces: one row
     [("a", ["d3", "d1"], "loved"), (None, ["d2"], None)]),
    (["d2", "d1"], {"d2": _o("a", "tjs", "fine"), "d1": _o("b", "tjs", "not_again")},       # the latest rating
     [("a", ["d2", "d1"], "fine")]),
    (["d2", "d1"], {"d2": _o("a", "tjs"), "d1": _o("b", "tjx")},                            # other pieces: two rows
     [("a", ["d2"], None), ("b", ["d1"], None)]),
])
def test_a_pieces_wears_are_grouped_by_the_outfit_they_were_worn_in(days, outfit_on, rows):
    got = worn.group_wears(days, outfit_on)
    assert [(r["outfit_id"], r["days"], r["rating"]) for r in got] == rows


def test_the_item_page_lists_the_outfits_a_piece_was_worn_in(client):
    ids = small(client)
    trio = [ids["tee"], ids["jeans"], ids["shoes"]]
    first = client.post("/api/outfits/worn", json={"item_ids": trio, "worn_on": days_ago(5)}).json()
    client.post(f"/api/items/{ids['tee']}/wears", json={"worn_on": days_ago(3)})            # worn on its own
    again = client.post("/api/outfits/worn", json={"item_ids": trio, "worn_on": days_ago(1)}).json()
    client.put(f"/api/outfits/worn/{again['id']}/rating", json={"rating": "loved"})
    client.post("/api/outfits/worn", json={"item_ids": all_ids(ids), "worn_on": days_ago(8)})   # with the jacket
    body = client.get(f"/api/items/{ids['tee']}").json()
    assert [(r["outfit_id"], r["days"], r["rating"]) for r in body["worn_in"]] == [
        (again["id"], [days_ago(1), days_ago(5)], "loved"), (None, [days_ago(3)], None),
        (body["worn_in"][2]["outfit_id"], [days_ago(8)], None)]
    assert body["worn_in"][0]["pieces"]["base"] == ids["tee"] and body["worn_in"][2]["pieces"]["outer"] == ids["jacket"]
    assert first["id"] != again["id"]
    # a wear removed on the item page leaves the outfit in Worn, and its day off the piece's page
    client.delete(f"/api/items/{ids['tee']}/wears/{days_ago(1)}")
    after = client.get(f"/api/items/{ids['tee']}").json()["worn_in"]
    assert [(r["outfit_id"], r["days"]) for r in after][:2] == [(None, [days_ago(3)]), (first["id"], [days_ago(5)])]
    # clean, Today can build around it; in the laundry it has nothing to build around, and the page says why
    assert client.post(f"/api/items/{ids['tee']}/laundry", json={"state": "clean"}).status_code == 200
    assert client.get(f"/api/items/{ids['tee']}").json()["build_around"] is None
    assert client.post(f"/api/items/{ids['tee']}/laundry", json={"state": "laundry"}).status_code == 200
    assert client.get(f"/api/items/{ids['tee']}").json()["build_around"] == "laundry"
