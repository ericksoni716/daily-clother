"""A garment's look is read from one place: the description its drawing was made from, with the owner's corrections
folded over it (`closet/look.py`). Every reader of the look (the item page's JSON, the review queue, corrections by
sentence, and the rows the outfit engine, the stylist, gaps and trips are given) follows a correction together with
the drawing.

Claude is never called: `FakeClaude` (conftest) describes every photo as a navy polo with short sleeves.
"""
import json
from contextlib import closing

import pytest

from closet import corrections, db, items, look, outfits, review, styling, today

from .conftest import upload


def described(client, services, claude, key="k1"):
    claude.mode = "answers"
    item = upload(client, key=key).json()
    services.worker.is_ready = lambda: True
    services.worker.drain()
    assert services.tag_worker.drain() == 1
    claude.mode = "unavailable"
    return client.get(f"/api/items/{item['id']}").json()


def answer(silhouette=None, **details):
    return {"category": "shirt", "silhouette": silhouette or {}, "details": details}


@pytest.mark.parametrize("found,expected", [
    (answer(), {}),                                                     # nothing said: nothing shown
    (answer({"sleeve": "short", "fit": "slim"}), {"sleeve": "short", "fit": "slim"}),   # the coarse shape fills in
    (answer({"sleeve": "short"}, sleeve_length="long"), {"sleeve": "long"}),            # the details decide
    (answer({"sleeve": "short"}, sleeve_length="na"), {"sleeve": "short"}),             # unless they leave it unsaid
    (answer({"fit": "slim"}, fit_detail="regular"), {"fit": "slim"}),    # "regular" is the details' unsaid, as drawn
    (answer(fit_detail="oversized"), {"fit": "oversized"}),
    (answer(fit_detail="cropped"), {"top_length": "cropped"}),          # the cut that is a length
    (answer({"neck": "crew"}, collar="button_down"), {"neck": "collar"}),
    (answer({"neck": "collar"}, collar="none", neckline="v_neck"), {"neck": "v"}),
    (answer(leg_shape="skinny", trouser_break="cropped"), {"leg": "tapered", "pant_length": "ankle"}),
    (answer({"shoe_height": "low"}, shoe_style="chelsea_boot"), {"shoe_height": "high"}),
    (answer({"sleeve": "very long", "made_up": "x"}), {}),              # words outside the vocabulary are left out
    (None, {}), ({"details": "heavy"}, {}),
])
def test_the_shape_is_read_the_way_the_drawing_reads_the_answer(found, expected):
    assert look.shape_of(found) == expected


def readers(cfg, item_id):
    """What each reader of the look says about the item's sleeves and weight."""
    with closing(db.connect(cfg.db_path("main"))) as conn:
        row = items.get(conn, item_id)
        engine = next(r for r in today.closet_rows(conn) if r["id"] == item_id)
        piece = outfits._piece(engine)
        return {
            "page": items.detail(conn, row)["silhouette"].get("sleeve"),
            "worn": next(w["value"] for w in items.detail(conn, row)["as_worn"] if w["part"] == "sleeve"),
            "engine": engine["silhouette"].get("sleeve"),
            "long_sleeve": piece.long_sleeve,
            "weight": engine["weight_class"],
            "stylist": styling._line(1, engine, piece, None),
            "sentence": corrections._description(row)["silhouette.sleeve"],
        }


def test_a_correction_changes_the_drawing_and_every_word_together(client, services, claude, cfg):
    item = described(client, services, claude)
    before = readers(cfg, item["id"])
    assert (before["page"], before["worn"], before["engine"], before["sentence"]) == ("short", "short", "short", "short")
    assert before["long_sleeve"] is False and before["weight"] == "midweight"
    drawing = client.get(item["illustration_url"]).text

    # the owner corrects the sleeves and the cloth's weight in the details one by one
    r = client.put(f"/api/items/{item['id']}/details", json={"details": {"sleeve_length": "long", "weight": "heavyweight"}})
    assert r.status_code == 200
    after = readers(cfg, item["id"])
    assert (after["page"], after["worn"], after["engine"], after["sentence"]) == ("long", "long", "long", "long")
    assert after["long_sleeve"] is True and after["weight"] == "heavyweight"   # the engine dresses what is drawn
    assert "long sleeve" in after["stylist"] and "short sleeve" not in after["stylist"]
    assert r.json()["details"]["sleeve_length"] == "long"                      # the details on the page are the drawing's
    assert client.get(r.json()["illustration_url"]).text != drawing            # and the drawing changed with them


def test_the_owners_shape_wins_once_set_and_every_reader_follows(client, services, claude, cfg):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"sleeve_length": "long"}})
    # set later on the coarse shape (the review queue does this): the latest word wins, everywhere
    assert client.patch(f"/api/items/{item['id']}", json={"silhouette": {"sleeve": "none"}}).status_code == 200
    now = readers(cfg, item["id"])
    assert (now["page"], now["worn"], now["engine"], now["sentence"]) == ("none", "none", "none", "none")


def test_the_review_queue_asks_only_about_what_is_still_claudes(client, services, claude, cfg):
    item = described(client, services, claude)
    with closing(db.connect(cfg.db_path("main"))) as conn:   # Claude was unsure of the shape
        conn.execute("UPDATE items SET confidence = json_set(confidence, '$.silhouette', 0.5) WHERE id = ?", (item["id"],))
        shape = next(f for f in review.doubtful(items.get(conn, item["id"])) if f["field"] == "silhouette")
    assert shape["value"]["sleeve"] == "short"
    client.put(f"/api/items/{item['id']}/details", json={"details": {"sleeve_length": "long"}})
    with closing(db.connect(cfg.db_path("main"))) as conn:
        shape = next(f for f in review.doubtful(items.get(conn, item["id"])) if f["field"] == "silhouette")
    assert "sleeve" not in shape["value"] and shape["value"]["neck"] == "collar"   # the sleeve is the owner's word now


def test_an_item_never_described_is_read_from_its_own_fields(client):
    item = upload(client).json()
    r = client.patch(f"/api/items/{item['id']}", json={"category": "tee", "silhouette": {"sleeve": "long", "fit": "slim"}})
    assert r.json()["silhouette"] == {"sleeve": "long", "fit": "slim"} and r.json()["details"] is None


def test_the_notes_are_found_in_whichever_box_they_are_kept(client):
    item = upload(client).json()
    client.patch(f"/api/items/{item['id']}", json={"wear_notes": "Only with the grey trousers"})
    found = client.get("/api/items", params={"q": "grey trousers"}).json()["items"]
    assert [i["id"] for i in found] == [item["id"]]


def test_a_row_without_a_description_or_with_a_broken_one_has_no_look():
    row = {"category": "bag", "color": "black", "pattern": "solid", "source": "{}", "silhouette": "{}",
           "tag_answer": "{nope", "own_details": None}
    assert look.answer(row) is None and look.shape(row) == {}
    assert json.loads(json.dumps(look.details(row)))["fit_detail"] == "regular"   # the plain details
