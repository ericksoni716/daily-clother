"""A product's page read by Nines itself (closet/productpage.py): what the page says about its product, and the rules
for fetching an address someone else chose.

Nothing here reaches the network: name lookups and requests are stand-ins (`names`, `Web`), and the one test of the
request itself stops the socket. The pages are small made-up HTML, no real shop's.
"""
import gzip
import json
import time

import pytest

from closet import productpage as pp

from .conftest import REAL_PAGE_GET

PUBLIC = "1.2.3.4"   # any address on the internet; nothing connects to it


def ld(*objects) -> str:
    return "".join(f'<script type="application/ld+json">{json.dumps(o)}</script>' for o in objects)


def page(head: str = "", body: str = "") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


def product(**changes) -> dict:
    base = {"@context": "https://schema.org", "@type": "Product", "name": "Linen camp-collar shirt",
            "image": "https://shop.example/img/shirt.jpg",
            "offers": {"@type": "Offer", "price": 68, "priceCurrency": "USD",
                       "availability": "https://schema.org/InStock"}}
    return {**base, **changes}


def parse(html: str, url: str = "https://shop.example/p/shirt") -> pp.Product:
    return pp.parse(html, url)


# ------------------------------------------------------------------ reading JSON-LD
def test_a_product_with_one_offer():
    p = parse(page(ld(product()) + '<meta property="og:site_name" content="Example Shop">'))
    assert p == pp.Product(name="Linen camp-collar shirt", shop="Example Shop",
                           image_url="https://shop.example/img/shirt.jpg", price=68.0, currency="USD", available=True)


def test_offers_as_a_list_give_the_lowest_price_that_can_be_bought():
    offers = [{"@type": "Offer", "price": "70.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
              {"@type": "Offer", "price": "55.00", "priceCurrency": "USD", "availability": "https://schema.org/OutOfStock"},
              {"@type": "Offer", "price": "64.50", "priceCurrency": "USD", "availability": "InStock",
               "seller": {"@type": "Organization", "name": "Seller Co"}}]
    p = parse(page(ld(product(offers=offers))))
    assert (p.price, p.currency, p.available, p.shop) == (64.5, "USD", True, "Seller Co")
    # every size sold out: the lowest price, and it cannot be bought
    gone = [{**o, "availability": "https://schema.org/SoldOut"} for o in offers]
    p = parse(page(ld(product(offers=gone))))
    assert (p.price, p.available) == (55.0, False)


def test_an_aggregate_offer_gives_its_lowest_price():
    p = parse(page(ld(product(offers={"@type": "AggregateOffer", "lowPrice": "45", "highPrice": "60",
                                      "priceCurrency": "GBP", "offerCount": 3}))))
    assert (p.price, p.currency) == (45.0, "GBP")


def test_a_product_inside_a_graph_or_a_list_is_found_before_the_ones_inside_it():
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": "A page"},
        {"@type": "BreadcrumbList", "itemListElement": []},
        product(isSimilarTo=product(name="Another shirt", offers={"@type": "Offer", "price": 10, "priceCurrency": "USD"}))]}
    assert parse(page(ld(graph))).name == "Linen camp-collar shirt"
    assert parse(page(ld([{"@type": "Organization", "name": "Example"}, product()]))).price == 68.0
    # a type given as a list or as a full address
    assert parse(page(ld(product(**{"@type": ["Product", "Thing"]})))).price == 68.0
    assert parse(page(ld(product(**{"@type": "http://schema.org/Product"})))).price == 68.0


@pytest.mark.parametrize(("written", "currency", "price", "read_currency"), [
    ("68.00", "USD", 68.0, "USD"),
    ("1,299.00", "USD", 1299.0, "USD"),
    ("$1,299.00", None, 1299.0, "USD"),      # the sign says which currency, when the page does not
    ("89,50 €", None, 89.5, "EUR"),
    ("1.299,00", "EUR", 1299.0, "EUR"),
    ("£45", None, 45.0, "GBP"),
    ("USD 45.10", None, 45.1, "USD"),
])
def test_a_price_written_as_text(written, currency, price, read_currency):
    offer = {"@type": "Offer", "price": written}
    if currency:
        offer["priceCurrency"] = currency
    p = parse(page(ld(product(offers=offer))))
    assert (p.price, p.currency) == (price, read_currency)


