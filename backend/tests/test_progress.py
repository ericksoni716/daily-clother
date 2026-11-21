"""One progress value per item (`progress.of`), worked out from its columns, and `GET /api/progress`."""
import pytest

from closet import progress, shoedraw, shoeviews, spend, tagjobs

from .conftest import upload


def row(**over):
    """An item with nothing under way: cut out, described, nothing measured, not a shoe."""
    base = {"category": "polo", "pattern": "solid", "cutout_state": "ready", "cutout_error": None,
            "tag_state": "done", "tag_error": None, "pattern_state": None, "trace_state": None,
            "views_state": None, "views_error": None, "drawn_state": None, "drawn_error": None, "drawn_note": None,
            "drawn_note_about": None}
    return {**base, **over}


def shoe(**over):
    return row(**{"category": "sneakers", "views_state": "sorted", "trace_state": "done", "drawn_state": "done", **over})


def brief(p):
    """(stage, step, state, waiting_for) of a progress value, or None."""
    return None if p is None else (p["stage"], p["step"], p["state"], p["waiting_for"])


@pytest.mark.parametrize("over, expected", [
    # nothing under way
    ({}, None),
    ({"tag_state": None}, None),                       # never to be described (the demo closet, older items)
    ({"cutout_state": None, "tag_state": "none"}, None),
    ({"pattern_state": "done"}, None),
    ({"pattern_state": "failed"}, None),               # the drawing stays as described; the page offers a new photo
    # 1: cutting out
    ({"cutout_state": "pending", "tag_state": None}, ("cutout", 1, "queued", None)),
    ({"cutout_state": "processing", "tag_state": None}, ("cutout", 1, "working", None)),
    ({"cutout_state": "failed", "tag_state": None}, ("cutout", 1, "failed", None)),
    # a new photo of an item already described is cut out again before anything else
    ({"cutout_state": "processing", "pattern_state": "waiting"}, ("cutout", 1, "working", None)),
    # 2: describing and drawing
    ({"tag_state": "waiting"}, ("describing", 2, "queued", None)),
    ({"tag_state": "working"}, ("describing", 2, "working", None)),
    ({"tag_state": "waiting", "tag_error": spend.LIMIT_REACHED}, ("describing", 2, "waiting", "limit")),
    ({"tag_state": "waiting", "tag_error": tagjobs.SIGN_IN}, ("describing", 2, "waiting", "sign-in")),
    ({"tag_state": "failed", "tag_error": tagjobs.FAILED}, ("describing", 2, "failed", None)),
    # 3: finishing the drawing, a pattern
    ({"pattern": "plaid", "pattern_state": "waiting"}, ("pattern", 3, "queued", None)),
    ({"pattern": "plaid", "pattern_state": "working"}, ("pattern", 3, "working", None)),
])
def test_each_state_of_an_item(over, expected):
    assert brief(progress.of(row(**over))) == expected


@pytest.mark.parametrize("over, expected", [
    ({}, None),
    ({"trace_state": "refused"}, None),                # drawn from its details; its own notice offers a new photo
    ({"drawn_state": "failed"}, None),                 # its own notice offers to try again
    ({"views_state": "failed"}, None),
    ({"views_state": None, "trace_state": None, "drawn_state": None}, None),   # a shoe kept before any of this
    ({"trace_state": "waiting"}, ("trace", 3, "queued", None)),
    ({"trace_state": "working"}, ("trace", 3, "working", None)),
    ({"views_state": "waiting"}, ("views", 3, "queued", None)),
    ({"views_state": "sorting"}, ("views", 3, "working", None)),
    ({"views_state": "asking"}, ("views", 3, "waiting", "you")),
    ({"views_state": "waiting", "views_error": shoeviews.NO_ROUTE}, ("views", 3, "waiting", "claude")),
    ({"views_state": "waiting", "views_error": shoeviews.LIMIT}, ("views", 3, "waiting", "limit")),
    ({"drawn_state": "waiting"}, ("shoe", 3, "queued", None)),
    ({"drawn_state": "drawing"}, ("shoe", 3, "working", None)),
    ({"drawn_state": "correcting", "drawn_note": "black laces"}, ("shoe", 3, "working", None)),
    ({"drawn_state": "waiting", "drawn_error": shoedraw.NO_ROUTE}, ("shoe", 3, "waiting", "claude")),
    ({"drawn_state": "waiting", "drawn_error": shoedraw.CORRECT_LIMIT, "drawn_note": "x"}, ("shoe", 3, "waiting", "limit")),
    ({"drawn_state": "waiting", "drawn_error": shoedraw.CORRECT_SIDE_NO_ROUTE, "drawn_note": "x",
      "drawn_note_about": "side"}, ("shoe", 3, "waiting", "claude")),
    ({"drawn_state": "waiting", "drawn_error": shoedraw.CORRECT_SIDE_LIMIT, "drawn_note": "x",
      "drawn_note_about": "side"}, ("shoe", 3, "waiting", "limit")),
    ({"drawn_state": "waiting", "views_state": "asking"}, ("views", 3, "waiting", "you")),
    ({"drawn_state": "waiting", "views_state": "failed"}, ("shoe", 3, "waiting", "you")),
    # the part going furthest is the one said: a trace being made before a drawing that waits for Claude
    ({"trace_state": "working", "drawn_state": "waiting", "drawn_error": shoedraw.LIMIT}, ("trace", 3, "working", None)),
    ({"views_state": "sorting", "drawn_state": "waiting"}, ("views", 3, "working", None)),
])
def test_each_state_of_a_shoe(over, expected):
    assert brief(progress.of(shoe(**over))) == expected


