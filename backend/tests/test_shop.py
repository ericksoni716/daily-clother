"""Shopping for a wish: finds kept and checked against the closet, price checks, products sent as links, the price
news the banner tells, and checkout codes (closet/shop.py, tagger/shopping.py, migrations 0018, 0042, 0045 and 0046).

Claude is never called: `FakeShop` stands in for it (searching and looking up prices), or, for the API route,
`FakeSearchApi` stands in for Anthropic's API with its web search tool, and the plan route's `claude -p` is never run.
No shop is reached either: `ShopPages` stands in for the web a link's page is read from, with made-up pages.
"""
import json
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, demo, gaps, life, productpage, shop, spend
from closet.tagger import correcting, shopping
from closet.tagger.shopping import Described, Found, PriceAnswer, PriceSeen, SaleAnswer, ShopAnswer
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

from .conftest import fake_cutter


def product(**changes) -> Found:
    """A product as Claude would describe it: a tan rain-proof coat."""
    base = dict(name="Tan rain coat", shop="Example Shop", url="https://shop.example/coat",
                image_url="https://shop.example/coat.jpg", price=120.0, currency="USD", category="coat", color="tan",
                formality="smart_casual", season="all", pattern="solid", weight_class="midweight", rain_proof=True,
                material="cotton gabardine")
    return Found(**{**base, **changes})


def described(**changes) -> Described:
    """A page sent as a link as Claude would describe it from its words: a white linen shirt."""
    base = dict(clothing=True, category="shirt", color="white", formality="casual", season="warm", pattern="solid",
                weight_class="lightweight", rain_proof=False, material="linen")
    return Described(**{**base, **changes})


class FakeShop:
    """Stands in for Claude searching shops, looking up prices and describing a page sent as a link. `prices_seen`:
    what the next price check answers (by default every price 20% lower); `error`: raised by the next calls instead.
    `described`: what each description was asked about (kept apart from `calls`, the searches and price checks);
    `description`: its answer (by default a white linen shirt), or an exception to raise."""

    def __init__(self):
        self.finds = [product(), product(name="Navy wool coat", url="https://other.example/p/2", color="navy",
                                         price=240.0, image_url="", weight_class="unknown", rain_proof=False)]
        self.prices_seen: list | None = None
        self.error: Exception | None = None
        self.calls: list[tuple] = []
        self.described: list[tuple] = []
        self.description: Described | Exception = described()
        self.sale_finds: list = []   # what the next "On sale now" look answers (test_sale.py gives it products)

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

    def sale(self, asked, routes):
        self.calls.append(("sale", asked, routes))
        if self.error:
            raise self.error
        return SaleAnswer(finds=self.sale_finds, note="")

    def describe(self, product, routes):
        self.described.append((product, routes))
        if isinstance(self.description, Exception):
            raise self.description
        return self.description


SHIRT = "https://shop.example/p/linen-shirt"
PLAIN = "https://shop.example/p/plain"


def shirt_page(price: str = "68.00", name: str = "Linen camp-collar shirt", banner: str = "") -> str:
    """A made-up product page with its structured data, as a shop writes it for search engines, and `banner` in its
    text (a checkout code, say)."""
    data = {"@context": "https://schema.org", "@type": "Product", "name": name,
            "offers": {"@type": "Offer", "price": price, "priceCurrency": "USD",
                       "availability": "https://schema.org/InStock"}}
    return (f'<html><head><script type="application/ld+json">{json.dumps(data)}</script>'
            f'<meta property="og:site_name" content="Example Shop"></head><body>{banner}</body></html>')


class ShopPages:
    """Stands in for the web a link's page is read from: made-up pages by address (any other is not found).
    shop.example and other.example are on the internet; inside.example is on the home network."""

    def __init__(self):
        self.pages: dict[str, str] = {SHIRT: shirt_page(), PLAIN: "<html><head><title>A plain shirt</title></head></html>"}
        self.names = {"shop.example": ["1.2.3.4"], "other.example": ["1.2.3.5"], "inside.example": ["192.168.1.9"]}
        self.asked: list[str] = []
        self.reader = productpage.Reader(resolve=self.resolve, get=self.get)

    def resolve(self, host: str) -> list[str]:
        if host not in self.names:
            raise productpage.Unreadable(productpage.NO_SUCH_PLACE)
        return self.names[host]

    def get(self, target, seconds):
        self.asked.append(target.url)
        text = self.pages.get(target.url)
        if text is None:
            return productpage.Answer(404, {"content-type": "text/html"}, b"")
        return productpage.Answer(200, {"content-type": "text/html; charset=utf-8"}, text.encode("utf-8"))


@pytest.fixture
def fake_shop():
    return FakeShop()


@pytest.fixture
def pages():
    return ShopPages()


@pytest.fixture
def usable():
    return {"routes": ("plan",)}


@pytest.fixture
def services(cfg, fake_shop, usable, pages):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                   routes=lambda: usable["routes"], shop_asker=fake_shop, page_reader=pages.reader)
    yield sv
    sv.stop()


@pytest.fixture
def client(services):
    c = TestClient(app_module.create_app(services))
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


def test_stop_watching_can_be_undone_with_the_find_and_its_price_history(client):
    # the review of 23 November (A8): "Stop watching" took a find and its prices away at once, with no way back
    wid = wish(client)
    find_some(client, wid)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    before = settle(client, wid)["finds"]
    first = before[0]
    assert first["history"]
    assert client.delete(f"/api/wishlist/{wid}/finds/{first['id']}").status_code == 204
    r = client.post(f"/api/wishlist/{wid}/finds/{first['id']}/restore")
    assert r.status_code == 200, r.text
    assert r.json()["finds"] == before   # the same find, in the same place, with its whole price history
    # once only, and only a find that was stopped
    assert client.post(f"/api/wishlist/{wid}/finds/{first['id']}/restore").status_code == 404
    assert client.post(f"/api/wishlist/{wid}/finds/nope/restore").status_code == 404
    # nor while a search has found the same page again
    assert client.delete(f"/api/wishlist/{wid}/finds/{first['id']}").status_code == 204
    again = [f for f in find_some(client, wid)["finds"] if f["url"] == first["url"]]
    assert again   # the stand-in finds the same products every time
    r = client.post(f"/api/wishlist/{wid}/finds/{first['id']}/restore")
    assert r.status_code == 409 and r.json()["detail"] == shop.WATCHED_AGAIN
    # nor once its wish has gone
    assert client.delete(f"/api/wishlist/{wid}/finds/{again[0]['id']}").status_code == 204
    assert client.delete(f"/api/wishlist/{wid}").status_code == 204
    assert client.post(f"/api/wishlist/{wid}/finds/{again[0]['id']}/restore").status_code == 404


def test_a_removed_wish_can_be_put_back_whole_with_undo(client):
    # the review of 24 November (finding 5): "Remove from the list" took the wish, its finds, the most you'd pay and its
    # note away at once, with no way back
    wid = wish(client, note="Size 40, not too long")
    assert client.patch(f"/api/wishlist/{wid}", json={"price_max": 150, "price_currency": "USD"}).status_code == 200
    find_some(client, wid)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    finds = settle(client, wid)["finds"]
    assert client.put(f"/api/wishlist/{wid}/finds/{finds[0]['id']}/code", json={"code": "TEST20", "percent": 20}).status_code == 200
    listed = client.get("/api/wishlist").json()["wishes"]
    before = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert before[0]["code"] and before[0]["history"]
    assert client.delete(f"/api/wishlist/{wid}").status_code == 204
    assert wid not in [w["id"] for w in client.get("/api/wishlist").json()["wishes"]]
    r = client.post(f"/api/wishlist/{wid}/restore")
    assert r.status_code == 200, r.text
    assert r.json() == next(w for w in listed if w["id"] == wid)
    assert client.get("/api/wishlist").json()["wishes"] == listed   # in its place, with its note and price
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"] == before   # its finds, prices and code
    # once only, and only a wish that was removed
    assert client.post(f"/api/wishlist/{wid}/restore").status_code == 404
    assert client.post("/api/wishlist/nope/restore").status_code == 404


def test_removing_a_find_during_a_price_check_keeps_the_other_prices(client, fake_shop, monkeypatch):
    wid = wish(client)
    first, second = find_some(client, wid)["finds"]
    real = fake_shop.prices

    def prices_after_removal(finds, routes):
        assert client.delete(f"/api/wishlist/{wid}/finds/{first['id']}").status_code == 204
        return real(finds, routes)

    monkeypatch.setattr(fake_shop, "prices", prices_after_removal)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    assert body["run"]["state"] == "done"
    assert body["run"]["added"] == 1
    remaining, = body["finds"]
    assert remaining["id"] == second["id"]
    assert remaining["price"] == second["price"] * 0.8
    assert len(remaining["history"]) == 2 and body["prices_checked_at"]


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
    assert verdicts[0]["outfits"] == 3   # the example outfits the check made with it, counted for "See it with your clothes"
    assert any("rain" in r.lower() for r in verdicts[0]["reasons"])
    assert verdicts[1]["verdict"] in ("have_it", "adds", "hard_to_wear") and verdicts[1]["reasons"]
    assert shop.judge(rows, worn, []) == []