def test_a_price_in_a_price_specification_and_a_product_group():
    spec = {"@type": "Offer", "priceSpecification": {"@type": "UnitPriceSpecification", "price": "39.95",
                                                     "priceCurrency": "EUR"}}
    assert (parse(page(ld(product(offers=spec)))).price, parse(page(ld(product(offers=spec)))).currency) == (39.95, "EUR")
    group = {"@type": "ProductGroup", "name": "Shirt", "hasVariant": [
        {"@type": "Product", "offers": {"@type": "Offer", "price": "50", "priceCurrency": "USD"}},
        {"@type": "Product", "offers": {"@type": "Offer", "price": "48", "priceCurrency": "USD"}}]}
    assert parse(page(ld(group))).price == 48.0


def test_text_is_read_as_text_and_a_broken_block_is_passed_over():
    html = page('<script type="application/ld+json">{"@type": "Product", "name": </script>'
                + ld(product(name="Shirt &amp; tie <b>set</b>", image=[{"@type": "ImageObject", "url": "/img/a.jpg"}]))
                + "<title>The shop &amp; co</title>", '<svg><title>An icon</title></svg>')
    p = parse(html)
    assert p.name == "Shirt & tie <b>set</b>"   # as text: the caller shows it as text, never as markup
    assert p.image_url == "https://shop.example/img/a.jpg"


def test_a_price_of_nothing_or_zero_is_no_price():
    assert parse(page(ld(product(offers={"@type": "Offer", "price": 0, "priceCurrency": "USD"})))).price is None
    assert parse(page(ld(product(offers={"@type": "Offer", "price": "Call us", "priceCurrency": "USD"})))).price is None
    assert parse(page(ld(product(offers={"@type": "Offer", "price": "-5", "priceCurrency": "USD"})))).price is None


# ------------------------------------------------------------------ the tags for link previews, and microdata
def test_opengraph_tags_when_there_is_no_json_ld():
    head = ('<meta property="og:title" content="Wool overcoat">'
            '<meta property="og:site_name" content="Example Shop">'
            '<meta property="og:image" content="/img/coat.jpg">'
            '<meta property="product:price:amount" content="249.00">'
            '<meta property="product:price:currency" content="USD">'
            '<meta property="product:availability" content="out of stock">')
    p = parse(page(head), "https://shop.example/coat")
    assert p == pp.Product(name="Wool overcoat", shop="Example Shop", image_url="https://shop.example/img/coat.jpg",
                           price=249.0, currency="USD", available=False)
    # the older og:price tags, and a name given by `name` rather than `property`
    p = parse(page('<meta name="og:price:amount" content="19,99"><meta name="og:price:currency" content="EUR">'))
    assert (p.price, p.currency, p.available) == (19.99, "EUR", True)


def test_json_ld_wins_over_the_tags_and_the_tags_fill_what_it_lacks():
    head = ld(product(image=None)) + ('<meta property="product:price:amount" content="99">'
                                      '<meta property="og:image" content="https://shop.example/og.jpg">')
    p = parse(page(head))
    assert (p.price, p.image_url) == (68.0, "https://shop.example/og.jpg")


def test_microdata_given_as_content():
    body = ('<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">Belt</h1>'
            '<span itemprop="price" content="35.00">$35</span><meta itemprop="priceCurrency" content="USD"></div>')
    p = parse(page("<title>Belt | Example Shop</title>", body))
    assert (p.name, p.price, p.currency) == ("Belt | Example Shop", 35.0, "USD")


def test_a_page_with_no_product_data():
    p = parse(page("<title>  Welcome to\n the shop </title>", "<p>Our story</p>"))
    assert p == pp.Product(name="Welcome to the shop")
    assert parse("") == pp.Product()
    assert parse("<<<not html at all") == pp.Product()


