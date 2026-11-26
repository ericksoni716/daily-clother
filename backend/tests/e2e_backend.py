"""Starts Nines for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

Every backend the browser tests start runs from here, so none of them reaches the
weather service: Open-Meteo and Nominatim are always out of reach (the place is
New York until one is chosen, so Today would otherwise ask the real one). The
specs fake the answers they need in the browser. With CLOSET_E2E_FAKES empty
nothing else is replaced: the model and Claude are the real code.

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude.

With CLOSET_E2E_ROUTES=api the plan route cannot be used and the API route is
the real one (its spend recorded and kept under the owner's limit) talking to
`conftest.FakeApi` instead of Anthropic: each request reports 20,000 tokens in
and 12,000 out, $0.008 at the prices written down, so a $0.01 limit allows
exactly one. Corrections by sentence
are read by the same stand-in the backend tests use (or, with CLOSET_E2E_ROUTES=api, by the
real API route talking to `conftest.FakeApi`).

Searching shops for a wish is a stand-in too (`FakeShop`): after a second it "finds" a tan rain-proof coat, a
navy polo and a product with a link that is not a web address (which the app drops), and a price check sees every
price 20% lower. "You might like" is the same stand-in (`FakeShop.picks`): after a second, a trench coat, a chore jacket, a
sweater, trousers and a striped shirt with long names, on new pages at each look. "On sale now" too (`FakeShop.sale`):
after a second, five products marked down, on made-up pages of shop.example that the real page reader reads
(`SALE_PAGES`): an overcoat whose page gives its price before as a strikethrough price (and whose size Claude says is
in stock), a knit whose price before only Claude saw, boots whose page gives an OpenGraph original price, trousers
only 8% off and a sold-out shirt (both dropped), each look on new pages. With CLOSET_E2E_SEED=demo the owner's own closet starts as a copy of the demo closet, so what is
found is checked against a closet with something in it (the demo closet itself never searches).

A product's page sent as a link is never fetched from the web, with or without the other stand-ins (`ShopPages`):
shop.example is the only name that can be found, and its made-up pages are a linen shirt whose structured data gives
its price ($68.00 the first time it is read, then 20% lower each time it is read again), a shirt with a very long
name and a shirt whose banner shows a checkout code, 40% off (the same prices), a shirt whose page takes three seconds
to answer (the same prices, so a test can see a wish named after the product while the page that showed it waits for
the run to end), and a page with no price, which goes to Claude's stand-in (a price check, $80.00). Once a page has given a name, Claude's stand-in describes it after a
second: a white casual linen shirt, whatever the page.

Finding the pieces in a photo of several is a stand-in too: after a second it gives the boxes of
`conftest.GARMENT_BOXES` (a red piece left, a blue one in the middle, a green one right), whatever the photo.

Sorting a shoe's photos into views is a stand-in too (`conftest.views_answer`): after a second it says the photos
show, in the order sent, the outer side, from above, the inner side, the front, the back and the sole, with the two
sides unsure and looking different once both are there, so the page asks which photo shows the outside. With
CLOSET_E2E_ROUTES=api the real API route asks `conftest.FakeApi`, which answers the same.

Drawing a shoe from its photos runs the real steps (two drawings straight on, the judge, two turns, the judge again;
each drawing made safe, rendered and checked) with a stand-in for Claude's answers: after a second each, every drawing,
straight on or turned, is the dress shoe the owner liked (`conftest.draw_answer`), the first check of each says it is
good and the judge keeps the first with no fault named (so nothing is fixed), as if on the Claude plan, with made-up
token counts; beside the turns the side is drawn as a plain low shoe (`conftest.side_answer`), said good at its first
check, except the first side, which cannot be used (so the first drawing keeps the trace as its picture, whatever
finishes first). With CLOSET_E2E_ROUTES=api the real
API route asks `conftest.FakeApi`, which answers the same. Changing a drawing from the owner's note runs the real steps
too: whatever the note, after a second each, the dress shoe comes back with black laces (`conftest.correct_answer`),
said to go against the photos, and the first check says it is good.

With CLOSET_E2E_STAGES=1 (and the stand-ins) each step of the work on a new item takes long enough to be watched one
at a time, as the owner would see it with the real model and Claude: the cutout takes 4 seconds, describing 4 seconds
(and the answer is a plaid polo, so its pattern is measured next), and measuring the pattern 4 seconds, after which
it is not found (the drawing stays in the item's colour, and the page says so).

With CLOSET_E2E_TAG_FAILS=N the first N descriptions fail with a reason Nines does not recognise, which quotes
something shaped like a key and a file outside Nines' folder (both made up), so the page can show a failed item.

Claude choosing the day's outfits on Today is never the real Claude. With CLOSET_E2E_STYLIST empty there is no stylist
at all, so Today is the rules engine's alone, as before. With CLOSET_E2E_STYLIST=1 a stand-in (`fake_stylist`) answers
after 1.5 seconds (so the page's waiting card can be seen) with the rules' second and first outfits, in that order;
with CLOSET_E2E_STYLIST=fails it cannot be reached. A message from the owner about the outfits (the brief's `say`) is
answered after 1.5 seconds too (6.5 when the message contains "slow", so a test can send another meanwhile), from words
in the message itself: "fail" cannot be reached; "why" is a question, answered in words with the outfits left as they
are; anything else turns the outfits around (the rules' first outfit first, then their third), and "never" or "always"
also offers to keep the message for the owner's style, "fits" a note on the first outfit's top.

The style conversation (Settings, Your style, "Talk to Claude about your style") is never the real Claude either: a
stand-in (`fake_chat`) answers every message after 1.5 seconds, from made-up scripts chosen by words in the message:
"fail" cannot be reached; "warm" or "cold" is answered with a line to keep about feeling the cold; "never" or
"always" offers to keep the message itself; anything else is answered with a question back and nothing to keep. With
CLOSET_E2E_FAKES a route to Claude looks usable, so the conversation can be shown; without them the
real routes say whether one is, and on a computer with neither the conversation says Claude can't be reached.

The API key box keeps keys in a stand-in keychain (never the computer's), and the check with Anthropic is a
stand-in too: a key ending in "refused" is turned down, any other well-formed key is accepted.

No key of Nines' own window is in force (closet/gate.py): the launcher makes one and gives it to the app, and here
the app is made without it, so the browser opens 127.0.0.1 directly, as the unit tests' client does. The address check
and the page's header are the real ones. Opening Nines with its key is tested in test_gate.py and test_window.py.
"""
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.error

