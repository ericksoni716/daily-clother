"""On sale now: what a sale look is told and where it starts, the page check, choosing, the weekly round with the clock
stood in, the limit and the demo closet, the daily re-read, and Shops you like (closet/picks.py, closet/shops.py,
tagger/shopping.py's `sale`, migration 0050).

Claude is never called (`PickShop` stands in, or `FakeSearchApi` for the API route) and no shop is reached: the pages
are made-up HTML read by the real `productpage` reader through stand-ins for the web (`SalePages`). No real shop,
brand or product.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, picks, productpage, shop, shops, sizes, spend
from closet.items import ItemError
from closet.tagger import shopping
from closet.tagger.shopping import SaleFound

from .conftest import fake_cutter
from .test_picks import PickShop, look, own_line
from .test_shop import FakeSearchApi


def sale_product(**changes) -> SaleFound:
    """A product as a sale look's Claude would give it: a tan coat at $140, $200 before."""
    base = dict(name="Tan wool overcoat", shop="Example Shop", url="https://shop.example/s/coat",
                image_url="https://shop.example/s/coat.jpg", price=140.0, currency="USD", category="coat", color="tan",
                formality="smart_casual", season="cool", pattern="solid", weight_class="midweight", rain_proof=False,
                material="wool", price_before=200.0, size_in_stock=None)
    return SaleFound(**{**base, **changes})


def sale_page(price, before=None, available="InStock", sizes=None, brand=None, og=False) -> str:
    """A made-up product page: its price, its price before as a strikethrough price (or as OpenGraph's original price
    with `og`), and its sizes as a product group's variants."""
    offer = {"@type": "Offer", "price": price, "priceCurrency": "USD", "availability": f"https://schema.org/{available}"}
    if before is not None and not og:
        offer["priceSpecification"] = [{"@type": "UnitPriceSpecification", "price": before,
                                        "priceType": "https://schema.org/StrikethroughPrice"}]
    data = {"@context": "https://schema.org", "@type": "ProductGroup" if sizes else "Product", "name": "A product",
            "offers": offer}
    if brand:
        data["brand"] = {"@type": "Brand", "name": brand}
    if sizes:
        data["hasVariant"] = [{"@type": "Product", "size": s, "offers": {**offer, "availability":
                               f"https://schema.org/{'InStock' if ok else 'OutOfStock'}"}} for s, ok in sizes.items()]
    head = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    if og and before is not None:
        head += f'<meta property="product:original_price:amount" content="{before}">'
    return f"<html><head>{head}</head><body></body></html>"


class SalePages:
    """The web the sale pages are read from: made-up pages by address. shop.example is on the internet,
    inside.example on the home network."""

    def __init__(self):
        self.pages: dict[str, str] = {}
        self.names = {"shop.example": ["1.2.3.4"], "inside.example": ["192.168.1.9"]}
        self.asked: list[str] = []
        self.reader = productpage.Reader(resolve=self.resolve, get=self.get)

    def resolve(self, host):
        if host not in self.names:
            raise productpage.Unreadable(productpage.NO_SUCH_PLACE)
        return self.names[host]

    def get(self, target, seconds):
        self.asked.append(target.url)
        text = self.pages.get(target.url)
        if text is None:
            return productpage.Answer(404, {"content-type": "text/html"}, b"")
        return productpage.Answer(200, {"content-type": "text/html; charset=utf-8"}, text.encode())


COAT, CREW, FLANNEL, BOOTS, SHIRT, GONE = (f"https://shop.example/s/{n}" for n in
                                           ("coat", "crew", "flannel", "boots", "shirt", "gone"))


@pytest.fixture
def fake_shop():
    s = PickShop()
    s.sale_finds = [
        sale_product(),                                        # 30% off on the page's own data: kept
        sale_product(name="Cream merino crewneck", url=CREW, category="sweater", color="cream", price=99.0,
                     price_before=120.0),                      # only Claude saw $120: kept, marked
        sale_product(name="Grey flannel trousers", url=FLANNEL, category="trousers", color="grey", price=100.0,
                     price_before=110.0),                      # 9% off: not a sale worth a pick
        sale_product(name="Brown suede boots", url=BOOTS, category="boots", color="brown"),   # sold out
        sale_product(name="Blue oxford shirt", url=SHIRT, category="shirt", color="blue", price=60.0,
                     price_before=80.0),                       # the page says $80: not lower than before
        sale_product(name="Olive chore jacket", url=GONE, category="jacket", color="olive"),  # page not found
        sale_product(name="Not a link", url="javascript:alert(1)")]
    return s


