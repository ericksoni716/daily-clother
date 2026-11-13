"""Correcting an item: picking details, saying what is wrong, and the history that can be undone.

Claude is never called: `FakeClaude` (conftest) reads the sentences it knows and stands in for both routes.
"""
import json
import sqlite3

import pytest

from closet import db, details, illustrations, tagjobs
from closet.config import bundle_dir
from closet.tagger.schema import NAMED_HEX, ItemTags

from .conftest import upload


def cut(services):
    services.worker.is_ready = lambda: True
    return services.worker.drain()


def described(client, services, claude, key="k1"):
    """An item Claude has described (as a navy polo with three white buttons)."""
    claude.mode = "answers"
    item = upload(client, key=key).json()
    cut(services)
    assert services.tag_worker.drain() == 1
    return client.get(f"/api/items/{item['id']}").json()


def with_answer(client, services, cfg, key, answer: dict):
    """An item described by a given answer (one of the demo closet's), without asking anyone."""
    item = upload(client, key=key).json()
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("BEGIN IMMEDIATE")
        tagjobs.apply_answer(conn, item["id"], ItemTags.model_validate(answer), "plan", "fake")
        conn.execute("COMMIT")
    finally:
        conn.close()
    return client.get(f"/api/items/{item['id']}").json()


def demo_answer(name):
    data = json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))
    return next(it["answer"] for it in data["items"] if it["name"] == name)


def svg(client, item):
    return client.get(item["illustration_url"]).text


def history(client, item_id):
    r = client.get(f"/api/items/{item_id}/history")
    assert r.status_code == 200
    return r.json()


# ---- by picking

def test_a_picked_detail_changes_the_drawing_and_survives_describe_it_again(client, services, claude, cfg):
    item = described(client, services, claude)
    before = svg(client, item)
    r = client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 1, "v_insert": "yes"}})
    assert r.status_code == 200
    picked = r.json()
    assert picked["own_details"] == {"placket_buttons": 1, "v_insert": "yes"}
    assert picked["details"]["placket_buttons"] == 3   # Claude's answer is never edited
    after = svg(client, picked)
    assert after != before

    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    again = client.get(f"/api/items/{item['id']}").json()
    assert again["own_details"] == {"placket_buttons": 1, "v_insert": "yes"}
    assert svg(client, again) == after

    # giving a detail back to Claude's answer
    back = client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": None, "v_insert": None}}).json()
    assert back["own_details"] == {} and svg(client, back) == before


def test_a_picked_value_must_be_one_of_the_choices_for_this_kind_of_garment(client, services, claude):
    item = described(client, services, claude)
    for bad in ({"placket_buttons": 40}, {"collar": "ruff"}, {"pleats": "yes"}, {"category": "shirt"}, {"nonsense": 1}):
        r = client.put(f"/api/items/{item['id']}/details", json={"details": bad})
        assert r.status_code == 422, bad
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {}
    assert len(history(client, item["id"])) == 1   # only Claude's answer
    assert client.get(f"/api/items/{item['id']}/details/pleats").status_code == 404
    assert client.put("/api/items/nope/details", json={"details": {"placket_buttons": 1}}).status_code == 404


KINDS = {"Blue oxford shirt": "top", "Cream v-neck sweater": "top", "Grey wool trousers": "bottom",
         "White leather sneakers": "shoe"}