# ------------------------------------------------------------------ the address
def names(table: dict[str, list[str]] | None = None, calls: list | None = None):
    """A stand-in for the computer's name lookup: shop.example is on the internet unless the table says otherwise."""
    table = {"shop.example": [PUBLIC], **(table or {})}

    def resolve(host: str) -> list[str]:
        if calls is not None:
            calls.append(host)
        if host not in table:
            raise pp.Unreadable(pp.NO_SUCH_PLACE)
        return table[host]
    return resolve


class Web:
    """A stand-in for the request: answers by address, and records every target asked for."""

    def __init__(self, answers: dict[str, pp.Answer] | None = None):
        self.answers = answers or {}
        self.asked: list[pp.Target] = []

    def get(self, target: pp.Target, seconds: float) -> pp.Answer:
        self.asked.append(target)
        assert 0 < seconds <= pp.TIMEOUT
        return self.answers.get(target.url) or pp.Answer(404, {}, b"")


def html_answer(text: str, **headers) -> pp.Answer:
    return pp.Answer(200, {"content-type": "text/html; charset=utf-8", **headers}, text.encode("utf-8"))


def redirect(to: str, **headers) -> pp.Answer:
    return pp.Answer(302, {"location": to, **headers}, b"")


@pytest.mark.parametrize(("url", "sentence"), [
    ("", pp.NOT_A_LINK),
    ("shop.example/p/shirt", pp.NOT_A_LINK),
    ("javascript:alert(1)", pp.NOT_A_LINK),
    ("ftp://shop.example/p", pp.NOT_A_LINK),
    ("https://shop.example/p shirt", pp.NOT_A_LINK),
    ("http://shop.example/p/shirt", pp.NOT_HTTPS),
    ("https://shop.example/" + "a" * pp.URL_MAX, pp.TOO_LONG),
    ("https://owner:secret@shop.example/p", pp.NOT_A_SHOP),
    ("https://shop.example:8443/p", pp.NOT_A_SHOP),
    ("https://93.184.216.34/p", pp.NOT_A_SHOP),
    ("https://127.0.0.1/p", pp.NOT_A_SHOP),
    ("https://[::1]/p", pp.NOT_A_SHOP),
    ("https://[2606:4700::1]/p", pp.NOT_A_SHOP),
    ("https://localhost/p", pp.NOT_A_SHOP),
    ("https://nas/p", pp.NOT_A_SHOP),
])
def test_addresses_nines_does_not_open(url, sentence):
    calls = []
    with pytest.raises(pp.Unsafe) as e:
        pp.Reader(resolve=names(calls=calls), get=Web().get).check(url)
    assert str(e.value) == sentence
    assert calls == []   # refused before any name is looked up
    assert pp.Reader(resolve=names()).check("https://shop.example/" + "a" * (pp.URL_MAX - 21)).host == "shop.example"


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.20", "169.254.169.254", "100.101.102.103", "0.0.0.0",
    "224.0.0.251", "240.0.0.1", "255.255.255.255", "198.18.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1", "::ffff:10.0.0.1", "::ffff:127.0.0.1",
    "2002:7f00:1::1", "64:ff9b::7f00:1",
])
def test_a_name_that_leads_to_this_computer_or_its_network_is_refused(address):
    web = Web()
    reader = pp.Reader(resolve=names({"shop.example": [address]}), get=web.get)
    with pytest.raises(pp.Unsafe) as e:
        reader.check("https://shop.example/p")
    assert str(e.value) == pp.NOT_A_SHOP
    with pytest.raises(pp.Unsafe):
        reader.read("https://shop.example/p")
    assert web.asked == []   # never fetched


def test_every_address_of_a_name_must_be_on_the_internet_and_the_checked_one_is_used():
    reader = pp.Reader(resolve=names({"mixed.example": [PUBLIC, "192.168.0.2"], "two.example": ["2606:4700::1", PUBLIC]}))
    with pytest.raises(pp.Unsafe):
        reader.check("https://mixed.example/p")
    target = reader.check("  https://two.example/p/shirt?colour=sand&size=m  ")
    assert target == pp.Target("https://two.example/p/shirt?colour=sand&size=m", "two.example", "/p/shirt?colour=sand&size=m",
                               "2606:4700::1")
    assert pp.public(PUBLIC) and pp.public("2606:4700::1") and not pp.public("not an address")