@pytest.fixture
def pages():
    p = SalePages()
    p.pages.update({COAT: sale_page(140, 200), CREW: sale_page(90), FLANNEL: sale_page(100, 110),
                    BOOTS: sale_page(80, 160, available="OutOfStock"), SHIRT: sale_page(80)})
    return p


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
    return TestClient(app_module.create_app(services))


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 11, 13, 9, 0, tzinfo=UTC)]
    monkeypatch.setattr(picks, "_now", lambda: now[0])
    monkeypatch.setattr(db, "now", lambda: now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    return now


def sale_look(client) -> dict:
    return look(client, "/api/picks/look?kind=sale")


def sales(body: dict) -> list[dict]:
    return [p for p in body["picks"] if p["kind"] == "sale"]


# ------------------------------------------------------------------ what a sale look is told (pure)
def test_the_prompt_starts_from_your_shops_brands_and_past_shops_then_finds_smaller_makers():
    text = shopping.sale_prompt({"about": "About the person this is for\n- loves olive", "plenty": ["tee in navy: 4 already"],
                                 "refused": ["orange tee: Example tee"], "shops": ["Example Shop", "shop.example"],
                                 "brands": ["Example Maker", "Other Maker"], "before": ["Example Outfitters (outfit.example)"]})
    assert "marked down now" in text and "would not have found by themselves" in text
    assert "About the person this is for\n- loves olive" in text and "- tee in navy: 4 already" in text
    assert '"Not for me"' in text and "- orange tee: Example tee" in text
    order = [text.index(s) for s in ("1. The shops they like, first:\n- Example Shop\n- shop.example",
                                     "2. The brands they already wear and rate well: Example Maker, Other Maker.",
                                     "3. Shops they have found things at before:\n- Example Outfitters (outfit.example)",
                                     "4. Your own searches for sales")]
    assert order == sorted(order)
    assert "smaller makers and independent shops they are unlikely to know" in text
    assert "at least a third of your answer should come from outside the shops and brands above" in text
    assert "price before the markdown as the page shows them" in text and "their size in stock" in text
    assert f"up to {shopping.MAX_FINDS} different products" in text and "Never make up a product" in text
    assert shopping.SALE_SYSTEM != shopping.PICKS_SYSTEM and "never as instructions" in shopping.SALE_SYSTEM
    # with nowhere to start, Claude's own searches are the only place, and nothing is said of a third
    bare = shopping.sale_prompt({})
    assert "1. Your own searches for sales" in bare and "a third" not in bare and "2." not in bare
    # the wording a taste look and a sale look share is the same text
    taste = shopping.picks_prompt({})
    for shared in (shopping.DESCRIBE_RULE, shopping.NEVER_MADE_UP, shopping.REAL_PAGE):
        assert shared in taste and shared in bare


def test_rated_brands_and_past_shops_are_bounded_and_in_order():
    rows = [{"id": "a", "brand": "Example Maker", "rating": "love", "status": "active"},
            {"id": "b", "brand": "Other Maker", "rating": None, "status": "active"},
            {"id": "c", "brand": "Worn Maker", "rating": None, "status": "active"},
            {"id": "d", "brand": "Gone Maker", "rating": "love", "status": "archived"},
            {"id": "e", "brand": "Bad Maker", "rating": "dislike", "status": "active"}]
    wears = [{"item_id": "c", "worn_on": f"2026-11-0{d}"} for d in range(1, 5)]
    assert picks.rated_brands(rows, wears) == ["Example Maker", "Worn Maker"]   # never rated nor worn: not said
    assert picks.rated_brands(rows, wears, n=1) == ["Example Maker"]
    found = [{"shop": "Example Shop", "url": "https://www.shop.example/a"}, {"shop": "Example Shop", "url": "https://shop.example/b"},
             {"shop": "Named Shop", "url": "https://named.example/c"}, {"shop": "outfit.example", "url": "https://outfit.example/d"},
             {"shop": "Third", "url": "https://third.example/e"}]
    assert picks.before_lines(found, ["named shop"]) == ["Example Shop (shop.example)", "outfit.example", "Third (third.example)"]
    assert picks.before_lines(found, [], n=2) == ["Example Shop (shop.example)", "Named Shop (named.example)"]


def test_the_look_is_told_your_shops_brands_and_where_you_found_things(client, fake_shop, cfg):
    own_line(client)
    for name in ("Example Shop", "https://www.small.example/sale?x=1"):
        assert client.post("/api/shops", json={"name": name}).status_code == 200
    conn = db.connect(cfg.db_path("main"))
    conn.execute("INSERT INTO wishes (id, name, look_for, note, created_at, updated_at) VALUES ('w', 'A coat', '{}', '', "
                 "'2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')")
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, currency, piece, verdict, found_at, updated_at) VALUES "
                 "('f', 'w', 'A coat', 'Example Outfitters', 'https://outfit.example/coat', 'USD', 'null', 'null', "
                 "'2026-11-02T00:00:00Z', '2026-11-02T00:00:00Z')")
    conn.close()
    sale_look(client)
    told = next(c[1] for c in fake_shop.calls if c[0] == "sale")
    assert told["shops"] == ["Example Shop", "small.example"]
    assert told["before"] == ["Example Outfitters (outfit.example)"]
    assert "brands" in told and "about" in told and "plenty" in told and "refused" in told


