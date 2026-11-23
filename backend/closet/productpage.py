"""A product's page, read by Nines itself: the address checked, the page fetched with care, the product read from it.

The owner sends a product's page as a link (`closet/shop.py`). Before Claude is asked anything, Nines fetches the page
from this computer and reads what shops publish for search engines and link previews: schema.org `Product` and
`Offer` in JSON-LD (`<script type="application/ld+json">`, with `@graph` and lists), then the OpenGraph
`product:price:amount` and `product:price:currency` tags, then microdata's `itemprop="price"`. The name, the shop, a
picture, the price, its currency and whether it can be bought come back as the page wrote them (`parse`, pure), with
what the page says about the product in words (its description, brand, colour and material), which Claude is given to
describe a link in the closet's words; the caller checks every value before it keeps one, as it does Claude's
(`shop.clean_read`).

A checkout code is read from the page's visible text only (never its scripts or styles): a discount and a code written
together in one short stretch, "40% off with code SAVE40", "Use code SAVE40 for 40% off", "$20 off with code TAKE20"
(`codes`). It is read with care: an offer for only some people (a first order, new customers, signing up, the app,
members) is passed over, and so is "up to 40% off" and a word that is plainly not a code. Many shops put their banners
in with a script, so most pages have none in their text: that is expected.

The address was chosen somewhere else, so it is fetched with care (`Reader`):
- only `https://`, on the usual port, with no name or password in it and at most URL_MAX characters;
- the host is a name, never a number, and every address the name stands for must be on the internet: not this
  computer, the home or office network, Tailscale's own addresses, link-local, multicast, reserved or unspecified
  ones, in IPv4 or IPv6 (`public`). The connection is made to the address that was checked, so the name cannot be
  pointed somewhere else between the check and the connection;
- a redirect is checked the same way, at most MAX_HOPS of them;
- GET only, no cookies sent or kept, a generic browser's User-Agent with nothing about the owner in it, a few seconds
  for the whole page (TIMEOUT) and at most MAX_BYTES read.

Nothing about an address or a page is logged.
"""
from __future__ import annotations

import html
import http.client
import ipaddress
import json
import re
import socket
import time
import zlib
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

from . import net

URL_MAX = 2000         # the longest address taken (shop.URL_MAX is this one)
MAX_HOPS = 3           # redirects followed
TIMEOUT = 10.0         # seconds for the whole page, every redirect included
WAIT = 5.0             # seconds to wait for any one step: connecting, the answer, the next part of the page
MAX_BYTES = 2 * 1024 * 1024
TEXT_MAX = 500         # characters kept of any one value read from a page (the caller shortens them further)
DESCRIPTION_MAX = 2000  # ...and of the product's description, which runs longer
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
           "Accept-Language": "en-US,en;q=0.8", "Accept-Encoding": "gzip"}
REDIRECTS = {301, 302, 303, 307, 308}
PAGE_TYPES = ("text/html", "application/xhtml+xml")
SIGNS = {"$": "USD", "€": "EUR", "£": "GBP"}   # a currency read from a price's sign, when the page names none
GONE = {"outofstock", "soldout", "discontinued", "oos"}
NAT64 = ipaddress.ip_network("64:ff9b::/96")
WRITTEN = re.compile(r"\s*([A-Z]{3})?\s*[$€£]?\s*-?\s*[\d.,]+\s*[$€£]?\s*([A-Z]{3})?\s*")

# A checkout code in the page's text (`codes`)
TEXT_KEPT = 200_000    # characters of the page's visible text looked through (a banner is near the top)
STRETCH = 80           # two neighbouring bits of text this short or shorter are read together ("40% off" / "Use code X")
NEAR = 50              # the most characters between a discount and its code
BREAK = 20             # ...each comma, full stop or box between them counting this many more (`_gap`)
HIDDEN = {"script", "style", "template", "noscript", "svg", "head", "title", "textarea", "select"}
BLOCKS = {"address", "article", "aside", "blockquote", "br", "button", "dd", "details", "dialog", "div", "dl", "dt",
          "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
          "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
          "ul", "body", "html"}
