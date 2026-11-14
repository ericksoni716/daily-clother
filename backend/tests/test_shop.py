"""Shopping for a wish: finds kept and checked against the closet, price checks (closet/shop.py, tagger/shopping.py,
migration 0018).

Claude is never called: `FakeShop` stands in for it (searching and looking up prices), or, for the API route,
`FakeSearchApi` stands in for Anthropic's API with its web search tool, and the plan route's `claude -p` is never run.
"""
import json
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, demo, shop, spend
from closet.tagger import correcting, shopping
from closet.tagger.shopping import Found, PriceAnswer, PriceSeen, ShopAnswer
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import PASSPHRASE, fake_cutter


def product(**changes) -> Found:
    """A product as Claude would describe it: a tan rain-proof coat."""
    base = dict(name="Tan rain coat", shop="Example Shop", url="https://shop.example/coat",
                image_url="https://shop.example/coat.jpg", price=120.0, currency="USD", category="coat", color="tan",
                formality="smart_casual", season="all", pattern="solid", weight_class="midweight", rain_proof=True,
                material="cotton gabardine")
    return Found(**{**base, **changes})


class FakeShop:
    """Stands in for Claude searching shops and looking up prices. `prices_seen`: what the next price check
    answers (by default every price 20% lower); `error`: raised by the next calls instead."""

    def __init__(self):
        self.finds = [product(), product(name="Navy wool coat", url="https://other.example/p/2", color="navy",
                                         price=240.0, image_url="", weight_class="unknown", rain_proof=False)]
        self.prices_seen: list | None = None
        self.error: Exception | None = None
        self.calls: list[tuple] = []

    def find(self, wish, routes):
        self.calls.append(("find", wish, routes))
        if self.error:
            raise self.error
        return ShopAnswer(finds=self.finds, note="")

    def prices(self, finds, routes):
        self.calls.append(("prices", [f["url"] for f in finds], routes))
        if self.error:
            raise self.error
        if self.prices_seen is not None:
            return PriceAnswer(prices=self.prices_seen)
        return PriceAnswer(prices=[PriceSeen(url=f["url"], price=round((f["price"] or 100) * 0.8, 2),
                                             currency=f["currency"], available=True) for f in finds])


@pytest.fixture
def fake_shop():
    return FakeShop()


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
    c = TestClient(app_module.create_app(services))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    return c


def wish(client, name="A tan rain coat", note="") -> str:
    r = client.post("/api/wishlist", json={"name": name, "note": note})
    assert r.status_code == 201
    return r.json()["id"]


def settle(client, wish_id: str) -> dict:
    """Waits for the search or price check on the wish to finish, and gives its finds."""
    for _ in range(400):
        body = client.get(f"/api/wishlist/{wish_id}/finds").json()
        if body["run"] and body["run"]["state"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("the search did not finish")


def find_some(client, wish_id: str) -> dict:
    r = client.post(f"/api/wishlist/{wish_id}/find")
    assert r.status_code == 202, r.text
    assert r.json()["run"]["kind"] == "find"
    return settle(client, wish_id)


# ------------------------------------------------------------------ the migration
def test_migration_0018_adds_finds_to_a_closet_made_before_it(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 18:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    conn.execute("INSERT INTO wishes (id, name, note, created_at, updated_at) VALUES ('w1', 'Loafers', '', 't', 't')")
    conn.close()
    result = db.migrate(path, tmp_path / "backups")
    assert result["applied"][0] == 18 and result["backup"]
    conn = db.connect(path)
    w = dict(conn.execute("SELECT * FROM wishes").fetchone())
    assert w["name"] == "Loafers" and w["price_min"] is None and w["prices_checked_at"] is None
    assert conn.execute("SELECT COUNT(*) FROM finds").fetchone()[0] == 0
    # finds and their prices go with their wish
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, currency, piece, found_at, updated_at) "
                 "VALUES ('f1', 'w1', 'n', 's', 'https://a.example', 'USD', '{}', 't', 't')")
    conn.execute("INSERT INTO find_prices (find_id, at, price, currency) VALUES ('f1', 't', 10, 'USD')")
    conn.execute("DELETE FROM wishes WHERE id = 'w1'")
    assert conn.execute("SELECT COUNT(*) FROM find_prices").fetchone()[0] == 0
    conn.close()