def test_find_some_also_tells_claude_about_the_owner(client, fake_shop):
    # what the closet says about the owner goes with the wish (aboutyou.py builds it; its own tests say what is in it)
    wid = wish(client)
    find_some(client, wid)
    assert fake_shop.calls[-1][1]["about"] == ""   # an empty closet with no sizes says nothing
    assert client.put("/api/sizes/jackets", json={"size": "40R"}).status_code == 200
    find_some(client, wid)
    about = fake_shop.calls[-1][1]["about"]
    assert about.startswith("About the person this is for") and "- Jackets and coats: 40R." in about
    assert "- Jackets and coats: 40R." in shopping.find_prompt(fake_shop.calls[-1][1])


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

    # what does not fit is not kept: another page, a price that is not one; a find sold out is marked so, at its last
    # price (the owner's report of 26 November: a price is never taken away by a check that shows none)
    fake_shop.prices_seen = [PriceSeen(url="https://elsewhere.example", price=1.0, currency="USD", available=True),
                             PriceSeen(url="https://shop.example/coat", price=-3.0, currency="USD", available=True),
                             PriceSeen(url="https://other.example/p/2", price=None, currency="USD", available=False)]
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    coat = next(f for f in body["finds"] if f["url"] == "https://shop.example/coat")
    navy = next(f for f in body["finds"] if f["url"] == "https://other.example/p/2")
    assert coat["price"] == 96.0 and len(coat["history"]) == 2 and coat["available"] is True
    assert navy["available"] is False and navy["price"] == 192.0 and navy["drop"]["to"] == 192.0
    assert [(h["price"], h["available"]) for h in navy["history"]] == [(240.0, True), (192.0, True), (192.0, False)]


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


def test_a_daily_price_check_whose_answer_could_not_be_kept_is_not_asked_again_the_same_day(client, services, fake_shop,
                                                                                            clock, monkeypatch):
    """Review 2, finding 5, the daily price round. Claude answers the day's price check, and keeping the answer fails
    once (the closet's database is busy, the fault `test_a_search_that_cannot_keep_its_finds_says_so` already expects).
    Once Claude has been asked and has answered, the day's look is made, whatever happens to the answer afterwards: the
    next hourly round does not ask Claude the same question again."""
    find_some(client, wish(client))
    fake_shop.calls.clear()
    real, failed = shop.save_prices, []

    def busy_once(*a, **k):
        if not failed:
            failed.append(1)
            raise sqlite3.OperationalError("database is locked")
        return real(*a, **k)
    monkeypatch.setattr(shop, "save_prices", busy_once)
    services.shopper.tick()
    assert [c[0] for c in fake_shop.calls] == ["prices"]
    clock[0] += timedelta(hours=1)
    services.shopper.tick()
    assert [c[0] for c in fake_shop.calls] == ["prices"], "Claude was asked for the same prices again an hour later"