_AMOUNT = r"\d{1,5}(?:[.,]\d{1,2})?"
# "40% off", "$20 off", "20 € off", "save 40%"; a match with neither "save" nor "off" is not a discount
DISCOUNT = re.compile(rf"(?P<save>\bsave\s+)?(?<![\w.,$€£])(?:(?P<pct>\d{{1,2}}(?:\.\d{{1,2}})?)\s?%"
                      rf"|(?P<sign>[$€£])\s?(?P<amt>{_AMOUNT})|(?P<amt2>{_AMOUNT})\s?(?P<sign2>[$€£]))(?P<off>\s*off\b)?",
                      re.I)
UP_TO = re.compile(r"\b(?:up\s+to|as\s+much\s+as)\s*$", re.I)
CODE = re.compile(r"(?<!\w)(?:promo\s*|discount\s*|coupon\s*|offer\s*)?code\b"
                  r"[\s:\-–—\"“'‘]*(?P<code>[A-Za-z0-9][A-Za-z0-9_-]{2,29})(?![A-Za-z0-9_-])", re.I)
# "zip code 10001", "style code AB-123": a code, but not one for checkout
NOT_THIS = re.compile(r"\b(?:zip|postal|post|area|country|security|verification|product|style|item|model|colou?r"
                      r"|reference|referral|gift\s+card)\s*$", re.I)
# an offer for only some people, said in the same stretch of text or the one beside it: passed over
LIMITED = re.compile(r"\b(?:first[\s-]+(?:order|purchase|time)|new\s+(?:customer|subscriber|member|account)s?|sign[\s-]?up"
                     r"|subscri(?:be|bed|ber|bers|bing|ption)|newsletter|e-?mail\s+list|app[\s-]+only|in[\s-]+(?:the\s+)?app"
                     r"|app\s+(?:exclusive|users?)|members?|membership|loyalty|students?|referr?al|refer\s+a\s+friend)\b",
                     re.I)
# words written after "code" that are plainly not one ("USE CODE AT CHECKOUT", "NO CODE NEEDED"); also checked of
# Claude's codes (`shop.clean_code`)
NOT_CODES = frozenset({
    "CODE", "CODES", "OFF", "SALE", "SAVE", "PROMO", "COUPON", "DISCOUNT", "USE", "USING", "ENTER", "APPLY", "APPLIED",
    "WITH", "AT", "CHECKOUT", "CART", "BAG", "FOR", "THE", "AND", "YOUR", "NOW", "TODAY", "HERE", "BELOW", "ABOVE", "ONLY",
    "EXTRA", "FREE", "SHIPPING", "ORDER", "ORDERS", "NEW", "NONE", "NEEDED", "REQUIRED", "NOT", "ALL", "SITEWIDE",
    "STOREWIDE", "DETAILS", "TERMS", "EXCLUSIONS", "VALID", "EXPIRES", "ENDS", "SHOP"})

# What the owner is told, in plain words
NOT_A_LINK = "That is not a link to a page. Paste the whole address, starting with https://."
NOT_HTTPS = "Nines only opens pages whose address starts with https://."
TOO_LONG = f"That link is too long: at most {URL_MAX:,} characters."
NOT_A_SHOP = "Nines won't open that address: it does not lead to a shop on the internet."
NO_SUCH_PLACE = "Nines could not find that address. Check the link, or try again in a while."
UNREACHABLE = "Nines could not open the page. The shop may be down, or may not let programs read it."
NOT_A_PAGE = "That link is not a web page."
REDIRECTED = "The shop's page sent Nines on to an address it does not open, so it stopped there."


class PageError(Exception):
    """A page that was not read, with the sentence to show."""


class Unsafe(PageError):
    """An address Nines does not open (see the rules above). It is never fetched, and Claude is not asked about it."""


class Unreadable(PageError):
    """A page that could not be fetched, or is not a page: the shop may be down or turn programs away."""


@dataclass
class Answer:
    status: int
    headers: dict[str, str]   # names in lower case
    body: bytes


@dataclass
class Target:
    url: str        # the address as given, without the spaces around it
    host: str       # its host name, in the form sent on the wire
    path: str       # what is asked for: the path and the query
    address: str    # the checked address the connection is made to


@dataclass
class Code:
    """A checkout code the page's text shows with its discount, as written (unchecked): a percent or an amount off."""
    code: str
    percent: float | None = None
    amount: float | None = None
    currency: str | None = None   # an amount's, from its sign