# ------------------------------------------------------------------ finding
def test_find_some_keeps_the_finds_with_their_verdicts(client, fake_shop):
    wid = wish(client, note="size L")
    body = find_some(client, wid)
    assert body["run"]["state"] == "done" and body["run"]["added"] == 2 and body["found_at"]
    coat, navy = body["finds"]
    assert coat["name"] == "Tan rain coat" and coat["shop"] == "Example Shop" and coat["url"] == "https://shop.example/coat"
    assert coat["price"] == 120.0 and coat["currency"] == "USD" and coat["image_url"] == "https://shop.example/coat.jpg"
    assert coat["piece"]["category"] == "coat" and coat["piece"]["rain_proof"] is True
    assert coat["piece"]["weight_class"] == "midweight" and "keeps the rain off" in coat["piece_words"]
    # checked against the (empty) closet with the "Would this work?" rules
    assert coat["verdict"] == "too_small" and coat["verdict_words"] and coat["reasons"]
    assert navy["image_url"] is None and navy["piece"]["weight_class"] is None
    assert [h["price"] for h in coat["history"]] == [120.0] and coat["drop"] is None
    # Claude was asked about the wish itself
    kind, asked, routes = fake_shop.calls[0]
    assert kind == "find" and asked["name"] == "A tan rain coat" and asked["note"] == "size L" and routes == ("plan",)

    # finding again brings a product found before up to date instead of keeping it twice
    fake_shop.finds = [product(price=110.0), product(name="Tan mac", url="https://third.example/mac")]
    body = find_some(client, wid)
    assert body["run"]["added"] == 1 and len(body["finds"]) == 3
    coat = next(f for f in body["finds"] if f["url"] == "https://shop.example/coat")
    assert [h["price"] for h in coat["history"]] == [120.0, 110.0] and coat["drop"]["to"] == 110.0


def test_finds_that_do_not_fit_are_dropped_and_the_rest_kept(client, fake_shop):
    fake_shop.finds = [
        product(url="javascript:alert(1)"),                         # not a web address
        product(url="https://shop.example/a", image_url="data:image/png;base64,AAAA"),   # a picture that is not one
        product(url="https://shop.example/b", category="other"),   # not a kind the closet can check
        product(url="https://shop.example/c", color="teal"),       # not one of the closet's colours
        product(url="https://shop.example/d", currency="dollars"),
        product(url="https://shop.example/e", price=-5.0),
        product(url="https://shop.example/f", name="   "),
        product(url="******shop.example/g"),
        product(url="https://shop.example/a"),                     # the same page twice: kept once
        product(url="ftp://shop.example/h"),
    ]
    body = find_some(client, wish(client))
    assert [f["url"] for f in body["finds"]] == ["https://shop.example/a"]
    assert body["finds"][0]["image_url"] is None


def test_at_most_eight_finds_are_kept_from_one_search(client, fake_shop):
    fake_shop.finds = [product(url=f"https://shop.example/{n}") for n in range(12)]
    assert len(find_some(client, wish(client))["finds"]) == shopping.MAX_FINDS == 8


def test_a_malformed_answer_keeps_nothing_and_says_so(client, fake_shop):
    wid = wish(client)
    fake_shop.error = TaggingError("the answer was outside the schema")
    body = find_some(client, wid)
    assert body["run"]["state"] == "failed" and body["run"]["message"] == shop.NOT_UNDERSTOOD and body["finds"] == []
    # an answer whose every product is unusable
    fake_shop.error = None
    fake_shop.finds = [product(url="not a link")]
    body = find_some(client, wid)
    assert body["run"]["state"] == "done" and body["run"]["message"] == shop.NOT_UNDERSTOOD and body["finds"] == []
    # nothing found at all
    fake_shop.finds = []
    body = find_some(client, wid)
    assert body["run"]["message"] == shop.NOTHING


def test_the_demo_closet_never_searches(client, fake_shop):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    wid = wish(client)
    r = client.post(f"/api/wishlist/{wid}/find")
    assert r.status_code == 409 and "demo closet never sends anything to Claude" in r.json()["detail"]
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 409
    assert client.get(f"/api/wishlist/{wid}/finds").json()["demo"] is True
    assert fake_shop.calls == []