def test_a_daily_price_check_whose_look_could_not_be_recorded_either_waits_a_day_while_nines_runs(
        client, services, fake_shop, clock, monkeypatch):
    """Review 2, finding 5: when even recording that the day's look was made fails, Nines remembers the time of the try
    while it runs, so the next hourly round still waits a day before asking Claude again."""
    find_some(client, wish(client))
    fake_shop.calls.clear()
    real = shop.save_prices, shop.mark_checked

    def busy(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(shop, "save_prices", busy)
    monkeypatch.setattr(shop, "mark_checked", busy)
    services.shopper.tick()
    clock[0] += timedelta(hours=1)
    services.shopper.tick()
    assert [c[0] for c in fake_shop.calls] == ["prices"]
    monkeypatch.setattr(shop, "save_prices", real[0])
    monkeypatch.setattr(shop, "mark_checked", real[1])
    clock[0] += timedelta(days=1)
    services.shopper.tick()
    assert [c[0] for c in fake_shop.calls] == ["prices", "prices"]   # a day on: asked again


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
    demo_prices = conn.execute("SELECT COUNT(*) FROM find_prices").fetchone()[0]   # the demo's own stand-in finds
    demo_checked = dict(conn.execute("SELECT id, prices_checked_at FROM wishes").fetchall())
    conn.close()
    fake_shop.calls.clear()

    assert services.shopper.tick() == 1   # the open wish with finds, in the real closet, whatever closet is open
    assert [c[0] for c in fake_shop.calls] == ["prices"] and "https://demo.example" not in fake_shop.calls[0][1]
    clock[0] += timedelta(hours=23)
    assert services.shopper.tick() == 0 and len(fake_shop.calls) == 1   # not again within the day
    clock[0] += timedelta(hours=1, seconds=1)
    assert services.shopper.tick() == 1 and len(fake_shop.calls) == 2   # a day on: once more
    conn = db.connect(cfg.db_path("demo"))
    assert conn.execute("SELECT COUNT(*) FROM find_prices").fetchone()[0] == demo_prices
    assert dict(conn.execute("SELECT id, prices_checked_at FROM wishes").fetchall()) == demo_checked
    assert demo_checked["dw"] is None
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


# ------------------------------------------------------------------ a product sent as a link
def add_link(client, url: str = SHIRT) -> str:
    """Sends a product's page from the wishlist, waits for it to be read, and gives the new wish's id."""
    r = client.post("/api/wishlist/link", json={"url": url})
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    assert settle(client, wid)["run"]["kind"] == "link"
    return wid


def test_a_link_becomes_a_wish_with_its_one_find_read_from_the_page(client, fake_shop, pages):
    r = client.post("/api/wishlist/link", json={"url": f"  {SHIRT}  "})
    assert r.status_code == 201
    wish_made = r.json()
    assert wish_made["name"] == "shop.example" and wish_made["gap_id"] is None   # until its page is read
    body = settle(client, wish_made["id"])
    assert body["run"]["kind"] == "link" and body["run"]["state"] == "done" and body["run"]["added"] == 1
    assert body["run"]["message"] is None
    find, = body["finds"]
    assert find["link"] is True and find["url"] == SHIRT and find["read_at"] and find["read_by"] == "page"
    assert (find["name"], find["shop"], find["price"], find["currency"]) == ("Linen camp-collar shirt", "Example Shop", 68.0, "USD")
    # described by Claude from the page's words, then judged against the (empty) closet as a search's finds are
    assert find["piece"]["category"] == "shirt" and find["piece"]["name"] == "Linen camp-collar shirt"
    assert "white shirt" in find["piece_words"] and find["verdict"] == "too_small" and find["reasons"]
    assert find["not_judged"] is None
    assert [h["price"] for h in find["history"]] == [68.0] and find["drop"] is None
    assert fake_shop.calls == []   # the page gave its price: Claude was not asked for it
    (asked, routes), = fake_shop.described
    assert asked["name"] == "Linen camp-collar shirt" and asked["shop"] == "Example Shop" and routes == ("plan",)
    listed, = client.get("/api/wishlist").json()["wishes"]
    assert listed["name"] == "Linen camp-collar shirt"   # named after the product once read
    assert listed["link"] == {"name": "Linen camp-collar shirt", "shop": "Example Shop", "price": 68.0, "currency": "USD",
                              "available": True}
    assert listed["drop"] is None

    # the same page sent again (the share sheet tapped twice) gives the same wish, and is not read again
    asked = len(pages.asked)
    again = client.post("/api/wishlist/link", json={"url": SHIRT})
    assert again.status_code == 200 and again.json()["id"] == wish_made["id"] and len(pages.asked) == asked
    assert len(client.get("/api/wishlist").json()["wishes"]) == 1


def test_a_long_product_name_names_the_wish_cut_at_a_word(client, pages):
    long = "Heavyweight garment-dyed linen camp-collar shirt in washed sand " * 3
    pages.pages[SHIRT] = shirt_page(name=long)
    wid = add_link(client, SHIRT)
    name = client.get("/api/wishlist").json()["wishes"][0]["name"]
    assert len(name) <= shop.LINK_NAME_MAX and name.endswith("…") and long.startswith(name[:-1]) and long[len(name) - 1] == " "
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["name"] == long.strip()[:shop.NAME_MAX].rstrip()
    assert shop.shortened("A shirt", 120) == "A shirt" and shop.shortened("x" * 130, 120) == "x" * 119 + "…"


def test_a_page_with_no_price_is_read_by_claude_as_a_price_check(client, fake_shop, pages):
    wid = add_link(client, PLAIN)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["name"] == "A plain shirt"   # the page gave its name, not its price
    assert find["price"] == 80.0 and find["read_by"] == "claude" and [h["price"] for h in find["history"]] == [80.0]
    assert fake_shop.calls == [("prices", [PLAIN], ("plan",))]   # that one page, as a price check
    assert client.get("/api/wishlist").json()["wishes"][0]["name"] == "A plain shirt"

    # a page that cannot be opened goes to Claude too; when Claude sees no price either, the wish says so
    fake_shop.prices_seen = [PriceSeen(url="https://shop.example/p/gone", price=None, currency="USD", available=True)]
    wid = add_link(client, "https://shop.example/p/gone")
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    assert body["run"]["message"] == shop.NO_PRICE_AT_ALL and body["finds"][0]["price"] is None
    assert body["finds"][0]["name"] == "shop.example"


def test_claude_out_of_reach_is_said_and_the_page_kept(client, fake_shop, usable):
    usable["routes"] = ()
    wid = add_link(client, PLAIN)
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    assert body["run"]["state"] == "done" and body["run"]["message"] == f"{shop.NO_PAGE_PRICE} {shop.NO_ROUTE}"
    assert body["finds"][0]["read_at"] and body["finds"][0]["price"] is None and fake_shop.calls == []


def test_a_link_added_on_a_wish_page(client, fake_shop, pages):
    wid = wish(client)
    find_some(client, wid)
    r = client.post(f"/api/wishlist/{wid}/link", json={"url": SHIRT})
    assert r.status_code == 202 and r.json()["run"]["kind"] == "link"
    body = settle(client, wid)
    assert len(body["finds"]) == 3 and body["run"]["added"] == 1
    linked = next(f for f in body["finds"] if f["link"])
    assert linked["url"] == SHIRT and linked["price"] == 68.0
    assert client.get("/api/wishlist").json()["wishes"][0]["name"] == "A tan rain coat"   # the owner's name is kept
    # a page Claude found, sent as a link: kept once, read by Nines from then on
    pages.pages["https://shop.example/coat"] = shirt_page("110.00", "Tan rain coat")
    assert client.post(f"/api/wishlist/{wid}/link", json={"url": "https://shop.example/coat"}).status_code == 202
    body = settle(client, wid)
    coat = next(f for f in body["finds"] if f["url"] == "https://shop.example/coat")
    assert len(body["finds"]) == 3 and coat["link"] is True and coat["price"] == 110.0 and coat["read_by"] == "page"
    assert coat["verdict"] == "too_small"   # it was described by Claude when found, so its verdict stays
    assert client.post("/api/wishlist/nope/link", json={"url": SHIRT}).status_code == 404


def test_a_link_nines_does_not_open_is_refused_with_a_plain_sentence(client, pages):
    wid = wish(client)
    for url, sentence in (("http://shop.example/p/linen-shirt", productpage.NOT_HTTPS),
                          ("https://inside.example/router", productpage.NOT_A_SHOP),
                          ("https://192.168.1.1/", productpage.NOT_A_SHOP),
                          ("not a link", productpage.NOT_A_LINK),
                          ("https://nowhere.example/p", productpage.NO_SUCH_PLACE)):
        for path in ("/api/wishlist/link", f"/api/wishlist/{wid}/link"):
            r = client.post(path, json={"url": url})
            assert r.status_code == 422 and r.json()["detail"] == sentence, (path, url)
    assert pages.asked == []   # nothing was fetched
    assert [w["id"] for w in client.get("/api/wishlist").json()["wishes"]] == [wid]   # and nothing kept
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"] == []
    assert client.post("/api/wishlist/link", json={"url": SHIRT, "note": "x"}).status_code == 422


def test_an_address_that_moved_inside_since_it_was_checked_is_not_opened_nor_sent_to_claude(client, services, fake_shop,
                                                                                           pages):
    looked = []

    def moves_inside(host):   # on the internet when the link is sent, the home network by the time it is fetched
        looked.append(host)
        return pages.resolve(host) if len(looked) == 1 else ["10.0.0.8"]
    services.shopper.reader = productpage.Reader(resolve=moves_inside, get=pages.get)
    r = client.post("/api/wishlist/link", json={"url": SHIRT})
    assert r.status_code == 201
    body = settle(client, r.json()["id"])
    assert body["run"]["message"] == productpage.NOT_A_SHOP and body["finds"][0]["price"] is None
    assert pages.asked == [] and fake_shop.calls == [] and len(looked) == 2


def test_the_demo_closet_reads_a_link_but_never_asks_claude(client, fake_shop, pages):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shirt = add_link(client, SHIRT)
    assert client.get(f"/api/wishlist/{shirt}/finds").json()["finds"][0]["price"] == 68.0
    plain = add_link(client, PLAIN)
    body = client.get(f"/api/wishlist/{plain}/finds").json()
    assert body["run"]["message"] == f"{shop.NO_PAGE_PRICE} {shop.DEMO_ASKS_NOTHING}" and body["finds"][0]["price"] is None
    # its price can be checked again, by reading the page only
    pages.pages[SHIRT] = shirt_page("60.00")
    assert client.post(f"/api/wishlist/{shirt}/prices").status_code == 202
    assert settle(client, shirt)["finds"][0]["price"] == 60.0
    assert fake_shop.calls == []


def test_check_prices_reads_the_links_itself_and_asks_claude_about_the_rest(client, fake_shop, pages, usable, cfg):
    wid = wish(client)
    find_some(client, wid)
    assert client.post(f"/api/wishlist/{wid}/link", json={"url": SHIRT}).status_code == 202
    settle(client, wid)
    pages.pages[SHIRT] = shirt_page("54.40")
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    assert fake_shop.calls[-1] == ("prices", ["https://shop.example/coat", "https://other.example/p/2"], ("plan",))
    linked = next(f for f in body["finds"] if f["link"])
    assert linked["price"] == 54.4 and linked["drop"] == {"from": 68.0, "to": 54.4, "currency": "USD", "percent": 20}
    assert body["run"]["added"] == 3 and body["run"]["message"] is None

    # Claude out of reach: the links are still read, and the wish says what was not
    usable["routes"] = ()
    checked = body["prices_checked_at"]
    calls = len(fake_shop.calls)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    assert body["run"]["message"] == f"{shop.NO_ROUTE} {shop.LINKS_ONLY}" and len(fake_shop.calls) == calls
    assert pages.asked.count(SHIRT) == 3
    assert body["prices_checked_at"] == checked   # the finds Claude found are tried again later
    # with no link, Claude out of reach is said before anything starts, as before
    other = wish(client, name="Loafers")
    usable["routes"] = ("plan",)
    find_some(client, other)
    usable["routes"] = ()
    r = client.post(f"/api/wishlist/{other}/prices")
    assert r.status_code == 409 and r.json()["detail"] == shop.NO_ROUTE


def test_a_drop_is_shown_on_the_wishlist_row(client, pages):
    wid = add_link(client, SHIRT)
    plain = wish(client, name="A belt")
    pages.pages[SHIRT] = shirt_page("51.00")
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    settle(client, wid)
    rows = {w["id"]: w for w in client.get("/api/wishlist").json()["wishes"]}
    assert rows[wid]["drop"] == {"from": 68.0, "to": 51.0, "currency": "USD", "percent": 25, "shop": "Example Shop"}
    assert rows[wid]["link"]["price"] == 51.0
    assert rows[plain]["drop"] is None and rows[plain]["link"] is None
    # back up again: no drop (the latest price is what counts)
    pages.pages[SHIRT] = shirt_page("70.00")
    client.post(f"/api/wishlist/{wid}/prices")
    settle(client, wid)
    assert {w["id"]: w for w in client.get("/api/wishlist").json()["wishes"]}[wid]["drop"] is None


def test_the_daily_round_reads_link_pages_first_whether_or_not_claude_can_be_asked(client, services, fake_shop, pages,
                                                                                   usable, clock):
    linked = add_link(client, SHIRT)
    found = wish(client)
    find_some(client, found)
    fake_shop.calls.clear()
    asked = pages.asked.count(SHIRT)
    assert services.shopper.tick() == 2   # both due; the link was read a moment ago, so it is not read again
    assert pages.asked.count(SHIRT) == asked
    assert [c[0] for c in fake_shop.calls] == ["prices"] and SHIRT not in fake_shop.calls[0][1]

    clock[0] += timedelta(days=1, seconds=1)
    pages.pages[SHIRT] = shirt_page("59.00")
    assert services.shopper.tick() == 2
    assert pages.asked.count(SHIRT) == asked + 1   # read by Nines itself
    assert all(SHIRT not in c[1] for c in fake_shop.calls)   # never sent to Claude: the page gave its price
    row = {w["id"]: w for w in client.get("/api/wishlist").json()["wishes"]}[linked]
    assert row["drop"]["to"] == 59.0

    # a day on with Claude out of reach: the link's page is still read, the rest waits for Claude
    clock[0] += timedelta(days=1, seconds=1)
    usable["routes"] = ()
    calls = len(fake_shop.calls)
    pages.pages[SHIRT] = shirt_page("57.00")
    assert services.shopper.tick() == 1 and len(fake_shop.calls) == calls
    assert client.get(f"/api/wishlist/{linked}/finds").json()["finds"][0]["price"] == 57.0
    assert services.shopper.tick() == 0   # within the day: not read again
    assert pages.asked.count(SHIRT) == asked + 2


def test_nothing_about_a_link_is_logged_when_its_page_breaks_the_reader(client, services, pages, caplog):
    class Breaks:
        def check(self, url):
            return pages.reader.check(url)

        def read(self, url):
            raise RuntimeError(f"could not read {url}")
    services.shopper.reader = Breaks()
    with caplog.at_level(logging.DEBUG):
        wid = add_link(client, SHIRT)
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["read_at"]
    assert "shop.example" not in caplog.text and "linen" not in caplog.text.lower()


# ------------------------------------------------------------------ a link described by Claude and judged
def described_page(name: str = "Linen camp-collar shirt", description: str = "A boxy shirt in washed linen.") -> str:
    """A made-up product page whose structured data gives its description, colour and material too."""
    data = {"@context": "https://schema.org", "@type": "Product", "name": name, "description": description,
            "brand": {"@type": "Brand", "name": "Example Brand"}, "color": "Sand", "material": "Linen",
            "image": "https://shop.example/img/shirt.jpg",
            "offers": {"@type": "Offer", "price": "68.00", "priceCurrency": "USD"}}
    return (f'<html><head><script type="application/ld+json">{json.dumps(data)}</script>'
            '<meta property="og:site_name" content="Example Shop"></head><body></body></html>')


def test_only_what_the_page_says_is_sent_to_claude_to_describe_a_link(client, fake_shop, pages):
    pages.pages[SHIRT] = described_page()
    wid = wish(client, name="A summer shirt", note="my size is L")
    assert client.post(f"/api/wishlist/{wid}/link", json={"url": SHIRT}).status_code == 202
    find, = settle(client, wid)["finds"]
    (asked, _), = fake_shop.described
    assert asked == {"name": "Linen camp-collar shirt", "shop": "Example Shop", "brand": "Example Brand",
                     "color": "Sand", "material": "Linen", "description": "A boxy shirt in washed linen."}
    prompt = shopping.describe_prompt(asked)
    assert "Description: A boxy shirt in washed linen." in prompt and "Brand: Example Brand" in prompt
    assert "my size is L" not in prompt and "A summer shirt" not in prompt   # nothing about the wish or the closet
    # judged, and shown with the shop's picture, as a search's find is
    assert find["verdict"] and find["image_url"] == "https://shop.example/img/shirt.jpg" and find["not_judged"] is None


def test_a_link_waits_for_claude_and_is_described_once_at_a_later_check(client, fake_shop, pages, usable):
    usable["routes"] = ()
    wid = add_link(client, SHIRT)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["piece"] is None and find["verdict"] is None and find["not_judged"] == "waiting"
    assert fake_shop.described == [] and find["price"] == 68.0   # its price is read all the same

    usable["routes"] = ("plan",)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["piece"]["category"] == "shirt" and find["verdict"] == "too_small" and find["not_judged"] is None
    assert len(fake_shop.described) == 1
    # described once: later checks judge it again with the closet as it is, without asking Claude again
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["verdict"] == "too_small" and len(fake_shop.described) == 1


def test_the_daily_round_describes_a_link_that_waited(client, services, fake_shop, pages, usable, clock):
    usable["routes"] = ()
    wid = add_link(client, SHIRT)
    usable["routes"] = ("plan",)
    clock[0] += timedelta(days=1, seconds=1)
    assert services.shopper.tick() == 1
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["piece"]["category"] == "shirt" and find["verdict"] and len(fake_shop.described) == 1


def test_an_answer_that_cannot_be_used_is_not_asked_again_for_the_same_page(client, fake_shop, pages):
    fake_shop.description = described(clothing=False)   # a gift card, say
    wid = add_link(client, SHIRT)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["piece"] is None and find["verdict"] is None and find["reasons"] == []
    assert find["not_judged"] == "unclear" and len(fake_shop.described) == 1
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    assert settle(client, wid)["finds"][0]["not_judged"] == "unclear" and len(fake_shop.described) == 1
    # the page changed: asked once more
    pages.pages[SHIRT] = shirt_page(name="Linen camp-collar shirt in sand")
    fake_shop.description = described()
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["piece"]["category"] == "shirt" and find["verdict"] and len(fake_shop.described) == 2

    # a description outside the closet's words, or no usable answer at all, counts as an answer that cannot be used
    for answer in (described(color="plaid-ish"), TaggingError("no valid answer")):
        fake_shop.description = answer
        other = add_link(client, PLAIN)
        assert client.get(f"/api/wishlist/{other}/finds").json()["finds"][0]["not_judged"] == "unclear"
        client.delete(f"/api/wishlist/{other}")


def test_claude_out_of_reach_while_describing_leaves_the_link_for_later(client, fake_shop, pages):
    for error in (Unreachable("no connection"), RouteUnavailable("signed out"), CapReached("the limit")):
        fake_shop.description = error
        wid = add_link(client, SHIRT)
        body = client.get(f"/api/wishlist/{wid}/finds").json()
        assert body["run"]["state"] == "done" and body["run"]["message"] is None   # the price was read all the same
        assert body["finds"][0]["price"] == 68.0 and body["finds"][0]["not_judged"] == "waiting"
        fake_shop.description = described()
        assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
        assert settle(client, wid)["finds"][0]["verdict"]   # asked again, and judged
        client.delete(f"/api/wishlist/{wid}")


def test_a_page_that_gives_no_name_is_not_described(client, fake_shop, pages):
    gone = "https://shop.example/p/gone"
    fake_shop.prices_seen = [PriceSeen(url=gone, price=50.0, currency="USD", available=True)]
    wid = add_link(client, gone)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["price"] == 50.0 and find["not_judged"] == "no_name" and fake_shop.described == []


def test_the_demo_closet_never_sends_a_link_to_claude_to_describe(client, fake_shop, pages):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    wid = add_link(client, SHIRT)
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["not_judged"] == "waiting" and find["verdict"] is None and fake_shop.described == []


def test_describing_a_link_through_the_api_key_is_refused_when_it_could_pass_the_limit(client, fake_shop, usable):
    usable["routes"] = ("api",)   # only the API key, and no limit set: nothing may be asked through it
    wid = add_link(client, SHIRT)
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["not_judged"] == "waiting"
    assert fake_shop.described == []


def test_claudes_description_is_checked_like_a_searchs():
    assert shop.clean_described(described(), "Shirt")["category"] == "shirt"
    assert shop.clean_described(described(weight_class="unknown"), "Shirt")["weight_class"] is None
    assert shop.clean_described(described(clothing=False), "Shirt") is None
    assert shop.clean_described(described(category="other"), "Shirt") is None
    assert shop.clean_described({"clothing": True, "category": "shirt"}, "Shirt") is None   # no colour
    assert shop.clean_described(None, "Shirt") is None
    # the fingerprint knows the same words again, and only them
    words = {"name": "Shirt", "shop": "Example Shop", "description": "Linen."}
    assert shop.fingerprint(shopping.describe_prompt(words)) == shop.fingerprint(shopping.describe_prompt(dict(words)))
    assert shop.fingerprint(shopping.describe_prompt(words)) != shop.fingerprint(
        shopping.describe_prompt({**words, "description": "Cotton."}))


def test_describing_a_link_is_a_short_question_recorded_with_its_own_purpose(services, cfg, monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["stdin"].read().decode("utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"structured_output": described().model_dump(), "usage": {"input_tokens": 10, "output_tokens": 5}}))
    monkeypatch.setattr(correcting.subprocess, "run", run)
    monkeypatch.setattr(correcting.claude_cli, "find_claude", lambda: "claude")
    answer = shop.ClaudeAsker(cfg, services.state).describe(
        {"name": "Linen camp-collar shirt", "shop": "Example Shop", "description": "A boxy shirt."}, ("plan",))
    assert answer.category == "shirt" and answer.clothing is True
    cmd = seen["cmd"]
    assert "WebSearch" not in cmd[cmd.index("--tools") + 1]   # no web search: the page's words are all it is given
    assert "Description: A boxy shirt." in seen["input"]
    conn = db.connect(cfg.db_path("main"))
    try:
        assert conn.execute("SELECT purpose FROM claude_calls").fetchone()[0] == spend.PURPOSE_DESCRIBE_LINK == "shop_describe"
    finally:
        conn.close()


# ------------------------------------------------------------------ price news
def at(day: int) -> str:
    """A moment on a day of November, as the database keeps it."""
    return f"2026-11-{day:02d}T09:00:00.000000Z"


def test_came_down_is_where_the_newest_price_came_down_to_a_drop():
    h = lambda *ps: [{"at": at(n + 1), "price": p, "currency": c, "available": a}  # noqa: E731
                     for n, (p, c, a) in enumerate(ps)]
    usd = lambda *prices: h(*((p, "USD", True) for p in prices))  # noqa: E731
    assert shop.came_down([]) is None
    assert shop.came_down(usd(80)) is None                       # first seen: no change
    assert shop.came_down(usd(80, 90)) is None                   # up
    assert shop.came_down(usd(100, 80)) == {"from": 100, "to": 80, "currency": "USD", "percent": 20, "at": at(2)}
    # checked again each day at the same price: still one drop, from the day it came down
    assert shop.came_down(usd(100, 80, 80, 80))["at"] == at(2)
    # down again: a new moment, from the highest before
    assert shop.came_down(usd(100, 80, 70)) == {"from": 100, "to": 70, "currency": "USD", "percent": 30, "at": at(3)}
    # back up from a lower price, though still under the highest: it did not come down
    assert shop.came_down(usd(100, 70, 80)) is None
    # a price not shown in between is passed over
    assert shop.came_down(usd(100, None, 80))["at"] == at(3)
    # sold out at the lower price: no news; another currency is not compared
    assert shop.came_down(h((100, "USD", True), (80, "USD", False))) is None
    assert shop.came_down(h((100, "EUR", True), (80, "USD", True))) is None


def test_a_price_that_came_down_while_sold_out_is_news_once_it_is_back_in_stock(tmp_path):
    """Review 2, finding 7. A find is seen at 100, then at 80 but sold out (no news, as decided), you open the wish (its
    news is marked seen), and then it is back in stock at 80. That is the first moment you could buy it for less, so it
    is news now: the moment of a drop is the first sighting at that price that could be bought."""
    path = tmp_path / "closet.db"
    db.migrate(path, tmp_path / "backups")
    conn = db.connect(path)
    try:
        conn.execute("INSERT INTO wishes (id, name, note, news_seen_at, created_at, updated_at) "
                     "VALUES ('w', 'A tan rain coat', '', ?, ?, ?)", (at(3), at(1), at(1)))
        conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, price, currency, piece, found_at, updated_at, link) "
                     "VALUES ('f', 'w', 'A coat', 'Example Shop', 'https://shop.example/f', 80, 'USD', '{}', ?, ?, 0)",
                     (at(1), at(1)))
        for n, price, available in ((1, 100, 1), (2, 80, 0), (4, 80, 1)):
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES ('f', ?, ?, 'USD', ?)",
                         (at(n), price, available))
        assert [(n["wish_id"], n["to"]) for n in shop.news(conn)] == [("w", 80.0)]
    finally:
        conn.close()
    # and told once: sold out again for a while and back at the same price, it came down on the day it first could be
    # bought at it
    h = lambda *ps: [{"at": at(n + 1), "price": p, "currency": "USD", "available": a}  # noqa: E731
                     for n, (p, a) in enumerate(ps)]
    assert shop.came_down(h((100, True), (80, False), (80, True)))["at"] == at(3)
    assert shop.came_down(h((100, True), (80, True), (80, False), (80, True)))["at"] == at(2)