@pytest.mark.parametrize("name", KINDS)
def test_the_options_are_the_ones_for_the_kind_of_garment_and_each_drawing_differs(client, services, cfg, name):
    answer = demo_answer(name)
    item = with_answer(client, services, cfg, name, answer)
    body = client.get(f"/api/items/{item['id']}/details").json()
    kind = KINDS[name]
    assert body["kind"] == kind
    assert [(g["id"], [d["name"] for d in g["details"]]) for g in body["groups"]] == \
        [(g, list(names)) for g, names in details.BY_KIND[kind]]
    current = svg(client, item)
    drawn_choices = 0
    for group in body["groups"]:
        for d in group["details"]:
            said = answer["details"].get(d["name"]) if d["name"] not in details.FEATURES else \
                ("yes" if d["name"] in answer["details"]["features"] else "no")
            assert d["value"] == said and d["own"] is False and d["words"]
            r = client.get(f"/api/items/{item['id']}/details/{d['name']}")
            assert r.status_code == 200
            found = r.json()["choices"]
            assert [c["value"] for c in found] == list(details.values(d["name"]))
            assert [c["value"] for c in found if c["current"]] == [said]
            for c in found:
                assert c["words"]
                if c["current"]:
                    assert c["svg"] is None
                elif c["svg"] is not None:
                    assert c["svg"] != current and c["svg"].startswith("<svg")
                    drawn_choices += 1
    assert drawn_choices > 3
    names = [d["name"] for g in body["groups"] for d in g["details"]]
    if kind == "top":
        assert "collar" in names and "placket_buttons" in names and "pleats" not in names
    if kind == "bottom":
        assert "pleats" in names and "waist" in names and "collar" not in names
    if kind == "shoe":
        assert "sole_color" in names and "toe_cap" in names and "placket" not in names


def test_buttons_on_a_shirt_are_offered_as_drawings(client, services, cfg):
    item = with_answer(client, services, cfg, "shirt", demo_answer("Blue oxford shirt"))
    found = client.get(f"/api/items/{item['id']}/details/placket_buttons").json()
    assert found["title"] == "number of buttons" and found["value"] == 7
    assert sum(1 for c in found["choices"] if c["svg"]) >= 5
    assert next(c for c in found["choices"] if c["value"] == 0)["words"] == "none"


def test_an_item_with_no_kind_has_nothing_to_fix(client):
    item = upload(client).json()
    body = client.get(f"/api/items/{item['id']}/details").json()
    assert body["kind"] is None and body["groups"] == [] and body["message"]


def test_a_detail_picked_on_an_item_claude_never_described_is_drawn(client):
    item = upload(client).json()
    client.patch(f"/api/items/{item['id']}", json={"category": "shirt", "color": "blue"})
    before = svg(client, client.get(f"/api/items/{item['id']}").json())
    picked = client.put(f"/api/items/{item['id']}/details", json={"details": {"collar": "band"}}).json()
    assert picked["own_details"] == {"collar": "band"} and svg(client, picked) != before


def test_a_shape_the_owner_sets_puts_aside_their_matching_details(client, services, claude):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"sleeve_length": "three_quarter", "placket_buttons": 1}})
    body = client.patch(f"/api/items/{item['id']}", json={"silhouette": {"sleeve": "long"}}).json()
    assert body["own_details"] == {"placket_buttons": 1}


# ---- by saying

def test_a_sentence_becomes_changes_applied_only_once_confirmed(client, services, claude):
    item = described(client, services, claude)
    before = svg(client, item)
    r = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "understood" and body["not_understood"] is None
    assert body["changes"] == [{"name": "placket_buttons", "title": "number of buttons", "value": 2, "before": 3,
                                "before_words": "3", "after_words": "2"}]
    assert "no photo" in body["sent"]
    sentence, description, allowed, photos, routes = claude.corrections[-1]
    assert photos == 0 and routes == ("plan",)
    assert description["placket_buttons"] == 3 and "name" not in description and "notes" not in description
    assert "2" in allowed["placket_buttons"] and "henley" in allowed["neckline"] and "pleats" not in allowed
    # nothing is applied yet
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {}
    assert len(history(client, item["id"])) == 1

    done = client.post(f"/api/items/{item['id']}/correct/confirm",
                       json={"sentence": body["sentence"], "changes": [{"name": c["name"], "value": c["value"]} for c in body["changes"]]})
    assert done.status_code == 200
    assert done.json()["own_details"] == {"placket_buttons": 2} and svg(client, done.json()) != before
    entry = history(client, item["id"])[0]
    assert entry["kind"] == "sentence" and entry["sentence"] == "it has two buttons" and entry["by"] == "owner"
    assert entry["parts"][0]["name"] == "placket_buttons" and (entry["parts"][0]["before"], entry["parts"][0]["after"]) == (3, 2)


