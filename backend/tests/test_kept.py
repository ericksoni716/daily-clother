"""Outfits you keep (closet/kept.py): kept without wearing, the same pieces kept twice said and not duplicated, a name
given later, removed with Undo, and an outfit whose piece has left the closet still kept and still worn again."""
import pytest

from .test_plans import clock, outfit_of, suggest  # noqa: F401  (the clock is a fixture)
from .test_weather import small_closet

pytestmark = pytest.mark.usefixtures("clock")


def keep(client, pieces, **more):
    return client.post("/api/outfits/kept", json={"pieces": pieces, **more})


def test_an_outfit_is_kept_without_wearing_it_and_kept_twice_is_said(client):
    ids = small_closet(client)
    r = keep(client, outfit_of(ids))
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["already"] is False and first["outfit"]["name"] is None and first["outfit"]["gone"] == []
    assert client.get(f"/api/items/{ids['tee1']}").json()["wear_count"] == 0   # not a wear
    # the same pieces in another order are the same outfit: said, not kept twice
    shuffled = {**outfit_of(ids), "accessories": []}
    again = keep(client, shuffled)
    assert again.status_code == 200 and again.json()["already"] is True and again.json()["outfit"]["id"] == first["outfit"]["id"]
    keep(client, outfit_of(ids, "tee2"))
    listed = client.get("/api/outfits/kept").json()["outfits"]
    assert [o["pieces"]["base"] for o in listed] == [ids["tee2"], ids["tee1"]]   # newest first


def test_a_kept_outfit_takes_a_name_later_and_is_removed_with_undo(client):
    ids = small_closet(client)
    oid = keep(client, outfit_of(ids)).json()["outfit"]["id"]
    named = client.patch(f"/api/outfits/kept/{oid}", json={"name": "  Friday   lunch "})
    assert named.status_code == 200 and named.json()["name"] == "Friday lunch"
    assert client.patch(f"/api/outfits/kept/{oid}", json={"name": "x" * 61}).status_code == 422
    assert client.patch(f"/api/outfits/kept/{oid}", json={"name": ""}).json()["name"] is None
    removed = client.delete(f"/api/outfits/kept/{oid}")
    assert removed.status_code == 200 and removed.json()["removed"]["id"] == oid
    assert client.get("/api/outfits/kept").json()["outfits"] == []
    assert client.delete(f"/api/outfits/kept/{oid}").status_code == 404
    back = client.post(f"/api/outfits/kept/{oid}/restore")
    assert back.status_code == 200 and [o["id"] for o in client.get("/api/outfits/kept").json()["outfits"]] == [oid]
    assert client.post(f"/api/outfits/kept/{oid}/restore").status_code == 404   # it is not removed
    # kept again after removing: the same one comes back
    client.delete(f"/api/outfits/kept/{oid}")
    again = keep(client, outfit_of(ids)).json()
    assert again["outfit"]["id"] == oid and again["already"] is False


def test_an_outfit_whose_piece_left_the_closet_stays_and_is_worn_with_its_place_filled(client):
    ids = small_closet(client)
    oid = keep(client, outfit_of(ids)).json()["outfit"]["id"]
    assert client.delete(f"/api/items/{ids['tee1']}").status_code in (200, 204)
    listed = client.get("/api/outfits/kept").json()["outfits"]
    assert [o["id"] for o in listed] == [oid] and listed[0]["gone"] == [ids["tee1"]]
    answer = suggest(client, again=oid)
    assert answer["context"]["again"] == {"id": oid, "worn_on": None, "kept": [ids["jeans"], ids["sneakers"]],
                                          "unavailable": [ids["tee1"]]}
    assert answer["outfits"][0]["pieces"]["base"] == ids["tee2"]


@pytest.mark.parametrize("pieces, status", [
    ({"base": "nothing"}, 422),                                  # one piece
    ({"base": "a", "bottom": "a"}, 422),                         # the same piece twice
    ({"hat": "a", "base": "b"}, 422),                            # not a place
    ("tee and jeans", 422),
])
def test_keeping_refuses_what_is_not_an_outfit(client, pieces, status):
    assert keep(client, pieces).status_code == status


def test_keeping_refuses_a_piece_not_in_the_closet(client):
    ids = small_closet(client)
    assert keep(client, {**outfit_of(ids), "base": "not-there"}).status_code == 404
    assert client.patch("/api/outfits/kept/nope", json={"name": "x"}).status_code == 404


def test_wear_this_on_a_kept_outfit_with_a_piece_away_fills_its_place_and_says_where_it_is(client):
    ids = small_closet(client)
    oid = keep(client, outfit_of(ids)).json()["outfit"]["id"]
    assert client.put(f"/api/items/{ids['tee1']}/away", json={"place": "tailor", "until": "2026-11-20"}).status_code == 200
    answer = suggest(client, again=oid)
    assert answer["context"]["again"]["unavailable"] == [ids["tee1"]]
    assert answer["context"]["again"]["away"] == {ids["tee1"]: "is at the tailor's until Friday 20 November"}
    assert answer["outfits"][0]["pieces"]["base"] == ids["tee2"]
