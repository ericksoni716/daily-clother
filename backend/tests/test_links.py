"""A link read, described and drawn properly, and a search that finds the right things (the owner's report of 26
November; closet/shop.py, tagger/shopping.py, closet/wouldwork.py, closet/illustrations.py, migration 0055).

1. A page that could not be read is not "sold out": the last price stands and the check is noted (`unread_at`).
2. A link Nines cannot read is read by Claude whole; a link whose name is kept is described even when its page turns
   Nines away.
3. A link that still has no name asks the owner for one.
4. Claude says what kind of garment a product is, and the drawing and the "Claude saw" line follow.
5. A search finds menswear, and not what is already watched.

Claude and the shops are never reached: the stand-ins of test_shop.py are used.
"""
# ruff: noqa: F811  (the fixtures of test_shop.py, imported by name)
import json
from datetime import timedelta
from types import SimpleNamespace

from closet import db, shop, spend
from closet.tagger import correcting, shopping
from closet.tagger.shopping import PriceSeen
from closet.tagger.tagging import TaggingError, Unreachable

from .test_shop import (  # noqa: F401  (fixtures used by name)
    PLAIN,
    SHIRT,
    add_link,
    at,
    client,
    clock,
    closet,
    described,
    fake_shop,
    find_row,
    link_read,
    pages,
    services,
    settle,
    shirt_page,
    usable,
    wish_row,
)