def test_a_sentence_can_change_several_details_and_the_item_fields(client, services, claude):
    item = described(client, services, claude)
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it's a henley, not a tee"}).json()
    assert {c["name"]: c["value"] for c in body["changes"]} == {"neckline": "henley", "placket": "henley"}
    green = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it's actually green"}).json()
    assert green["changes"][0]["name"] == "color" and green["changes"][0]["after_words"] == "green"
    done = client.post(f"/api/items/{item['id']}/correct/confirm", json={
        "sentence": "it's a henley and green", "changes": [{"name": c["name"], "value": c["value"]}
                                                           for c in body["changes"] + green["changes"]]}).json()
    assert done["color"] == "green" and done["source"]["color"] == "user" and done["color_hex"].startswith("#")
    assert done["own_details"] == {"neckline": "henley", "placket": "henley"}
    entry = history(client, item["id"])[0]
    assert {p["name"] for p in entry["parts"]} == {"color", "color_hex", "neckline", "placket"}


def test_an_unclear_sentence_changes_nothing(client, services, claude):
    item = described(client, services, claude)
    for sentence in ("make it look nicer", "it is teal", "it has three buttons"):   # three is what it already has
        body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": sentence}).json()
        assert body["state"] == "not_understood" and body["changes"] == [] and body["not_understood"], sentence
    assert "teal" in client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it is teal"}).json()["not_understood"]
    # a value outside the vocabulary is refused even when sent to be confirmed
    r = client.post(f"/api/items/{item['id']}/correct/confirm",
                    json={"sentence": "it is teal", "changes": [{"name": "color", "value": "teal"}]})
    assert r.status_code == 422
    after = client.get(f"/api/items/{item['id']}").json()
    assert after["own_details"] == {} and after["color"] == "navy"
    assert len(history(client, item["id"])) == 1
    assert client.post(f"/api/items/{item['id']}/correct", json={"sentence": "   "}).status_code == 422
    assert client.post(f"/api/items/{item['id']}/correct", json={"sentence": "x" * 501}).status_code == 422


def test_the_photo_is_sent_only_when_the_sentence_needs_it(client, services, claude):
    item = described(client, services, claude)
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "the colour is wrong"}).json()
    assert [c[3] for c in claude.corrections] == [0, 1]
    assert "photo" in body["sent"] and "no photo" not in body["sent"]
    assert body["changes"][0]["name"] == "color" and body["changes"][0]["value"] == "burgundy"


def test_with_no_route_the_sentence_waits_and_nothing_changes(client, services, claude):
    item = described(client, services, claude)
    claude.mode = "unavailable"
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    assert body["state"] == "waiting" and body["changes"] == [] and "can't be reached" in body["message"]
    services.tag_worker.routes = lambda: ("plan",)   # looks usable, but the call finds the plan's limit reached
    assert client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()["state"] == "waiting"
    claude.mode = "fails"
    assert client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()["state"] == "failed"
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {}
    assert len(history(client, item["id"])) == 1


# ---- history and undo

def test_history_records_each_kind_of_change_newest_first(client, services, claude):
    item = described(client, services, claude)
    client.patch(f"/api/items/{item['id']}", json={"color": "green", "color_hex": "#3f7d4f"})
    client.patch(f"/api/items/{item['id']}", json={"notes": "a favourite", "location": "drawer"})   # not the description
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket": "half_placket_popover"}})
    found = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "the collar is white"}).json()
    client.post(f"/api/items/{item['id']}/correct/confirm", json={"sentence": "the collar is white", "changes": found["changes"]})
    entries = history(client, item["id"])
    assert [(e["kind"], e["by"]) for e in entries] == [("sentence", "owner"), ("detail", "owner"), ("field", "owner"),
                                                       ("answer", "claude")]
    assert entries[-1]["first_description"] and not entries[-1]["can_undo"] and entries[-1]["why_not"]
    assert all(e["at"] for e in entries) and all(e["can_undo"] for e in entries[:3])
    field = entries[2]["parts"]
    assert [(p["name"], p["before"], p["after"]) for p in field] == [("color", "navy", "green"),
                                                                     ("color_hex", item["color_hex"], "#3f7d4f")]
    detail = entries[1]["parts"][0]
    assert (detail["title"], detail["before_words"], detail["after_words"]) == ("front", "a polo placket", "a half placket")
    assert entries[0]["parts"][0]["name"] == "trim_color"

    # describing it again is recorded too, even when Claude says the same again
    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    entries = history(client, item["id"])
    assert entries[0]["kind"] == "answer" and not entries[0]["first_description"]
    assert entries[0]["parts"] == [] and not entries[0]["can_undo"]