def test_a_name_that_cannot_be_found():
    with pytest.raises(pp.Unreadable) as e:
        pp.Reader(resolve=names()).check("https://nowhere.example/p")
    assert str(e.value) == pp.NO_SUCH_PLACE


def test_letters_beyond_ascii_are_sent_as_the_web_writes_them():
    target = pp.Reader(resolve=names({"xn--bcher-kva.example": [PUBLIC]})).check("https://bücher.example/hemd/größe")
    assert target.host == "xn--bcher-kva.example" and target.path == "/hemd/gr%C3%B6%C3%9Fe"


# ------------------------------------------------------------------ fetching
def test_a_page_is_fetched_and_read():
    web = Web({"https://shop.example/p/shirt": html_answer(page(ld(product())))})
    p = pp.Reader(resolve=names(), get=web.get).read("https://shop.example/p/shirt")
    assert p.price == 68.0 and [t.address for t in web.asked] == [PUBLIC]


def test_each_redirect_is_checked_like_the_first_and_at_most_three_are_followed():
    lookups = []
    resolve = names({"go.example": [PUBLIC], "inside.example": ["10.0.0.7"]}, lookups)
    shirt = html_answer(page(ld(product())))
    # a relative redirect, then another shop's page
    web = Web({"https://go.example/s/1": redirect("/s/2"), "https://go.example/s/2": redirect("https://shop.example/p/shirt"),
               "https://shop.example/p/shirt": shirt})
    assert pp.Reader(resolve=resolve, get=web.get).read("https://go.example/s/1").price == 68.0
    assert [t.url for t in web.asked] == ["https://go.example/s/1", "https://go.example/s/2", "https://shop.example/p/shirt"]
    assert lookups == ["go.example", "go.example", "shop.example"]   # each hop's name looked up and checked again

    # sent on to the home network, or to plain http: stopped there, and the address is never asked for
    for to in ("https://inside.example/admin", "http://shop.example/p/shirt", "https://10.0.0.7/"):
        web = Web({"https://go.example/s/1": redirect(to)})
        with pytest.raises(pp.Unreadable) as e:
            pp.Reader(resolve=resolve, get=web.get).read("https://go.example/s/1")
        assert str(e.value) == pp.REDIRECTED and [t.url for t in web.asked] == ["https://go.example/s/1"]

    # three redirects are followed, a fourth is not
    hops = {f"https://go.example/{n}": redirect(f"/{n + 1}") for n in range(4)}
    web = Web({**hops, "https://go.example/3": html_answer(page(ld(product())))})
    assert pp.Reader(resolve=resolve, get=web.get).read("https://go.example/0").price == 68.0
    web = Web({**hops, "https://go.example/4": html_answer(page(ld(product())))})
    with pytest.raises(pp.Unreadable):
        pp.Reader(resolve=resolve, get=web.get).read("https://go.example/0")
    assert len(web.asked) == pp.MAX_HOPS + 1 == 4


def test_what_is_not_a_page_is_not_read():
    for answer, sentence in ((pp.Answer(403, {"content-type": "text/html"}, b"go away"), pp.UNREACHABLE),
                             (pp.Answer(500, {}, b""), pp.UNREACHABLE),
                             (pp.Answer(200, {"content-type": "application/pdf"}, b"%PDF"), pp.NOT_A_PAGE),
                             (pp.Answer(302, {}, b""), pp.UNREACHABLE)):
        web = Web({"https://shop.example/p": answer})
        with pytest.raises(pp.Unreadable) as e:
            pp.Reader(resolve=names(), get=web.get).read("https://shop.example/p")
        assert str(e.value) == sentence