@pytest.fixture
def closet(tmp_path):
    path = tmp_path / "closet.db"
    db.migrate(path, tmp_path / "backups")
    conn = db.connect(path)
    yield conn
    conn.close()


def wish_row(conn, name: str = "A tan rain coat", price_max: float | None = None, currency: str | None = None,
             seen: str | None = None, bought: str | None = None) -> str:
    wid = name.lower().replace(" ", "-")
    conn.execute("INSERT INTO wishes (id, name, note, price_max, price_currency, news_seen_at, bought_at, created_at, "
                 "updated_at) VALUES (?, ?, '', ?, ?, ?, ?, ?, ?)",
                 (wid, name, price_max, currency or ("USD" if price_max is not None else None), seen, bought, at(1), at(1)))
    return wid


def find_row(conn, wid: str, prices: list, link: bool = False, shop_name: str = "Example Shop",
             currency: str = "USD") -> str:
    """A find of the wish seen at these prices, a day apart from 1 November."""
    fid = f"{wid}-{shop_name}-{len(prices)}".lower().replace(" ", "-")
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, price, currency, piece, found_at, updated_at, link) "
                 "VALUES (?, ?, 'A coat', ?, ?, ?, ?, ?, ?, ?, ?)",
                 (fid, wid, shop_name, f"https://shop.example/{fid}", prices[-1], currency, "null" if link else "{}",
                  at(1), at(1), int(link)))
    for n, price in enumerate(prices):
        conn.execute("INSERT INTO find_prices (find_id, at, price, currency) VALUES (?, ?, ?, ?)",
                     (fid, at(n + 1), price, currency))
    return fid