def test_undo_restores_the_value_and_the_drawing(client, services, claude):
    item = described(client, services, claude)
    before = svg(client, item)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 1}})
    entry = history(client, item["id"])[0]
    r = client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo")
    assert r.status_code == 200
    body = r.json()
    assert body["item"]["own_details"] == {} and svg(client, body["item"]) == before
    assert body["history"][0]["kind"] == "undo" and body["history"][0]["undoes"] == entry["id"]
    assert body["history"][1]["undone"] and not body["history"][1]["can_undo"]
    assert client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo").status_code == 409

    # a field: its value, who set it and the drawing come back
    changed = client.patch(f"/api/items/{item['id']}", json={"color": "green", "color_hex": "#3f7d4f"}).json()
    assert svg(client, changed) != before
    entry = history(client, item["id"])[0]
    undone = client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo").json()["item"]
    assert (undone["color"], undone["color_hex"], undone["source"]["color"]) == (item["color"], item["color_hex"], "ai")
    assert undone["confidence"]["color"] == item["confidence"]["color"]
    assert svg(client, undone) == before

    # an undo can itself be undone
    again = history(client, item["id"])[0]
    redone = client.post(f"/api/items/{item['id']}/history/{again['id']}/undo").json()["item"]
    assert redone["color"] == "green"


def test_undoing_a_new_description_puts_the_earlier_one_back(client, services, claude, cfg):
    item = described(client, services, claude)
    first = svg(client, item)
    other = ItemTags.model_validate(demo_answer("Oatmeal henley"))
    services.tag_worker.tagger = lambda images, routes: tagjobs.TagResult(other, "fake", 0, 0, 0, 0.0, 1, route="plan")
    client.post(f"/api/items/{item['id']}/retag")
    assert services.tag_worker.drain() == 1
    changed = client.get(f"/api/items/{item['id']}").json()
    assert changed["category"] == "tee" and svg(client, changed) != first
    entry = history(client, item["id"])[0]
    assert entry["kind"] == "answer" and entry["can_undo"]
    back = client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo").json()["item"]
    assert back["category"] == "polo" and back["details"]["placket_buttons"] == 3 and svg(client, back) == first


def test_undo_is_refused_when_a_later_change_touched_the_same_thing(client, services, claude):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 1}})
    client.put(f"/api/items/{item['id']}/details", json={"details": {"collar": "spread"}})   # something else
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 2}})
    entries = history(client, item["id"])
    first = entries[2]
    assert not first["can_undo"] and "number of buttons" in first["why_not"]
    r = client.post(f"/api/items/{item['id']}/history/{first['id']}/undo")
    assert r.status_code == 409 and "undo that first" in r.json()["detail"]
    assert entries[1]["can_undo"]   # the collar was not touched again
    assert client.post(f"/api/items/{item['id']}/history/{entries[1]['id']}/undo").status_code == 200
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {"placket_buttons": 2}
    assert client.post(f"/api/items/{item['id']}/history/{entries[0]['id']}/undo").status_code == 200
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {"placket_buttons": 1}
    # the change from Claude's first description
    assert client.post(f"/api/items/{item['id']}/history/{entries[-1]['id']}/undo").status_code == 409
    assert client.post(f"/api/items/{item['id']}/history/99999/undo").status_code == 404