def test_no_route_to_claude_is_said_before_anything_is_asked(client, fake_shop, usable):
    usable["routes"] = ()
    r = client.post(f"/api/wishlist/{wish(client)}/find")
    assert r.status_code == 409 and r.json()["detail"] == shop.NO_ROUTE and fake_shop.calls == []


def test_an_unknown_wish_or_a_second_search_at_once(client, fake_shop, monkeypatch):
    assert client.post("/api/wishlist/nope/find").status_code == 404
    assert client.get("/api/wishlist/nope/finds").status_code == 404
    wid = wish(client)
    slow = {"go": False}
    real = fake_shop.find

    def wait_then_find(w, routes):
        for _ in range(200):
            if slow["go"]:
                break
            time.sleep(0.02)
        return real(w, routes)
    monkeypatch.setattr(fake_shop, "find", wait_then_find)
    assert client.post(f"/api/wishlist/{wid}/find").status_code == 202
    r = client.post(f"/api/wishlist/{wid}/find")
    assert r.status_code == 409 and r.json()["detail"] == shop.BUSY
    slow["go"] = True
    assert settle(client, wid)["run"]["state"] == "done"


def test_a_find_can_be_removed_and_goes_with_its_wish(client, cfg):
    wid = wish(client)
    first = find_some(client, wid)["finds"][0]
    assert client.delete(f"/api/wishlist/{wid}/finds/{first['id']}").status_code == 204
    assert client.delete(f"/api/wishlist/{wid}/finds/{first['id']}").status_code == 404
    assert len(client.get(f"/api/wishlist/{wid}/finds").json()["finds"]) == 1
    assert client.delete(f"/api/wishlist/{wid}").status_code == 204
    conn = sqlite3.connect(cfg.db_path("main"))
    assert conn.execute("SELECT COUNT(*) FROM finds").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM find_prices").fetchone()[0] == 0
    conn.close()


def hold_write_lock(cfg, wish_id: str) -> sqlite3.Connection:
    """Another connection in the middle of writing to the closet, as a worker or a request would be."""
    other = db.connect(cfg.db_path("main"))
    other.execute("BEGIN IMMEDIATE")
    other.execute("UPDATE wishes SET note = 'held' WHERE id = ?", (wish_id,))
    return other


def signal_when_asked(fake_shop, monkeypatch) -> threading.Event:
    asked, real = threading.Event(), fake_shop.find

    def find_then_signal(w, routes):
        answer = real(w, routes)
        asked.set()
        return answer
    monkeypatch.setattr(fake_shop, "find", find_then_signal)
    return asked


def test_a_search_waits_for_another_writer_and_then_keeps_its_finds(client, fake_shop, cfg, monkeypatch):
    wid = wish(client)
    asked = signal_when_asked(fake_shop, monkeypatch)
    other = hold_write_lock(cfg, wid)
    try:
        assert client.post(f"/api/wishlist/{wid}/find").status_code == 202
        assert asked.wait(10)
        time.sleep(0.5)   # the search is saving its finds now, and must wait for the lock, not give up
        assert client.get(f"/api/wishlist/{wid}/finds").json()["run"]["state"] == "running"
    finally:
        other.execute("COMMIT")
        other.close()
    body = settle(client, wid)
    assert body["run"]["state"] == "done" and body["run"]["added"] == 2 and len(body["finds"]) == 2


def test_a_search_that_cannot_keep_its_finds_says_so(client, fake_shop, cfg, monkeypatch):
    real_connect = db.connect

    def connect(path):   # the search's connection gives up on a lock quickly, everyone else waits as usual
        conn = real_connect(path)
        if threading.current_thread().name == "shop":
            conn.execute("PRAGMA busy_timeout = 200")
        return conn
    monkeypatch.setattr(db, "connect", connect)
    wid = wish(client)
    other = hold_write_lock(cfg, wid)
    try:
        assert client.post(f"/api/wishlist/{wid}/find").status_code == 202
        for _ in range(400):
            run = client.get(f"/api/wishlist/{wid}/finds").json()["run"]
            if run["state"] != "running":
                break
            time.sleep(0.05)
    finally:
        other.execute("COMMIT")
        other.close()
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    assert body["run"]["state"] == "failed" and body["run"]["message"] == shop.NOT_SAVED and body["finds"] == []
    # once the closet is free again, the next search keeps them
    body = find_some(client, wid)
    assert body["run"]["state"] == "done" and len(body["finds"]) == 2


