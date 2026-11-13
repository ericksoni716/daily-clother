import io
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from closet import app as app_module
from closet.config import Config
from closet.tagger.correcting import Change, CorrectionAnswer, CorrectionResult
from closet.tagger.schema import Details, ItemTags, Silhouette
from closet.tagger.tagging import RouteUnavailable, TaggingError, TagResult

PASSPHRASE = "correct horse battery"


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