# ------------------------------------------------------------------ 1. a page that could not be read
def test_migration_0055_leaves_every_find_read_and_not_asked_again(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 55:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    wid = wish_row(conn)
    find_row(conn, wid, [100.0, 80.0])
    conn.close()
    assert db.migrate(path, tmp_path / "backups")["applied"][0] == 55   # and any later ones
    conn = db.connect(path)
    try:
        find, = shop.list_finds(conn, wid)
        assert find["unread_at"] is None
        assert tuple(conn.execute("SELECT read_asked, kind_asked_at FROM finds").fetchone()) == (None, None)
    finally:
        conn.close()


def test_a_price_check_answer_says_whether_the_page_was_read_and_sold_out_only_when_the_page_says_so():
    assert PriceSeen(url="https://shop.example/p", price=None, currency="USD", available=True).read is True
    prompt = shopping.price_prompt([{"url": "https://shop.example/p", "name": "A shirt", "shop": "Example Shop",
                                     "price": 68.0, "currency": "USD"}])
    assert "could not open the page" in prompt and "read false" in prompt
    assert "only when the page itself says" in prompt and "When you cannot tell, give true" in prompt


def priced(conn, wid: str) -> str:
    """A find seen at 100 then 80 USD, on 1 and 2 November."""
    return find_row(conn, wid, [100.0, 80.0])


def state(conn, fid: str) -> tuple:
    r = conn.execute("SELECT price, currency, available, unread_at FROM finds WHERE id = ?", (fid,)).fetchone()
    n = conn.execute("SELECT COUNT(*) FROM find_prices WHERE find_id = ?", (fid,)).fetchone()[0]
    return r["price"], r["currency"], r["available"], r["unread_at"], n


def test_an_answer_that_could_not_read_the_page_changes_nothing_but_says_so(closet):
    wid = wish_row(closet)
    fid = priced(closet, wid)
    find = {"id": fid, "url": f"https://shop.example/{fid}", "currency": "USD"}
    for seen in ({"url": find["url"], "price": None, "currency": "USD", "available": False, "read": False},
                 {"url": find["url"], "price": 50.0, "currency": "EUR", "available": False, "read": False},
                 {"url": find["url"], "price": None, "currency": "USD", "available": True}):   # no price for a priced one
        assert shop.save_prices(closet, wid, [find], [seen]) == 0
        price, currency, available, unread_at, points = state(closet, fid)
        assert (price, currency, available, points) == (80.0, "USD", 1, 2) and unread_at
    # a page read that says sold out without a price: sold out at the last price
    assert shop.save_prices(closet, wid, [find], [{"url": find["url"], "price": None, "currency": "USD",
                                                   "available": False}]) == 1
    assert state(closet, fid) == (80.0, "USD", 0, None, 3)
    # the next check that reads a price clears it
    assert shop.save_prices(closet, wid, [find], [{"url": find["url"], "price": 75.0, "currency": "USD",
                                                   "available": True}]) == 1
    assert state(closet, fid) == (75.0, "USD", 1, None, 4)


def test_a_find_that_never_had_a_price_keeps_no_price(closet):
    wid = wish_row(closet)
    closet.execute("INSERT INTO finds (id, wish_id, name, shop, url, price, currency, piece, found_at, updated_at, link) "
                   "VALUES ('f', ?, 'A coat', 'Example Shop', 'https://shop.example/f', NULL, 'USD', '{}', ?, ?, 0)",
                   (wid, at(1), at(1)))
    find = {"id": "f", "url": "https://shop.example/f", "currency": "USD"}
    shop.save_prices(closet, wid, [find], [{"url": find["url"], "price": None, "currency": "USD", "available": True,
                                            "read": False}])
    price, _, available, unread_at, points = state(closet, "f")
    assert price is None and available == 1 and unread_at and points == 0   # read nothing: nothing kept
    shop.save_prices(closet, wid, [find], [{"url": find["url"], "price": None, "currency": "USD", "available": True}])
    assert state(closet, "f")[0] is None and state(closet, "f")[4] == 1   # read, no price shown: "no price", as before


def test_drop_came_down_news_and_the_wishlists_cost_ignore_a_check_that_read_nothing(closet):
    wid = wish_row(closet, price_max=90)
    fid = priced(closet, wid)
    find = {"id": fid, "url": f"https://shop.example/{fid}", "currency": "USD"}
    before = shop.list_finds(closet, wid)[0]
    news_before = shop.news(closet)
    cost_before = shop.wish_prices(closet)
    shop.save_prices(closet, wid, [find], [{"url": find["url"], "price": None, "currency": "USD", "available": False,
                                            "read": False}])
    after = shop.list_finds(closet, wid)[0]
    assert after["drop"] == before["drop"] == {"from": 100.0, "to": 80.0, "currency": "USD", "percent": 20}
    assert after["history"] == before["history"] and after["available"] is True and after["price"] == 80.0
    assert shop.came_down(shop._history(closet, fid))["at"] == at(2)
    assert shop.news(closet) == news_before and [n["to"] for n in news_before] == [80.0]
    assert shop.wish_prices(closet) == cost_before == [{"wish_id": wid, "prices": [{"price": 80.0, "currency": "USD"}]}]


def test_nines_reading_sets_and_clears_unread_at_and_removing_a_find_keeps_it(closet):
    wid = wish_row(closet)
    fid = find_row(closet, wid, [68.0], link=True)
    shop.save_read(closet, wid, fid, None)   # the page could not be opened
    price, _, available, unread_at, points = state(closet, fid)
    assert (price, available, points) == (68.0, 1, 1) and unread_at
    removed = shop.remove_find(closet, wid, fid)
    shop.restore_find(closet, wid, removed)
    assert state(closet, fid)[3] == unread_at   # Undo puts it back as it was
    read = {"name": None, "shop": None, "image_url": None, "price": 60.0, "currency": "USD", "available": True,
            "code": None}
    assert shop.save_read(closet, wid, fid, read) is True
    assert state(closet, fid)[3] is None


def test_a_small_shop_that_turns_nines_away_keeps_its_last_price_and_is_not_sold_out(client, fake_shop, pages):
    """The owner's report: the second read of a small shop's page is turned away, Claude cannot open it either and
    answered no price and not available; the card said "Price not shown · Sold out"."""
    wid = add_link(client, SHIRT)
    del pages.pages[SHIRT]   # turned away from now on
    fake_shop.prices_seen = [PriceSeen(url=SHIRT, price=None, currency="USD", available=False, read=False)]
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    find, = body["finds"]
    assert find["price"] == 68.0 and find["available"] is True and find["unread_at"]
    assert [h["price"] for h in find["history"]] == [68.0]
    assert body["run"]["message"] == shop.kept_last(1)
    assert body["run"]["message"] == "Nines could not read 1 of the pages today. Its last price is shown."
    listed, = client.get("/api/wishlist").json()["wishes"]
    assert listed["link"]["price"] == 68.0 and listed["link"]["available"] is True

    # Claude out of reach as well: said once, with why
    fake_shop.prices_seen = None
    pages.pages[SHIRT] = shirt_page("60.00")
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["price"] == 60.0 and find["unread_at"] is None


def test_the_sentence_says_unread_pages_once(client, fake_shop, pages, usable):
    wid = add_link(client, SHIRT)
    del pages.pages[SHIRT]
    usable["routes"] = ()   # Claude cannot be asked: the page's last price stands
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    body = settle(client, wid)
    assert body["finds"][0]["price"] == 68.0 and body["finds"][0]["unread_at"]
    assert body["run"]["message"] == f"{shop.kept_last(1)} {shop.NO_ROUTE}"
    assert shop.SOME_UNREAD not in body["run"]["message"]
    assert shop.kept_last(2) == "Nines could not read 2 of the pages today. Their last prices are shown."


# ------------------------------------------------------------------ 2. a link Nines cannot read, read by Claude whole
GONE = "https://shop.example/p/wool-chore-coat"   # a page that turns Nines away (no page stands in for it)


def coat_read(**changes):
    """The big shop's page as Claude reads it whole: a grey wool chore coat."""
    return link_read(**{**dict(read=True, name="Felted wool chore coat", shop="Example Shop",
                               image_url="https://shop.example/img/coat.jpg", price=268.0, currency="USD",
                               available=True, clothing=True, category="coat", color="grey", formality="casual",
                               season="cool", pattern="solid", weight_class="heavyweight", material="wool"),
                        **changes})


def test_a_link_nines_cannot_read_is_read_by_claude_whole_in_one_answer(client, fake_shop, pages):
    fake_shop.whole = coat_read()
    wid = add_link(client, GONE)
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    find, = body["finds"]
    assert fake_shop.calls == [("read", GONE, ("plan",))]   # one question: no price check, no description apart
    assert fake_shop.described == []
    assert (find["name"], find["shop"], find["image_url"]) == ("Felted wool chore coat", "Example Shop",
                                                               "https://shop.example/img/coat.jpg")
    assert find["price"] == 268.0 and find["read_by"] == "claude" and [h["price"] for h in find["history"]] == [268.0]
    assert find["piece"]["category"] == "coat" and find["piece"]["name"] == "Felted wool chore coat"
    assert find["verdict"] and find["not_judged"] is None and find["unread_at"] is None
    assert body["run"]["message"] is None and body["run"]["added"] == 1
    listed, = client.get("/api/wishlist").json()["wishes"]
    assert listed["name"] == "Felted wool chore coat"
    # nothing about the wish or the closet goes with the question
    prompt = shopping.read_prompt({"url": GONE})
    assert GONE in prompt and "read false" in prompt and "Never guess from the address alone" in prompt


def test_a_value_from_a_whole_read_that_does_not_fit_is_dropped_alone(client, fake_shop):
    fake_shop.whole = coat_read(image_url="javascript:alert(1)", price=-3.0, shop="", color="heather-ish",
                                code="TEST40", code_percent=40.0)
    wid = add_link(client, GONE)
    find, = client.get(f"/api/wishlist/{wid}/finds").json()["finds"]
    assert find["name"] == "Felted wool chore coat" and find["shop"] == "shop.example"   # its address, as before
    assert find["image_url"] is None and find["price"] is None and find["code"]["code"] == "TEST40"
    assert find["piece"] is None and find["not_judged"] == "unclear"   # a colour outside the closet's words
    assert client.get("/api/wishlist").json()["wishes"][0]["name"] == "Felted wool chore coat"


def test_a_page_claude_cannot_read_either_waits_for_a_name_and_is_not_asked_every_day(client, services, fake_shop,
                                                                                     clock):
    wid = add_link(client, GONE)   # Claude could not open it (the stand-in's default)
    body = client.get(f"/api/wishlist/{wid}/finds").json()
    find, = body["finds"]
    assert find["name"] == "shop.example" and find["not_judged"] == "no_name" and find["price"] is None
    assert body["run"]["message"] == shop.NO_PRICE_AT_ALL and fake_shop.calls == [("read", GONE, ("plan",))]
    # the daily round does not ask the same again
    clock[0] += timedelta(days=1, seconds=1)
    assert services.shopper.tick() == 1 and len(fake_shop.calls) == 1
    # a Check now by the owner does; a name that is only the address counts as none
    fake_shop.whole = coat_read(name="shop.example")
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    assert settle(client, wid)["finds"][0]["not_judged"] == "no_name" and len(fake_shop.calls) == 2
    fake_shop.whole = coat_read()
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    assert find["name"] == "Felted wool chore coat" and find["verdict"] and len(fake_shop.calls) == 3
    # read once it has a name: later checks ask for its price as any page's
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    settle(client, wid)
    assert fake_shop.calls[-1][0] == "prices"


def test_claude_out_of_reach_while_reading_whole_leaves_the_link_for_later(client, fake_shop):
    for error in (Unreachable("no connection"), TaggingError("no valid answer")):
        fake_shop.whole = error
        wid = add_link(client, GONE)
        assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["not_judged"] == "no_name"
        fake_shop.whole = coat_read()
        assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
        assert settle(client, wid)["finds"][0]["name"] == "Felted wool chore coat"
        client.delete(f"/api/wishlist/{wid}")


def test_the_demo_closet_never_reads_a_link_through_claude(client, fake_shop):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    wid = add_link(client, GONE)
    assert client.get(f"/api/wishlist/{wid}/finds").json()["finds"][0]["not_judged"] == "no_name"
    assert fake_shop.calls == []


def test_a_link_whose_name_is_kept_is_described_when_nines_is_turned_away(client, fake_shop, pages, usable):
    """The owner's small shop: the name and picture were read once, then every read is turned away; the link was
    never described ("Nines checks it against your closet once Claude can describe it")."""
    usable["routes"] = ()
    wid = add_link(client, SHIRT)   # read by Nines: named, not described
    del pages.pages[SHIRT]
    usable["routes"] = ("plan",)
    fake_shop.description = described(category="shirt", color="green", pattern="plaid")
    assert client.post(f"/api/wishlist/{wid}/prices").status_code == 202
    find, = settle(client, wid)["finds"]
    (asked, _), = fake_shop.described
    assert asked == {"name": "Linen camp-collar shirt", "shop": "Example Shop", "brand": None, "color": None,
                     "material": None, "description": None}
    assert find["piece"]["category"] == "shirt" and find["verdict"] and find["not_judged"] is None
    assert find["price"] == 54.4 and find["read_by"] == "claude"   # Claude read the price, as before
    # asked once: the same question is not asked again
    fake_shop.description = described(clothing=False)
    other = add_link(client, PLAIN)
    pages.pages.pop(PLAIN)
    assert client.post(f"/api/wishlist/{other}/prices").status_code == 202
    assert settle(client, other)["finds"][0]["not_judged"] == "unclear"
    asked = len(fake_shop.described)
    assert client.post(f"/api/wishlist/{other}/prices").status_code == 202
    settle(client, other)
    assert len(fake_shop.described) == asked


def test_reading_a_link_whole_is_asked_with_the_web_tools_and_counted_as_a_price_check(services, cfg, monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["stdin"].read().decode("utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"structured_output": coat_read().model_dump(), "usage": {"input_tokens": 10, "output_tokens": 5}}))
    monkeypatch.setattr(correcting.subprocess, "run", run)
    monkeypatch.setattr(correcting.claude_cli, "find_claude", lambda: "claude")
    answer = shop.ClaudeAsker(cfg, services.state).read({"url": GONE}, ("plan",))
    assert answer.read is True and answer.name == "Felted wool chore coat"
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == shopping.PLAN_TOOLS and GONE in seen["input"]
    conn = db.connect(cfg.db_path("main"))
    try:
        assert conn.execute("SELECT purpose FROM claude_calls").fetchone()[0] == spend.PURPOSE_PRICES
    finally:
        conn.close()
