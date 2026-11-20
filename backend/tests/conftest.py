import io
import json
import re
import sys
import urllib.error
import zlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pydantic import BaseModel

from closet import app as app_module
from closet import weather
from closet.config import Config
from closet.drawing import drawn
from closet.tagger.correcting import Change, CorrectionAnswer, CorrectionResult
from closet.tagger.garments import Garment, Garments
from closet.tagger.schema import Details, ItemTags, Silhouette
from closet.tagger.shoedrawing import CheckAnswer, CorrectAnswer, CorrectCheckAnswer, DrawAnswer
from closet.tagger.stylist import ChatReply
from closet.tagger.tagging import RouteUnavailable, TaggingError, TagResult
from closet.tagger.views import PhotoView, ShoeViews

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


# How the stand-ins sort a shoe's photos into views, by their place in the order sent: the outer side, from above, the
# inner side, the front, the back, the sole. The two sides are unsure, and look different once both are there, so
# the owner is asked which photo shows the outside.
VIEW_ORDER = ("outer", "top", "inner", "front", "back", "sole")


def views_answer(count: int) -> ShoeViews:
    return ShoeViews(photos=[PhotoView(photo=n, view=VIEW_ORDER[n - 1], sure=VIEW_ORDER[n - 1] not in ("outer", "inner"))
                             for n in range(1, count + 1)], sides_differ=count >= 3)


# How the stand-ins draw a shoe: the feature sheet of a tan cap-toe dress shoe and, as its drawing, the dress shoe the
# owner liked (one of the worked examples, which passes the automatic checks); a check says it is good at once.
SHEET = {
    "kind": "tan cap-toe oxford (fairly sure)", "archetype": "cap-toe oxford",
    "archetype_front": "A slim, rounded toe box with a straight cap line across it; closed lacing on a narrow vamp; a "
                       "thin leather sole that barely shows past the upper.",
    "silhouette": {"toe": "round", "bulk": "slim", "height": "low", "sole": "thin flat"},
    "proportions": "The sole's front edge is a thin line under a tall toe box; the sole stands out very little.",
    "palette": [{"name": "tan leather", "hex": "#b5622f", "role": "upper"},
                {"name": "dark brown sole", "hex": "#5b3822", "role": "sole"},
                {"name": "brown laces", "hex": "#3a2a24", "role": "laces"}],
    "parts": [{"part": "toe cap", "colour": "tan leather", "where": "across the toe", "seen_from_front": True}],
    "signature": ["straight toe cap line", "closed lacing with five pairs of eyelets"],
    "one_side_mark": False, "front_pull_tab": False, "opening_front_y": 32.0, "top_y": 30.0, "instep_y": 30.0,
}


def draw_answer() -> DrawAnswer:
    return DrawAnswer.model_validate({"sheet": SHEET, "left": {"behind": "", "front": drawn.example("dress-shoe")},
                                      "right": None})


def check_answer(good: bool = True) -> CheckAnswer:
    return CheckAnswer.model_validate({"good": good, "problems": [] if good else ["The toe box was too narrow."],
                                       "sheet": SHEET, "left": {"behind": "", "front": drawn.example("dress-shoe")},
                                       "right": None})


# How the stand-ins change a drawing from the owner's note: the dress shoe with its laces black (the only shape the
# note is about), said to go against the photos, which show brown laces; a check says it is good at once.
BLACK_LACES = "the laces should be black"
AGAINST = "The photos show brown laces, not black; drawn as you asked."


def black_laces(svg: str) -> str:
    return re.sub("#3a2a24", "#111111", svg, flags=re.IGNORECASE)


def correct_answer(against: str | None = AGAINST) -> CorrectAnswer:
    sheet = {**SHEET, "palette": [*SHEET["palette"][:2], {"name": "black laces", "hex": "#111111", "role": "laces"}]}
    return CorrectAnswer.model_validate({"changed": "The laces are black now.", "against_photos": against,
                                         "sheet": sheet, "left": {"behind": "", "front": black_laces(drawn.example("dress-shoe"))},
                                         "right": None})


