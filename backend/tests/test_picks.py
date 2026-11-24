"""You might like: what a look is told and asks, how three are chosen, the weekly look, Save and Not for me
(closet/picks.py, tagger/shopping.py's `picks`, migration 0048).

Claude is never called: `PickShop` stands in for it (the same stand-in as a wish's search, with looks of its own), or,
for the API route, `FakeSearchApi` stands in for Anthropic's API with its web search tool.
"""
import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, picks, shop, spend, styleprofile
from closet.tagger import shopping
from closet.tagger.shopping import ShopAnswer
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import fake_cutter
from .test_shop import FakeSearchApi, FakeShop, product


class PickShop(FakeShop):
    """Claude for shopping, with "You might like" too. `pick_finds`: what the next look answers (by default a coat, a
    sweater, trousers, a second coat and a product whose link is not a web address); `told`: what each look was told."""

    def __init__(self):
        super().__init__()
        self.pick_finds = [
            product(name="Olive chore coat", url="https://shop.example/p/chore", color="olive"),
            product(name="Cream merino crewneck", url="https://shop.example/p/crew", category="sweater", color="cream",
                    rain_proof=False, season="cool"),
            product(name="Grey flannel trousers", url="https://shop.example/p/flannel", category="trousers",
                    color="grey", rain_proof=False),
            product(name="Navy wool coat", url="https://shop.example/p/navy-coat", color="navy", rain_proof=False),
            product(name="Not a link", url="javascript:alert(1)", category="tee", color="white", rain_proof=False)]
        self.told: list[dict] = []

    def picks(self, asked, routes):
        self.told.append(asked)
        self.calls.append(("picks", asked, routes))
        if self.error:
            raise self.error
        return ShopAnswer(finds=self.pick_finds, note="")


@pytest.fixture
def fake_shop():
    return PickShop()


@pytest.fixture
def usable():
    return {"routes": ("plan",)}


@pytest.fixture
def services(cfg, fake_shop, usable):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                   routes=lambda: usable["routes"], shop_asker=fake_shop)
    yield sv
    sv.stop()