@dataclass
class Product:
    """What a page says about its product, as written (unchecked)."""
    name: str | None = None
    shop: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str | None = None
    available: bool = True
    codes: list[Code] = field(default_factory=list)   # every checkout code its text shows; the caller keeps the best
    # what the page says about the product in words, for Claude to describe it in the closet's (`shop.describe`)
    description: str | None = None
    brand: str | None = None
    color: str | None = None
    material: str | None = None


Resolve = Callable[[str], list[str]]
Get = Callable[[Target, float], Answer]


# ------------------------------------------------------------------ the address
def public(address: str) -> bool:
    """True for an address on the internet; False for this computer, a private or shared network (Tailscale's
    included), link-local, multicast, reserved or unspecified addresses, and anything that is not an address. An IPv6
    address that carries an IPv4 one (mapped, 6to4, NAT64) is judged by that one too."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        inner = ip.ipv4_mapped or ip.sixtofour or (ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF) if ip in NAT64 else None)
        if inner is not None and not public(str(inner)):
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_private or ip.is_loopback or ip.is_link_local
                                 or ip.is_reserved or ip.is_unspecified)


def _resolve(host: str) -> list[str]:
    """The addresses a name stands for, from the computer's own lookup."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as e:
        raise Unreadable(NO_SUCH_PLACE) from e
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _parts(url: object):
    """The address split into its parts, or Unsafe with the sentence: https on the usual port, a host name, no name or
    password, no spaces, at most URL_MAX characters."""
    if not isinstance(url, str):
        raise Unsafe(NOT_A_LINK)
    url = url.strip()
    if not url or any(c.isspace() or ord(c) < 32 for c in url):
        raise Unsafe(NOT_A_LINK)
    if len(url) > URL_MAX:
        raise Unsafe(TOO_LONG)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise Unsafe(NOT_A_LINK) from None
    scheme = parts.scheme.lower()
    if scheme == "http":
        raise Unsafe(NOT_HTTPS)
    if scheme != "https" or not parts.hostname:
        raise Unsafe(NOT_A_LINK)
    if parts.username is not None or parts.password is not None or port not in (None, 443):
        raise Unsafe(NOT_A_SHOP)
    host = parts.hostname.rstrip(".")
    try:
        ipaddress.ip_address(host)
        raise Unsafe(NOT_A_SHOP)   # a number, not a shop's name
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise Unsafe(NOT_A_LINK) from None
    if not host or "." not in host:
        raise Unsafe(NOT_A_SHOP)   # "localhost", a computer on the home network by its bare name
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return url, host, quote(path, safe="!#$%&'()*+,/:;=?@[]~")   # anything else (letters beyond ASCII) %-encoded


# ------------------------------------------------------------------ fetching
class _Pinned(http.client.HTTPSConnection):
    """HTTPS to the address that was checked, with the shop's certificate checked against its name."""

    def __init__(self, target: Target, wait: float):
        super().__init__(target.host, 443, timeout=wait, context=net.ssl_context())
        address = target.address
        self._create_connection = lambda where, timeout=wait, source=None: socket.create_connection((address, 443), timeout)


def _connection(target: Target, wait: float) -> http.client.HTTPSConnection:
    return _Pinned(target, wait)


def _get(target: Target, seconds: float) -> Answer:
    """One GET, with no cookie, the generic headers and at most MAX_BYTES read in `seconds`. Only a page's own answer
    is read; a redirect's is not."""
    deadline = time.monotonic() + seconds
    conn = _connection(target, min(WAIT, max(seconds, 0.1)))
    try:
        conn.request("GET", target.path, headers=HEADERS)
        resp = conn.getresponse()
        return _answer(resp, deadline)
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise Unreadable(UNREACHABLE) from e
    finally:
        conn.close()


def _answer(resp, deadline: float) -> Answer:
    """The answer, its page read up to MAX_BYTES and until `deadline` (what came by then is kept)."""
    headers = {str(k).lower(): str(v) for k, v in resp.getheaders()}
    body = bytearray()
    if resp.status == 200:
        while len(body) < MAX_BYTES and time.monotonic() < deadline:
            chunk = resp.read(min(65536, MAX_BYTES - len(body)))
            if not chunk:
                break
            body += chunk
    return Answer(resp.status, headers, bytes(body))