def test_a_note_about_the_side_says_it_is_the_side_drawing_that_changes():
    front = progress.of(shoe(drawn_state="correcting", drawn_note="black laces"))
    side = progress.of(shoe(drawn_state="correcting", drawn_note="a taller heel", drawn_note_about="side"))
    waiting = progress.of(shoe(drawn_state="waiting", drawn_note="a taller heel", drawn_note_about="side"))
    assert front["words"] == progress.CORRECTING == "Changing the drawing as you asked"
    assert side["words"] == waiting["words"] == progress.CORRECTING_SIDE == "Changing the side drawing as you asked"


def test_a_shoes_columns_mean_nothing_on_anything_else():
    assert progress.of(row(trace_state="working", views_state="sorting", drawn_state="drawing")) is None


@pytest.mark.parametrize("model, waits_for", [("missing", "model"), ("failed", "model"), ("downloading", "download")])
def test_a_cutout_waits_for_background_removal(model, waits_for):
    p = progress.of(row(cutout_state="pending", tag_state=None), progress.Waits(model=model))
    assert brief(p) == ("cutout", 1, "waiting", waits_for)
    assert p["words"] == progress.WAIT_WORDS[waits_for] and "background" in p["why"].lower()
    # one already being cut out carries on
    assert progress.of(row(cutout_state="processing"), progress.Waits(model=model))["state"] == "working"


def test_describing_waits_for_claude_only_when_the_queue_found_it_out_of_reach():
    assert brief(progress.of(row(tag_state="waiting"), progress.Waits(claude=True))) == ("describing", 2, "waiting", "claude")
    # a reason Closet knows is said over the general one
    assert progress.of(row(tag_state="waiting", tag_error=spend.LIMIT_REACHED), progress.Waits(claude=True))["waiting_for"] == "limit"


def test_the_words_and_what_can_be_tried_again():
    p = progress.of(row(cutout_state="processing"))
    assert p["title"] == "Cutting out" and p["words"] == "Removing the background" and p["of"] == 3
    assert p["about"].startswith("On this computer") and not p["can_retry"]
    p = progress.of(row(tag_state="working"))
    assert p["title"] == "Describing and drawing" and p["words"] == "Claude is describing it"
    assert "The drawing appears as soon as it is described" in p["about"]
    p = progress.of(row(pattern="plaid", pattern_state="working"))
    assert (p["title"], p["words"]) == ("Finishing the drawing", "Measuring the plaid from the photo")
    assert progress.of(row(pattern="stripe", pattern_state="working"))["words"] == "Measuring the stripes from the photo"
    assert progress.of(shoe(drawn_state="drawing"))["about"] == "By Claude, four to ten minutes."
    failed = progress.of(row(cutout_state="failed", cutout_error="Too dark."))
    assert (failed["error"], failed["can_retry"], failed["retry"]) == ("Too dark.", True, "cutout")
    failed = progress.of(row(tag_state="failed", tag_error=tagjobs.FAILED))
    assert (failed["error"], failed["retry"]) == (tagjobs.FAILED, "describe")
    limit = progress.of(row(tag_state="waiting", tag_error=spend.LIMIT_REACHED))
    assert limit["why"] == spend.LIMIT_REACHED and not limit["can_retry"]


def test_the_item_carries_its_progress(client, services):
    item = upload(client).json()
    assert item["progress"]["stage"] == "cutout"
    listed = client.get("/api/items").json()["items"][0]
    assert listed["progress"]["stage"] == "cutout"


def test_the_endpoint_lists_only_items_under_way(client, services, claude):
    first = upload(client, key="a").json()
    second = upload(client, key="b").json()
    got = client.get("/api/progress").json()
    # the model is not set up in tests: both cutouts wait for it, and why is said once
    assert [i["id"] for i in got["items"]] == [first["id"], second["id"]]
    assert {i["progress"]["waiting_for"] for i in got["items"]} == {"model"}
    assert (got["going"], got["waiting"]) == (0, 2) and "background" in got["why"].lower()

    services.worker.is_ready = lambda: True
    services.worker.drain()   # cut out; no way to reach Claude in tests until a test says so
    services.tag_worker.drain()
    got = client.get("/api/progress").json()
    assert {i["progress"]["waiting_for"] for i in got["items"]} == {"claude"}
    assert got["why"] is None   # nothing for the owner to see to in Settings: it goes on by itself
    assert got["items"][0]["thumb_url"].startswith("/media/")

    claude.mode = "answers"
    services.tag_worker.drain()
    got = client.get("/api/progress").json()
    assert got == {"items": [], "going": 0, "waiting": 0, "why": None}
    assert client.get(f"/api/items/{first['id']}").json()["progress"] is None


def test_the_endpoint_needs_a_login(anon):
    assert anon.get("/api/progress").status_code == 401
