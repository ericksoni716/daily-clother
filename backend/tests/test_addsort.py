"""One Add for everything: what each chosen photo shows, asked of Claude before anything is added (17 November)."""
import pytest

from closet import spend
from closet.tagger import addsort, correcting
from closet.tagger.addsort import PhotoKind, PhotoKinds
from closet.tagger.tagging import CapReached, TaggingError, Unreachable

from .conftest import photo_bytes


def answer(*rows):
    return PhotoKinds(photos=[PhotoKind(photo=i, kind=k, shoe=s) for i, k, s in rows])


def test_the_answer_is_tidied_shoes_numbered_in_order_and_gaps_are_pieces():
    got = addsort.read(answer((1, "shoe", 7), (2, "piece", 0), (3, "shoe", 3), (4, "shoe", 7), (6, "shoe", 0),
                              (9, "pieces", 0)), 6)
    assert got == [{"kind": "shoe", "shoe": 1}, {"kind": "piece", "shoe": 0}, {"kind": "shoe", "shoe": 2},
                   {"kind": "shoe", "shoe": 1}, {"kind": "piece", "shoe": 0},   # photo 5 was not answered
                   {"kind": "shoe", "shoe": 3}]                                   # a shoe photo with no number: its own


def test_the_photos_go_small_in_one_call_and_never_more_than_ten(monkeypatch):
    from PIL import Image
    seen = {}

    def fake_ask(text, images, routes, **kw):
        seen.update(count=len(images), sizes={max(i.size) for i in images}, model=kw["model"], text=text)
        return correcting.CorrectionResult(answer((1, "piece", 0), (2, "shoe", 1)), "plan", kw["model"])
    monkeypatch.setattr(correcting, "ask", fake_ask)
    photos = [Image.new("RGB", (3000, 2000)), Image.new("RGB", (900, 1600))]
    assert addsort.ask(photos, ("plan",)) == [{"kind": "piece", "shoe": 0}, {"kind": "shoe", "shoe": 1}]
    assert seen["count"] == 2 and seen["sizes"] == {addsort.MAX_EDGE} and seen["model"] == addsort.MODEL
    assert "There are 2 photos" in seen["text"]
    with pytest.raises(ValueError):
        addsort.ask([Image.new("RGB", (10, 10))] * (addsort.MAX_PHOTOS + 1), ("plan",))
    # a sort costs a fraction of a cent
    assert spend.estimate_sort_add(10) < 0.05


def post(client, n=2):
    files = [("photos", (f"p{i}.jpg", photo_bytes(color=(i * 20, 80, 120)), "image/jpeg")) for i in range(n)]
    return client.post("/api/add/sort", files=files)


def test_sorting_on_add_through_claude_and_when_it_cannot(client, services, claude):
    claude.mode = "answers"   # a route to Claude can be used
    services.add_sorter = lambda photos, routes: [{"kind": "piece", "shoe": 0}, {"kind": "shoe", "shoe": 1}]
    r = post(client)
    assert r.status_code == 200 and r.json() == {"sorted": True, "message": None,
                                                 "photos": [{"kind": "piece", "shoe": 0}, {"kind": "shoe", "shoe": 1}]}
    plain = [{"kind": "piece", "shoe": 0}] * 2
    for error, words in ((CapReached("limit"), "spending limit"), (Unreachable("offline"), "can't be reached"),
                         (TaggingError("bad"), "couldn't tell")):
        def failing(photos, routes, e=error):
            raise e
        services.add_sorter = failing
        body = post(client).json()
        assert body["sorted"] is False and body["photos"] == plain and words in body["message"], body
    claude.mode = "unavailable"   # no route at all: Claude is not even asked
    services.add_sorter = lambda photos, routes: pytest.fail("asked with no route")
    assert post(client).json()["sorted"] is False
    assert post(client, addsort.MAX_PHOTOS + 1).status_code == 422
    assert client.post("/api/add/sort", files=[("photos", ("x.jpg", b"not a photo", "image/jpeg"))]).status_code in (200, 400)


def test_the_demo_closet_is_never_sent_to_claude(client, services, claude):
    claude.mode = "answers"
    services.add_sorter = lambda photos, routes: pytest.fail("the demo was sent to Claude")
    client.post("/api/profile", json={"profile": "demo"})
    body = post(client).json()
    assert body["sorted"] is False and "demo" in body["message"]


def test_sorting_needs_login(anon):
    assert anon.post("/api/add/sort", files=[("photos", ("p.jpg", photo_bytes(), "image/jpeg"))]).status_code == 401