def undo(client, item_id, entry_id):
    return client.post(f"/api/items/{item_id}/history/{entry_id}/undo")


def redescribe(client, services, item_id, answer: ItemTags):
    services.tag_worker.tagger = lambda images, routes: tagjobs.TagResult(answer, "fake", 0, 0, 0, 0.0, 1, route="plan")
    assert client.post(f"/api/items/{item_id}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    return client.get(f"/api/items/{item_id}").json()


def test_undo_goes_back_several_steps(client, services, claude):
    item = described(client, services, claude)
    first = svg(client, item)
    for n in (1, 4, 6):
        client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": n}})
    six, four, one = history(client, item["id"])[:3]
    assert not four["can_undo"] and not one["can_undo"]
    assert undo(client, item["id"], six["id"]).json()["item"]["own_details"] == {"placket_buttons": 4}
    entries = {e["id"]: e for e in history(client, item["id"])}
    assert entries[four["id"]]["can_undo"] and not entries[one["id"]]["can_undo"]
    assert undo(client, item["id"], four["id"]).json()["item"]["own_details"] == {"placket_buttons": 1}
    assert {e["id"]: e for e in history(client, item["id"])}[one["id"]]["can_undo"]   # undone changes do not block
    back = undo(client, item["id"], one["id"]).json()["item"]
    assert back["own_details"] == {} and svg(client, back) == first

    # an undo undone puts the change back, and that blocks the earlier change again
    latest = history(client, item["id"])[0]
    assert latest["kind"] == "undo" and latest["undoes"] == one["id"]
    assert undo(client, item["id"], latest["id"]).json()["item"]["own_details"] == {"placket_buttons": 1}
    assert {e["id"]: e for e in history(client, item["id"])}[one["id"]]["undone"]
    redo_four = next(e for e in history(client, item["id"]) if e["kind"] == "undo" and e["undoes"] == four["id"])
    assert undo(client, item["id"], redo_four["id"]).json()["item"]["own_details"] == {"placket_buttons": 4}
    entries = history(client, item["id"])
    assert not next(e for e in entries if e["undoes"] == one["id"])["can_undo"]   # buttons changed again since


def test_undoing_a_new_description_puts_back_everything_it_changed(client, services, claude):
    item = described(client, services, claude)
    assert (item["name"], item["material"]) == ("Navy polo", "100% cotton")
    henley = redescribe(client, services, item["id"], ItemTags.model_validate(demo_answer("Oatmeal henley")))
    assert henley["name"] != item["name"] and henley["material"] is None
    assert henley["confidence"]["details"] != item["confidence"]["details"]
    entry = history(client, item["id"])[0]
    back = undo(client, item["id"], entry["id"]).json()["item"]
    for field in ("name", "material", "category", "color", "pattern", "silhouette", "confidence", "source"):
        assert back[field] == item[field], field
    assert svg(client, back) == svg(client, item)


def test_undoing_the_owners_change_after_a_new_description_follows_the_current_answer(client, services, claude):
    item = described(client, services, claude)
    green = client.patch(f"/api/items/{item['id']}", json={"color": "green", "color_hex": "#3f7d4f"}).json()
    assert green["source"]["color"] == "user"
    henley = ItemTags.model_validate(demo_answer("Oatmeal henley"))
    again = redescribe(client, services, item["id"], henley)
    assert again["color"] == "green"   # the owner's word stands
    owners = next(e for e in history(client, item["id"]) if e["kind"] == "field")
    assert owners["can_undo"]
    back = undo(client, item["id"], owners["id"]).json()["item"]
    # the field is what the answer now says, as if the answer had come after the undo
    assert (back["color"], back["color_hex"], back["source"]["color"]) == ("cream", NAMED_HEX["cream"], "ai")
    assert back["confidence"]["color"] == henley.color_confidence
    drawn = svg(client, back)
    assert redescribe(client, services, item["id"], henley)["color"] == "cream"
    assert svg(client, client.get(f"/api/items/{item['id']}").json()) == drawn   # the drawing already matched the answer


def test_undoing_the_answer_afterwards_takes_back_what_it_gave_to_other_fields(client, services, claude):
    item = described(client, services, claude)
    client.patch(f"/api/items/{item['id']}", json={"color": "green", "color_hex": "#3f7d4f"})
    redescribe(client, services, item["id"], ItemTags.model_validate(demo_answer("Oatmeal henley")))
    owners = next(e for e in history(client, item["id"]) if e["kind"] == "field")
    assert undo(client, item["id"], owners["id"]).json()["item"]["color"] == "cream"
    answer = next(e for e in history(client, item["id"]) if e["kind"] == "answer")
    assert answer["can_undo"]
    back = undo(client, item["id"], answer["id"]).json()["item"]
    # the colour came from the henley's answer, so it goes back with it to what the polo's answer says
    for field in ("category", "color", "color_hex"):
        assert back[field] == item[field], field
    assert back["source"]["color"] == "ai" and back["confidence"]["color"] == item["confidence"]["color"]
    assert svg(client, back) == svg(client, item)


def test_the_demo_drawing_made_in_advance_comes_back_whenever_the_item_is_as_it_was(client, services, cfg):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    polo = next(i for i in client.get("/api/items").json()["items"] if i["name"] == "Navy polo")
    drawn = svg(client, client.get(f"/api/items/{polo['id']}").json())
    client.put(f"/api/items/{polo['id']}/details", json={"details": {"placket_buttons": 3}})
    client.put(f"/api/items/{polo['id']}/details", json={"details": {"button_color": "white"}})
    buttons, colour = history(client, polo["id"])[1], history(client, polo["id"])[0]
    middle = undo(client, polo["id"], buttons["id"]).json()["item"]   # not the latest entry
    assert svg(client, middle) != drawn   # the white buttons are still there
    back = undo(client, polo["id"], colour["id"]).json()["item"]
    assert back["own_details"] == {} and svg(client, back) == drawn
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200


@pytest.mark.parametrize("state", ["pending", "failed"])
def test_no_photo_is_sent_while_its_background_is_not_removed(client, services, claude, cfg, state):
    claude.mode = "answers"
    item = upload(client, key="k1").json()   # not cut out yet
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("BEGIN IMMEDIATE")
        tagjobs.apply_answer(conn, item["id"], ItemTags.model_validate(demo_answer("Navy polo")), "plan", "fake")
        conn.execute("UPDATE items SET cutout_state = ? WHERE id = ?", (state, item["id"]))
        conn.execute("COMMIT")
    finally:
        conn.close()
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "the colour is wrong"}).json()
    assert [c[3] for c in claude.corrections] == [0]   # asked once, words only
    assert body["state"] == "not_understood" and body["changes"] == []
    assert "no photo" in body["sent"]
    assert "photo" in body["not_understood"] and ("not been removed yet" if state == "pending" else "could not be removed") \
        in body["not_understood"]