def correct_check_answer(good: bool = True, against: str | None = AGAINST) -> CorrectCheckAnswer:
    answer = correct_answer(against)
    return CorrectCheckAnswer.model_validate({"good": good, "problems": [] if good else ["The toe cap had moved."],
                                              "against_photos": against, "sheet": answer.sheet.model_dump(),
                                              "left": answer.left.model_dump(), "right": None})


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
        return () if self.mode == "unavailable" else ("plan",)   # "unreachable" looks usable until called

    def __call__(self, images, routes):
        self.calls.append(routes)
        assert images and images[0].mode == "RGBA"   # the cutout comes first
        if self.mode == "unavailable":
            raise RouteUnavailable("Claude Code is not signed in")
        if self.mode == "fails":
            raise TaggingError("the answer was outside the schema")
        if self.mode == "unreachable":   # a route looks usable, but Claude cannot be reached (offline, overloaded)
            from closet.tagger.tagging import Unreachable
            raise Unreachable("Claude could not be reached")
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
    """Stands in for the Anthropic API behind the API-key route (its `messages.parse`, and `messages.create` for
    describing an item); no test reaches the real one.

    Asked to describe an item (`create`, with the form as a tool), it calls the tool with `tag_answers` in turn, the
    last one again once they run out (ANSWER by default). Answers ANSWER (or, asked to read a correction, `correction`: two buttons; asked to sort a shoe's photos, `views`,
    else `views_answer` for the photos sent) and reports token counts as the real API does; `error` makes the next
    calls raise it instead. `requests` keeps what each call was sent. Asked to draw a shoe, or to check its drawing,
    which is streamed (`messages.stream`), it answers `drawing` (`draw_answer`) or `checked` (`check_answer`), as text
    in the answer's schema, turned or not; asked to change a drawing from the owner's note, or to check the change,
    `corrected` (`correct_answer`) or `correct_checked` (`correct_check_answer`); asked to judge drawings, the first,
    with no fault named. A message in the style conversation is answered with `chat` (a few words, one line to keep).
    """

    def __init__(self, input_tokens: int = 2000, output_tokens: int = 400):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.cache_write = self.cache_read = 0   # what each streamed answer says went to and came from the cache
        self.error: Exception | None = None
        self.calls = 0
        self.requests: list[dict] = []
        self.messages = self
        self.correction = CorrectionAnswer(changes=[Change(name="placket_buttons", value="2")], not_understood="",
                                           needs_photo=False)
        # asked where the pieces are in a 1024-pixel-wide pile photo: GARMENT_BOXES, in its pixels
        self.garments = Garments(garments=[Garment(name=b["label"], x0=b["x0"] * 1024, y0=b["y0"] * 768,
                                                   x1=b["x1"] * 1024, y1=b["y1"] * 768) for b in GARMENT_BOXES])
        self.views: ShoeViews | None = None
        self.drawing = draw_answer()
        self.checked = check_answer()
        self.corrected = correct_answer()
        self.correct_checked = correct_check_answer()
        self.tag_answers: list = [ANSWER]   # what describing an item answers, in turn: models, dicts, or None (no call)
        self.chat = ChatReply(reply="Noted: a little lighter than most.", remember=["I run warm."])

    def create(self, **kw):
        """Describing an item on the API-key route: the answer comes back as a call of the form's tool."""
        self.calls += 1
        self.requests.append(kw)
        if self.error:
            raise self.error
        usage = SimpleNamespace(input_tokens=self.input_tokens, output_tokens=self.output_tokens)
        answer = self.tag_answers[min(len(self.requests_to("create")) - 1, len(self.tag_answers) - 1)]
        if answer is None:   # answered in words, without calling the tool
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="A navy shirt.")], stop_reason="end_turn",
                                   usage=usage)
        data = answer.model_dump(mode="json") if isinstance(answer, BaseModel) else answer
        call = SimpleNamespace(type="tool_use", id=f"toolu_{self.calls}", name=kw["tools"][0]["name"], input=data)
        return SimpleNamespace(content=[call], stop_reason="tool_use", usage=usage)

    def requests_to(self, method: str) -> list[dict]:
        """The requests made with `create` (they carry `tools`) or the others."""
        return [r for r in self.requests if ("tools" in r) == (method == "create")]

    def stream(self, **kw):
        self.calls += 1
        self.requests.append(kw)
        if self.error:
            raise self.error
        props = kw["output_config"]["format"]["schema"]["properties"]
        if "best" in props:   # the judge, choosing between drawings: the first, with no fault named
            from closet.tagger.shoedrawing import Verdict
            answer = Verdict(observations="the panels", faults=["A: none", "B: none", "C: none"], best="a",
                             ranking=["a", "b", "c"])
        elif "against_photos" in props:   # changing a drawing from the owner's note, or checking the change
            answer = self.correct_checked if "good" in props else self.corrected
        else:
            answer = self.checked if "good" in props else self.drawing
        message = SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(answer.model_dump()))],
                                  stop_reason="end_turn",
                                  usage=SimpleNamespace(input_tokens=self.input_tokens, output_tokens=self.output_tokens,
                                                        cache_creation_input_tokens=self.cache_write,
                                                        cache_read_input_tokens=self.cache_read))

        class Stream:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: message)

            def __exit__(self, *exc):
                return False
        return Stream()

    def parse(self, **kw):
        self.calls += 1
        self.requests.append(kw)
        if self.error:
            raise self.error
        usage = SimpleNamespace(input_tokens=self.input_tokens, output_tokens=self.output_tokens)
        answer = {CorrectionAnswer: self.correction, Garments: self.garments,
                  ChatReply: self.chat}.get(kw.get("output_format"), ANSWER)
        if kw.get("output_format") is ShoeViews:
            sent = kw["messages"][0]["content"]
            answer = self.views or views_answer(sum(1 for part in sent if part.get("type") == "image"))
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