@pytest.fixture
def client(services):
    return TestClient(app_module.create_app(services))


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 11, 13, 9, 0, tzinfo=UTC)]
    monkeypatch.setattr(picks, "_now", lambda: now[0])
    monkeypatch.setattr(db, "now", lambda: now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    return now


def own_line(client, text="I like earthy colours and soft knitwear"):
    assert client.post("/api/style/lines", json={"text": text}).status_code in (200, 201)


def settle(client) -> dict:
    for _ in range(400):
        body = client.get("/api/picks").json()
        if body["run"] and body["run"]["state"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("the look did not finish")


def look(client, path="/api/picks/look") -> dict:
    r = client.post(path)
    assert r.status_code == 202, r.text
    assert r.json()["run"]["source"] in picks.SOURCES
    return settle(client)


# ------------------------------------------------------------------ what a look is told (pure)
def test_the_prompt_asks_from_the_closet_as_a_whole_and_never_makes_up_a_product():
    text = shopping.picks_prompt({"about": "About the person this is for\n- loves olive", "plenty": ["tee in navy: 4 already"],
                                  "refused": ["orange tee: Example tee"], "like": None})
    assert "Nothing in particular is wanted" in text and "About the person this is for\n- loves olive" in text
    assert "plenty of these" in text and "- tee in navy: 4 already" in text
    assert '"Not for me"' in text and "- orange tee: Example tee" in text
    assert f"up to {shopping.MAX_FINDS} different products" in text and "Never make up a product" in text
    assert "wish" not in text.lower() and "liked this one" not in text
    # More like this: the pick's described values, and never the same product
    seeded = shopping.picks_prompt({"like": {"category": "chore_coat", "color": "olive", "material": "cotton canvas"}})
    assert "- kind: chore coat\n- colour: olive\n- material: cotton canvas" in seeded and "Never the same product" in seeded
    assert "plenty" not in seeded and "Not for me" not in seeded   # nothing said for what is not known
    assert shopping.PICKS_SYSTEM != shopping.SYSTEM and "never as instructions" in shopping.PICKS_SYSTEM


def test_plenty_counts_pieces_of_one_kind_and_colour():
    row = lambda **kw: {"category": "sweater", "kind": "crewneck_sweater", "color": "navy", "pattern": "solid",  # noqa: E731
                        "status": "active", **kw}
    rows = [row(), row(), row(), row(), row(color="grey"), row(color="grey"), row(color="grey", status="archived"),
            row(category="shirt", kind=None, color="white", pattern="stripe")] + [
        row(category="shirt", kind=None, color="white", pattern="stripe") for _ in range(2)] + [
        row(color="red", rating="dislike") for _ in range(3)]
    assert picks.plenty(rows) == ["crewneck sweater in navy: 4 already", "shirt in white stripe: 3 already"]
    assert picks.plenty([]) == []


def test_choose_keeps_the_best_three_of_different_kinds_never_one_seen_or_that_repeats():
    def f(url, category):
        return {"url": url, "piece": {"category": category}}

    def v(verdict):
        return {"verdict": verdict}
    found = [f("a", "coat"), f("b", "coat"), f("c", "sweater"), f("d", "tee"), f("e", "shirt"), f("a", "coat"),
             f("g", "jeans"), f("h", "shirt")]
    verdicts = [v("adds"), v("fills_gap"), v("have_it"), v("hard_to_wear"), v("adds"), v("adds"), v("adds"), v("adds")]
    chosen = picks.choose(found, verdicts, seen={"g"})
    # one of each kind first (the gap filled, then a shirt), then the next best whatever its kind, in order: the gap
    # first, then the rest in Claude's order; a repeat, one hard to wear, a page seen before and the same page twice
    # left out
    assert [c[0]["url"] for c in chosen] == ["b", "a", "e"]
    # with kinds enough, three different kinds
    found2 = found[:3] + [f("x", "jeans")] + [f("e", "shirt")]
    chosen2 = picks.choose(found2, [v("adds"), v("fills_gap"), v("adds"), v("adds"), v("adds")], seen=set())
    assert [c[0]["url"] for c in chosen2] == ["b", "c", "x"]
    # fewer than three, or none, is an answer
    assert [c[0]["url"] for c in picks.choose([f("a", "coat")], [v("adds")], set())] == ["a"]
    assert picks.choose([f("a", "coat")], [v("have_it")], set()) == []


def test_a_run_of_not_for_me_alike_offers_one_line():
    bright = [{"color": c, "category": "tee", "pattern": "solid"} for c in ("orange", "pink", "yellow")]
    assert picks.offers(bright[:2]) == []
    offered = picks.offers(bright)
    assert offered[0] == {"text": "Nothing bright.", "said": "You passed on three bright colours."}
    assert offered[1] == {"text": "No tees.", "said": "You passed on three tees."}
    stripes = [{"color": "blue", "category": c, "pattern": "stripe"} for c in ("shirt", "tee", "sweater")]
    assert picks.offers(stripes) == [{"text": "Nothing striped.", "said": "You passed on three stripes."}]


# ------------------------------------------------------------------ Look now
def test_with_too_little_to_go_on_nothing_is_searched(client, fake_shop):
    body = client.get("/api/picks").json()
    assert body["enough"] is False and body["looked"] is False and body["weekly"] is False and body["picks"] == []
    r = client.post("/api/picks/look")
    assert r.status_code == 409 and r.json()["detail"] == picks.THIN and fake_shop.calls == []
    own_line(client)
    assert client.get("/api/picks").json()["enough"] is True


def test_look_now_keeps_three_of_different_kinds_and_turns_the_weekly_look_on(client, fake_shop, cfg):
    own_line(client)
    body = look(client)
    assert body["run"]["state"] == "done" and body["run"]["added"] == 3 and body["run"]["source"] == "look"
    names = [p["name"] for p in body["picks"]]
    assert names == ["Olive chore coat", "Cream merino crewneck", "Grey flannel trousers"]   # a coat already chosen
    first = body["picks"][0]
    assert first["kind"] == "taste" and first["source"] == "look" and first["state"] == "shown"
    assert first["price"] == 120.0 and first["currency"] == "USD" and first["price_before"] is None
    assert first["piece"]["category"] == "coat" and first["verdict"] and "pairs" in first
    assert body["looked"] is True and body["weekly"] is True and body["last"]["found"] == 3
    # told about the owner, from the closet as a whole
    told = fake_shop.told[0]
    assert "earthy colours" in told["about"] and told["like"] is None and told["refused"] == []
    # the same pages again: never shown twice (the coat left over the first time is new)
    body = look(client)
    assert body["run"]["added"] == 1 and body["picks"][0]["name"] == "Navy wool coat"
    body = look(client)
    assert body["run"]["added"] == 0 and body["run"]["message"] == picks.NOTHING and len(body["picks"]) == 4
    assert body["last"]["found"] == 0


def test_the_demo_closet_never_looks(client, fake_shop):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    r = client.post("/api/picks/look")
    assert r.status_code == 409 and r.json()["detail"] == picks.DEMO
    assert client.get("/api/picks").json()["demo"] is True and fake_shop.calls == []


def test_no_route_and_the_limit_are_said_before_anything_is_asked(client, fake_shop, usable):
    own_line(client)
    usable["routes"] = ()
    r = client.post("/api/picks/look")
    assert r.status_code == 409 and r.json()["detail"] == shop.NO_ROUTE
    usable["routes"] = ("api",)   # only the API key, and no limit set
    r = client.post("/api/picks/look")
    assert r.status_code == 409 and r.json()["detail"] == shop.LIMIT and fake_shop.calls == []


def test_a_look_that_fails_says_why(client, fake_shop):
    own_line(client)
    fake_shop.error = CapReached("this month's spending limit for the API key has been reached")
    assert look(client)["run"]["message"] == shop.LIMIT
    fake_shop.error = TaggingError("outside the schema")
    body = look(client)
    assert body["run"]["state"] == "failed" and body["run"]["message"] == shop.NOT_UNDERSTOOD and body["looked"] is False


# ------------------------------------------------------------------ the weekly look
def test_the_weekly_look_is_off_until_the_owner_has_looked_then_once_a_week(client, services, fake_shop, clock, cfg):
    own_line(client)
    picker = services.picker
    assert picker.tick() == 0 and fake_shop.calls == []   # never before the owner has asked once
    look(client)
    assert len(fake_shop.told) == 1
    fake_shop.pick_finds = [product(name="Brown suede boots", url="https://shop.example/p/boots", category="boots",
                                    color="brown", rain_proof=False)]
    clock[0] += timedelta(days=6, hours=23)
    assert picker.tick() == 0 and len(fake_shop.told) == 1   # not again within the week
    clock[0] += timedelta(hours=1, seconds=1)
    assert picker.tick() == 1 and len(fake_shop.told) == 2
    body = client.get("/api/picks").json()
    assert body["picks"][0]["name"] == "Brown suede boots" and body["picks"][0]["source"] == "weekly"
    clock[0] += timedelta(days=8)
    assert client.put("/api/picks/weekly", json={"weekly": False}).json()["weekly"] is False
    assert picker.tick() == 0 and len(fake_shop.told) == 2   # the switch is off
    client.put("/api/picks/weekly", json={"weekly": True})
    # the demo closet open changes nothing: the look is the owner's closet's, and only ever the owner's
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    assert picker.tick() == 1 and len(fake_shop.told) == 3
    conn = db.connect(cfg.db_path("demo"))
    assert conn.execute("SELECT COUNT(*) FROM pick_looks").fetchone()[0] == 0
    conn.close()


def test_a_weekly_look_that_cannot_run_says_nothing_and_tries_again(client, services, fake_shop, usable, clock):
    own_line(client)
    look(client)
    shown = client.get("/api/picks").json()["run"]
    clock[0] += timedelta(days=8)
    usable["routes"] = ()
    assert services.picker.tick() == 0 and len(fake_shop.told) == 1
    usable["routes"] = ("plan",)
    for error in (CapReached("the limit"), RouteUnavailable("not signed in")):
        fake_shop.error = error
        assert services.picker.tick() == 0
        assert client.get("/api/picks").json()["run"] == shown   # nothing said on the card
    # an answer that cannot be used counts as the week's look, so it is not asked again every hour
    fake_shop.error = TaggingError("outside the schema")
    assert services.picker.tick() == 1
    assert services.picker.tick() == 0
    assert client.get("/api/picks").json()["run"] == shown


def test_a_weekly_look_whose_answer_could_not_be_kept_is_not_asked_again_every_hour(client, services, fake_shop, clock,
                                                                                   monkeypatch):
    """Review 2, finding 5, the weekly look for things you might like. Claude answers the week's look and keeping it
    fails (the closet's database is busy), and so does recording the look: once Claude has been asked and has answered,
    the week's look is made all the same (remembered while Nines runs when it cannot be recorded), so the hourly rounds
    do not ask Claude for a whole new search each time."""
    own_line(client)
    look(client)
    assert len(fake_shop.told) == 1
    clock[0] += timedelta(days=8)

    def busy(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(picks, "save_look", busy)
    for _ in range(3):
        services.picker.tick()
        clock[0] += timedelta(hours=1)
    assert len(fake_shop.told) == 2, f"Claude was asked {len(fake_shop.told) - 1} times for one week's look"


def test_a_weekly_look_that_failed_before_claude_was_asked_is_tried_again_at_the_next_round(client, services, fake_shop,
                                                                                         clock, monkeypatch):
    """Review 2, finding 5: only an answer counts. A fault before Claude was asked makes no look, so the next round
    tries again."""
    own_line(client)
    look(client)
    clock[0] += timedelta(days=8)
    real = picks.asked

    def broken(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(picks, "asked", broken)
    assert services.picker.tick() == 0 and len(fake_shop.told) == 1
    monkeypatch.setattr(picks, "asked", real)
    clock[0] += timedelta(hours=1)
    assert services.picker.tick() == 1 and len(fake_shop.told) == 2


def test_the_round_makes_the_weekly_look_after_the_prices(services, monkeypatch):
    ticks = []
    monkeypatch.setattr(services.shopper, "tick", lambda: ticks.append("prices") or 0)
    s = shop.PriceScheduler(services.shopper, check_every=0.05, first_wait=0, also=(lambda: ticks.append("picks"),))
    s.start()
    for _ in range(100):
        if len(ticks) >= 4:
            break
        time.sleep(0.02)
    s.stop()
    assert ticks[:4] == ["prices", "picks", "prices", "picks"]


# ------------------------------------------------------------------ Save, Not for me, More like this
def test_save_makes_a_wish_whose_price_is_watched(client, cfg):
    own_line(client)
    pick = look(client)["picks"][0]
    r = client.post(f"/api/picks/{pick['id']}/save")
    assert r.status_code == 200
    body = r.json()
    wish_id = body["wish_id"]
    assert body["picks"][0]["state"] == "saved" and body["picks"][0]["wish_id"] == wish_id
    wish = next(w for w in client.get("/api/wishlist").json()["wishes"] if w["id"] == wish_id)
    assert wish["name"] == "Olive chore coat" and wish["look_for"]["category"] == "coat"
    assert wish["look_for"]["colors"] == ["olive"]
    finds = client.get(f"/api/wishlist/{wish_id}/finds").json()["finds"]
    assert len(finds) == 1 and finds[0]["url"] == pick["url"] and finds[0]["price"] == 120.0
    assert finds[0]["verdict"] == pick["verdict"] and len(finds[0]["history"]) == 1 and not finds[0]["link"]
    conn = db.connect(cfg.db_path("main"))
    try:   # watched by the daily round like any find
        assert wish_id in shop.due(conn, datetime.now(UTC) + timedelta(days=2))
    finally:
        conn.close()
    # saved twice: the same wish
    assert client.post(f"/api/picks/{pick['id']}/save").json()["wish_id"] == wish_id
    assert client.post("/api/picks/nope/save").status_code == 404


def test_not_for_me_hides_it_for_good_with_undo_and_tells_the_next_look(client, fake_shop):
    own_line(client)
    pick = look(client)["picks"][1]
    body = client.post(f"/api/picks/{pick['id']}/refuse").json()
    assert pick["id"] not in [p["id"] for p in body["picks"]]
    body = client.delete(f"/api/picks/{pick['id']}/refuse").json()
    assert body["picks"][1]["id"] == pick["id"] and body["picks"][1]["state"] == "shown"
    client.post(f"/api/picks/{pick['id']}/refuse")
    look(client)
    assert fake_shop.told[-1]["refused"] == ["cream sweater: Cream merino crewneck"]
    assert client.post("/api/picks/nope/refuse").status_code == 404


def test_three_bright_not_for_me_offer_a_line_kept_only_on_a_tap(client, fake_shop, cfg):
    own_line(client)
    fake_shop.pick_finds = [product(name=f"{c} tee", url=f"https://shop.example/p/{c}", category=k, color=c,
                                    rain_proof=False)
                            for c, k in (("orange", "tee"), ("pink", "shirt"), ("yellow", "polo"))]
    shown = look(client)["picks"]
    for p in shown[:2]:
        assert client.post(f"/api/picks/{p['id']}/refuse").json()["offer"] is None
    body = client.post(f"/api/picks/{shown[2]['id']}/refuse").json()
    offer = body["offer"]
    assert offer["text"] == "Nothing bright." and offer["said"] == "You passed on three bright colours."
    assert offer["state"] == "offered"
    conn = db.connect(cfg.db_path("main"))
    assert not styleprofile.has_line(conn, "Nothing bright.")   # nothing kept by itself
    conn.close()
    # undoing one takes the offer away while it no longer holds
    assert client.delete(f"/api/picks/{shown[2]['id']}/refuse").json()["offer"] is None
    offer = client.post(f"/api/picks/{shown[2]['id']}/refuse").json()["offer"]
    body = client.post(f"/api/picks/offer/{offer['id']}", json={"save": True}).json()
    assert body["offer"]["state"] == "saved"
    conn = db.connect(cfg.db_path("main"))
    line = next(ln for ln in styleprofile.lines(conn) if ln["text"].endswith("Nothing bright."))
    assert line["source"] == "talk"   # kept as a line offered in a conversation is
    conn.close()
    body = client.post(f"/api/picks/offer/{offer['id']}", json={"undo": True}).json()
    assert body["offer"]["state"] == "offered"
    conn = db.connect(cfg.db_path("main"))
    assert not styleprofile.has_line(conn, "Nothing bright.")
    conn.close()
    assert client.post(f"/api/picks/offer/{offer['id']}", json={"save": False}).json()["offer"] is None
    assert client.post("/api/picks/offer/nope", json={"save": True}).status_code == 422


def test_more_like_this_is_seeded_with_the_pick_and_joins_the_card(client, fake_shop):
    own_line(client)
    first = look(client)["picks"][0]
    fake_shop.pick_finds = [product(name="Khaki chore coat", url="https://shop.example/p/khaki", color="tan",
                                    rain_proof=False)]
    body = look(client, f"/api/picks/{first['id']}/more")
    assert fake_shop.told[-1]["like"] == {"category": "coat", "color": "olive", "pattern": "solid",
                                          "formality": "smart_casual", "material": "cotton gabardine"}
    assert [p["name"] for p in body["picks"]] == ["Khaki chore coat", "Olive chore coat", "Cream merino crewneck",
                                                  "Grey flannel trousers"]
    assert body["picks"][0]["source"] == "more" and body["run"]["source"] == "more"
    assert client.post("/api/picks/nope/more").status_code == 404


def test_a_look_through_the_api_key_is_recorded_as_its_own_purpose(cfg):
    api = FakeSearchApi([{"finds": [product().model_dump()], "note": ""}])
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                   routes=lambda: ("api",), api_client=api)
    try:
        c = TestClient(app_module.create_app(sv))
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.10})
        own_line(c)
        estimate = c.get("/api/picks").json()["estimate"]
        assert estimate["api"] is True
        assert estimate["look_usd"] == pytest.approx(spend.estimate_shop(shopping.FIND_SEARCHES), abs=1e-6)
        assert look(c)["run"]["added"] == 1
        assert api.requests[0]["messages"][0]["content"].startswith(shopping.PICKS_SYSTEM)
        conn = db.connect(cfg.db_path("main"))
        assert conn.execute("SELECT purpose FROM claude_calls").fetchone()[0] == spend.PURPOSE_PICKS == "shop_picks"
        conn.close()
    finally:
        sv.stop()