@pytest.mark.parametrize("method,path,payload", [
    ("post", "correct/confirm", {"sentence": "x", "changes": [{"name": "color", "value": [1]}]}),
    ("post", "correct/confirm", {"sentence": "x", "changes": [{"name": "color", "value": {"a": 1}}]}),
    ("post", "correct/confirm", {"sentence": "x", "changes": [{"name": 5, "value": "navy"}]}),
    ("post", "correct/confirm", {"sentence": "x", "changes": [{"name": "placket_buttons", "value": True}]}),
    ("post", "correct/confirm", {"sentence": "x", "changes": "navy"}),
    ("post", "correct/confirm", {"sentence": 5, "changes": [{"name": "color", "value": "navy"}]}),
    ("post", "correct/confirm", {"changes": [{"name": "color", "value": "navy"}]}),
    ("post", "correct/confirm", [1, 2]),
    ("post", "correct", {"sentence": ["it has two buttons"]}),
    ("post", "correct", {}),
    ("post", "correct", "it has two buttons"),
    ("put", "details", {"details": {"collar": ["band"]}}),
    ("put", "details", {"details": {"silhouette.sleeve": {"a": 1}}}),
    ("put", "details", {"details": "collar"}),
    ("put", "details", {}),
    ("post", "history/abc/undo", None),
])
def test_wrong_input_gets_a_plain_422(client, services, claude, method, path, payload):
    item = described(client, services, claude)
    r = getattr(client, method)(f"/api/items/{item['id']}/{path}", **({} if payload is None else {"json": payload}))
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str) and r.json()["detail"][0].isupper() and "{" not in r.json()["detail"]
    r = client.post(f"/api/items/{item['id']}/correct/confirm", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert len(history(client, item["id"])) == 1


def test_changing_the_kind_of_garment_puts_aside_details_it_does_not_have(client, services, claude):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"collar": "spread", "placket_buttons": 1}})
    trousers = client.patch(f"/api/items/{item['id']}", json={"category": "trousers"}).json()
    assert trousers["own_details"] == {}
    entry = history(client, item["id"])[0]
    assert {p["name"] for p in entry["parts"]} >= {"category", "collar", "placket_buttons"}
    back = undo(client, item["id"], entry["id"]).json()["item"]
    assert back["category"] == "polo" and back["own_details"] == {"collar": "spread", "placket_buttons": 1}
    # a sentence that changes the kind and sets a detail of the new kind
    client.patch(f"/api/items/{item['id']}", json={"category": "shirt"})
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {"collar": "spread", "placket_buttons": 1}