def _text_of(answer: Answer) -> str:
    """The page as text: unpacked when the shop sent it packed (at most MAX_BYTES), decoded by its charset."""
    body = answer.body
    packing = answer.headers.get("content-encoding", "").strip().lower()
    if packing in ("gzip", "x-gzip", "deflate"):
        try:
            body = zlib.decompressobj(zlib.MAX_WBITS | 32).decompress(body, MAX_BYTES)
        except zlib.error as e:
            raise Unreadable(UNREACHABLE) from e
    elif packing not in ("", "identity"):
        raise Unreadable(UNREACHABLE)
    charset = re.search(r"charset=[\"']?([\w.:-]+)", answer.headers.get("content-type", ""), re.I)
    if not charset:
        charset = re.search(rb"<meta[^>]+charset=[\"']?([\w.:-]+)", body[:4096], re.I)
    name = charset.group(1) if charset else "utf-8"
    name = name.decode("ascii", "replace") if isinstance(name, bytes) else name
    try:
        return body.decode(name, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class Reader:
    """Checks an address and reads its page. `resolve` (a name to its addresses) and `get` (one GET to a checked
    address) are its two edges to the network; tests stand in for them."""

    def __init__(self, resolve: Resolve | None = None, get: Get | None = None):
        self._resolve_with, self._get_with = resolve, get

    def check(self, url: object) -> Target:
        """The address, checked: Unsafe (with the sentence) when Nines does not open it, Unreadable when its name
        cannot be found."""
        url, host, path = _parts(url)
        addresses = (self._resolve_with or _resolve)(host)
        if not addresses or not all(public(a) for a in addresses):
            raise Unsafe(NOT_A_SHOP)
        return Target(url, host, path, addresses[0])

    def fetch(self, url: str) -> tuple[str, str]:
        """The page's final address and its text, following at most MAX_HOPS redirects, each checked as the first."""
        deadline = time.monotonic() + TIMEOUT
        for hop in range(MAX_HOPS + 1):
            try:
                target = self.check(url)
            except Unsafe:
                if hop:
                    raise Unreadable(REDIRECTED) from None
                raise
            left = deadline - time.monotonic()
            if left <= 0:
                raise Unreadable(UNREACHABLE)
            answer = (self._get_with or _get)(target, left)
            if answer.status in REDIRECTS:
                location = answer.headers.get("location", "").strip()
                if not location or hop == MAX_HOPS:
                    raise Unreadable(UNREACHABLE)
                url = urljoin(target.url, location)
                continue
            if answer.status != 200:
                raise Unreadable(UNREACHABLE)
            kind = answer.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind and kind not in PAGE_TYPES:
                raise Unreadable(NOT_A_PAGE)
            return target.url, _text_of(answer)
        raise Unreadable(UNREACHABLE)

    def read(self, url: str) -> Product:
        """What the page at `url` says about its product (PageError when it was not read)."""
        final, page = self.fetch(url)
        return parse(page, final)


# ------------------------------------------------------------------ reading the page (pure)
class _Collect(HTMLParser):
    """The JSON-LD blocks, the meta tags (by property or name, the first of each), the microdata given as `content`,
    the title, and the visible text in bits, one per block of the page (a paragraph, a list's line, a banner's div);
    never what is inside a script, a style, the head or a drawing."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.meta: dict[str, str] = {}
        self.items: dict[str, str] = {}
        self.title: str | None = None
        self.text: list[str] = []
        self._block: list[str] | None = None
        self._title: list[str] | None = None
        self._svg = 0
        self._hidden = 0
        self._bit: list[str] = []
        self._kept = 0

    def _break(self):
        bit = " ".join("".join(self._bit).split())
        self._bit = []
        if bit and self._kept < TEXT_KEPT:
            self.text.append(bit)
            self._kept += len(bit)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and a.get("type", "").split(";")[0].strip().lower() == "application/ld+json":
            self._block = []
        elif tag == "svg":
            self._svg += 1
        elif tag == "title" and self.title is None and not self._svg:
            self._title = []
        if tag == "body":
            self._hidden = 0   # a head whose end tag was left out (HTML allows it) ends where the body starts
        if tag in HIDDEN:
            self._hidden += 1
        elif tag in BLOCKS:
            self._break()
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            if key and "content" in a:
                self.meta.setdefault(key, a["content"])
        if a.get("itemprop") and "content" in a:
            self.items.setdefault(a["itemprop"].strip().lower(), a["content"])

    def handle_endtag(self, tag):
        if tag == "script" and self._block is not None:
            self.blocks.append("".join(self._block))
            self._block = None
        elif tag == "svg" and self._svg:
            self._svg -= 1
        elif tag == "title" and self._title is not None:
            self.title = "".join(self._title)
            self._title = None
        if tag in HIDDEN:
            self._hidden = max(0, self._hidden - 1)
        elif tag in BLOCKS:
            self._break()

    def handle_data(self, data):
        if self._block is not None:
            self._block.append(data)
        elif self._title is not None:
            self._title.append(data)
        elif not self._hidden:
            self._bit.append(data)

    def close(self):
        super().close()
        self._break()


def _text(value: object, limit: int = TEXT_MAX) -> str | None:
    """A value as plain text: a string, the first string of a list, or the `name` of an object (a brand, a seller)."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, (str, dict))), None)
    if isinstance(value, dict):
        value = value.get("name")
    if not isinstance(value, str):
        return None
    value = " ".join(html.unescape(value).split())
    return value[:limit] or None


def _image(value: object) -> str | None:
    """A picture's address: a string, a list's first, or an ImageObject's `url` or `contentUrl`."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, (str, dict))), None)
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return value.strip() if isinstance(value, str) and value.strip() else None


def number(value: object) -> tuple[float | None, str | None]:
    """A price as written, as a number and the currency its sign or code names (or None): 68, "68.00", "$1,299.00",
    "89,50 €", "1.299,00", "USD 45". A comma or a point before the last one or two digits is the decimal mark."""
    if isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float)):
        return (float(value), None) if value == value and abs(value) != float("inf") else (None, None)
    if not isinstance(value, str):
        return None, None
    text = html.unescape(value)
    sign = next((code for s, code in SIGNS.items() if s in text), None)
    code = WRITTEN.fullmatch(text)   # a code only right beside the number: "USD 45", "45.00 EUR"
    currency = (code.group(1) or code.group(2)) if code and (code.group(1) or code.group(2)) else sign
    found = re.search(r"\d(?:[\d.,]*\d)?", text)
    if not found or re.search(r"-\s*$", text[:found.start()]):
        return None, currency   # no number, or a negative one
    digits = found.group(0)
    if "," in digits and "." in digits:
        mark = "," if digits.rfind(",") > digits.rfind(".") else "."
        digits = digits.replace("." if mark == "," else ",", "").replace(",", ".")
    elif "," in digits or digits.count(".") > 1:
        sep = "," if "," in digits else "."
        head, _, tail = digits.rpartition(sep)
        decimal = digits.count(sep) == 1 and len(tail) <= 2
        digits = head.replace(sep, "") + ("." if decimal else "") + tail
    try:
        return float(digits), currency
    except ValueError:
        return None, currency


def _available(value: object) -> bool | None:
    """Whether it can be bought, from schema.org's availability ("https://schema.org/InStock", "OutOfStock") or a
    meta tag's ("in stock", "oos"); None when the page does not say."""
    if not isinstance(value, str) or not value.strip():
        return None
    word = re.sub(r"[\s_-]", "", value.strip().rsplit("/", 1)[-1].rsplit(":", 1)[-1]).lower()
    return word not in GONE


def _types(node: dict) -> set[str]:
    kinds = node.get("@type")
    return {str(k).rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower() for k in (kinds if isinstance(kinds, list) else [kinds])
            if isinstance(k, str)}


def _loads(block: str) -> object:
    text = block.strip()
    for wrap in (("<!--", "-->"), ("/*<![CDATA[*/", "/*]]>*/"), ("<![CDATA[", "]]>")):
        if text.startswith(wrap[0]) and text.endswith(wrap[1]):
            text = text[len(wrap[0]):-len(wrap[1])].strip()
    try:
        return json.loads(text, strict=False)
    except ValueError:
        return None


def _nodes(data: object, limit: int = 5000) -> Iterator[dict]:
    """Every object in the data, the shallowest first (a page's own product before the related ones inside it)."""
    queue, seen = deque([data]), 0
    while queue and seen < limit:
        x = queue.popleft()
        if isinstance(x, list):
            queue.extend(x)
        elif isinstance(x, dict):
            seen += 1
            yield x
            queue.extend(v for v in x.values() if isinstance(v, (dict, list)))


def _offers(product: dict) -> list[dict]:
    raw = product.get("offers")
    offers = [o for o in (raw if isinstance(raw, list) else [raw]) if isinstance(o, dict)]
    for o in list(offers):
        inner = o.get("offers")   # an AggregateOffer may list its offers too
        offers += [i for i in (inner if isinstance(inner, list) else [inner]) if isinstance(i, dict)]
    if not offers and "productgroup" in _types(product):
        for variant in product.get("hasVariant") if isinstance(product.get("hasVariant"), list) else []:
            if isinstance(variant, dict):
                offers += _offers(variant)
    return offers


def _offer(o: dict) -> tuple[float | None, str | None, bool | None]:
    """An offer's price, currency and whether it can be bought. An AggregateOffer's price is its lowest."""
    raw = o.get("lowPrice") if "aggregateoffer" in _types(o) and o.get("lowPrice") is not None else o.get("price")
    currency = _text(o.get("priceCurrency"))
    if raw is None:
        specs = o.get("priceSpecification")
        spec = next((s for s in (specs if isinstance(specs, list) else [specs])
                     if isinstance(s, dict) and s.get("price") is not None), None)
        if spec:
            raw, currency = spec.get("price"), currency or _text(spec.get("priceCurrency"))
    price, written = number(raw)
    return price, (currency or written), _available(o.get("availability"))


def _best(offers: list[tuple[float | None, str | None, bool | None]]) -> tuple[float | None, str | None, bool]:
    """The lowest price among the offers that can be bought, else the lowest of all (then it cannot be bought)."""
    priced = [o for o in offers if o[0] is not None and o[0] > 0]
    buyable = [o for o in priced if o[2] is not False]
    if buyable:
        price, currency, _ = min(buyable, key=lambda o: o[0])
        return price, currency, True
    if priced:
        price, currency, _ = min(priced, key=lambda o: o[0])
        return price, currency, False
    return None, next((o[1] for o in offers if o[1]), None), next((o[2] for o in offers if o[2] is not None), True)


def _stretches(bits: list[str]) -> Iterator[tuple[int, int, str]]:
    """Each bit of visible text, then each two neighbouring short bits read together (a banner often puts the discount
    and the code in two boxes), with the first and last bit's places."""
    for i, bit in enumerate(bits):
        yield i, i, bit
    for i in range(len(bits) - 1):
        if len(bits[i]) <= STRETCH and len(bits[i + 1]) <= STRETCH:
            yield i, i + 1, f"{bits[i]} | {bits[i + 1]}"


def _discounts(text: str) -> list[tuple[int, int, float | None, float | None, str | None]]:
    """Every discount in the text: (start, end, percent, amount, the amount's currency). Not "up to 40% off", which
    is not every product."""
    out = []
    for m in DISCOUNT.finditer(text):
        if not (m.group("save") or m.group("off")) or UP_TO.search(text[max(0, m.start() - 20):m.start()]):
            continue
        if m.group("pct"):
            out.append((m.start(), m.end(), float(m.group("pct")), None, None))
        else:
            amount, _ = number(m.group("amt") or m.group("amt2"))
            out.append((m.start(), m.end(), None, amount, SIGNS[m.group("sign") or m.group("sign2")]))
    return out


def _codes_in(text: str) -> list[tuple[int, int, str]]:
    """Every code in the text after "code" or "promo code": (start, end, the code). A word written in small letters
    with no digit ("use code at checkout") is a word, not a code; so is one plainly not a code ("CODE", "OFF")."""
    out = []
    for m in CODE.finditer(text):
        token = m.group("code")
        if NOT_THIS.search(text[max(0, m.start() - 25):m.start()]) or token.upper() in NOT_CODES:
            continue
        if token.isupper() or any(c.isdigit() for c in token):
            out.append((m.start(), m.end(), token))
    return out


def _gap(text: str, a: tuple, b: tuple) -> int:
    """How far apart two things found in the text are, by (start, end): the characters between them, and BREAK more
    for each comma, full stop or box between (so "SAVE20 for 20% off, or code SAVE40" keeps 20% with SAVE20); -1 when
    they overlap."""
    start, end = (a[1], b[0]) if b[0] >= a[1] else (b[1], a[0]) if a[0] >= b[1] else (0, -1)
    if end < start:
        return -1
    between = text[start:end]
    return len(between) + BREAK * sum(between.count(c) for c in ",.;!?|")


def _far(text: str, a: tuple, b: tuple) -> int:
    """`_gap`, with things that overlap as far apart as can be."""
    g = _gap(text, a, b)
    return g if g >= 0 else 10**6


def codes(bits: list[str]) -> list[Code]:
    """The checkout codes the page's visible text shows with their discount: a code and a discount in one short stretch
    of text, at most NEAR characters apart, each the other's nearest. An offer said there, or in the text just before
    or after it, to be for only some people (`LIMITED`) is passed over. Unchecked: the caller checks each value and keeps
    the biggest discount."""
    out: list[Code] = []
    for first, last, text in _stretches(bits):
        found, offers = _codes_in(text), _discounts(text)
        if not found or not offers:
            continue
        around = " ".join(bits[max(0, first - 1):last + 2])
        if LIMITED.search(around):
            continue
        for c in found:
            d = min(offers, key=lambda d: _far(text, c, d))
            if _far(text, c, d) > NEAR or min(found, key=lambda other: _far(text, other, d)) is not c:
                continue   # none near enough, or the discount belongs to another code, nearer to it
            code = Code(c[2], percent=d[2], amount=d[3], currency=d[4])
            if code not in out:
                out.append(code)
    return out


def parse(page: str, url: str) -> Product:
    """What the page says about its product: from JSON-LD first, then the OpenGraph tags, then microdata, then its
    title; and the checkout codes its visible text shows (`codes`). Nothing is checked here beyond being read; a price
    of 0 is taken as none (shops write it for "ask us"). The description is the product's own, else the page's for link
    previews and search engines; its brand, colour and material only as the product's data gives them."""
    collect = _Collect()
    try:
        collect.feed(page)
        collect.close()
    except Exception:   # a page too broken to read is a page with nothing on it
        pass
    meta, items = collect.meta, collect.items
    product: dict | None = None
    for block in collect.blocks:
        product = next((n for n in _nodes(_loads(block)) if _types(n) & {"product", "productgroup"}), None)
        if product is not None:
            break
    out = Product()
    seller = None
    if product is not None:
        out.name = _text(product.get("name"))
        out.image_url = _image(product.get("image"))
        offers = _offers(product)
        out.price, out.currency, out.available = _best([_offer(o) for o in offers])
        seller = next((_text(o.get("seller")) for o in offers if _text(o.get("seller"))), None)
        out.description = _text(product.get("description"), DESCRIPTION_MAX)
        out.brand, out.color, out.material = (_text(product.get(k)) for k in ("brand", "color", "material"))
    if out.price is None:
        for amount, code, stock in (("product:price:amount", "product:price:currency", "product:availability"),
                                    ("og:price:amount", "og:price:currency", "og:availability")):
            price, written = number(meta.get(amount))
            if price is not None and price > 0:
                out.price, out.currency = price, _text(meta.get(code)) or written
                out.available = _available(meta.get(stock)) is not False
                break
    if out.price is None:
        price, written = number(items.get("price"))
        if price is not None and price > 0:
            out.price, out.currency = price, _text(items.get("pricecurrency")) or written
            out.available = _available(items.get("availability")) is not False
    out.name = out.name or _text(meta.get("og:title")) or _text(meta.get("twitter:title")) or _text(collect.title)
    out.shop = _text(meta.get("og:site_name")) or seller
    out.description = out.description or next(
        (_text(meta.get(k), DESCRIPTION_MAX) for k in ("og:description", "description", "twitter:description")
         if _text(meta.get(k))), None)
    image = out.image_url or _image(meta.get("og:image:secure_url")) or _image(meta.get("og:image")) \
        or _image(meta.get("twitter:image"))
    out.image_url = urljoin(url, image) if image else None
    out.codes = codes(collect.text)
    return out