def test_a_price_that_came_down_is_news_with_or_without_the_most_the_owner_would_pay(closet):
    plain = wish_row(closet, "A belt")
    find_row(closet, plain, [60.0, 50.0])
    under = wish_row(closet, "A tan rain coat", price_max=150)
    find_row(closet, under, [177.0, 177.0, 150.0], link=True)
    over = wish_row(closet, "Brown loafers", price_max=100)
    find_row(closet, over, [180.0, 140.0])                       # down, but not to the price: no news
    news = {n["wish_id"]: n for n in shop.news(closet)}
    assert set(news) == {plain, under}
    assert news[under] == {"wish_id": under, "name": "A tan rain coat", "shop": "Example Shop", "from": 177.0,
                           "to": 150.0, "currency": "USD", "percent": 15, "at": at(3), "at_price": True}
    assert news[plain]["at_price"] is False and (news[plain]["from"], news[plain]["to"]) == (60.0, 50.0)
    assert [n["wish_id"] for n in shop.news(closet)] == [under, plain]   # the newest first


def test_a_price_in_another_currency_than_the_owners_is_news_without_being_at_their_price(closet):
    wid = wish_row(closet, price_max=100, currency="EUR")
    find_row(closet, wid, [180.0, 140.0])
    assert [(n["to"], n["at_price"]) for n in shop.news(closet)] == [(140.0, False)]


def test_a_find_first_seen_under_the_price_is_no_news_until_it_comes_down(closet):
    wid = wish_row(closet, price_max=150)
    fid = find_row(closet, wid, [120.0])
    assert shop.news(closet) == []
    closet.execute("INSERT INTO find_prices (find_id, at, price, currency) VALUES (?, ?, 110, 'USD')", (fid, at(5)))
    assert [n["to"] for n in shop.news(closet)] == [110.0]


def test_seen_hides_the_news_and_a_new_drop_after_it_shows_again(closet):
    wid = wish_row(closet)
    fid = find_row(closet, wid, [100.0, 80.0])                 # came down on the 2nd
    other = wish_row(closet, "A belt")
    find_row(closet, other, [60.0, 50.0])
    shop.mark_seen(closet, [wid, "no-such-wish"])
    assert [n["wish_id"] for n in shop.news(closet)] == [other]
    assert closet.execute("SELECT news_seen_at FROM wishes WHERE id = ?", (other,)).fetchone()[0] is None
    # checked again the next day at the same price: still seen
    closet.execute("INSERT INTO find_prices (find_id, at, price, currency) VALUES (?, '2099-01-01T09:00:00.000000Z', 80, "
                   "'USD')", (fid,))
    assert [n["wish_id"] for n in shop.news(closet)] == [other]
    # down again after it was seen: news again
    closet.execute("INSERT INTO find_prices (find_id, at, price, currency) VALUES (?, '2099-01-02T09:00:00.000000Z', 70, "
                   "'USD')", (fid,))
    assert [(n["wish_id"], n["to"]) for n in shop.news(closet)][0] == (wid, 70.0)


def test_a_bought_wish_never_has_news_and_the_biggest_drop_of_a_wish_is_told(closet):
    bought = wish_row(closet, "A belt", bought=at(9))
    find_row(closet, bought, [60.0, 50.0])
    wid = wish_row(closet)
    find_row(closet, wid, [100.0, 90.0], shop_name="Example Shop")
    find_row(closet, wid, [100.0, 60.0], shop_name="Other Shop", link=True)   # sent as a link: the same rule
    news, = shop.news(closet)
    assert (news["wish_id"], news["shop"], news["to"]) == (wid, "Other Shop", 60.0)