def test_the_sentence_routes_read_the_closet_once(client, services, claude, monkeypatch):
    claude.mode = "answers"
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    polo = next(i for i in client.get("/api/items").json()["items"] if i["name"] == "Navy polo")
    real = services.state.get
    reads = []

    def get(key):   # the closet switches to the real one just after the request starts
        if key == "profile":
            reads.append(key)
            return "demo" if len(reads) == 1 else "main"
        return real(key)
    monkeypatch.setattr(services.state, "get", get)
    r = client.post(f"/api/items/{polo['id']}/correct", json={"sentence": "it has two buttons"})
    assert r.status_code == 409 and claude.corrections == []
    reads.clear()
    r = client.post(f"/api/items/{polo['id']}/correct/confirm",
                    json={"sentence": "x", "changes": [{"name": "placket_buttons", "value": 2}]})
    assert r.status_code == 409
    monkeypatch.setattr(services.state, "get", real)
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200


def test_a_confirmation_is_refused_when_the_item_changed_since_claude_read_it(client, services, claude):
    item = described(client, services, claude)
    found = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 5}})
    r = client.post(f"/api/items/{item['id']}/correct/confirm", json={"sentence": found["sentence"], "changes": found["changes"]})
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {"placket_buttons": 5}


def test_confirming_a_field_is_recorded_and_can_be_undone(client, services, claude):
    item = described(client, services, claude)
    assert client.post(f"/api/items/{item['id']}/confirm", json={"fields": ["formality"]}).status_code == 200
    entry = history(client, item["id"])[0]
    assert entry["kind"] == "field" and [(p["name"], p["before"], p["after"], p["same"]) for p in entry["parts"]] == [
        ("formality", "smart_casual", "smart_casual", True)]
    back = undo(client, item["id"], entry["id"]).json()["item"]
    assert back["source"]["formality"] == "ai" and back["confidence"]["formality"] == item["confidence"]["formality"]
    # the same value given again by the owner makes it theirs: recorded too
    client.patch(f"/api/items/{item['id']}", json={"color": "navy"})
    entry = history(client, item["id"])[0]
    assert entry["kind"] == "field" and entry["parts"][0]["name"] == "color" and entry["parts"][0]["same"]
    # but a PATCH that changes nothing at all is not
    count = len(history(client, item["id"]))
    client.patch(f"/api/items/{item['id']}", json={"color": "navy"})
    assert len(history(client, item["id"])) == count