def test_finds_are_never_shown_older_than_the_run(client, services, fake_shop, monkeypatch):
    wid = wish(client)
    armed, go, real_find, real_list = threading.Event(), threading.Event(), fake_shop.find, shop.list_finds

    def find_when_told(w, routes):
        assert go.wait(10)
        return real_find(w, routes)

    def list_then_let_the_search_finish(conn, wish_id):
        finds = real_list(conn, wish_id)
        if armed.is_set() and not go.is_set():
            go.set()   # the search saves and ends after the finds were read, before the answer is sent
            for _ in range(200):
                if not services.shopper.running("main", wish_id):
                    break
                time.sleep(0.02)
        return finds
    monkeypatch.setattr(fake_shop, "find", find_when_told)
    monkeypatch.setattr(shop, "list_finds", list_then_let_the_search_finish)
    assert client.post(f"/api/wishlist/{wid}/find").status_code == 202
    armed.set()
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    assert body["run"]["state"] == "running" and body["finds"] == []   # not "done" with nothing found
    assert len(settle(client, wid)["finds"]) == 2


def test_the_finds_are_checked_against_the_closet_with_the_would_this_work_rules(cfg):
    demo.ensure(cfg)
    rows, worn = app_module.closet_inputs(cfg, "demo")
    # heavyweight: under the owner's bands (#150) a midweight mac is short of warm on the cold rainy days, and a smart
    # casual coat is too far from sport and formal days, so a midweight one covers too few of the rain gap's days
    coat = shop.clean_find(product(weight_class="heavyweight"))
    polo = shop.clean_find(product(name="Navy polo", url="https://shop.example/polo", category="polo", color="navy",
                                   formality="smart_casual", season="warm", rain_proof=False, weight_class="midweight"))
    verdicts = shop.judge(rows, worn, [coat["piece"], polo["piece"]])
    assert verdicts[0]["verdict"] == "fills_gap" and verdicts[0]["verdict_words"] == "Fills a gap"
    assert any("rain" in r.lower() for r in verdicts[0]["reasons"])
    assert verdicts[1]["verdict"] in ("have_it", "adds", "hard_to_wear") and verdicts[1]["reasons"]
    assert shop.judge(rows, worn, []) == []


# ------------------------------------------------------------------ the wish's price range
def test_a_price_range_is_set_checked_and_cleared(client, fake_shop):
    wid = wish(client)
    r = client.patch(f"/api/wishlist/{wid}", json={"price_max": 150})
    assert r.status_code == 200 and (r.json()["price_min"], r.json()["price_max"], r.json()["price_currency"]) == (None, 150, "USD")
    r = client.patch(f"/api/wishlist/{wid}", json={"price_min": 50, "price_currency": "eur"})
    assert (r.json()["price_min"], r.json()["price_max"], r.json()["price_currency"]) == (50, 150, "EUR")
    assert client.patch(f"/api/wishlist/{wid}", json={"price_min": 200}).status_code == 422
    assert client.patch(f"/api/wishlist/{wid}", json={"price_max": -1}).status_code == 422
    assert client.patch(f"/api/wishlist/{wid}", json={"price_currency": "euros"}).status_code == 422
    assert client.patch(f"/api/wishlist/{wid}", json={"note": "size L"}).json()["price_max"] == 150   # untouched
    find_some(client, wid)
    asked = fake_shop.calls[-1][1]
    assert "between 50 and 150 EUR" in shopping.find_prompt(asked)
    r = client.patch(f"/api/wishlist/{wid}", json={"price_min": None, "price_max": None})
    assert (r.json()["price_min"], r.json()["price_max"], r.json()["price_currency"]) == (None, None, None)