def test_migration_0045_tells_a_price_already_down_once(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 45:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    conn.execute("INSERT INTO wishes (id, name, note, created_at, updated_at) VALUES ('w1', 'A tan rain coat', '', ?, ?)",
                 (at(1), at(1)))
    wid = "w1"
    find_row(conn, wid, [100.0, 80.0])
    conn.close()
    assert db.migrate(path, tmp_path / "backups")["applied"][0] == 45   # and any later ones
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT news_seen_at FROM wishes").fetchone()[0] is None
        assert [n["wish_id"] for n in shop.news(conn)] == [wid]
    finally:
        conn.close()


def test_the_news_is_read_without_changing_anything_and_marked_seen_by_the_page(client, pages):
    wid = add_link(client, SHIRT)
    assert client.get("/api/wishlist/news").json() == {"news": []}   # first seen: nothing came down
    pages.pages[SHIRT] = shirt_page("51.00")
    client.post(f"/api/wishlist/{wid}/prices")
    settle(client, wid)
    for _ in range(2):   # reading it changes nothing
        news, = client.get("/api/wishlist/news").json()["news"]
    assert (news["wish_id"], news["name"], news["shop"], news["from"], news["to"], news["at_price"]) == (
        wid, "Linen camp-collar shirt", "Example Shop", 68.0, 51.0, False)
    r = client.post("/api/wishlist/news/seen", json={"wish_ids": [wid]})
    assert r.status_code == 200 and r.json() == {"news": []}
    assert client.get("/api/wishlist/news").json() == {"news": []}
    # the page still shows the drop; only the news is over
    assert client.get("/api/wishlist").json()["wishes"][0]["drop"]["to"] == 51.0


def test_marking_news_seen_takes_only_a_list_of_wishes(client):
    assert client.post("/api/wishlist/news/seen", json={}).status_code == 422
    assert client.post("/api/wishlist/news/seen", json={"wish_ids": "all"}).status_code == 422
    assert client.post("/api/wishlist/news/seen", json={"wish_ids": [], "all": True}).status_code == 422
    assert client.post("/api/wishlist/news/seen", json={"wish_ids": ["w"] * (shop.SEEN_MAX + 1)}).status_code == 422


def test_the_demo_closet_never_has_news(client, pages, cfg):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    wid = add_link(client, SHIRT)
    pages.pages[SHIRT] = shirt_page("51.00")
    client.post(f"/api/wishlist/{wid}/prices")
    assert settle(client, wid)["finds"][0]["drop"]["to"] == 51.0
    assert client.get("/api/wishlist/news").json() == {"news": []}
    assert client.post("/api/wishlist/news/seen", json={"wish_ids": [wid]}).json() == {"news": []}
    conn = db.connect(cfg.db_path("demo"))
    try:   # nothing written to the demo closet
        assert conn.execute("SELECT news_seen_at FROM wishes WHERE id = ?", (wid,)).fetchone()[0] is None
    finally:
        conn.close()


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


def test_finds_are_judged_on_the_same_weighed_list_as_would_this_work():
    # a find for a wish and the same piece described on "Would this work?" must get the same answer once the owner
    # has said how they live (a find used to be judged on the plain list, naming gaps for days they never have)
    from closet import wouldwork

    from .test_wouldwork import demo as demo_closet
    rows, worn = demo_closet()
    answers, home = life.example()
    weighed = life.analyse(rows, worn, answers, home, wouldwork.ALL_GAPS)
    weighed["context"] = {"life": answers, "climate": home}
    pieces = [wouldwork.parse_piece({"category": "dress_shoes", "color": "black", "formality": "business"}),
              wouldwork.parse_piece({"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True})]
    found = shop.judge(rows, worn, pieces, weighed)
    for p, f in zip(pieces, found, strict=True):
        check = wouldwork.check(rows, worn, p, weighed, answers, home)
        assert (f["verdict"], f["reasons"]) == (check["verdict"], check["reasons"])
    assert [f["verdict"] for f in shop.judge(rows, worn, pieces)] == [
        wouldwork.check(rows, worn, p, gaps.find_gaps(rows, worn, {"max_gaps": wouldwork.ALL_GAPS}))["verdict"] for p in pieces]


def test_the_app_gives_the_shopper_the_list_it_keeps(client, services, cfg):
    # the plain list until the owner has said how they live, the weighed one in the demo; either way the one the
    # Wardrobe's list is made from, kept, so a search or a price check does not work it out again
    plain = services.shopper.listed("main", app_module.closet_inputs(cfg, "main"))
    assert plain["context"]["life"] is None   # not said how they live yet
    assert services.shopper.listed("main", app_module.closet_inputs(cfg, "main")) is plain
    client.post("/api/profile", json={"profile": "demo"})
    assert services.shopper.listed("demo", app_module.closet_inputs(cfg, "demo"))["context"]["life"] == life.DEMO_LIFE


def owner_closet_like_the_demo(cfg) -> None:
    """The owner's own closet starts as a copy of the demo closet, as the browser tests' `seed: 'demo'` makes it."""
    demo.ensure(cfg)
    src, dst = sqlite3.connect(cfg.db_path("demo")), sqlite3.connect(cfg.db_path("main"))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def test_a_search_and_a_price_check_judge_on_the_list_the_wardrobe_keeps(cfg, fake_shop, usable, pages, monkeypatch):
    # Until the owner has said how they live, each search and each price check worked the plain list out again: a
    # third of what judging two finds costs on the demo's closet, and with the browser tests' four files at once on a
    # slow computer, what took the finds past their wait. The list kept for the Wardrobe is the same list.
    owner_closet_like_the_demo(cfg)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                   routes=lambda: usable["routes"], shop_asker=fake_shop, page_reader=pages.reader)
    try:
        client = TestClient(app_module.create_app(sv))
        worked_out = []
        plain = gaps.find_gaps
        monkeypatch.setattr(gaps, "find_gaps", lambda *a, **kw: worked_out.append(1) or plain(*a, **kw))
        assert client.get("/api/gaps").json()["gaps"]   # the Wardrobe's list, worked out once
        assert len(worked_out) == 1
        polo = product(name="Navy polo", url="https://other.example/polo", category="polo", color="navy", season="warm",
                       rain_proof=False, material="")
        fake_shop.finds = [product(weight_class="heavyweight"), polo]
        wid = wish(client)
        found = find_some(client, wid)["finds"]
        assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
        checked = settle(client, wid)
        assert checked["run"]["state"] == "done" and checked["finds"][0]["drop"]
        assert len(worked_out) == 1   # neither the search nor the price check worked it out again
        # and the finds are judged exactly as on the list worked out afresh
        rows, worn = app_module.closet_inputs(cfg, "main")
        afresh = shop.judge(rows, worn, [f["piece"] for f in found])
        assert [(f["verdict"], f["reasons"]) for f in found] == [(v["verdict"], v["reasons"]) for v in afresh]
        assert [(f["verdict"], f["reasons"]) for f in checked["finds"]] == [(v["verdict"], v["reasons"]) for v in afresh]
        assert found[0]["verdict"] == "fills_gap"
    finally:
        sv.stop()


# ------------------------------------------------------------------ checkout codes
CODED = "https://shop.example/p/coded-shirt"
COAT, NAVY = "https://shop.example/coat", "https://other.example/p/2"


def coded(price: str = "177.00", banner: str = '<div class="promo">40% off with code TEST40</div>') -> str:
    """A made-up product page whose text shows a checkout code."""
    return shirt_page(price, "Linen shirt with a code", banner)


@pytest.mark.parametrize("code,percent,amount,price,kept", [
    ("test40", 40, None, 177.0, {"code": "TEST40", "percent": 40.0, "amount": None}),   # kept upper-case
    (" TAKE-20_x ", None, 20, 177.0, {"code": "TAKE-20_X", "percent": None, "amount": 20.0}),
    ("ABC", 1, None, None, {"code": "ABC", "percent": 1.0, "amount": None}),          # a percent needs no price
    ("X" * 30, 90, None, 177.0, {"code": "X" * 30, "percent": 90.0, "amount": None}),
    ("TEST", None, 176.99, 177.0, {"code": "TEST", "percent": None, "amount": 176.99}),
    ("AB", 10, None, 177.0, shop.BAD_CODE),
    ("X" * 31, 10, None, 177.0, shop.BAD_CODE),
    ("TEST 40", 40, None, 177.0, shop.BAD_CODE),
    ("TEST!40", 40, None, 177.0, shop.BAD_CODE),
    ("---", 40, None, 177.0, shop.BAD_CODE),
    (40, 40, None, 177.0, shop.BAD_CODE),
    ("TEST40", 40, 20, 177.0, shop.ONE_DISCOUNT),
    ("TEST40", None, None, 177.0, shop.ONE_DISCOUNT),
    ("TEST40", 0, None, 177.0, shop.BAD_PERCENT),
    ("TEST40", 0.5, None, 177.0, shop.BAD_PERCENT),
    ("TEST40", 91, None, 177.0, shop.BAD_PERCENT),
    ("TEST40", True, None, 177.0, shop.BAD_PERCENT),
    ("TEST40", "40", None, 177.0, shop.BAD_PERCENT),
    ("TEST40", None, 0, 177.0, shop.BAD_AMOUNT),
    ("TEST40", None, -5, 177.0, shop.BAD_AMOUNT),
    ("TEST40", None, 177, 177.0, shop.BAD_AMOUNT),     # not less than the price
    ("TEST40", None, 20, None, shop.NO_PRICE_YET),
])
def test_a_code_is_checked_before_it_is_kept(code, percent, amount, price, kept):
    checked, problem = shop.code_problem(code, percent, amount, price)
    assert (checked if isinstance(kept, dict) else problem) == kept
    assert (checked is None) == (problem is not None)


def test_a_code_read_on_a_page_is_never_a_word_that_is_plainly_not_one():
    assert shop.clean_code("SALE", 40, None, 100.0) is None and shop.clean_code("code", 40, None, 100.0) is None
    assert shop.code_problem("SALE", 40, None, 100.0)[0]["code"] == "SALE"   # typed: the owner's word
    assert shop.clean_code("TEST40", 40, None, 100.0) == {"code": "TEST40", "percent": 40.0, "amount": None}


def test_the_price_with_a_code_is_worked_out_to_the_cent():
    assert shop.price_with(177.0, 40, None) == 106.2
    assert shop.price_with(68.0, 20, None) == 54.4
    assert shop.price_with(19.99, 15, None) == 16.99
    assert shop.price_with(10.05, 50, None) == 5.03     # half a cent up
    assert shop.price_with(177.0, None, 20) == 157.0
    assert shop.price_with(20.0, None, 20) is None      # an amount no longer less than the price
    assert shop.price_with(None, 40, None) is None and shop.price_with(100.0, None, None) is None


def test_of_the_codes_a_page_shows_the_biggest_discount_that_fits_is_kept():
    def read(price, *found):
        return shop.clean_read(productpage.Product(name="A shirt", price=price, currency="USD", codes=list(found)))
    C = productpage.Code
    found = (C("TEST20", percent=20), C("TAKE50", amount=50, currency="USD"), C("TAKE60", amount=60, currency="EUR"),
             C("SALE", percent=70), C("TEST95", percent=95))
    assert read(177.0, *found)["code"] == {"code": "TAKE50", "percent": None, "amount": 50.0, "currency": "USD"}
    assert read(40.0, *found)["code"]["code"] == "TEST20"   # $50 off is more than the price: not a discount on it
    # with no price an amount cannot be checked: the biggest percent
    assert read(None, C("TEST20", percent=20), C("TEST30", percent=30), C("TAKE10", amount=10, currency="USD"))["code"][
        "code"] == "TEST30"
    assert read(177.0)["code"] is None and read(177.0, C("TEST95", percent=95))["code"] is None


def point(day: int, price, with_code=None, code=None, currency="USD", available=True) -> dict:
    return {"at": at(day), "price": price, "currency": currency, "available": available, "with_code": with_code,
            "code": code}


def test_a_drop_and_a_price_that_came_down_count_the_price_after_the_code():
    appears = [point(1, 177.0), point(2, 177.0, 106.2, "TEST40")]
    assert shop.drop(appears) == {"from": 177.0, "to": 106.2, "currency": "USD", "percent": 40, "code": "TEST40"}
    assert shop.came_down(appears)["at"] == at(2)           # a code that appears and brings the price down: news
    goes = appears + [point(3, 177.0)]
    assert shop.drop(goes) is None and shop.came_down(goes) is None   # a code that goes: no drop, no news
    first = [point(1, 177.0, 106.2, "TEST40"), point(2, 177.0, 106.2, "TEST40")]
    assert shop.drop(first) is None                          # first seen with its code: nothing came down
    lower_without = [point(1, 177.0, 106.2, "TEST40"), point(2, 150.0)]
    assert shop.drop(lower_without) is None                  # the price came down, but what you'd pay went up
    both = [point(1, 177.0, 106.2, "TEST40"), point(2, 150.0, 90.0, "TEST40")]
    assert shop.drop(both) == {"from": 106.2, "to": 90.0, "currency": "USD", "percent": 15, "code": "TEST40"}
    other = [point(1, 177.0, currency="EUR"), point(2, 177.0, 106.2, "TEST40")]
    assert shop.drop(other) is None and shop.came_down(other) is None   # never compared across currencies


def coded_row(conn, wid: str, points: list[tuple]) -> str:
    """A find sent as a link, seen at these (price, price after the code, code), a day apart from 1 November."""
    fid = f"{wid}-coded"
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, price, currency, piece, found_at, updated_at, link) "
                 "VALUES (?, ?, 'A coat', 'Example Shop', ?, ?, 'USD', 'null', ?, ?, 1)",
                 (fid, wid, f"https://shop.example/{fid}", points[-1][0], at(1), at(1)))
    for n, (price, after, code) in enumerate(points):
        conn.execute("INSERT INTO find_prices (find_id, at, price, currency, with_code, code) VALUES (?, ?, ?, 'USD', ?, ?)",
                     (fid, at(n + 1), price, after, code))
    return fid


def test_within_your_price_counts_the_price_after_the_code(closet):
    under = wish_row(closet, "A tan rain coat", price_max=120)
    coded_row(closet, under, [(177.0, None, None), (177.0, 106.2, "TEST40")])
    over = wish_row(closet, "Brown loafers", price_max=100)
    coded_row(closet, over, [(177.0, None, None), (177.0, 106.2, "TEST40")])
    news, = shop.news(closet)
    assert (news["wish_id"], news["to"], news["code"], news["at_price"]) == (under, 106.2, "TEST40", True)


def test_a_code_on_the_page_is_kept_with_the_price_after_it_and_goes_when_the_page_drops_it(client, pages, fake_shop):
    pages.pages[CODED] = coded()
    wid = add_link(client, CODED)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert {k: find["code"][k] for k in ("code", "percent", "amount", "by")} == {
        "code": "TEST40", "percent": 40.0, "amount": None, "by": "page"} and find["code"]["seen_at"]
    assert (find["price"], find["with_code"]) == (177.0, 106.2)
    assert (find["history"][-1]["with_code"], find["history"][-1]["code"]) == (106.2, "TEST40")
    assert find["drop"] is None and fake_shop.calls == []   # first seen with it; read by Nines alone
    row, = client.get("/api/wishlist").json()["wishes"]
    assert row["link"] == {"name": "Linen shirt with a code", "shop": "Example Shop", "price": 177.0, "currency": "USD",
                           "available": True, "code": "TEST40", "with_code": 106.2}
    assert client.get("/api/wishlist/news").json() == {"news": []}

    # the page shows no code now: it goes, and its going is no drop and no news
    pages.pages[CODED] = coded(banner="<p>Free returns</p>")
    find = check(client, wid)
    assert find["code"] is None and find["with_code"] is None and find["drop"] is None
    assert client.get("/api/wishlist/news").json() == {"news": []}
    assert "code" not in client.get("/api/wishlist").json()["wishes"][0]["link"]

    # a code that appears and brings the price down is news, said with its code
    pages.pages[CODED] = coded(banner="<p>Use code TEST25 for 25% off</p>")
    find = check(client, wid)
    assert find["drop"] == {"from": 177.0, "to": 132.75, "currency": "USD", "percent": 25, "code": "TEST25"}
    news, = client.get("/api/wishlist/news").json()["news"]
    assert (news["from"], news["to"], news["code"]) == (177.0, 132.75, "TEST25")
    assert client.get("/api/wishlist").json()["wishes"][0]["drop"]["code"] == "TEST25"


def check(client, wid: str) -> dict:
    """Check now on a wish with one find; gives the find once it is done."""
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    return settle(client, wid)["finds"][0]


def check_all(client, wid: str) -> dict[str, dict]:
    """Check now on a wish; gives its finds by their page once it is done."""
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    return {f["url"]: f for f in settle(client, wid)["finds"]}


def test_a_code_you_type_stays_until_you_remove_it_and_is_not_news_to_you(client, pages):
    wid = add_link(client, SHIRT)
    fid = client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["id"]
    r = client.put(f"/api/wishlist/{wid}/finds/{fid}/code", json={"code": " test20 ", "percent": 20})
    assert r.status_code == 200
    find, = r.json()["finds"]
    assert {k: find["code"][k] for k in ("code", "percent", "amount", "by")} == {
        "code": "TEST20", "percent": 20.0, "amount": None, "by": "you"}
    assert find["with_code"] == 54.4 and find["drop"]["to"] == 54.4 and find["drop"]["code"] == "TEST20"
    assert client.get("/api/wishlist/news").json() == {"news": []}   # you added it: not news to you
    points = len(find["history"])
    client.put(f"/api/wishlist/{wid}/finds/{fid}/code", json={"code": "TEST20", "percent": 20})
    assert len(client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["history"]) == points   # saved again: once

    # a read of the page never takes it away, nor puts another in its place
    pages.pages[SHIRT] = shirt_page("68.00", banner="<p>30% off with code TEST30</p>")
    assert check(client, wid)["code"]["code"] == "TEST20"
    pages.pages[SHIRT] = shirt_page("60.00")
    find = check(client, wid)
    assert (find["code"]["code"], find["code"]["by"], find["with_code"]) == ("TEST20", "you", 48.0)
    assert client.get("/api/wishlist/news").json()["news"][0]["to"] == 48.0   # the price itself came down: news

    # an amount off, in the find's currency
    r = client.put(f"/api/wishlist/{wid}/finds/{fid}/code", json={"code": "TAKE10", "amount": 10})
    assert r.json()["finds"][0]["with_code"] == 50.0
    # removed: gone; and a code read from the page that you removed is not taken from it again
    r = client.delete(f"/api/wishlist/{wid}/finds/{fid}/code")
    assert r.status_code == 200 and r.json()["finds"][0]["code"] is None and r.json()["finds"][0]["drop"]["to"] == 60.0
    pages.pages[SHIRT] = shirt_page("60.00", banner="<p>30% off with code TEST30</p>")
    assert check(client, wid)["code"]["code"] == "TEST30"
    client.delete(f"/api/wishlist/{wid}/finds/{fid}/code")
    assert check(client, wid)["code"] is None
    pages.pages[SHIRT] = shirt_page("60.00", banner="<p>35% off with code TEST35</p>")
    assert check(client, wid)["code"]["code"] == "TEST35"   # another code is


def test_a_code_that_does_not_fit_is_refused_with_a_sentence(client, pages, usable):
    wid = add_link(client, SHIRT)
    fid = client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["id"]
    path = f"/api/wishlist/{wid}/finds/{fid}/code"
    for body, sentence in (({"code": "a b", "percent": 20}, shop.BAD_CODE),
                           ({"code": "TEST20", "percent": 20, "amount": 5}, shop.ONE_DISCOUNT),
                           ({"code": "TEST20"}, shop.ONE_DISCOUNT),
                           ({"code": "TEST95", "percent": 95}, shop.BAD_PERCENT),
                           ({"code": "TAKE68", "amount": 68}, shop.BAD_AMOUNT)):
        r = client.put(path, json=body)
        assert r.status_code == 422 and r.json()["detail"] == sentence, body
    assert client.put(path, json={"code": "TEST20", "percent": 20, "by": "page"}).status_code == 422
    assert client.put(path, json={"percent": 20}).status_code == 422
    assert client.put(f"/api/wishlist/{wid}/finds/nope/code", json={"code": "TEST20", "percent": 20}).status_code == 404
    assert client.put(f"/api/wishlist/nope/finds/{fid}/code", json={"code": "TEST20", "percent": 20}).status_code == 404
    assert client.delete(f"/api/wishlist/{wid}/finds/nope/code").status_code == 404
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["code"] is None and len(find["history"]) == 1   # nothing kept
    assert client.delete(path).status_code == 200   # no code to remove: nothing happens

    # a find whose price is not known yet takes a percent, not an amount
    usable["routes"] = ()
    plain = add_link(client, PLAIN)
    pid = client.get(f"/api/wishlist/{plain}/finds").json()["finds"][0]["id"]
    r = client.put(f"/api/wishlist/{plain}/finds/{pid}/code", json={"code": "TAKE10", "amount": 10})
    assert r.status_code == 422 and r.json()["detail"] == shop.NO_PRICE_YET
    r = client.put(f"/api/wishlist/{plain}/finds/{pid}/code", json={"code": "TEST10", "percent": 10})
    assert r.json()["finds"][0]["code"]["code"] == "TEST10" and r.json()["finds"][0]["with_code"] is None
    assert r.json()["finds"][0]["history"] == []


def test_a_code_typed_in_the_demo_closet_marks_nothing_seen(client, pages, cfg):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    wid = add_link(client, SHIRT)
    fid = client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["id"]
    assert client.put(f"/api/wishlist/{wid}/finds/{fid}/code", json={"code": "TEST20", "percent": 20}).status_code == 200
    conn = db.connect(cfg.db_path("demo"))
    try:
        assert conn.execute("SELECT news_seen_at FROM wishes WHERE id = ?", (wid,)).fetchone()[0] is None
    finally:
        conn.close()


def test_claude_may_give_the_code_a_page_shows_and_one_that_does_not_fit_is_dropped_alone(client, fake_shop, pages):
    wid = wish(client)
    find_some(client, wid)
    fake_shop.prices_seen = [
        PriceSeen(url=COAT, price=120.0, currency="USD", available=True, code="test40", code_percent=40),
        PriceSeen(url=NAVY, price=240.0, currency="USD", available=True, code="SALE", code_percent=30)]
    body = check_all(client, wid)
    assert (body[COAT]["code"]["code"], body[COAT]["code"]["by"], body[COAT]["with_code"]) == ("TEST40", "claude", 72.0)
    assert body[COAT]["drop"] == {"from": 120.0, "to": 72.0, "currency": "USD", "percent": 40, "code": "TEST40"}
    assert body[NAVY]["price"] == 240.0 and body[NAVY]["code"] is None   # not a code: dropped, the price kept

    # an amount off that is not less than the price, or both kinds of discount: dropped; Claude's code goes with it
    fake_shop.prices_seen = [
        PriceSeen(url=COAT, price=120.0, currency="USD", available=True, code="TAKE200", code_amount=200),
        PriceSeen(url=NAVY, price=240.0, currency="USD", available=True, code="TEST10", code_percent=10, code_amount=5)]
    body = check_all(client, wid)
    assert body[COAT]["code"] is None and body[NAVY]["code"] is None and body[COAT]["price"] == 120.0

    # never in place of a code you typed
    client.put(f"/api/wishlist/{wid}/finds/{body[COAT]['id']}/code", json={"code": "TEST15", "percent": 15})
    fake_shop.prices_seen = [PriceSeen(url=COAT, price=120.0, currency="USD", available=True, code="TEST40",
                                       code_percent=40)]
    assert check_all(client, wid)[COAT]["code"]["code"] == "TEST15"


def test_a_code_nines_read_on_the_page_is_kept_over_claudes_and_claudes_goes_once_nines_can_read_the_price(
        client, fake_shop, pages):
    # the page gives no price but shows a code: Nines keeps the code, Claude reads the price
    pages.pages[PLAIN] = "<html><head><title>A plain shirt</title></head><body><p>40% off with code TEST40</p></body></html>"
    fake_shop.prices_seen = [PriceSeen(url=PLAIN, price=80.0, currency="USD", available=True, code="OTHER30",
                                       code_percent=30)]
    wid = add_link(client, PLAIN)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert (find["code"]["code"], find["code"]["by"], find["price"], find["with_code"]) == ("TEST40", "page", 80.0, 48.0)

    # no code in its text any more: Claude's is kept
    pages.pages[PLAIN] = "<html><head><title>A plain shirt</title></head><body></body></html>"
    find = check(client, wid)
    assert (find["code"]["code"], find["code"]["by"], find["with_code"]) == ("OTHER30", "claude", 56.0)
    # the page gives its price now and shows no code: Claude is not asked, so its code goes
    pages.pages[PLAIN] = shirt_page("80.00", "A plain shirt")
    calls = len(fake_shop.calls)
    find = check(client, wid)
    assert find["code"] is None and len(fake_shop.calls) == calls


def test_the_price_check_asks_for_a_code_anyone_can_use_in_optional_fields_on_both_routes(monkeypatch):
    from anthropic.lib._parse._transform import transform_schema
    text = shopping.price_prompt([{"url": COAT, "name": "Coat", "shop": "Example Shop", "price": 120.0, "currency": "USD"}])
    assert "a code to enter at checkout" in text and "before any code" in text and "Never make up a code" in text
    assert all(words in text for words in ('"up to"', "first order", "new customers", "signing up", "newsletter",
                                           "the app", "members"))
    item = transform_schema(PriceAnswer)["$defs"]["PriceSeen"]
    assert set(item["required"]) == {"url", "price", "currency", "available"}
    assert {"code", "code_percent", "code_amount"} <= set(item["properties"])
    assert PriceAnswer.model_validate({"prices": [{"url": COAT, "price": 1, "currency": "USD", "available": True}]})

    # the plan route: the same form on the command line, and a code read back from its answer
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        answer = {"prices": [{"url": COAT, "price": 99.0, "currency": "USD", "available": True, "code": "TEST40",
                              "code_percent": 40}]}
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"structured_output": answer, "usage": {"input_tokens": 10, "output_tokens": 5}}))
    monkeypatch.setattr(correcting.subprocess, "run", run)
    answer = shopping.prices([{"url": COAT, "name": "Coat", "shop": "Shop", "price": 120.0, "currency": "USD"}], ("plan",),
                             exe="claude")
    assert (answer.prices[0].code, answer.prices[0].code_percent) == ("TEST40", 40.0)
    sent = json.loads(seen["cmd"][seen["cmd"].index("--json-schema") + 1])
    assert set(sent["$defs"]["PriceSeen"]["required"]) == set(item["required"])

    # the API route: the same form as a strict tool
    api = FakeSearchApi([{"prices": [{"url": COAT, "price": 99.0, "currency": "USD", "available": True}]}])
    result = shopping.ask_api(api, shopping.MODEL, "check a price", PriceAnswer, 1)
    tool = api.requests[0]["tools"][1]
    assert tool["strict"] is True and tool["input_schema"]["$defs"]["PriceSeen"] == item
    assert result.answer.prices[0].code is None


