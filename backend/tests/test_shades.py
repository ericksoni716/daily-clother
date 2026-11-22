"""The owner choosing a named shade by hand (22 November, the owner: "i feel like i don't have that many color choices").

A shade is one of the taxonomy's named shades. Chosen by the owner, it is kept with their details, decides the colour
word (which outfits, gaps and Would this work? read) and the colour the item is drawn in, and stays when the item is
described again. Claude is never called: `FakeClaude` (conftest) describes every photo as a navy polo.
"""
import json
from contextlib import closing

from closet import corrections, db, items, vocab
from closet.tagger.taxonomy import SHADES

from .conftest import upload

SAGE, TEAL = SHADES["sage"][0], SHADES["teal"][0]


def described(client, services, claude, key="k1"):
    claude.mode = "answers"
    item = upload(client, key=key).json()
    services.worker.is_ready = lambda: True
    services.worker.drain()
    assert services.tag_worker.drain() == 1
    return client.get(f"/api/items/{item['id']}").json()


def patch(client, item_id, **changes):
    r = client.patch(f"/api/items/{item_id}", json=changes)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_page_is_given_every_shade_with_its_colour_word():
    listed = items.shades()
    assert [s["name"] for s in listed] == list(SHADES)
    assert all(s["color"] in vocab.COLOR and s["hex"] == SHADES[s["name"]][0] for s in listed)


def test_the_vocabulary_carries_the_shades(client):
    got = client.get("/api/vocab").json()
    assert got["shades"] == items.shades()
    assert {"name": "sage", "hex": SAGE, "color": "green"} in got["shades"]


def test_a_chosen_shade_sets_the_colour_word_and_the_drawn_colour_as_the_owners(client, services, claude):
    item = described(client, services, claude)
    assert item["color"] == "navy"
    saved = patch(client, item["id"], shade="sage")
    assert (saved["color"], saved["color_hex"], saved["shade"]) == ("green", SAGE, "sage")
    assert saved["source"]["color"] == "user" and saved["source"]["color_hex"] == "user"
    assert saved["own_details"] == {"shade": "sage"}
    assert SAGE in client.get(saved["illustration_url"]).text.lower()
    # one change in the history, which can be undone as one
    entry = client.get(f"/api/items/{item['id']}/history").json()[0]
    assert entry["kind"] == "field" and {p["name"] for p in entry["parts"]} == {"color", "color_hex", "shade"}
    undone = client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo").json()["item"]
    assert (undone["color"], undone["own_details"]) == ("navy", {})
    assert undone["shade"] != "sage"


def test_the_shade_decides_the_colour_sent_with_it(client, services, claude):
    item = described(client, services, claude)
    saved = patch(client, item["id"], shade="teal", color="navy", color_hex="#27344f")
    assert (saved["color"], saved["color_hex"], saved["shade"]) == ("green", TEAL, "teal")


def test_the_owners_shade_stays_when_the_item_is_described_again(client, services, claude):
    item = described(client, services, claude)
    patch(client, item["id"], shade="sage")
    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    again = client.get(f"/api/items/{item['id']}").json()
    assert (again["color"], again["color_hex"], again["shade"]) == ("green", SAGE, "sage")


def test_a_colour_chosen_alone_puts_aside_a_shade_of_another_colour(client, services, claude):
    item = described(client, services, claude)
    patch(client, item["id"], shade="sage")
    saved = patch(client, item["id"], color="navy", color_hex="#27344f")
    assert saved["own_details"] == {}
    assert saved["color"] == "navy" and saved["shade"] in {n for n, (_, c) in SHADES.items() if c == "navy"}
    # the same colour word and the shade's own colour leave it standing
    patch(client, item["id"], shade="sage")
    assert patch(client, item["id"], color="green", color_hex=SAGE)["shade"] == "sage"
    # another colour of the same word is no longer that shade
    assert patch(client, item["id"], color_hex="#3f7d4f")["own_details"] == {}


def test_a_null_shade_gives_it_back_and_leaves_the_colour(client, services, claude):
    item = described(client, services, claude)
    patch(client, item["id"], shade="sage")
    saved = patch(client, item["id"], shade=None)
    assert saved["own_details"] == {} and (saved["color"], saved["color_hex"]) == ("green", SAGE)


def test_an_unknown_shade_is_refused(client, services, claude):
    item = described(client, services, claude)
    for bad in ("ultraviolet", 3):
        r = client.patch(f"/api/items/{item['id']}", json={"shade": bad})
        assert r.status_code == 422
    assert client.get(f"/api/items/{item['id']}").json()["color"] == "navy"


def test_fix_the_details_no_longer_offers_the_shade_but_sets_it_by_the_same_rule(client, services, claude):
    item = described(client, services, claude)
    groups = client.get(f"/api/items/{item['id']}/details").json()["groups"]
    assert "shade" not in {d["name"] for g in groups for d in g["details"]}
    r = client.put(f"/api/items/{item['id']}/details", json={"details": {"shade": "teal"}})
    assert r.status_code == 200
    assert (r.json()["color"], r.json()["color_hex"], r.json()["shade"]) == ("green", TEAL, "teal")


def test_a_sentence_can_name_the_shade(client, services, claude, cfg):
    item = described(client, services, claude)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert "teal" in corrections._allowed(items.get(conn, item["id"]))["shade"]
        saved = corrections.confirm(conn, item["id"], "it is teal", [{"name": "color", "value": "green"},
                                                                    {"name": "shade", "value": "teal"}])
    assert (saved["color"], saved["color_hex"], saved["shade"]) == ("green", TEAL, "teal")


def test_anything_can_have_a_shade_and_keeps_it_when_its_kind_changes(client, services, claude, cfg):
    item = described(client, services, claude)
    patch(client, item["id"], shade="cognac")
    belt = patch(client, item["id"], category="belt")
    assert (belt["color"], belt["shade"], belt["own_details"]) == ("brown", "cognac", {"shade": "cognac"})
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert json.loads(items.get(conn, item["id"])["own_details"]) == {"shade": "cognac"}