def test_the_prompt_says_what_the_wish_is_for():
    w = {"name": "A rain-proof outer layer", "note": "", "price_min": None, "price_max": 90.0, "price_currency": "GBP",
         "look_for": {"category": "coat", "formality": "smart_casual", "season": None, "weight_class": "midweight",
                      "colors": ["navy", "light_blue"], "pattern": None, "material": "waterproof",
                      "avoid_patterns": ["camo"]}}
    text = shopping.find_prompt(w)
    assert "A rain-proof outer layer" in text and "smart casual" in text and "navy, light blue" in text
    assert "at most 90 GBP" in text and "patterns to avoid: camo" in text and "The owner says" not in text
    assert "_" not in text.split("Wish:")[1].split("Search the web")[0]


# ------------------------------------------------------------------ price checks
def test_a_price_check_records_the_prices_and_shows_a_drop(client, fake_shop):
    wid = wish(client)
    find_some(client, wid)
    r = client.post(f"/api/wishlist/{wid}/prices")
    assert r.status_code == 202 and r.json()["run"]["kind"] == "prices"
    body = settle(client, wid)
    assert body["run"]["state"] == "done" and body["prices_checked_at"]
    coat = next(f for f in body["finds"] if f["url"] == "https://shop.example/coat")
    assert coat["price"] == 96.0 and [h["price"] for h in coat["history"]] == [120.0, 96.0]
    assert coat["drop"] == {"from": 120.0, "to": 96.0, "currency": "USD", "percent": 20}
    assert coat["verdict"] == "too_small"   # checked against the closet again
    # it is asked only about its own finds, by their pages
    assert fake_shop.calls[-1] == ("prices", ["https://shop.example/coat", "https://other.example/p/2"], ("plan",))

    # what does not fit is not kept: another page, a price that is not one; a find sold out is marked so
    fake_shop.prices_seen = [PriceSeen(url="https://elsewhere.example", price=1.0, currency="USD", available=True),
                             PriceSeen(url="https://shop.example/coat", price=-3.0, currency="USD", available=True),
                             PriceSeen(url="https://other.example/p/2", price=None, currency="USD", available=False)]
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    coat = next(f for f in body["finds"] if f["url"] == "https://shop.example/coat")
    navy = next(f for f in body["finds"] if f["url"] == "https://other.example/p/2")
    assert coat["price"] == 96.0 and len(coat["history"]) == 2 and coat["available"] is True
    assert navy["available"] is False and navy["price"] is None and navy["drop"] is None
    assert [h["price"] for h in navy["history"]] == [240.0, 192.0, None]


def test_a_price_check_needs_finds(client):
    r = client.post(f"/api/wishlist/{wish(client)}/prices")
    assert r.status_code == 409 and r.json()["detail"] == shop.NO_FINDS


def test_drop_compares_with_the_highest_price_before_in_the_same_currency():
    h = lambda *ps: [{"at": str(n), "price": p, "currency": c, "available": True} for n, (p, c) in enumerate(ps)]  # noqa: E731
    assert shop.drop([]) is None
    assert shop.drop(h((100, "USD"))) is None
    assert shop.drop(h((100, "USD"), (100, "USD"))) is None
    assert shop.drop(h((100, "USD"), (120, "USD"))) is None
    assert shop.drop(h((80, "USD"), (120, "USD"), (90, "USD")))["from"] == 120
    assert shop.drop(h((120, "EUR"), (90, "USD"))) is None
    assert shop.drop(h((120, "USD"), (None, "USD"))) is None