# ------------------------------------------------------------------ the page check (pure)
def read(price=140.0, before=None, available=True, sizes=None, currency="USD", image=None) -> dict:
    return {"price": price, "price_before": before, "available": available, "sizes": sizes or {}, "currency": currency,
            "image_url": image, "brand": None}


def found(**changes) -> dict:
    return {**shop.clean_sale(sale_product()), **changes}


def test_a_sale_is_kept_only_when_its_page_shows_a_real_markdown():
    kept = picks.check_sale(found(price=120.0), read(140, 200), None)   # the page's price, not Claude's
    assert (kept["price"], kept["price_before"], kept["before_by"]) == (140.0, 200.0, "page")
    kept = picks.check_sale(found(price_before=200.0), read(150, None), None)   # only Claude saw a price before
    assert (kept["price_before"], kept["before_by"]) == (200.0, "claude")
    assert picks.check_sale(found(), None, None) is None                       # the page could not be read
    assert picks.check_sale(found(), read(140, 200, available=False), None) is None   # sold out
    assert picks.check_sale(found(), read(None), None) is None                 # no price on the page
    assert picks.check_sale(found(price_before=140.0), read(140), None) is None   # not below the price before
    assert picks.check_sale(found(price_before=None), read(140), None) is None    # nobody read a price before
    assert picks.check_sale(found(price_before=200.0), read(140, currency="EUR"), None) is None   # not compared
    # 15% off is a sale; a little less is not
    assert picks.check_sale(found(), read(85, 100), None) is not None
    assert picks.check_sale(found(), read(85.01, 100), None) is None
    assert picks.SALE_MIN == 0.15


def test_your_size_in_stock_is_the_pages_word_first():
    assert picks.check_sale(found(), read(140, 200, sizes={"M": True, "L": False}), "m")["in_stock"] is True
    assert picks.check_sale(found(), read(140, 200, sizes={"M": False, "L": True}), "M") is None   # your size sold out
    # the page lists no size of yours: Claude's word, if it gave one
    assert picks.check_sale(found(size_in_stock=True), read(140, 200, sizes={"S": True}), "M")["in_stock"] is True
    assert picks.check_sale(found(size_in_stock=False), read(140, 200), "M") is None
    assert picks.check_sale(found(), read(140, 200), "M")["in_stock"] is None
    saved = {"jackets": {"size": "M", "brands": [{"brand": "Example Maker", "size": "L"}]}}
    assert picks.size_for(saved, "coat") == "M" and picks.size_for(saved, "coat", "example maker") == "L"
    assert picks.size_for(saved, "scarf") is None and picks.size_for({}, "coat") is None