def test_the_estimate_still_covers_a_price_check_that_may_give_codes():
    from anthropic.lib._parse._transform import transform_schema
    finds = [{"url": "https://shop.example/" + "p" * (shop.URL_MAX - 21), "name": "n" * shop.NAME_MAX,
              "shop": "s" * shop.SHOP_MAX, "price": shop.PRICE_MAX, "currency": "USD"}] * shop.PRICE_FINDS_MAX
    asked = shopping.price_prompt(finds) + shopping.SYSTEM + json.dumps(transform_schema(PriceAnswer))
    # 2 characters to a token: the longest price check asks in a tenth of what the estimate allows for the pages read
    assert len(asked) / 2 <= spend.SHOP_INPUT_TOKENS / 10
    # the answer with every price and a code, for pages with addresses of a usual length, in the longest answer allowed
    answer = PriceAnswer(prices=[PriceSeen(url="https://shop.example/" + "p" * 200, price=shop.PRICE_MAX, currency="USD",
                                           available=True, code="C" * 30, code_percent=12.5)] * shop.PRICE_FINDS_MAX)
    assert len(answer.model_dump_json()) / 2 <= shopping.MAX_TOKENS / 2


def test_migration_0046_leaves_every_find_without_a_code(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 46:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    wid = wish_row(conn)
    find_row(conn, wid, [100.0, 80.0])
    conn.close()
    assert db.migrate(path, tmp_path / "backups")["applied"][0] == 46   # and any later ones
    conn = db.connect(path)
    try:
        find, = shop.list_finds(conn, wid)
        assert find["code"] is None and find["with_code"] is None
        assert find["drop"] == {"from": 100.0, "to": 80.0, "currency": "USD", "percent": 20}
        assert [(h["with_code"], h["code"]) for h in find["history"]] == [(None, None), (None, None)]
        assert [n["to"] for n in shop.news(conn)] == [80.0]
    finally:
        conn.close()


# ------------------------------------------------------------------ a find worn with the owner's clothes
def test_a_judged_find_comes_back_with_the_outfits_made_with_it(client, services, cfg):
    # the demo closet's items as plain rows (read from its file, not built into a database): the engine needs a closet
    # with enough in it, and the route reads whatever the shopper's closet gives
    from .test_wouldwork import demo as demo_items
    services.shopper.closet = lambda profile: demo_items()
    wid = wish(client)
    coat = shop.clean_find(product(name="Tan gabardine trench coat"))
    conn = db.connect(cfg.db_path("main"))
    try:
        shop.save_finds(conn, wid, [coat], [{"verdict": "fills_gap", "verdict_words": "Fills a gap", "reasons": [],
                                             "outfits": 3, "checked_at": db.now()}])
        link = shop.keep_link(conn, wid, "https://shop.example/not-described-yet")
    finally:
        conn.close()
    find = next(f for f in client.get(f"/api/wishlist/{wid}/finds").json()["finds"] if f["piece"])
    assert find["outfits"] == 3

    r = client.get(f"/api/wishlist/{wid}/finds/{find['id']}/outfits")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["piece"] == find["piece"] and 1 <= len(body["outfits"]) <= 3
    assert all(o["day"]["words"] and "~candidate" in o["pieces"].values() for o in body["outfits"])

    assert client.get(f"/api/wishlist/{wid}/finds/nope/outfits").status_code == 404
    assert client.get(f"/api/wishlist/nope/finds/{find['id']}/outfits").status_code == 404
    r = client.get(f"/api/wishlist/{wid}/finds/{link}/outfits")
    assert r.status_code == 409 and r.json()["detail"] == shop.NOT_DESCRIBED


def test_a_striped_finds_outfits_are_drawn_with_its_stripes(client, services, cfg):
    """A find carries its pattern word into the outfits made with it, and the figure draws it striped (a plain,
    typical stripe from the words: `drawing.wordpattern`); the same find described as plain is drawn in one colour."""
    from .conftest import upload
    from .test_wouldwork import demo as demo_items
    services.shopper.closet = lambda profile: demo_items()
    wid = wish(client, name="A striped shirt")
    striped = shop.clean_find(product(name="Striped poplin shirt", category="shirt", color="light_blue",
                                      pattern="stripe", formality="casual", rain_proof=False, url="https://shop.example/s"))
    conn = db.connect(cfg.db_path("main"))
    try:
        shop.save_finds(conn, wid, [striped], [{"verdict": "adds", "verdict_words": "Adds something", "reasons": [],
                                                "outfits": 3, "checked_at": db.now()}])
    finally:
        conn.close()
    find = client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]
    body = client.get(f"/api/wishlist/{wid}/finds/{find['id']}/outfits").json()
    assert body["piece"]["pattern"] == "stripe"
    place = next(p for p, v in body["outfits"][0]["pieces"].items() if v == "~candidate")
    trousers = upload(client, key="t").json()
    client.patch(f"/api/items/{trousers['id']}", json={"category": "trousers", "color": "grey"})

    def drawn(piece) -> str:
        r = client.post("/api/outfits/figure", json={place: "~candidate", "bottom": trousers["id"], "piece": piece})
        assert r.status_code == 200, r.text
        return r.text

    assert "<image href=\"data:image/jpeg" in drawn(body["piece"])   # the shirt's stripes, as a tile
    assert "<image" not in drawn({**body["piece"], "pattern": "solid"})