from closet import apikey, app, cli, demo, productpage, tracejobs, weather
from closet.tagger import routes as tagger_routes
from closet.tagger import shoedrawing
from closet.tagger.correcting import CorrectionResult
from closet.tagger.shopping import Described, Found, LinkRead, PriceAnswer, PriceSeen, SaleAnswer, SaleFound, ShopAnswer
from closet.tagger.tagging import TaggingError, TagResult, Unreachable

from .conftest import (
    ANSWER,
    GARMENT_BOXES,
    FakeApi,
    FakeClaude,
    MemoryKeychain,
    check_answer,
    correct_answer,
    correct_check_answer,
    draw_answer,
    fake_cutter,
    side_answer,
    side_check_answer,
    side_correct_answer,
    side_correct_check_answer,
    views_answer,
)

_real_build = app.build_services


_failing = {"left": int(os.environ.get("CLOSET_E2E_TAG_FAILS") or 0)}
STAGE_SECONDS = 4 if os.environ.get("CLOSET_E2E_STAGES") else 0   # each step long enough to watch (see above)


def fake_claude(images, routes):
    time.sleep(STAGE_SECONDS or 1)   # long enough for the page to show it being described
    if _failing["left"] > 0:
        _failing["left"] -= 1
        raise TaggingError("the stand-in was told to fail: key sk-ant-api03-" + "Zz9" * 12
                           + " refused, see /home/someone/.claude/session.json")
    answer = ANSWER.model_copy(update={"pattern": "plaid"}) if STAGE_SECONDS else ANSWER
    return TagResult(answer, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def slow_cutter(img):
    time.sleep(STAGE_SECONDS)
    return fake_cutter(img)


def slow_measurer(cut, how, words, marks, **extra):
    """Measuring a pattern, as long as the other steps, finding nothing."""
    time.sleep(STAGE_SECONDS)
    return None


def fake_finder(photo, routes):
    time.sleep(1)   # long enough for the page to show it looking
    return [dict(b) for b in GARMENT_BOXES]


def fake_add_sorter(photos, routes):
    """What each photo chosen on Add shows, from its file name: "shoe..." is one shoe (all such photos the same one;
    "outer", "inner", "front" ... in the name is its side, "pair" that it shows the pair), "several..." or "pile..."
    several pieces, anything else one piece."""
    out = []
    for p in photos:
        name = p.info.get("filename", "").lower()
        if name.startswith("shoe"):   # "shoe-outer...", "shoe-front...", "shoe-pair...": the side, or the pair
            view = next((v for v in ("outer", "inner", "front", "top", "back") if v in name), "other")
            out.append({"kind": "shoe", "shoe": 1, "view": view, "pair": "pair" in name})
        else:
            kind = "pieces" if name.startswith(("several", "pile")) else "piece"
            out.append({"kind": kind, "shoe": 0, "view": None, "pair": False})
    return out


fake_add_sorter.needs_route = False   # answers on a computer with no route to Claude too (the CI)


def fake_sorter(photos, routes):
    time.sleep(1)   # long enough for the page to show it sorting
    return views_answer(len(photos))


_sides = {"asked": 0}


def fake_asker(text, images, routes, answer_model=None, model="", **kw):
    """Claude's answers to the drawing and its check, after a second each: the dress shoe, said to be good, straight
    on or turned; to the judge: the first, with no fault named; to a correction and its check: the dress shoe with
    black laces, said to go against the photos, and good; and to the side and its check: a plain low shoe, good,
    except the first side this backend is asked for, which cannot be used (lettering only), so the first drawing has
    no side and the page shows the trace until the shoe is drawn again; to a change of the side and its check: the plain
    low shoe with a light grey upper, said to go against the photos, and good."""
    time.sleep(1)   # long enough for the page to show it drawing
    if answer_model is shoedrawing.SideAnswer:
        _sides["asked"] += 1
        if _sides["asked"] == 1:
            return CorrectionResult(side_answer("<text>shoe</text>"), routes[0], model, 42_000, 6_500, 12_000)
    if answer_model is shoedrawing.Verdict:
        answer = shoedrawing.Verdict(observations="The panels as the photos show them.", best="a",
                                     ranking=["a", "b"], faults=["A: none", "B: none"])
    else:
        answer = {shoedrawing.DrawAnswer: draw_answer, shoedrawing.TurnedDrawAnswer: draw_answer,
                  shoedrawing.CorrectAnswer: correct_answer, shoedrawing.TurnedCorrectAnswer: correct_answer,
                  shoedrawing.CorrectCheckAnswer: correct_check_answer,
                  shoedrawing.TurnedCorrectCheckAnswer: correct_check_answer,
                  shoedrawing.SideAnswer: side_answer,
                  shoedrawing.SideCheckAnswer: side_check_answer,
                  shoedrawing.SideCorrectAnswer: side_correct_answer,
                  shoedrawing.SideCorrectCheckAnswer: side_correct_check_answer}.get(answer_model, check_answer)()
        if answer_model in TURNED:   # the same answer in the turned form (the same fields): the dress shoe as drawn,
            answer = answer_model.model_validate(answer.model_dump())   # which passes the turned view's checks
    return CorrectionResult(answer, routes[0], model, 42_000, 6_500, 12_000)


TURNED = {shoedrawing.TurnedDrawAnswer, shoedrawing.TurnedCheckAnswer, shoedrawing.TurnedCorrectAnswer,
          shoedrawing.TurnedCorrectCheckAnswer}


def fake_drawer(photos, routes, notes=(), style=None, measures=None, side_notes=()):
    return shoedrawing.draw(photos, routes, asker=fake_asker, notes=notes, style=style, measures=measures,
                            side_notes=side_notes)


def fake_adder(note, notes, photo, now, geometry, outline, render, routes=(), client=None, meter=None):
    """Claude adding to a garment's drawing: a red patch on the chest, whatever the line says, over what is there."""
    from closet.drawing import added
    from closet.tagger import adding
    patch = added.read_one({"what": "red patch on the chest", "role": "inlay", "color": "#c0392b",
                            "d": "M 222,118 L 250,118 L 250,146 L 222,146 Z"})
    render([*now, patch])   # the drawing with it is made, as for the check
    return adding.Result([*now, patch], "Drew a red patch on the chest.", checks=1, route=(routes or ("plan",))[0],
                         api_usd=0.18, seconds=31.0)


def fake_drawing_corrector(photos, kept, note, routes):
    return shoedrawing.correct(photos, kept, note, routes, asker=fake_asker)


def fake_side_corrector(photos, kept, note, routes, measures=None):
    return shoedrawing.correct_side(photos, kept, note, routes, asker=fake_asker, measures=measures)


def api_only_status(order="auto", claude_exe=None):
    routes = {"plan": {"id": "plan", "available": False, "detail": "Claude Code is not installed on this computer."},
              "api": {"id": "api", "available": True, "detail": ""}}
    return {"order": list(tagger_routes.ORDERS[order]), "routes": [routes[r] for r in tagger_routes.ORDERS[order]]}


def _found(**kw) -> Found:
    base = dict(shop="Example Shop", image_url="", currency="USD", formality="smart_casual", season="all",
                pattern="solid", weight_class="midweight", rain_proof=False, material="")
    return Found(**{**base, **kw})


class FakeShop:
    """Stands in for Claude searching shops and looking up prices; never reaches the web."""

    def find(self, wish, routes):
        time.sleep(1)   # long enough for the page to show it searching
        return ShopAnswer(note="", finds=[
            _found(name="Tan gabardine rain coat", url="https://shop.example/tan-coat", price=180.0, category="coat",
                   color="tan", rain_proof=True, material="cotton gabardine"),
            _found(name="Navy pique polo", shop="Other Shop", url="https://other.example/polo", price=45.0,
                   category="polo", color="navy", season="warm"),
            _found(name="Not a real link", url="javascript:alert(1)", price=10.0, category="tee", color="white")])

    def prices(self, finds, routes):
        time.sleep(1)
        return PriceAnswer(prices=[PriceSeen(url=f["url"], price=round((f["price"] or 100) * 0.8, 2),
                                             currency=f["currency"], available=True) for f in finds])

    def __init__(self):
        self.looks = 0

    def picks(self, asked, routes):
        """Things you might like: after a second, six products of different kinds with long names (against a closet
        like the demo's the coat fills a gap, the jacket, sweater and trousers add something, the striped shirt repeats
        one, and the last has no web address), each look's on pages of their own, so a look never offers one shown
        before."""
        time.sleep(1)   # long enough for the page to show Claude searching
        self.looks += 1
        n = self.looks
        return ShopAnswer(note="", finds=[
            _found(name="Water-repellent cotton gabardine single-breasted trench coat with a removable warm lining",
                   url=f"https://shop.example/pick-{n}-coat", price=320.0, category="coat", color="tan",
                   season="cool", material="cotton gabardine"),
            _found(name="Garment-dyed heavyweight cotton canvas chore jacket with four patch pockets and corozo buttons",
                   url=f"https://shop.example/pick-{n}-chore", price=148.0, category="jacket", color="olive",
                   formality="casual", material="cotton canvas"),
            _found(name="Brushed merino and cashmere blend crewneck sweater in a relaxed fit with ribbed cuffs and hem",
                   shop="Example Knitwear Company of Long Names", url=f"https://shop.example/pick-{n}-sweater",
                   price=129.5, category="sweater", color="grey", formality="smart_casual", season="cool",
                   material="merino and cashmere"),
            _found(name="Pleated wide-leg wool flannel trousers with side adjusters and a high rise",
                   url=f"https://shop.example/pick-{n}-trousers", price=210.0, category="trousers", color="grey",
                   formality="smart_casual", season="cool", material="wool flannel"),
            _found(name="Striped oxford cloth button-down shirt", url=f"https://shop.example/pick-{n}-shirt",
                   price=89.0, category="shirt", color="blue", pattern="stripe", formality="smart_casual"),
            _found(name="Not a real link", url="javascript:alert(1)", price=10.0, category="tee", color="white")])

    def sale(self, asked, routes):
        """On sale now: after a second, five products marked down with long names, each look's on pages of their own
        (`SALE_PAGES` gives what each page shows; the overcoat, the knit and the boots are kept)."""
        time.sleep(1)
        self.looks += 1
        n = self.looks

        def on_sale(slug, **kw):
            found = _found(url=f"https://shop.example/sale-{n}-{slug}",
                           **{k: v for k, v in kw.items() if k not in ("price_before", "size_in_stock")})
            return SaleFound(**found.model_dump(), price_before=kw.get("price_before"),
                             size_in_stock=kw.get("size_in_stock"))
        return SaleAnswer(note="", finds=[
            on_sale("overcoat", name="Double-faced wool and cashmere unstructured overcoat with raglan sleeves and patch "
                    "pockets", shop="Example Maker of Considered Outerwear and Other Long Names", price=168.0,
                    price_before=240.0, category="coat", color="tan", season="cool", material="wool and cashmere",
                    size_in_stock=True),
            on_sale("knit", name="Hand-framed lambswool shawl-collar cardigan in a heathered oatmeal with leather buttons",
                    price=105.0, price_before=150.0, category="sweater", color="olive", season="cool",
                    formality="smart_casual", material="lambswool"),
            on_sale("boots", name="Waxed suede chukka boots on a crepe sole", price=195.0, price_before=260.0,
                    category="boots", color="black", material="suede"),
            on_sale("trousers", name="Cotton twill pleated trousers", price=110.0, price_before=120.0,
                    category="trousers", color="tan"),
            on_sale("shirt", name="Brushed flannel work shirt", price=60.0, price_before=95.0, category="shirt",
                    color="green", pattern="plaid")])

    def read(self, find, routes):
        """A link's page read whole: Claude could not open it either (no page here turns Nines away)."""
        time.sleep(1)
        return LinkRead(read=False, name="", shop="", image_url="", price=None, currency="USD", available=True,
                        clothing=False, category="shirt", color="white", formality="casual", season="all",
                        pattern="solid", weight_class="unknown", rain_proof=False, material="")

    def describe(self, product, routes):
        time.sleep(1)   # long enough for the page to show Claude describing it
        return Described(clothing=True, category="shirt", color="white", formality="casual", season="warm",
                         pattern="solid", weight_class="lightweight", rain_proof=False, material="linen")


SHOP_PAGE_NAMES = {
    "https://shop.example/linen-shirt": "Linen camp-collar shirt",
    "https://shop.example/long-name": ("Heavyweight garment-dyed linen camp-collar short-sleeve shirt in washed sand with "
                                       "horn-effect buttons and a boxy cropped fit"),
    "https://shop.example/code-shirt": "Linen shirt with a code",
    "https://shop.example/slow-shirt": "Slowly read linen shirt",
}
# pages that take a while to answer, so the page that sent the link has asked for the wishlist before they are read
SLOW_SHOP_PAGES = {"https://shop.example/slow-shirt"}
# what a page's text shows besides its structured data: a banner with a checkout code (made-up codes)
SHOP_PAGE_TEXT = {
    "https://shop.example/long-name": '<div class="banner"><p>Take 40% off everything with code TESTWEEKEND40</p></div>',
    "https://shop.example/code-shirt": '<div class="promo"><span>40% off</span> with code <b>TEST40</b></div>',
}


# What each "On sale now" page shows (`FakeShop.sale`), by the end of its address: (price, the price before in its own
# data, how it gives it, whether it can be bought)
SALE_PAGES = {
    "overcoat": (168.0, 240.0, "strikethrough", True),
    "knit": (105.0, None, None, True),        # the page gives no price before: only Claude saw $150
    "boots": (195.0, 260.0, "og", True),
    "trousers": (110.0, 120.0, "strikethrough", True),   # 8% off: not a sale worth a pick
    "shirt": (60.0, 95.0, "strikethrough", False),       # sold out
}


def sale_page(slug: str) -> str:
    price, before, how, available = SALE_PAGES[slug]
    offer = {"@type": "Offer", "price": f"{price:.2f}", "priceCurrency": "USD",
             "availability": f"https://schema.org/{'InStock' if available else 'OutOfStock'}"}
    if how == "strikethrough":
        offer["priceSpecification"] = [{"@type": "UnitPriceSpecification", "price": f"{before:.2f}",
                                        "priceType": "https://schema.org/StrikethroughPrice"}]
    data = {"@context": "https://schema.org", "@type": "Product", "name": slug, "offers": offer}
    head = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    if how == "og":
        head += f'<meta property="product:original_price:amount" content="{before:.2f}">'
    return f"<html><head>{head}</head><body></body></html>"


class ShopPages:
    """Stands in for the web a link's page is read from (see the top): the real reading of the page, on made-up
    pages."""

    def __init__(self):
        self.reads: dict[str, int] = {}
        self.reader = productpage.Reader(resolve=self.resolve, get=self.get)

    def resolve(self, host: str) -> list[str]:
        if host != "shop.example":
            raise productpage.Unreadable(productpage.NO_SUCH_PLACE)
        return ["1.2.3.4"]   # any address on the internet: nothing connects to it

    def get(self, target, seconds):
        url = target.url.split("?")[0]
        slug = url.rsplit("-", 1)[-1] if url.startswith("https://shop.example/sale-") else None
        if url == "https://shop.example/plain-shirt":
            text = "<html><head><title>A plain shirt</title></head><body></body></html>"
        elif slug in SALE_PAGES:
            text = sale_page(slug)
        elif url in SHOP_PAGE_NAMES:
            if url in SLOW_SHOP_PAGES:
                time.sleep(3)
            n = self.reads.get(url, 0)
            self.reads[url] = n + 1
            data = {"@context": "https://schema.org", "@type": "Product", "name": SHOP_PAGE_NAMES[url],
                    "offers": {"@type": "Offer", "price": f"{68 * 0.8 ** n:.2f}", "priceCurrency": "USD",
                               "availability": "https://schema.org/InStock"}}
            text = (f'<html><head><script type="application/ld+json">{json.dumps(data)}</script>'
                    '<meta property="og:site_name" content="Example Shop"></head>'
                    f'<body>{SHOP_PAGE_TEXT.get(url, "")}</body></html>')
        else:
            return productpage.Answer(404, {"content-type": "text/html"}, b"")
        return productpage.Answer(200, {"content-type": "text/html; charset=utf-8"}, text.encode("utf-8"))


def seed_from_demo(cfg):
    """The owner's own closet starts as a copy of the demo closet (only when it does not exist yet)."""
    main = cfg.db_path("main")
    if main.exists():
        return
    demo.ensure(cfg)
    src, dst = sqlite3.connect(cfg.db_path("demo")), sqlite3.connect(main)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    if cfg.images_dir("demo").exists():
        shutil.copytree(cfg.images_dir("demo"), cfg.images_dir("main"), dirs_exist_ok=True)


def no_weather_service(url):
    """The browser tests never reach the weather service. One place is stood in for, so a day somewhere else can be
    tried: Lisbon is on the map, and its forecast is a mild, windy day with rain, the same in every hour (so the
    words on Today do not depend on the hour the test runs at). Everything else is out of reach, as before."""
    from datetime import UTC, datetime
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(url)
    params = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if parts.netloc == "geocoding-api.open-meteo.com" and params.get("name", "").lower().startswith("lisbon"):
        return json.dumps({"results": [{"name": "Lisbon", "latitude": 38.71667, "longitude": -9.13333,
                                        "timezone": "Europe/Lisbon", "country": "Portugal"}]}).encode()
    if parts.netloc == "api.open-meteo.com" and params.get("latitude", "").startswith("38.7") and "hourly" in params:
        day = datetime.now(UTC).date().isoformat()
        every = {"temperature_2m": 17.0, "apparent_temperature": 13.0, "precipitation_probability": 70,
                 "precipitation": 1.5, "wind_speed_10m": 38.0, "wind_gusts_10m": 50.0, "relative_humidity_2m": 60,
                 "uv_index": 2.0, "weather_code": 61}
        return json.dumps({"utc_offset_seconds": 0, "daily": {
            "time": [day], "temperature_2m_min": [14.0], "temperature_2m_max": [18.0],
            "precipitation_probability_max": [70], "weather_code": [61]},
            "hourly": {"time": [f"{day}T{h:02d}:00" for h in range(24)], **{k: [v] * 24 for k, v in every.items()}}}).encode()
    raise urllib.error.URLError("the browser tests never reach the weather service")


def fake_day_reader(text, today, home, routes):
    """Stands in for Claude reading the day in the owner's words, from words in the sentence itself: "Lisbon" is a
    place, "four days" four days, "outside" noon to six, "wedding" a formal day; anything else says nothing."""
    words = text.lower()
    return {"place": "Lisbon, Portugal" if "lisbon" in words else None, "starts_in_days": 0,
            "days": 4 if "four days" in words else 1, "outside": (12, 18) if "outside" in words else None,
            "exposure": "outside" if "outside" in words else "mixed",
            "activity": "a wedding" if "wedding" in words else "walking the city" if "walking" in words else "",
            "occasion": "formal" if "wedding" in words else None}


fake_day_reader.needs_route = False   # as fake_add_sorter


STYLIST_WORDS = {"base": "base", "mid layer": "mid", "outer layer": "outer", "bottom": "bottom", "shoes": "shoes"}


def _look(line: str) -> dict:
    """One line of the rules' shortlist ("- base 7; mid layer 11; ...; accessories 35, 36") as one of Claude's looks."""
    look: dict = {"base": 0, "mid": 0, "outer": 0, "bottom": 0, "shoes": 0, "accessories": []}
    for part in line[2:].split(";"):
        part = part.strip()
        if part.startswith("accessories "):
            look["accessories"] = [int(n) for n in part[len("accessories "):].split(",") if n.strip().isdigit()]
            continue
        words, _, number = part.rpartition(" ")
        if words in STYLIST_WORDS and number.isdigit():
            look[STYLIST_WORDS[words]] = int(number)
    return look


def fake_stylist(brief, routes):
    """Stands in for Claude choosing the day's outfits: the rules' second outfit first (so Claude's first differs from
    the rules' first), then their first; with only one, that one. A message of the owner's (`say`) is answered by
    `fake_reply`."""
    lines = [ln for ln in brief["shortlist"].splitlines() if ln.startswith("- ") and not ln.startswith("- The rules")]
    if brief.get("say") is not None:
        return fake_reply(brief["say"], lines, routes)
    chosen = [lines[1], lines[0]] if len(lines) > 1 else lines[:1]
    looks = []
    for i, line in enumerate(chosen):
        looks.append({**_look(line), "why": "Chosen by the stand-in: these go together.",
                      "watch": "" if i == 0 else "The stand-in has no eye for colour."})
    return {"looks": looks, "read": "It is a made-up day, so the stand-in chose by number.", "route": routes[0],
            "model": "stand-in", "input_tokens": 100, "output_tokens": 50}


def fake_reply(say: str, lines: list[str], routes) -> dict:
    """Stands in for Claude answering the owner's message, from words in it: "fail" cannot be reached; "why" (a
    question) is answered in words and leaves the outfits as they are; anything else turns them around, so the first
    outfit on the page changes (the rules' first outfit first, then their third, or second), and offers to keep the
    message for the owner's style when it says "never" or "always", and a note on the first outfit's top when it says
    "fits"."""
    words = say.lower()
    meta = {"read": "", "route": routes[0], "model": "stand-in", "input_tokens": 100, "output_tokens": 50}
    if "fail" in words:
        raise Unreachable("offline")
    if "why" in words:
        return {**meta, "looks": [], "reply": "Because the stand-in chose by number.", "remember": []}
    chosen = [lines[0], lines[2] if len(lines) > 2 else lines[1]] if len(lines) > 1 else lines[:1]
    looks = [{**_look(line), "why": "Turned around by the stand-in, as you asked.", "watch": ""} for line in chosen]
    remember = []
    if "never" in words or "always" in words:
        text = say.strip()
        remember.append({"about": 0, "text": text[:1].upper() + text[1:]})
    if "fits" in words and looks:
        remember.append({"about": looks[0]["base"], "text": "Fits well under a jacket."})
    return {**meta, "looks": looks, "reply": "Done: the stand-in turned the outfits around.", "remember": remember}


def slow_stylist(brief, routes):
    time.sleep(1.5)   # long enough for the page to show Claude choosing, or answering a message
    if "slow" in str(brief.get("say") or "").lower():
        time.sleep(5)   # a message that asks for it is answered slowly, so another can be sent meanwhile
    return fake_stylist(brief, routes)


def failing_stylist(brief, routes):
    raise Unreachable("offline")


def fake_chat(brief, routes):
    """Stands in for Claude in the style conversation, from words in the owner's message (see the module's words)."""
    time.sleep(1.5)   # long enough for the page to show Claude answering
    words = brief["say"].lower()
    meta = {"route": routes[0], "model": "stand-in", "input_tokens": 80, "output_tokens": 40}
    if "fail" in words:
        raise Unreachable("offline")
    if "warm" in words or "cold" in words:
        hot = "warm" in words
        return {**meta, "reply": f"Noted. I'll dress you a little {'lighter' if hot else 'warmer'} than the weather "
                                 "suggests.",
                "remember": ["I run warm, so one layer fewer than most people." if hot else
                             "I feel the cold, so one layer more than most people."]}
    if "never" in words or "always" in words:
        text = brief["say"].strip()
        return {**meta, "reply": "Understood. I'll keep to that.", "remember": [text[:1].upper() + text[1:]]}
    return {**meta, "reply": "Thanks. What do you usually wear for work?", "remember": []}


def build_services(cfg, **kwargs):
    sv = _build_services(cfg, **kwargs)
    if not os.environ.get("CLOSET_E2E_STYLIST"):
        sv.stylist = None   # no stylist at all: the real Claude would otherwise choose without the other stand-ins
    sv.ahead = None   # nothing is asked ahead of the page in a browser test: every question is one a test caused
    return sv


def _build_services(cfg, **kwargs):
    # sorting the photos on Add never reaches Claude from a browser test, with or without the other stand-ins
    kwargs.setdefault("add_sorter", fake_add_sorter)
    kwargs.setdefault("day_reader", fake_day_reader)   # nor does reading the day in the owner's words
    kwargs.setdefault("chat_ask", fake_chat)   # nor does the style conversation
    kwargs.setdefault("page_reader", ShopPages().reader)   # and a link's page is never fetched from the web
    chooser = os.environ.get("CLOSET_E2E_STYLIST")
    if chooser:   # nor does choosing the day's outfits
        kwargs.setdefault("stylist_ask", failing_stylist if chooser == "fails" else slow_stylist)
    if not os.environ.get("CLOSET_E2E_FAKES"):
        return _real_build(cfg, **kwargs)
    if os.environ.get("CLOSET_E2E_SEED") == "demo":
        seed_from_demo(cfg)
    kwargs.setdefault("shop_asker", FakeShop())
    kwargs.setdefault("adder", fake_adder)   # adding to a drawing never reaches Claude either
    kwargs.setdefault("tracer", tracejobs.tracer())   # shoes are traced with GrabCut alone, as without the model
    apikey.use_store(MemoryKeychain())
    apikey.check = lambda key: "refused" if key.endswith("refused") else None
    if os.environ.get("CLOSET_E2E_ROUTES") == "api":
        tagger_routes.status = api_only_status
        sv = _real_build(cfg, cutter=fake_cutter, api_client=FakeApi(input_tokens=20_000, output_tokens=12_000), **kwargs)
    else:
        reader = FakeClaude()
        reader.mode = "answers"
        if STAGE_SECONDS:
            kwargs.setdefault("measurer", slow_measurer)
        sv = _real_build(cfg, cutter=slow_cutter if STAGE_SECONDS else fake_cutter, tagger=fake_claude,
                         routes=lambda: ("plan",), corrector=reader.correct, finder=fake_finder, sorter=fake_sorter,
                         drawer=fake_drawer, drawing_corrector=fake_drawing_corrector,
                         side_corrector=fake_side_corrector, **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


_real_create = app.create_app


def create_app(sv, window_key=None):
    """The app the launcher makes, without the key of its window (see the top)."""
    return _real_create(sv)


if __name__ == "__main__":
    weather.fetch = no_weather_service
    app.build_services = build_services
    app.create_app = create_app
    sys.exit(cli.main(sys.argv[1:]))