def test_claudes_extra_values_are_cleaned():
    f = shop.clean_sale(sale_product(price_before=-5, size_in_stock=None))
    assert f["price_before"] is None and f["size_in_stock"] is None
    assert shop.clean_sale(sale_product(url="javascript:alert(1)")) is None


# ------------------------------------------------------------------ a look
def test_a_sale_look_keeps_only_what_its_page_shows_marked_down(client, fake_shop, pages):
    own_line(client)
    body = sale_look(client)
    kept = sales(body)
    assert [p["url"] for p in kept] == [COAT, CREW] and body["run"]["kind"] == "sale" and body["run"]["added"] == 2
    coat, crew = kept
    assert (coat["price"], coat["price_before"], coat["before_by"]) == (140.0, 200.0, "page")
    assert (crew["price"], crew["price_before"], crew["before_by"]) == (90.0, 120.0, "claude")   # the page's price
    assert all(p["kind"] == "taste" for p in body["picks"] if p not in kept) and len(body["picks"]) == 2
    assert body["views"]["sale"]["looked"] is True and body["views"]["taste"]["looked"] is False
    # each page read through the reader a link goes through; the address that is not a web page never asked
    assert set(pages.asked) == {COAT, CREW, FLANNEL, BOOTS, SHIRT, GONE}
    assert [c[0] for c in fake_shop.calls] == ["sale"]


def test_a_page_claude_gave_goes_through_the_link_checks(client, fake_shop, pages):
    own_line(client)
    fake_shop.sale_finds = [sale_product(url="https://inside.example/s/coat"), sale_product(url="http://shop.example/s/coat"),
                            sale_product(url=COAT)]
    assert [p["url"] for p in sales(sale_look(client))] == [COAT]
    assert pages.asked == [COAT]   # the home network and plain http were never fetched


def test_the_pages_read_are_bounded_in_number_and_time(client, fake_shop, pages, monkeypatch):
    own_line(client)
    monkeypatch.setattr(picks, "SALE_READS", 2)
    sale_look(client)
    assert pages.asked == [COAT, CREW]
    fake_shop.sale_finds = [sale_product(url=f"https://shop.example/s/more-{i}") for i in range(3)]
    monkeypatch.setattr(picks, "SALE_READ_SECONDS", -1.0)
    pages.asked.clear()
    assert sale_look(client)["run"]["added"] == 0 and pages.asked == []


def test_nothing_on_sale_says_so_and_a_page_is_never_shown_twice(client, fake_shop):
    own_line(client)
    sale_look(client)
    body = sale_look(client)   # the same answer again: both pages shown before
    assert body["run"]["added"] == 0 and body["run"]["message"] == picks.SALE_NOTHING
    assert len(sales(body)) == 2


def test_a_sale_look_and_a_taste_look_never_offer_the_same_page(client, fake_shop, pages):
    own_line(client)
    fake_shop.pick_finds = [fake_shop.pick_finds[0]]
    look(client)
    fake_shop.sale_finds = [sale_product(url=fake_shop.pick_finds[0].url)]
    pages.pages[fake_shop.pick_finds[0].url] = sale_page(140, 200)
    assert sale_look(client)["run"]["added"] == 0


def test_the_demo_closet_the_limit_and_too_little_to_go_on(client, fake_shop, usable):
    assert client.post("/api/picks/look?kind=sale").status_code == 409   # nothing to go on yet
    own_line(client)
    usable["routes"] = ()
    r = client.post("/api/picks/look?kind=sale")
    assert r.status_code == 409 and r.json()["detail"] == shop.NO_ROUTE
    usable["routes"] = ("plan",)
    assert client.post("/api/picks/look?kind=nope").status_code == 422
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    r = client.post("/api/picks/look?kind=sale")
    assert r.status_code == 409 and r.json()["detail"] == picks.DEMO
    assert fake_shop.calls == []


