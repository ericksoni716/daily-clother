import io
import sys
import urllib.error
import zlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from closet import app as app_module
from closet import weather
from closet.config import Config
from closet.tagger.correcting import Change, CorrectionAnswer, CorrectionResult
from closet.tagger.garments import Garment, Garments
from closet.tagger.schema import Details, ItemTags, Silhouette
from closet.tagger.tagging import RouteUnavailable, TaggingError, TagResult

PASSPHRASE = "correct horse battery"
REAL_FETCH = weather.fetch   # for the tests of the request itself, which stop urlopen instead


def pytest_runtest_setup(item):
    if item.get_closest_marker("windows") and sys.platform != "win32":
        pytest.skip("Windows only")


@pytest.fixture(autouse=True)
def no_weather_service(monkeypatch):
    """No test reaches Open-Meteo or Nominatim. The place is New York until one is chosen, so anything that looks up
    the weather finds the service unreachable unless the test answers for it by replacing `weather.fetch` itself."""
    def unreachable(url: str) -> bytes:
        raise urllib.error.URLError("no network in tests")
    monkeypatch.setattr(weather, "fetch", unreachable)


def photo_bytes(fmt="JPEG", size=(900, 1200), color=(180, 60, 60)) -> bytes:
    im = Image.new("RGB", size, (240, 240, 235))
    ImageDraw.Draw(im).rectangle((size[0] // 4, size[1] // 6, size[0] * 3 // 4, size[1] * 5 // 6), fill=color)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def fake_cutter(img: Image.Image) -> Image.Image:
    """Stands in for the model: keeps the middle of the photo."""
    w, h = img.size
    out = img.convert("RGBA").crop((w // 4, h // 6, w * 3 // 4, h * 5 // 6))
    return out


# Several pieces laid out in one photo (`pile_bytes`): a red piece left, a blue one in the middle, a green one right,
# on a pale background; and the boxes Claude would give for them, as fractions of the photo.
PILE = ((0.05, 0.10, 0.30, 0.60, (190, 40, 40)), (0.40, 0.10, 0.65, 0.90, (30, 70, 170)),
        (0.72, 0.30, 0.95, 0.70, (40, 150, 60)))
GARMENT_BOXES = [{"x0": x0, "y0": y0, "x1": x1, "y1": y1, "label": label}
                 for (x0, y0, x1, y1, _), label in zip(PILE, ("red shirt", "blue trousers", "green scarf"), strict=True)]


def pile_bytes(size=(1200, 900), shift=0) -> bytes:
    """A synthetic photo of several pieces (coloured shapes); `shift` moves them to make a different file."""
    w, h = size
    im = Image.new("RGB", size, (235, 232, 225))
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1, color in PILE:
        d.rectangle((x0 * w + shift, y0 * h, x1 * w + shift, y1 * h), fill=color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class FakeFinder:
    """Stands in for Claude finding the pieces in a photo: answers `boxes` (GARMENT_BOXES unless told otherwise),
    or raises `error`. `calls` counts the photos it was asked about."""

    def __init__(self, boxes=None):
        self.boxes = GARMENT_BOXES if boxes is None else boxes
        self.error: Exception | None = None
        self.calls = 0

    def __call__(self, photo, routes):
        self.calls += 1
        if self.error:
            raise self.error
        return [dict(b) for b in self.boxes]


# A fixed, valid answer, as Claude would give it for a navy polo.
ANSWER = ItemTags(
    category="polo", category_confidence=0.95, color="navy", color_confidence=0.9, secondary_colors=["white"],
    pattern="solid", pattern_confidence=0.92, formality="smart_casual", formality_confidence=0.7,
    season="warm", season_confidence=0.8, silhouette=Silhouette.of(sleeve="short", neck="collar", fit="regular"),
    silhouette_confidence=0.85,
    details=Details.plain(fit_detail="regular", sleeve_length="short", neckline="polo_collar", collar="flat_knit",
                          placket="polo", placket_buttons=3, button_color="white", cuff="rib_knit", sleeve_construction="set_in",
                          hem="tennis_tail", fabric="pique", fiber="cotton", weight="midweight",
                          other_features=["embroidered chest logo"]),
    details_confidence=0.8, brand=None, size=None, material="100% cotton", needs_shot=None)


# what the stand-in understands in a correction by sentence: sentence -> (changes, not understood, needs the photo)
SENTENCES = {
    "it has three buttons": ([("placket_buttons", "3")], "", False),
    "it has two buttons": ([("placket_buttons", "2")], "", False),
    "the collar is white": ([("trim_color", "white")], "", False),
    "it's a henley, not a tee": ([("neckline", "henley"), ("placket", "henley")], "", False),
    "it's actually green": ([("color", "green")], "", False),
    "it is teal": ([("color", "teal")], "", False),
    "the colour is wrong": ([], "", True),
    "make it look nicer": ([], "I could not tell what to change from “make it look nicer”.", False),
}


class FakeClaude:
    """Stands in for both routes to Claude; no test ever reaches the real one.

    mode "answers": a route is available and returns ANSWER; "fails": a route is available but every call fails;
    "unavailable": no route can be used (the default, so tests that are not about tagging never tag).
    """

    def __init__(self):
        self.mode = "unavailable"
        self.calls: list[tuple[str, ...]] = []
        self.corrections: list[tuple] = []

    def routes(self) -> tuple[str, ...]:
        return () if self.mode == "unavailable" else ("plan",)

    def __call__(self, images, routes):
        self.calls.append(routes)
        assert images and images[0].mode == "RGBA"   # the cutout comes first
        if self.mode == "unavailable":
            raise RouteUnavailable("Claude Code is not signed in")
        if self.mode == "fails":
            raise TaggingError("the answer was outside the schema")
        return TagResult(ANSWER, "claude-haiku-5-5", 0.1, 100, 50, 0.0, 1, route=routes[0])

    def correct(self, sentence, description, allowed, images, routes):
        """A correction by sentence, as Claude would read it (the sentences above; anything else is not understood)."""
        self.corrections.append((sentence, description, allowed, len(images), routes))
        if self.mode == "unavailable" or not routes:
            raise RouteUnavailable("Claude Code is not signed in")
        if self.mode == "fails":
            raise TaggingError("the answer was outside the schema")
        if sentence == "the colour is wrong" and images:
            return CorrectionResult(CorrectionAnswer(changes=[Change(name="color", value="burgundy")], not_understood="",
                                                     needs_photo=False), routes[0], "fake")
        changes, unclear, photo = SENTENCES.get(sentence, ([], f"I could not understand “{sentence}”.", False))
        return CorrectionResult(CorrectionAnswer(changes=[Change(name=n, value=v) for n, v in changes], not_understood=unclear,
                                                 needs_photo=photo), routes[0], "fake")


class FakeApi:
    """Stands in for the Anthropic API behind the API-key route (its `messages.parse`); no test reaches the real one.

    Answers ANSWER (or, asked to read a correction, `correction`: two buttons) and reports token counts as the real
    API does; `error` makes the next calls raise it instead. `requests` keeps what each call was sent.
    """

    def __init__(self, input_tokens: int = 2000, output_tokens: int = 400):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.error: Exception | None = None
        self.calls = 0
        self.requests: list[dict] = []
        self.messages = self
        self.correction = CorrectionAnswer(changes=[Change(name="placket_buttons", value="2")], not_understood="",
                                           needs_photo=False)
        # asked where the pieces are in a 1024-pixel-wide pile photo: GARMENT_BOXES, in its pixels
        self.garments = Garments(garments=[Garment(name=b["label"], x0=b["x0"] * 1024, y0=b["y0"] * 768,
                                                   x1=b["x1"] * 1024, y1=b["y1"] * 768) for b in GARMENT_BOXES])

    def parse(self, **kw):
        self.calls += 1
        self.requests.append(kw)
        if self.error:
            raise self.error
        usage = SimpleNamespace(input_tokens=self.input_tokens, output_tokens=self.output_tokens)
        answer = {CorrectionAnswer: self.correction, Garments: self.garments}.get(kw.get("output_format"), ANSWER)
        return SimpleNamespace(parsed_output=answer, stop_reason="end_turn", usage=usage)


class MemoryKeychain:
    """Stands in for the computer's keychain in every test, so no test reads or writes a real one."""
    where = "this Mac's keychain"

    def __init__(self):
        self.key = None

    def get(self):
        return self.key

    def set(self, key):
        self.key = key

    def delete(self):
        self.key = None


@pytest.fixture(autouse=True)
def keychain():
    from closet import apikey
    store = MemoryKeychain()
    apikey.use_store(store)
    yield store
    apikey.use_store(None)


@pytest.fixture
def cfg(tmp_path):
    return Config(data_dir=tmp_path / "Closet", auto_download_model=False)


@pytest.fixture
def claude():
    return FakeClaude()


@pytest.fixture
def services(cfg, claude):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None,   # independent of whether the page is built
                                   tagger=claude, routes=lambda: claude.routes(), corrector=claude.correct)
    yield sv
    sv.stop()


@pytest.fixture
def anon(services):
    return TestClient(app_module.create_app(services))


@pytest.fixture
def client(anon):
    assert anon.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    return anon


def photo_for(key: str) -> bytes:
    """A photo of its own for each upload key: the closet refuses a photo it already has, so tests that
    need several items must send several photos. The same key gives the same photo, as a retry would."""
    h = zlib.crc32(key.encode())
    return photo_bytes(color=(40 + h % 180, 40 + (h >> 8) % 180, 40 + (h >> 16) % 180))


def upload(client, data=None, key="k1", name=None):
    fields = {"client_key": key}
    if name:
        fields["name"] = name
    return client.post("/api/items", files={"photo": ("p.jpg", data or photo_for(key), "image/jpeg")}, data=fields)