# ------------------------------------------------------------------ the daily round
@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 11, 13, 9, 0, tzinfo=UTC)]
    monkeypatch.setattr(shop, "_now", lambda: now[0])
    real = db.now
    monkeypatch.setattr(db, "now", lambda: now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ") if now else real())
    return now


def test_the_daily_round_checks_each_wish_at_most_once_a_day_and_never_the_demo(client, services, fake_shop, cfg, clock):
    wid = wish(client)
    find_some(client, wid)
    bought = wish(client, name="Loafers")
    find_some(client, bought)
    client.post(f"/api/wishlist/{bought}/bought")
    no_finds = wish(client, name="A belt")
    # a wish with a find in the demo closet: never looked at
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    conn = db.connect(cfg.db_path("demo"))
    conn.execute("INSERT INTO wishes (id, name, note, created_at, updated_at) VALUES ('dw', 'Demo wish', '', 't', 't')")
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, currency, piece, found_at, updated_at) VALUES "
                 "('df', 'dw', 'n', 's', 'https://demo.example', 'USD', ?, 't', 't')", (json.dumps(product().model_dump()),))
    conn.close()
    fake_shop.calls.clear()

    assert services.shopper.tick() == 1   # the open wish with finds, in the real closet, whatever closet is open
    assert [c[0] for c in fake_shop.calls] == ["prices"] and "https://demo.example" not in fake_shop.calls[0][1]
    clock[0] += timedelta(hours=23)
    assert services.shopper.tick() == 0 and len(fake_shop.calls) == 1   # not again within the day
    clock[0] += timedelta(hours=1, seconds=1)
    assert services.shopper.tick() == 1 and len(fake_shop.calls) == 2   # a day on: once more
    conn = db.connect(cfg.db_path("demo"))
    assert conn.execute("SELECT COUNT(*) FROM find_prices").fetchone()[0] == 0
    assert conn.execute("SELECT prices_checked_at FROM wishes").fetchone()[0] is None
    conn.close()
    conn = db.connect(cfg.db_path("main"))
    checked = {r["id"]: r["prices_checked_at"] for r in conn.execute("SELECT id, prices_checked_at FROM wishes")}
    conn.close()
    assert checked[wid] and checked[bought] is None and checked[no_finds] is None


def test_the_daily_round_waits_for_claude_and_does_not_count_a_round_it_could_not_make(client, services, fake_shop,
                                                                                         usable, clock, cfg):
    wid = wish(client)
    find_some(client, wid)
    fake_shop.calls.clear()
    usable["routes"] = ()
    assert services.shopper.tick() == 0 and fake_shop.calls == []
    usable["routes"] = ("plan",)
    fake_shop.error = CapReached("this month's spending limit for the API key has been reached")
    assert services.shopper.tick() == 0
    assert client.get(f"/api/wishlist/{wid}/finds").json()["run"]["message"] == shop.LIMIT
    fake_shop.error = RouteUnavailable("Claude Code is not signed in")
    assert services.shopper.tick() == 0
    conn = db.connect(cfg.db_path("main"))
    assert conn.execute("SELECT prices_checked_at FROM wishes").fetchone()[0] is None   # it will try again
    conn.close()
    # a malformed answer counts as a look, so it is not asked again and again
    fake_shop.error = TaggingError("the answer was outside the schema")
    assert services.shopper.tick() == 1
    assert services.shopper.tick() == 0
    fake_shop.error = None
    clock[0] += timedelta(days=1, seconds=1)
    assert services.shopper.tick() == 1


def test_the_scheduler_runs_the_round_while_the_program_runs(services, monkeypatch):
    ticks = []
    monkeypatch.setattr(services.shopper, "tick", lambda: ticks.append(1) or 0)
    s = shop.PriceScheduler(services.shopper, check_every=0.05, first_wait=0)
    s.start()
    for _ in range(100):
        if len(ticks) >= 2:
            break
        time.sleep(0.02)
    s.stop()
    assert len(ticks) >= 2


# ------------------------------------------------------------------ the API route and the monthly limit
class FakeSearchApi:
    """Stands in for the Anthropic API with the web search tool (`messages.create`). Each answer is the next of
    `answers`: a dict for the answer tool's input, "pause" for a search paused by the API, or "text" for no answer."""

    def __init__(self, answers, input_tokens=100_000, output_tokens=2_000, searches=3):
        self.answers = list(answers)
        self.input_tokens, self.output_tokens, self.searches = input_tokens, output_tokens, searches
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        given = self.answers.pop(0)
        usage = SimpleNamespace(input_tokens=self.input_tokens, output_tokens=self.output_tokens,
                                server_tool_use=SimpleNamespace(web_search_requests=self.searches))
        if given == "pause":
            return SimpleNamespace(content=[SimpleNamespace(type="server_tool_use", name="web_search", input={})],
                                   stop_reason="pause_turn", usage=usage)
        if given == "text":
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Here are some coats.")],
                                   stop_reason="end_turn", usage=usage)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Done."),
                                        SimpleNamespace(type="tool_use", name=shopping.ANSWER_TOOL, input=given)],
                               stop_reason="tool_use", usage=usage)