def test_a_packed_page_and_its_charset():
    text = page(ld(product(name="Chemise à col cubain")))
    packed = pp.Answer(200, {"content-type": "text/html; charset=windows-1252", "content-encoding": "gzip"},
                       gzip.compress(text.encode("windows-1252")))
    web = Web({"https://shop.example/p": packed})
    assert pp.Reader(resolve=names(), get=web.get).read("https://shop.example/p").name == "Chemise à col cubain"
    sniffed = pp.Answer(200, {"content-type": "text/html"}, ('<meta charset="iso-8859-1">' + text).encode("iso-8859-1"))
    assert pp.Reader(resolve=names(), get=Web({"https://shop.example/p": sniffed}).get).read(
        "https://shop.example/p").name == "Chemise à col cubain"


# ------------------------------------------------------------------ the request itself
class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"", chunk=None):
        self.status, self._headers, self._body, self._chunk = status, headers or [], body, chunk
        self.reads = 0

    def getheaders(self):
        return self._headers

    def read(self, n):
        self.reads += 1
        if self._chunk is not None:   # an endless page
            return self._chunk[:n]
        out, self._body = self._body[:n], self._body[n:]
        return out


class FakeConnection:
    made: list = []

    def __init__(self, target, wait, response):
        self.target, self.wait, self.response = target, wait, response
        self.requests = []
        FakeConnection.made.append(self)

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body, dict(headers or {})))

    def getresponse(self):
        return self.response

    def close(self):
        pass


def test_the_request_is_a_plain_get_with_nothing_about_the_owner_and_no_cookies(monkeypatch):
    FakeConnection.made = []
    answers = iter([FakeResponse(302, [("Location", "/p/shirt"), ("Set-Cookie", "session=abc; Path=/")]),
                    FakeResponse(200, [("Content-Type", "text/html")], page(ld(product())).encode())])
    monkeypatch.setattr(pp, "_connection", lambda target, wait: FakeConnection(target, wait, next(answers)))
    p = pp.Reader(resolve=names(), get=REAL_PAGE_GET).read("https://shop.example/go")
    assert p.price == 68.0
    first, second = FakeConnection.made
    assert first.target.address == PUBLIC and 0 < first.wait <= pp.WAIT
    for conn in (first, second):
        (method, path, body, headers), = conn.requests
        assert method == "GET" and body is None
        assert set(headers) == {"User-Agent", "Accept", "Accept-Language", "Accept-Encoding"}   # no Cookie, ever
        assert headers["User-Agent"] == pp.USER_AGENT and "Nines" not in pp.USER_AGENT
    assert first.requests[0][1] == "/go" and second.requests[0][1] == "/p/shirt"


def test_at_most_two_megabytes_are_read_and_no_longer_than_the_time_given(monkeypatch):
    endless = FakeResponse(200, [("Content-Type", "text/html")], chunk=b"x" * 65536)
    answer = pp._answer(endless, time.monotonic() + 60)
    assert len(answer.body) == pp.MAX_BYTES
    late = FakeResponse(200, [("Content-Type", "text/html")], chunk=b"x" * 65536)
    assert pp._answer(late, time.monotonic() - 1).body == b"" and late.reads == 0
    # a redirect's own page is never read
    assert pp._answer(FakeResponse(301, [("Location", "/")], b"moved"), time.monotonic() + 5).body == b""


def test_the_connection_goes_to_the_address_that_was_checked(monkeypatch):
    made = []

    def connect(where, timeout=None, source=None):
        made.append((where, timeout))
        raise OSError("no network in tests")

    def no_lookup(*args, **kwargs):
        raise AssertionError("the name must not be looked up again when connecting")
    monkeypatch.setattr(pp.socket, "create_connection", connect)
    monkeypatch.setattr(pp.socket, "getaddrinfo", no_lookup)
    target = pp.Target("https://shop.example/p", "shop.example", "/p", PUBLIC)
    with pytest.raises(pp.Unreadable) as e:
        REAL_PAGE_GET(target, 3.0)
    assert str(e.value) == pp.UNREACHABLE
    assert made == [((PUBLIC, 443), 3.0)]