def test_a_sale_look_through_the_api_key_is_recorded_as_its_own_purpose(cfg, pages):
    api = FakeSearchApi([{"finds": [sale_product().model_dump()], "note": ""}])
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=lambda images, routes: None,
                                   routes=lambda: ("api",), api_client=api, page_reader=pages.reader)
    try:
        c = TestClient(app_module.create_app(sv))
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.10})
        own_line(c)
        assert sale_look(c)["run"]["added"] == 1
        assert api.requests[0]["messages"][0]["content"].startswith(shopping.SALE_SYSTEM)
        conn = db.connect(cfg.db_path("main"))
        assert conn.execute("SELECT purpose FROM claude_calls").fetchone()[0] == spend.PURPOSE_SALE == "shop_sale"
        conn.close()
    finally:
        sv.stop()


# ------------------------------------------------------------------ saving a sale
def test_a_saved_sale_keeps_its_price_before_so_the_wish_shows_the_drop(client):
    own_line(client)
    coat = sales(sale_look(client))[0]
    wish_id = client.post(f"/api/picks/{coat['id']}/save").json()["wish_id"]
    find = client.get(f"/api/wishlist/{wish_id}/finds").json()["finds"][0]
    assert [h["price"] for h in find["history"]] == [200.0, 140.0]
    assert find["drop"]["from"] == 200.0 and find["drop"]["to"] == 140.0 and find["drop"]["percent"] == 30
    assert client.get("/api/wishlist/news").json()["news"] == []   # you saw the sale: it is not news to you


# ------------------------------------------------------------------ the weekly round
def test_the_weekly_round_makes_a_sale_look_too_never_on_the_same_day_as_a_taste_look(client, services, fake_shop,
                                                                                    clock, pages):
    own_line(client)
    picker = services.picker
    look(client)   # Look now on For you turns the weekly look on
    clock[0] += timedelta(days=8)
    assert picker.tick() == 1 and [c[0] for c in fake_shop.calls] == ["picks", "picks"]   # no sale before you looked
    sale_look(client)
    assert [c[0] for c in fake_shop.calls][-1] == "sale"
    fake_shop.sale_finds = [sale_product(url=COAT + "-2")]
    pages.pages[COAT + "-2"] = sale_page(140, 200)
    clock[0] += timedelta(days=7, seconds=1)   # both due again: the taste look first, the sale look a day later
    assert picker.tick() == 1 and [c[0] for c in fake_shop.calls][-1] == "picks"
    clock[0] += timedelta(hours=23)
    assert picker.tick() == 0 and len(fake_shop.calls) == 4
    clock[0] += timedelta(hours=1, seconds=1)
    assert picker.tick() == 1 and [c[0] for c in fake_shop.calls][-1] == "sale"
    assert sales(client.get("/api/picks").json())[0]["source"] == "weekly"
    # one switch covers both
    clock[0] += timedelta(days=9)
    client.put("/api/picks/weekly", json={"weekly": False})
    assert picker.tick() == 0 and len(fake_shop.calls) == 5


def test_a_weekly_sale_look_needs_the_limit_and_never_runs_in_the_demo(client, services, fake_shop, clock, usable, cfg):
    own_line(client)
    sale_look(client)
    clock[0] += timedelta(days=8)
    usable["routes"] = ()
    assert services.picker.tick() == 0 and len(fake_shop.calls) == 1
    usable["routes"] = ("plan",)
    client.post("/api/profile", json={"profile": "demo"})
    fake_shop.sale_finds = []
    assert services.picker.tick() == 1   # the owner's closet, whichever is open
    conn = db.connect(cfg.db_path("demo"))
    assert conn.execute("SELECT COUNT(*) FROM pick_looks").fetchone()[0] == 0
    conn.close()


def test_the_daily_round_reads_a_shown_sale_again_and_takes_away_one_that_ended(client, services, fake_shop, clock,
                                                                               pages):
    own_line(client)
    sale_look(client)
    calls = len(fake_shop.calls)
    pages.asked.clear()
    assert services.picker.recheck() == 0   # read when found: not again the same day
    clock[0] += timedelta(days=1, seconds=1)
    pages.pages[COAT] = sale_page(140)       # the page's own price before is gone: the sale ended
    pages.pages[CREW] = sale_page(80)        # cheaper still
    assert services.picker.recheck() == 2 and set(pages.asked) == {COAT, CREW}
    left = sales(client.get("/api/picks").json())
    assert [(p["url"], p["price"], p["price_before"]) for p in left] == [(CREW, 80.0, 120.0)]
    # a page that cannot be read twice in a row leaves the card too; a sold-out one at once
    del pages.pages[CREW]
    clock[0] += timedelta(days=1, seconds=1)
    services.picker.recheck()
    assert len(sales(client.get("/api/picks").json())) == 1
    clock[0] += timedelta(days=1, seconds=1)
    services.picker.recheck()
    assert sales(client.get("/api/picks").json()) == []
    assert len(fake_shop.calls) == calls   # Claude is never asked