ONE_ANSWER = {"finds": [product().model_dump()], "note": ""}
ONE_REQUEST = spend.cost_usd(shopping.MODEL, 100_000, 2_000) + 3 * spend.SEARCH_USD


@pytest.fixture
def api_services(cfg):
    holder = {}

    def build(api):
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                       routes=lambda: ("api",), api_client=api)
        holder["sv"] = sv
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return c
    yield build
    if "sv" in holder:
        holder["sv"].stop()


def test_the_api_route_uses_web_search_and_records_what_it_cost(api_services, cfg):
    api = FakeSearchApi([ONE_ANSWER])
    c = api_services(api)
    c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.10})
    wid = wish(c)
    finds = c.get(f"/api/wishlist/{wid}/finds").json()
    assert finds["estimate"]["api"] is True
    assert finds["estimate"]["find_usd"] == pytest.approx(spend.estimate_shop(shopping.FIND_SEARCHES), abs=1e-6)
    body = find_some(c, wid)
    assert body["run"]["state"] == "done" and len(body["finds"]) == 1
    sent = api.requests[0]
    assert {"type": "web_search_20250305", "name": "web_search", "max_uses": shopping.FIND_SEARCHES} in sent["tools"]
    assert any(t.get("name") == shopping.ANSWER_TOOL and t.get("strict") for t in sent["tools"])
    conn = db.connect(cfg.db_path("main"))
    row = dict(conn.execute("SELECT purpose, route, cost_usd FROM claude_calls").fetchone())
    conn.close()
    assert row["purpose"] == spend.PURPOSE_SHOP and row["route"] == "api"
    assert row["cost_usd"] == pytest.approx(ONE_REQUEST)   # the searches on top of the tokens

    # the next search could take the month past the limit: refused before anything is asked, with the note
    r = c.post(f"/api/wishlist/{wid}/find")
    assert r.status_code == 409 and r.json()["detail"] == shop.LIMIT and len(api.requests) == 1
    assert "spending limit for the API key has been reached" in shop.LIMIT


def test_the_limit_stops_a_search_in_the_middle(api_services):
    api = FakeSearchApi(["pause", ONE_ANSWER])
    c = api_services(api)
    c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.10})
    body = find_some(c, wish(c))
    assert body["run"]["state"] == "failed" and body["run"]["message"] == shop.LIMIT and body["finds"] == []
    assert len(api.requests) == 1   # the second request was never made


def test_the_api_route_lets_a_paused_search_go_on_and_retries_a_malformed_answer():
    api = FakeSearchApi(["pause", {"finds": "not a list"}, "text", ONE_ANSWER])
    with pytest.raises(TaggingError):
        shopping.ask_api(api, shopping.MODEL, "find a coat", ShopAnswer, 5)
    assert len(api.requests) == 3   # paused and went on, then two answers that could not be used
    assert api.requests[1]["messages"][1]["role"] == "assistant"   # went on from where it stopped
    api = FakeSearchApi(["pause", ONE_ANSWER])
    result = shopping.ask_api(api, shopping.MODEL, "find a coat", ShopAnswer, 5)
    assert result.route == "api" and result.searches == 6 and result.answer.finds[0].name == "Tan rain coat"


def test_the_plan_route_may_only_search_the_web(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["stdin"].read().decode("utf-8")
        answer = {"prices": [{"url": "https://shop.example/coat", "price": 99.0, "currency": "USD", "available": True}]}
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"structured_output": answer, "usage": {"input_tokens": 10, "output_tokens": 5}}))
    monkeypatch.setattr(correcting.subprocess, "run", run)
    answer = shopping.prices([{"url": "https://shop.example/coat", "name": "Coat", "shop": "Shop", "price": 120.0,
                               "currency": "USD"}], ("plan",), exe="claude")
    assert answer.prices[0].price == 99.0
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch" and cmd[cmd.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert "https://shop.example/coat" in seen["input"] and not any("shop.example" in part for part in cmd)