def test_the_history_goes_with_a_deleted_item(client, services, claude, cfg):
    item = described(client, services, claude)
    client.put(f"/api/items/{item['id']}/details", json={"details": {"placket_buttons": 1}})
    assert client.delete(f"/api/items/{item['id']}").status_code in (200, 204)
    conn = db.connect(cfg.db_path("main"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM changes WHERE item_id = ?", (item["id"],)).fetchone()[0] == 0
    finally:
        conn.close()
    assert client.get(f"/api/items/{item['id']}/history").status_code == 404


# ---- the demo closet, login, the migration

def test_the_demo_closet_can_be_corrected_by_picking_but_is_never_sent_to_claude(client, services, claude, cfg):
    claude.mode = "answers"
    mine = described(client, services, claude)
    client.put(f"/api/items/{mine['id']}/details", json={"details": {"placket_buttons": 1}})
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    polo = next(i for i in client.get("/api/items").json()["items"] if i["name"] == "Navy polo")
    body = client.get(f"/api/items/{polo['id']}").json()
    drawn = svg(client, body)
    assert history(client, polo["id"]) == []
    assert client.get(f"/api/items/{mine['id']}/history").status_code == 404
    options = client.get(f"/api/items/{polo['id']}/details").json()
    assert next(d for g in options["groups"] for d in g["details"] if d["name"] == "placket_buttons")["value"] == 2
    picked = client.put(f"/api/items/{polo['id']}/details", json={"details": {"placket_buttons": 3}}).json()
    assert svg(client, picked) != drawn
    r = client.post(f"/api/items/{polo['id']}/correct", json={"sentence": "it has two buttons"})
    assert r.status_code == 409 and "never sent to Claude" in r.json()["detail"]
    r = client.post(f"/api/items/{polo['id']}/correct/confirm",
                    json={"sentence": "x", "changes": [{"name": "placket_buttons", "value": 2}]})
    assert r.status_code == 409
    assert all(c[0] != "it has two buttons" for c in claude.corrections)
    entry = history(client, polo["id"])[0]
    back = client.post(f"/api/items/{polo['id']}/history/{entry['id']}/undo").json()["item"]
    assert svg(client, back) == drawn   # the demo's own drawing comes back

    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.get(f"/api/items/{polo['id']}/history").status_code == 404
    assert client.get(f"/api/items/{mine['id']}").json()["own_details"] == {"placket_buttons": 1}
    assert [e["kind"] for e in history(client, mine["id"])] == ["detail", "answer"]


def test_correcting_needs_login(anon):
    assert anon.get("/api/items/x/details").status_code == 401
    assert anon.get("/api/items/x/details/collar").status_code == 401
    assert anon.put("/api/items/x/details", json={"details": {"collar": "band"}}).status_code == 401
    assert anon.post("/api/items/x/correct", json={"sentence": "it has two buttons"}).status_code == 401
    assert anon.post("/api/items/x/correct/confirm", json={"sentence": "a", "changes": []}).status_code == 401
    assert anon.get("/api/items/x/history").status_code == 401
    assert anon.post("/api/items/x/history/1/undo").status_code == 401


def test_the_migration_runs_on_a_closet_made_by_the_previous_version(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = sqlite3.connect(path)
    last = 0
    ours = next(v for v, f in db.migration_files() if f.name.endswith("_corrections.sql"))
    for version, file in db.migration_files():
        if version < ours:   # a closet made by the version before corrections
            old.executescript(file.read_text(encoding="utf-8") + f"\nPRAGMA user_version = {version};")
            last = version
    old.execute("INSERT INTO items (id, name, category, cutout_state, created_at, updated_at) "
                "VALUES ('a', 'Old shirt', 'shirt', 'ready', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    old.commit()
    old.close()
    result = db.migrate(path, cfg.local_backups_dir)
    assert result["from"] == last and ours in result["applied"] and result["backup"]
    conn = db.connect(path)
    r = conn.execute("SELECT * FROM items WHERE id = 'a'").fetchone()
    assert r["name"] == "Old shirt" and r["own_details"] is None and details.own(r) == {}
    assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 0
    assert illustrations.make(r).svg   # drawn as before
    conn.close()