def test_your_size_in_stock_is_not_said_once_the_page_no_longer_says_it(client, services, clock, pages):
    """Review 2, a suspicion tried: the coat's page listed your size in stock when the sale was found (Claude said
    nothing about sizes), so the card says "Your size is in stock". A day on the page lists no sizes any more: nobody
    says it now, so neither does the card."""
    own_line(client)
    assert client.put(f"/api/sizes/{sizes.kind_of('coat')}", json={"size": "M"}).status_code == 200
    pages.pages[COAT] = sale_page(140, 200, sizes={"M": True, "L": False})
    coat = next(p for p in sales(sale_look(client)) if p["url"] == COAT)
    assert coat["in_stock"] is True
    clock[0] += timedelta(days=1, seconds=1)
    pages.pages[COAT] = sale_page(140, 200)
    services.picker.recheck()
    coat = next(p for p in sales(client.get("/api/picks").json()) if p["url"] == COAT)
    assert coat["in_stock"] is None


def test_a_sold_out_sale_leaves_the_card_and_a_saved_one_is_left_to_its_wish(client, services, clock, pages):
    own_line(client)
    coat, crew = sales(sale_look(client))
    client.post(f"/api/picks/{coat['id']}/save")
    clock[0] += timedelta(days=1, seconds=1)
    pages.pages[CREW] = sale_page(90, available="OutOfStock")
    pages.asked.clear()
    services.picker.recheck()
    assert pages.asked == [CREW]   # the saved one's price is watched on its wish
    assert [p["url"] for p in sales(client.get("/api/picks").json())] == [COAT]


# ------------------------------------------------------------------ Shops you like
def test_shops_are_cleaned_bounded_and_kept_in_the_closet(client, cfg):
    assert client.get("/api/shops").json() == {"shops": [], "max_shops": 12, "max_name": 60}
    body = client.post("/api/shops", json={"name": "  Example\tShop  "}).json()
    assert [s["name"] for s in body["shops"]] == ["Example Shop"]
    assert client.post("/api/shops", json={"name": "example shop"}).json()["detail"] == shops.ALREADY
    assert client.post("/api/shops", json={"name": "https://www.small.example/sale/men?x=1"}).json()["shops"][1]["name"] \
        == "small.example"
    assert client.post("/api/shops", json={"name": "maker.example/collections/sale"}).json()["shops"][2]["name"] \
        == "maker.example"
    assert client.post("/api/shops", json={"name": "   "}).status_code == 422
    assert client.post("/api/shops", json={"name": "x" * 61}).json()["detail"] == shops.TOO_LONG
    for i in range(9):
        assert client.post("/api/shops", json={"name": f"Shop {i}"}).status_code == 200
    r = client.post("/api/shops", json={"name": "One too many"})
    assert r.status_code == 422 and r.json()["detail"] == shops.TOO_MANY
    first = client.get("/api/shops").json()["shops"][0]["id"]
    assert len(client.delete(f"/api/shops/{first}").json()["shops"]) == 11
    assert client.delete(f"/api/shops/{first}").status_code == 404
    assert len(client.get("/api/settings").json()["shops"]["shops"]) == 11
    assert client.get("/api/picks").json()["shops"] == 11
    # the demo closet has its own list
    client.post("/api/profile", json={"profile": "demo"})
    assert client.get("/api/shops").json()["shops"] == []


def test_a_shop_name_is_cleaned_before_it_is_kept():
    assert shops.clean("Example\x00 Shop") == "Example Shop"
    assert shops.clean("https://shop.example") == "shop.example"
    assert shops.clean("Example Shop, ") == "Example Shop"
    for bad in ("", " , ", None, 5):
        with pytest.raises(ItemError):
            shops.clean(bad)
