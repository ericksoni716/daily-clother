"""The web API and the page it serves."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from . import (
    APP_NAME,
    __version__,
    access,
    additions,
    apikey,
    autostart,
    away,
    background,
    backup,
    climate,
    corrections,
    daynote,
    db,
    demo,
    gate,
    history,
    illustrations,
    images,
    instance,
    items,
    jobs,
    kept,
    kinds,
    life,
    outfits,
    patjobs,
    phone,
    picks,
    plans,
    productpage,
    progress,
    review,
    savedtrips,
    shoedraw,
    shoes,
    shoeviews,
    shop,
    shops,
    sizes,
    sources,
    spend,
    storage,
    styleahead,
    stylechat,
    stylejobs,
    styleprofile,
    stylequestions,
    tagjobs,
    tailnet,
    tracejobs,
    tripday,
    trips,
    updates,
    vocab,
    wears,
    wishlist,
    worn,
    wouldjobs,
)
from .config import PROFILES, Config, bundle_dir
from .cutout import make_cutout, predict_mask
from .insights import find_insights
from .modelstore import MODEL, SECOND_MODEL, ModelStore
from .state import HOME_PLACE, State
from .tagger import correcting
from .tagger import routes as tagger_routes
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable
from .today import closet_rows
from .today import suggest as suggest_today
from .weather import WeatherError, check_place, lookup, place_near, search_places

log = logging.getLogger("closet.app")

GAPS_ALL = 100   # gaps asked of the analysis; the list shows at most gaps.MAX_GAPS not yet decided on
TAGGING_FRESH_SECONDS = 10   # how long an answer of `GET /api/tagging` (Claude Code's sign-in) is given again


@dataclass
class Services:
    cfg: Config
    state: State
    model: ModelStore
    worker: jobs.Worker
    scheduler: backup.Scheduler
    web_dir: Path | None = None
    tag_worker: tagjobs.Worker | None = None
    pattern_worker: patjobs.Worker | None = None
    second_model: ModelStore | None = None   # asked as well when the first leaves a patterned item see-through
    corrector: corrections.Corrector = correcting.correct
    check_tagger: tagjobs.Tagger | None = None   # describes a photo for "Would this work?", recorded as its own purpose
    shopper: shop.Shopper | None = None           # searches shops for a wish and looks prices up again
    price_checks: shop.PriceScheduler | None = None   # looks prices up once a day while the program runs
    picker: picks.Picker | None = None            # "You might like": a look on a tap, and once a week on the same round
    finder: sources.Worker | None = None          # asks where each piece is in a photo of several
    views: shoeviews.Worker | None = None         # sorts a shoe's photos into views
    draws: shoedraw.Worker | None = None          # draws a shoe from its sorted photos
    additions: additions.Drawer | None = None      # draws the owner's line onto a garment's drawing (closet/additions.py)
    add_sorter: object = None                      # says what each photo chosen on Add shows (tagger/addsort.py)
    day_reader: object = None                      # reads the day in the owner's words (tagger/dayread.py)
    stylist: stylejobs.Stylist | None = None       # Claude choosing the day's outfits (closet/stylejobs.py); None: the rules only
    ahead: styleahead.Ahead | None = None          # asks Claude for the day's outfits before the owner's first look
    chat: stylechat.Chat | None = None             # the conversation about the owner's style (Settings, Your style)
    on_quit: Callable[[], None] = lambda: None
    on_show: Callable[[], bool] = lambda: False   # shows Nines' own window; False when there is none (the browser is used)
    # Windows keeping Nines running (closet/background.py): whether this copy is the background copy, and how an
    # ordinary copy hands its port over to it (the launcher starts this program afresh and quits)
    background_copy: bool = False
    on_hand_over: Callable[[], None] = lambda: None
    updater: updates.Updater | None = None   # new releases: checked once a day, installed when the owner says
    phone_watch: phone.Watch | None = field(default=None, repr=False)   # phone access, looked up in the background

    def __post_init__(self) -> None:
        if self.phone_watch is None:
            self.phone_watch = phone.Watch(self.cfg.port)

    def start(self) -> None:
        self.phone_watch.start()   # `tailscale` is asked now, so Settings has an answer when it is first opened
        if not self.model.ready and self.cfg.auto_download_model:
            self.model.keep_trying()   # a failed download heals by itself (modelstore.RETRY_DELAYS)
        self.worker.start()
        if self.tag_worker:
            self.tag_worker.start()
        if self.pattern_worker:
            self.pattern_worker.start()
        if self.finder:
            self.finder.start()
        if self.views:
            self.views.start()
        if self.draws:
            self.draws.start()
        if self.second_model is not None and not self.second_model.ready and self.cfg.auto_download_model:
            self.second_model.keep_trying()
        self.scheduler.start()
        if self.updater is not None:
            self.updater.start()
        if self.price_checks:
            self.price_checks.start()
        if self.ahead:
            self.ahead.start()

    def wake(self) -> None:
        """Nudge both queues (a new item, another closet opened)."""
        self.worker.wake()
        if self.tag_worker:
            self.tag_worker.wake()
        if self.pattern_worker:
            self.pattern_worker.wake()
        if self.finder:
            self.finder.wake()
        if self.views:
            self.views.wake()
        if self.draws:
            self.draws.wake()

    def stop(self) -> None:
        self.scheduler.stop()
        if self.updater is not None:
            self.updater.stop()
        if self.price_checks:
            self.price_checks.stop()
        if self.ahead:
            self.ahead.stop()
        if self.tag_worker:
            self.tag_worker.stop()
        if self.pattern_worker:
            self.pattern_worker.stop()
        if self.finder:
            self.finder.stop()
        if self.views:
            self.views.stop()
        if self.draws:
            self.draws.stop()
        self.worker.stop()
        self.model.stop()
        if self.second_model is not None:
            self.second_model.stop()

    def phone_info(self) -> dict | None:
        """Phone access as last looked up, at once; None until the first lookup is in (`phone.Watch`)."""
        return self.phone_watch.current()


def build_services(cfg: Config, cutter: jobs.Cutter | None = None, web_dir: Path | str | None = "bundled",
                   tagger: tagjobs.Tagger | None = None, routes: tagjobs.Routes | None = None, api_client=None,
                   corrector: corrections.Corrector | None = None, measurer: patjobs.Measurer | None = None,
                   landmarker: patjobs.Landmarker | None = None, shop_asker: shop.Asker | None = None,
                   finder: sources.Finder | None = None, tracer: tracejobs.Tracer | None = None,
                   sorter: shoeviews.Sorter | None = None, drawer: shoedraw.Drawer | None = None,
                   drawing_corrector: shoedraw.Corrector | None = None, add_sorter=None,
                   side_drawer: shoedraw.Sider | None = None, day_reader=None, stylist_ask: stylejobs.Asker | None = None,
                   stylist_look: stylejobs.Looker | None = None, chat_ask: stylechat.Asker | None = None,
                   side_corrector: shoedraw.SideCorrector | None = None, adder: additions.Adder | None = None,
                   page_reader: productpage.Reader | None = None) -> Services:
    """Open the settings, bring the closet database up to date and wire the background workers.

    `web_dir` is the built page to serve: "bundled" looks for the one shipped
    with the program, None serves no page (tests), or give a folder. `tagger`,
    `routes` and `corrector` stand in for Claude in tests; by default the real routes are used, each call recorded and
    the API key kept under its monthly limit. `api_client` stands in for the API alone (tests), behind that same limit.
    `shop_asker` stands in for Claude searching shops and looking up prices (tests), `finder` for Claude finding
    the pieces in a photo of several (tests). `tracer` traces shoes from their photos; tests standing in for Claude
    trace none unless they give one. `sorter` stands in for Claude sorting a shoe's photos into views (tests); tests
    standing in for Claude sort none unless they give one. `drawer` stands in for Claude drawing a shoe from its
    sorted photos (tests); tests standing in for Claude draw none unless they give one. `drawing_corrector` stands in
    for Claude changing a shoe's drawing from the owner's note (tests); tests standing in for Claude change none unless
    they give one. `side_drawer` stands in for Claude drawing the side of a shoe drawn without one (tests); tests
    standing in for Claude draw no sides by themselves unless they give one. `side_corrector` stands in for Claude
    changing a shoe's side drawing from the owner's note (tests); tests standing in for Claude change none unless they
    give one. `chat_ask` stands in for Claude in the
    style conversation (tests); tests standing in for Claude have no conversation unless they give one. `adder` stands
    in for Claude adding to a garment's drawing at the owner's word (`tagger.adding.add` without its routes, meter and
    client; tests); tests standing in for Claude draw nothing on unless they give one. `page_reader` reads a product's
    page sent as a link (`productpage.Reader`, whose two edges to the web tests stand in for).
    """
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    state = State(cfg.state_path)
    backup.recover(cfg)   # a restore cut short is finished or undone before the closet is opened
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    if state.get("profile") == "demo":
        demo.ensure(cfg)
    conn = db.connect(cfg.db_path(state.get("profile")))
    try:
        jobs.requeue_interrupted(conn)
        additions.recover(conn)   # a line being drawn onto a drawing when Nines stopped: the page says to send it again
    finally:
        conn.close()
    holder: dict = {}
    model = ModelStore(cfg.models_dir, state, on_ready=lambda: holder["worker"].wake())

    # once it is here, the cutouts made without it are looked at again (`jobs.recheck`)
    second = ModelStore(cfg.models_dir, state, name=SECOND_MODEL, url_key="second_model_url",
                        on_ready=lambda: holder["worker"].wake())

    def real_cutter(img: Image.Image) -> Image.Image:
        mask = predict_mask(img, MODEL, model.path)
        if second.ready:
            from .patterns import masks  # OpenCV: loaded only once a cutout is made
            # a plaid's dark checks taken for background, or the duvet under a jacket kept with it: ask the other
            # model, keep what the two agree on, and leave out a surface the garment only lies on
            if masks.doubtful(img, mask):
                mask = masks.settle(img, mask, predict_mask(img, SECOND_MODEL, second.path), log.info)
        return make_cutout(img, mask)[0]

    meter = spend.Meter(cfg, state)

    def real_tagger(images: list[Image.Image], usable: tuple[str, ...]):
        return tagjobs.claude_tagger(images, usable, meter=meter, client=api_client)

    reading = spend.Meter(cfg, state, spend.PURPOSE_CORRECT, spend.estimate_correction)

    def real_corrector(sentence: str, description: dict, allowed: dict, images: list, usable: tuple[str, ...]):
        return correcting.correct(sentence, description, allowed, images, usable, client=api_client, meter=reading)

    check_meter = spend.Meter(cfg, state, wouldjobs.PURPOSE)

    def check_tagger(images: list[Image.Image], usable: tuple[str, ...]):
        return tagjobs.claude_tagger(images, usable, meter=check_meter, client=api_client)

    def model_mask(img: Image.Image):
        return np.asarray(predict_mask(img, MODEL, model.path)) if model.ready else None

    if tracer is None and tagger is None:
        tracer = tracejobs.tracer(model_mask if cutter is None else None)
    tag_worker = tagjobs.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)), tagger or real_tagger)
    def cutouts_made() -> None:   # the next step for each: describing it, or measuring its pattern from the new cutout
        tag_worker.wake()
        if holder.get("patterns") is not None:
            holder["patterns"].wake()

    worker = jobs.Worker(cfg, state, lambda: model.ready, cutter or real_cutter, on_done=cutouts_made, tracer=tracer,
                         second=(lambda: second.ready) if cutter is None else None)
    holder["worker"] = worker
    landmark_meter = spend.Meter(cfg, state, spend.PURPOSE_LANDMARKS, spend.estimate_landmarks)

    def real_landmarker(cut: Image.Image, usable: tuple[str, ...]) -> dict:
        from .tagger import landmarks
        return landmarks.ask(cut, usable, client=api_client, meter=landmark_meter)

    def real_measurer(cut, pattern, words, marks, surface=None, category=None):
        if pattern == patjobs.SURFACE:   # the cloth Claude described, sized and pieced from the photo
            from .patterns.surface import kept_for_item  # OpenCV: loaded only when a pattern is measured
            return kept_for_item(cut, surface, marks, category)
        from .patterns.measure import measure  # OpenCV: loaded only when a pattern is measured
        return measure(cut, pattern, words, marks)

    pattern_worker = patjobs.Worker(cfg, state, measurer or real_measurer,
                                    landmarker if landmarker is not None else (None if tagger else real_landmarker),
                                    routes or (lambda: tagjobs.usable_routes(state)))
    if measurer is None and tagger is not None:
        pattern_worker = None    # tests standing in for Claude measure no patterns unless they ask to
    holder["patterns"] = pattern_worker
    model.refresh()  # know the model's real state before the first request is answered
    if web_dir == "bundled":
        candidate = bundle_dir() / "web"
        web_dir = candidate if (candidate / "index.html").exists() else None
    second.refresh()
    views_meter = spend.Meter(cfg, state, spend.PURPOSE_VIEWS, spend.estimate_views)

    def real_sorter(photos: list[Image.Image], usable: tuple[str, ...]):
        from .tagger import views
        return views.ask(photos, usable, client=api_client, meter=views_meter)

    def no_sorter(photos: list[Image.Image], usable: tuple[str, ...]):
        raise RouteUnavailable("tests standing in for Claude sort no photos unless they ask to")

    views_worker = shoeviews.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)),
                                    sorter or (no_sorter if tagger is not None else real_sorter))
    add_meter = spend.Meter(cfg, state, spend.PURPOSE_SORT_ADD, spend.estimate_sort_add)

    def real_add_sorter(photos: list[Image.Image], usable: tuple[str, ...]):
        from .tagger import addsort
        return addsort.ask(photos, usable, client=api_client, meter=add_meter)

    def no_add_sorter(photos: list[Image.Image], usable: tuple[str, ...]):
        raise RouteUnavailable("tests standing in for Claude sort no photos on Add unless they ask to")
    day_meter = spend.Meter(cfg, state, spend.PURPOSE_DAY, spend.estimate_day)

    def real_day_reader(text: str, today, home: str | None, usable: tuple[str, ...]):
        from .tagger import dayread
        return dayread.ask(text, today, home, usable, client=api_client, meter=day_meter)

    def no_day_reader(text: str, today, home: str | None, usable: tuple[str, ...]):
        raise RouteUnavailable("tests standing in for Claude read no day notes unless they ask to")
    style_meter = spend.Meter(cfg, state, spend.PURPOSE_STYLE, spend.estimate_style)

    def real_stylist(brief: dict, usable: tuple[str, ...]) -> dict:
        from .tagger import stylist
        return stylist.given(stylist.ask(brief, usable, client=api_client, meter=style_meter))

    def real_look(brief: dict, pictures: list, usable: tuple[str, ...]) -> dict:
        from .tagger import stylist
        return stylist.seen(stylist.look(brief, pictures, usable, client=api_client, meter=style_meter))

    def draw_outfits(path, found: list[dict]) -> list:
        """Each outfit drawn as worn on the figure, as a picture for Claude to look at."""
        import io

        from PIL import Image

        from .drawing import drawn
        from .tagger import stylist
        conn = db.connect(path)
        try:
            return [Image.open(io.BytesIO(drawn.render_png(
                illustrations.outfit_figure(conn, {k: v for k, v in o["pieces"].items() if v}),
                stylist.PICTURE_WIDTH, background="#ffffff"))).convert("RGB") for o in found]
        finally:
            conn.close()

    chat_meter = spend.Meter(cfg, state, spend.PURPOSE_STYLE_CHAT, spend.estimate_style_chat)

    def real_chat(brief: dict, usable: tuple[str, ...]) -> dict:
        from .tagger import stylist
        return stylist.chatted(stylist.chat(brief, usable, client=api_client, meter=chat_meter))

    talk = chat_ask or (None if tagger is not None else real_chat)

    # tests standing in for Claude get no stylist unless they give one: Today is then the rules engine's, as before
    choose = stylist_ask or (None if tagger is not None else real_stylist)
    # the real stylist looks at its outfits as drawn; a stand-in does when the test gives a look of its own
    looker = stylist_look or (real_look if choose is real_stylist else None)
    draw_meter = spend.Meter(cfg, state, spend.PURPOSE_DRAW, spend.estimate_draw)

    def real_drawer(photos: list, usable: tuple[str, ...], notes=(), style=None, measures=None, side_notes=()):
        from .tagger import shoedrawing
        return shoedrawing.draw(photos, usable, client=api_client, meter=draw_meter, notes=notes, style=style,
                                mask_of=model_mask, measures=measures, side_notes=side_notes)

    def no_drawer(photos: list, usable: tuple[str, ...], notes=(), style=None, measures=None, side_notes=()):
        raise RouteUnavailable("tests standing in for Claude draw no shoes unless they ask to")

    def real_side_drawer(photos: list, usable: tuple[str, ...], sheet=None, notes=(), measures=None, side_notes=()):
        from .tagger import shoedrawing
        return shoedrawing.draw_side(photos, usable, client=api_client, meter=draw_meter, sheet=sheet, notes=notes,
                                     measures=measures, mask_of=model_mask, side_notes=side_notes)

    correct_meter = spend.Meter(cfg, state, spend.PURPOSE_CORRECT_DRAWING, spend.estimate_correct_drawing)

    def real_drawing_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...]):
        from .tagger import shoedrawing
        return shoedrawing.correct(photos, kept, note, usable, client=api_client, meter=correct_meter)

    def no_drawing_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...]):
        raise RouteUnavailable("tests standing in for Claude change no drawings unless they ask to")

    def real_side_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...], measures=None):
        from .tagger import shoedrawing
        return shoedrawing.correct_side(photos, kept, note, usable, client=api_client, meter=correct_meter,
                                        measures=measures, mask_of=model_mask)

    def no_side_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...], measures=None):
        raise RouteUnavailable("tests standing in for Claude change no side drawings unless they ask to")

    draw_worker = shoedraw.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)),
                                  drawer or (no_drawer if tagger is not None else real_drawer),
                                  corrector=drawing_corrector or (no_drawing_corrector if tagger is not None
                                                                  else real_drawing_corrector),
                                  sider=side_drawer or (None if tagger is not None else real_side_drawer),
                                  side_corrector=side_corrector or (no_side_corrector if tagger is not None
                                                                    else real_side_corrector))
    views_worker.on_sorted = draw_worker.wake   # a shoe sorted for the first time is drawn next

    def described() -> None:   # patterns are measured, shoes traced and their photos sorted next
        worker.wake()
        if pattern_worker:
            pattern_worker.wake()
        views_worker.wake()

    tag_worker.on_described = described
    finding_meter = spend.Meter(cfg, state, spend.PURPOSE_GARMENTS, spend.estimate_garments)

    def real_finder(photo: Image.Image, usable: tuple[str, ...]) -> list[dict]:
        from .tagger import garments
        return garments.ask(photo, usable, client=api_client, meter=finding_meter)

    def no_finder(photo: Image.Image, usable: tuple[str, ...]) -> list[dict]:
        raise RouteUnavailable("tests standing in for Claude find no pieces unless they ask to")

    finding = sources.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)),
                             finder or (no_finder if tagger is not None else real_finder))
    shopper = shop.Shopper(cfg, state, lambda profile: closet_inputs(cfg, profile), tag_worker.routes,
                           shop_asker or shop.ClaudeAsker(cfg, state, client=api_client), page_reader)
    picker = picks.Picker(shopper)
    sv = Services(cfg, state, model, worker, backup.Scheduler(cfg, state), web_dir, tag_worker=tag_worker,
                  pattern_worker=pattern_worker, second_model=second if cutter is None else None,
                  corrector=corrector or real_corrector,
                  check_tagger=tagger or check_tagger, shopper=shopper, picker=picker,
                  price_checks=shop.PriceScheduler(shopper, also=(picker.tick,)),
                  finder=finding, views=views_worker, draws=draw_worker, updater=updates.Updater(cfg, state),
                  add_sorter=add_sorter or (no_add_sorter if tagger is not None else real_add_sorter),
                  day_reader=day_reader or (no_day_reader if tagger is not None else real_day_reader),
                  stylist=stylejobs.Stylist(choose, routes or (lambda: tagjobs.usable_routes(state)), draw=draw_outfits,
                                            look=looker) if choose else None,
                  chat=stylechat.Chat(talk, routes or (lambda: tagjobs.usable_routes(state))) if talk else None)
    sv.ahead = styleahead.Ahead(cfg, state, lambda: sv.stylist)

    add_meter = spend.Meter(cfg, state, spend.PURPOSE_ADD_TO_DRAWING, spend.estimate_add_to_drawing)

    def no_adder(*args, **kwargs):
        raise RouteUnavailable("tests standing in for Claude draw nothing onto drawings unless they ask to")

    def adder_now() -> additions.Adder:
        from .tagger import adding
        usable = (routes or (lambda: tagjobs.usable_routes(state)))()
        given = adder or (no_adder if tagger is not None else adding.add)
        return lambda *a: given(*a, routes=usable, client=api_client, meter=add_meter)
    sv.additions = additions.Drawer(adder_now)
    return sv


def closet_inputs(cfg: Config, profile: str) -> tuple[list[dict], list[dict]]:
    """A closet's item rows and wear log, as the gap analysis and "Would this work?" read them."""
    conn = db.connect(cfg.db_path(profile))
    try:
        rows = closet_rows(conn)
        worn = [{"item_id": r["item_id"], "worn_on": r["worn_on"]}
                for r in conn.execute("SELECT item_id, worn_on FROM wears ORDER BY item_id, worn_on")]
    finally:
        conn.close()
    return rows, worn


class ProfileChoice(BaseModel):
    profile: str


class ModelUrl(BaseModel):
    url: str | None = None


# the routes that correct an item answer wrong input with a sentence, not pydantic's list of errors
CORRECTING = re.compile(r"^/api/items/[^/]+/(details|kind|correct|correct/confirm|history/[^/]+/undo)$")
PLAIN_INPUT = {
    "sentence": "Write the correction as words.",
    "changes": "Send the changes to confirm as a list, each with a name and a value.",
    "details": "Send the details to change as names, each with its new value.",
    "kind": "Send the kind to choose, as its name in the list.",
    "change_id": "That is not a change in this item's history.",
}


def plain_input(e: RequestValidationError) -> str:
    for err in e.errors():
        for part in err.get("loc", ()):
            if part in PLAIN_INPUT:
                return PLAIN_INPUT[part]
    if any(err.get("type") == "json_invalid" for err in e.errors()):
        return "The request could not be read: it is not valid JSON."
    return "The request is not in the form this needs."


class DetailsBody(BaseModel):
    details: dict


class KindBody(BaseModel):
    kind: str


class Sentence(BaseModel):
    sentence: str


class Confirmed(BaseModel):
    sentence: str
    changes: list


class WearDay(BaseModel):
    worn_on: str | None = None
    model_config = {"extra": "forbid"}


class WearMany(BaseModel):
    item_ids: list[str]
    worn_on: str | None = None
    outfit: dict | None = None
    model_config = {"extra": "forbid"}


class WearManyDay(BaseModel):
    item_ids: list[str]
    worn_on: str
    outfit_id: str | None = None
    model_config = {"extra": "forbid"}


class OutfitByHand(BaseModel):
    item_ids: list[str]
    worn_on: str | None = None
    model_config = {"extra": "forbid"}


class OutfitRating(BaseModel):
    rating: str | None = None
    reasons: list[str] = []
    note: str | None = None
    model_config = {"extra": "forbid"}


class LaundryState(BaseModel):
    state: str
    # what marking it clean answered, sent back with "laundry" to put it back as it was (`wears.set_laundry`)
    undo: object = None


class AwayChoice(BaseModel):
    """Where a piece is going: "cleaner", "tailor" or "lent", with the day it is expected back and a note (`away.py`)."""
    place: str
    until: str | None = None
    note: str | None = None
    since: str | None = None
    model_config = {"extra": "forbid"}


class Confirm(BaseModel):
    fields: list[str]
    model_config = {"extra": "forbid"}


class Check(BaseModel):
    kind: str | None = None
    changes: dict = {}
    fields: list[str] = []
    model_config = {"extra": "forbid"}


class ApiKeyBody(BaseModel):
    key: str
    model_config = {"extra": "forbid"}


class UpdateChoice(BaseModel):
    mode: str
    model_config = {"extra": "forbid"}


class SettingsPatch(BaseModel):
    backup_folder: str | None = None
    autostart: bool | None = None
    tagging_api_enabled: bool | None = None
    tagging_api_cap_usd: float | None = None
    tagging_route_order: str | None = None
    place: dict | None = None
    life: object = None
    life_prompt_dismissed: bool | None = None
    rewear: object = None
    laundry: object = None
    stylist_on: bool | None = None
    show_drawings: bool | None = None
    cloudflare_team: str | None = None   # the door through Cloudflare (closet/access.py); an empty value clears one
    cloudflare_aud: str | None = None
    cloudflare_host: str | None = None
    model_config = {"extra": "forbid"}


CLOUDFLARE_FIELDS = (access.TEAM_KEY, access.AUD_KEY, access.HOST_KEY)
NOT_FROM_CLOUDFLARE = "Change this on the computer Nines runs on, or from your phone or another computer through Tailscale."
# the passphrase's session cookie, from before the door decided who comes in; ignored, and taken away by /api/session
OLD_SESSION_COOKIE = "closet_session"


def create_app(sv: Services, window_key: str | None = None, *, access_keys: access.SigningKeys | None = None,
               tailscale_check: tailnet.Check | None = None) -> FastAPI:
    """The web app. `window_key` is the key of Nines' own window (`gate.window_key`): the launcher always gives it,
    and then a request by this computer's own name must carry it (closet/gate.py). Tests give none.

    `access_keys` stands in for Cloudflare's published keys (tests); without it they are fetched from the team.
    `tailscale_check` says whether a connection is the Tailscale service's; without it, the one for this computer
    (`tailnet.checker()`: on Windows, asked of Windows; elsewhere none, and Tailscale is believed)."""
    app = FastAPI(title=APP_NAME, version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    cfg, state = sv.cfg, sv.state
    # while Windows keeps Nines running, the API key is also kept sealed in the data folder, for a copy started before
    # sign-in that cannot read Credential Manager (closet/apikey.py)
    apikey.keep_sealed(background.key_changed(cfg))

    # ---------------------------------------------------------------- helpers
    # each door's check (the address, Tailscale's word, Cloudflare's sign-in, the window's key), the page's header and
    # the size limits, before any body is read; who came in is recorded there too, for the routes (`gate.came_in`)
    app.add_middleware(gate.Gate, key=window_key,
                       key_cookie=gate.key_cookie(cfg.port), cloudflare=lambda: access.load(state), keys=access_keys,
                       tailscale_check=tailscale_check or tailnet.checker())

    # laundry that keeps itself: the owner's counts and laundry day (Settings), read live
    wears.set_policy(lambda: wears.policy_from(state.get("laundry"), savedtrips.rewear(state)))

    def conn_dep():
        path = cfg.db_path(state.get("profile"))
        conn = db.connect(path)
        try:
            wears.catch_up(conn, str(path))   # what the last laundry day washed is clean before anything is read
        except Exception:   # never in the way of the request itself
            log.exception("the laundry could not be brought up to date")
        try:
            yield conn
        finally:
            conn.close()

    def images_dir() -> Path:
        return cfg.images_dir(state.get("profile"))

    @app.exception_handler(items.ItemError)
    async def item_error(_: Request, e: items.ItemError):
        return JSONResponse({"detail": e.message}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, e: RequestValidationError):
        if request.url.path == "/api/settings/api-key":
            return JSONResponse({"detail": "Enter the API key as text, with no other fields."}, status_code=422)
        if CORRECTING.match(request.url.path):
            return JSONResponse({"detail": plain_input(e)}, status_code=422)
        return await request_validation_exception_handler(request, e)

    @app.exception_handler(images.ImageError)
    async def image_error(_: Request, e: images.ImageError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    # ------------------------------------------------------- the first calls
    @app.get("/api/health")
    def health():
        return {"app": "closet", "status": "ok", "version": __version__, "model_state": sv.model.info()["state"],
                "profile": state.get("profile")}

    @app.get("/api/session")
    def session(request: Request, response: Response):
        """What the page opens with. `authenticated` is always true now that the door decides who comes in: a page
        from Nines 0.12.0 or earlier reads it, and would otherwise show its passphrase screen. The old session cookie
        is taken away when one is sent (it is ignored either way)."""
        if OLD_SESSION_COOKIE in request.cookies:
            response.delete_cookie(OLD_SESSION_COOKIE, path="/")
        return {"authenticated": True, "version": __version__, "profile": state.get("profile")}

    # The passphrase's own calls are gone. A page from an older Nines still open somewhere (or kept by its service
    # worker) may call them; it shows the sentence it is given, so it is told to reload, which brings the new page.
    @app.post("/api/setup")
    @app.post("/api/login")
    @app.post("/api/logout")
    def passphrase_gone():
        raise HTTPException(410, gate.OLD_PAGE)

    # ------------------------------------------------------------------ items
    @app.get("/api/vocab")
    def get_vocab():
        return {**vocab.as_dict(), "kind_groups": kinds.catalogue()["groups"], "shades": items.shades()}

    @app.get("/api/kinds")
    def get_kinds():
        return kinds.catalogue()

    @app.get("/api/kinds/{kind}.svg")
    def get_kind_drawing(kind: str, color: str = kinds.TILE_HEX):
        if kind not in kinds.KINDS:
            raise HTTPException(404, "There is no such kind.")
        svg = kinds.drawing(kind, color.lower())
        if svg is None:
            raise HTTPException(404, "This kind has no drawing.")
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "private, max-age=86400", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.get("/api/items")
    def list_items(status: str = "active", category: str | None = None, q: str | None = None, laundry: str | None = None,
                   conn=Depends(conn_dep)):
        if status not in ("active", "archived"):
            raise HTTPException(422, "Status must be active or archived.")
        if laundry is not None and laundry not in wears.LAUNDRY:
            raise HTTPException(422, "The laundry filter must be clean or laundry.")
        return {"items": items.list_items(conn, status, category, q, laundry)}

    @app.post("/api/items")
    async def create_item(response: Response, photo: UploadFile = File(...), client_key: str | None = Form(None),
                          name: str | None = Form(None), photo_sha256: str | None = Form(None), shoe: bool = Form(False),
                          conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        # decoding, resizing and encoding a photo takes a fifth of a second or more: on a worker thread, so the other
        # requests of an import (and the closet's polling) are not held up behind it
        item, created = await run_in_threadpool(items.create_from_photo, conn, images_dir(), data, client_key, name,
                                                photo_sha256 or None, shoe=shoe, demo=state.get("profile") == "demo")
        response.status_code = 201 if created else 200
        sv.worker.wake()
        return item

    @app.get("/api/progress")
    def get_progress(conn=Depends(conn_dep)):
        # asked every few seconds while work runs: only the items under way, with what the program waits on
        # cutouts wait for what their worker waits for (the model, unless a cutter stands in for it in tests)
        model = "ready" if sv.worker.is_ready() else sv.model.info()["state"]
        waits = progress.Waits(model=model, claude=bool(sv.tag_worker and sv.tag_worker.blocked))
        return progress.listing(conn, waits)

    @app.get("/api/items/{item_id}")
    def get_item(item_id: str, conn=Depends(conn_dep)):
        return items.detail(conn, items.get(conn, item_id))

    @app.get("/api/items/{item_id}/illustration.svg")
    def get_illustration(item_id: str, v: str | None = None, conn=Depends(conn_dep)):
        svg = illustrations.current(conn, items.get(conn, item_id))["illustration_svg"]
        if svg is None:
            raise HTTPException(404, "This item has no illustration yet.")
        # Only cache the drawing under its own version, not an old address another tab still has.
        cache = "private, max-age=31536000, immutable" if v == hashlib.sha256(svg.encode()).hexdigest() else "no-store"
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": cache, "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.get("/api/items/{item_id}/back.svg")
    def get_back(item_id: str, v: str | None = None, conn=Depends(conn_dep)):
        svg = illustrations.back(items.get(conn, item_id))
        if svg is None:
            raise HTTPException(404, "This item has no drawing from the back.")
        cache = "private, max-age=31536000, immutable" if v == hashlib.sha256(svg.encode()).hexdigest() else "no-store"
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": cache, "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    def _traced_soon(item) -> None:
        """An item just said to be a shoe waits to be traced (and its photos to be sorted): the queues need not wait
        for their next round."""
        if isinstance(item, dict) and (item.get("trace") or {}).get("state") == "waiting":
            sv.worker.wake()
        if isinstance(item, dict) and (item.get("views") or {}).get("state") == "waiting" and sv.views:
            sv.views.wake()

    @app.patch("/api/items/{item_id}")
    async def patch_item(item_id: str, request: Request, conn=Depends(conn_dep)):
        try:
            changes = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(changes, dict):
            raise HTTPException(422, "Send an object of fields to change.")
        # a change redraws the item (and a busy closet can keep the write waiting): on a worker thread, so the other
        # requests (the closet's polling among them) are answered meanwhile
        saved = await run_in_threadpool(items.update, conn, item_id, changes)
        _traced_soon(saved)
        return saved

    @app.delete("/api/items/{item_id}", status_code=204)
    def delete_item(item_id: str, conn=Depends(conn_dep)):
        items.delete(conn, images_dir(), item_id)
        return Response(status_code=204)

    @app.post("/api/items/{item_id}/retry-cutout", status_code=202)
    def retry_cutout(item_id: str, conn=Depends(conn_dep)):
        item = items.retry_cutout(conn, item_id)
        sv.worker.wake()
        return item

    # ---------------------------------------------- a shoe traced from its photo
    async def shoe_body(request: Request):
        try:
            return await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")

    @app.post("/api/items/{item_id}/trace/fix")
    async def fix_trace(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        return await run_in_threadpool(shoes.fix, conn, item_id, body)   # redraws the shoe

    @app.put("/api/items/{item_id}/trace/plain")
    async def plain_trace(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        return await run_in_threadpool(shoes.set_plain, conn, item_id,   # redraws the shoe
                                       body.get("plain") if isinstance(body, dict) else None)

    @app.post("/api/items/{item_id}/retrace", status_code=202)
    def retrace(item_id: str, conn=Depends(conn_dep)):
        item = shoes.retrace(conn, item_id)
        sv.worker.wake()
        return item

    def views_soon() -> None:
        """A shoe's photos changed: a new main photo is cut out and traced again, and the photos are sorted again."""
        sv.worker.wake()
        if sv.views:
            sv.views.wake()

    @app.post("/api/items/{item_id}/photo")
    async def replace_photo(item_id: str, photo: UploadFile = File(...), photo_sha256: str | None = Form(None),
                            conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        # a shoe is traced again from its new photo; anything else is cut out, described and measured again
        retake = shoes.replace_photo if tracejobs.wanted(items.get(conn, item_id)["category"]) else items.replace_photo
        item = await run_in_threadpool(retake, conn, images_dir(), item_id, data, photo_sha256 or None,
                                       demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.post("/api/items/{item_id}/photos", status_code=201)
    async def add_photo(item_id: str, photo: UploadFile = File(...), view: str | None = Form(None),
                        photo_sha256: str | None = Form(None), conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        item = await run_in_threadpool(shoes.add_photo, conn, images_dir(), item_id, data, view or None,
                                       photo_sha256 or None, demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.delete("/api/items/{item_id}/photos/{photo_id}")
    def remove_photo(item_id: str, photo_id: str, conn=Depends(conn_dep)):
        item = shoes.remove_photo(conn, images_dir(), item_id, photo_id, demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.put("/api/items/{item_id}/photos/{photo_id}/view")
    async def set_photo_view(item_id: str, photo_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        if not isinstance(body, dict) or "view" not in body:
            raise HTTPException(422, "Send the view as {\"view\": \"outer\"} (or inner, top, front, back, sole, other).")
        item = await run_in_threadpool(shoes.set_view, conn, item_id, photo_id, body["view"])
        sv.worker.wake()   # the answer may make another photo the main one: it is cut out and traced
        if sv.draws:
            sv.draws.wake()   # the answer may have settled the views: a shoe sorted for the first time is drawn next
        return item

    # ---------------------------------------------- a shoe drawn by Claude from its photos
    @app.post("/api/items/{item_id}/drawn", status_code=202)
    def draw_again(item_id: str, conn=Depends(conn_dep)):
        demo_closet = state.get("profile") == "demo"
        conn.execute("BEGIN IMMEDIATE")
        try:
            shoedraw.ask(conn, item_id, demo_closet)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        if sv.views:
            sv.views.wake()   # photos never sorted are sorted first
        if sv.draws:
            sv.draws.wake()
        return items.detail(conn, items.get(conn, item_id))

    @app.post("/api/items/{item_id}/drawn/correct", status_code=202)
    async def correct_drawing(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        note = body.get("note") if isinstance(body, dict) else None
        about = body.get("about", "front") if isinstance(body, dict) else "front"
        demo_closet = state.get("profile") == "demo"

        def work() -> None:
            conn.execute("BEGIN IMMEDIATE")
            try:
                shoedraw.correct(conn, item_id, note, demo_closet, about)
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

        await run_in_threadpool(work)
        if sv.draws:
            sv.draws.wake()
        return await run_in_threadpool(lambda: items.detail(conn, items.get(conn, item_id)))

    # ------------------------------------------------------- Claude adding to a garment's drawing
    @app.post("/api/items/{item_id}/additions", status_code=202)
    async def add_to_drawing(item_id: str, request: Request):
        body = await shoe_body(request)
        note = body.get("note") if isinstance(body, dict) else None
        profile = state.get("profile")
        path, folder = cfg.db_path(profile), cfg.images_dir(profile)

        def work() -> dict:
            conn = db.connect(path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    additions.start(conn, item_id, note, profile == "demo")
                    conn.execute("COMMIT")
                except Exception:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
                if sv.additions:
                    sv.additions.run(item_id, path, folder)
                return items.detail(conn, items.get(conn, item_id))
            finally:
                conn.close()
        return await run_in_threadpool(work)

    @app.post("/api/items/{item_id}/additions/back")
    def additions_back(item_id: str, conn=Depends(conn_dep)):
        conn.execute("BEGIN IMMEDIATE")
        try:
            additions.back(conn, item_id)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return items.detail(conn, items.get(conn, item_id))

    @app.delete("/api/items/{item_id}/additions")
    def additions_remove(item_id: str, conn=Depends(conn_dep)):
        conn.execute("BEGIN IMMEDIATE")
        try:
            additions.remove(conn, item_id)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return items.detail(conn, items.get(conn, item_id))

    @app.post("/api/items/{item_id}/drawn/back")
    def drawn_back(item_id: str, conn=Depends(conn_dep)):
        conn.execute("BEGIN IMMEDIATE")
        try:
            shoedraw.back(conn, item_id)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return items.detail(conn, items.get(conn, item_id))

    @app.get("/api/items/{item_id}/drawn.svg")
    def drawn_preview(item_id: str, conn=Depends(conn_dep)):
        from .drawing import drawn

        made = shoedraw.stored(items.get(conn, item_id))
        if made is None:
            raise HTTPException(404, "This shoe has not been drawn from its photos.")
        try:
            svg = drawn.preview_svg(made["left"], made.get("right"), view=drawn.VIEWS.get(made.get("view"), drawn.FRONT))
        except drawn.DrawingError:
            raise HTTPException(404, "This shoe's drawing can't be shown.")
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.get("/api/items/{item_id}/drawn/side.svg")
    def drawn_side(item_id: str, conn=Depends(conn_dep)):
        from .drawing import drawnside

        side = shoedraw.side_of(shoedraw.stored(items.get(conn, item_id)))
        if side is None:
            raise HTTPException(404, "This shoe has not been drawn from its side.")
        try:
            svg = drawnside.card_svg(side["svg"])
        except drawnside.drawn.DrawingError:
            raise HTTPException(404, "This shoe's side drawing can't be shown.") from None
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.post("/api/items/{item_id}/retag", status_code=202)
    def retag(item_id: str, conn=Depends(conn_dep)):
        if state.get("profile") == "demo":
            items.get(conn, item_id)
            raise HTTPException(409, "The demo closet is never sent to Claude; its descriptions were made in advance.")
        item = items.retag(conn, item_id)
        sv.wake()
        return item

    # ---------------------------------------------- correcting an item, and its history
    def not_in_demo(profile: str, conn, item_id: str) -> None:
        """Refuse to send a demo item to Claude. `profile` is read once by the route, and the same reading chooses
        the closet the item is read from, so a switch of closet meanwhile cannot let a demo item through."""
        if profile == "demo":
            items.get(conn, item_id)
            raise HTTPException(409, "The demo closet is never sent to Claude, so it can't read sentences here. "
                                     "Pick the details instead.")

    @app.get("/api/items/{item_id}/details")
    def detail_options(item_id: str, conn=Depends(conn_dep)):
        return corrections.options(items.get(conn, item_id))

    @app.get("/api/items/{item_id}/details/{name}")
    async def detail_choices(item_id: str, name: str):
        path = cfg.db_path(state.get("profile"))

        def work() -> dict:
            conn = db.connect(path)
            try:
                return corrections.choices(items.get(conn, item_id), name)
            finally:
                conn.close()
        return await run_in_threadpool(work)

    @app.put("/api/items/{item_id}/details")
    def set_details(item_id: str, body: DetailsBody, conn=Depends(conn_dep)):
        return corrections.apply(conn, item_id, body.details)

    @app.put("/api/items/{item_id}/kind")
    def set_kind(item_id: str, body: KindBody, conn=Depends(conn_dep)):
        saved = corrections.set_kind(conn, item_id, body.kind)
        _traced_soon(saved)
        return saved

    @app.post("/api/items/{item_id}/correct")
    async def correct_item(item_id: str, body: Sentence):
        profile = state.get("profile")
        path, folder = cfg.db_path(profile), cfg.images_dir(profile)

        def work() -> dict:
            conn = db.connect(path)
            try:
                not_in_demo(profile, conn, item_id)
                routes = sv.tag_worker.routes() if sv.tag_worker else ()
                return corrections.understand(conn, folder, item_id, body.sentence, routes, sv.corrector)
            finally:
                conn.close()
        # asking Claude takes a while; other requests keep being answered meanwhile
        return await run_in_threadpool(work)

    @app.post("/api/items/{item_id}/correct/confirm")
    def confirm_correction(item_id: str, body: Confirmed):
        profile = state.get("profile")
        conn = db.connect(cfg.db_path(profile))
        try:
            not_in_demo(profile, conn, item_id)
            return corrections.confirm(conn, item_id, body.sentence, body.changes)
        finally:
            conn.close()

    @app.get("/api/items/{item_id}/history")
    def item_history(item_id: str, conn=Depends(conn_dep)):
        items.get(conn, item_id)
        return history.listing(conn, item_id)

    @app.post("/api/items/{item_id}/history/{change_id}/undo")
    def undo_change(item_id: str, change_id: int, conn=Depends(conn_dep)):
        saved = corrections.undo(conn, item_id, change_id)
        _traced_soon(saved["item"])
        return saved

    @app.get("/api/items/{item_id}/wears")
    def list_wears(item_id: str, conn=Depends(conn_dep)):
        return {"wears": wears.list_wears(conn, item_id)}

    @app.post("/api/items/{item_id}/wears")
    def add_wear(item_id: str, response: Response, body: WearDay | None = None, conn=Depends(conn_dep)):
        item, created = wears.add(conn, item_id, body.worn_on if body else None)
        response.status_code = 201 if created else 200
        return item

    @app.delete("/api/items/{item_id}/wears/{worn_on}")
    def remove_wear(item_id: str, worn_on: str, conn=Depends(conn_dep)):
        return wears.remove(conn, item_id, worn_on)

    @app.post("/api/wears")
    def add_wears(body: WearMany, response: Response, conn=Depends(conn_dep)):
        if body.outfit is not None:
            result = worn.wear(conn, body.item_ids, body.worn_on, body.outfit)
        else:
            result = wears.add_many(conn, body.item_ids, body.worn_on)
        response.status_code = 201 if result["recorded"] or result.get("outfit") else 200
        return result

    @app.post("/api/wears/remove")
    def remove_wears(body: WearManyDay, conn=Depends(conn_dep)):
        if body.outfit_id is not None:
            return worn.undo(conn, body.item_ids, body.worn_on, body.outfit_id)
        return wears.remove_many(conn, body.item_ids, body.worn_on)

    @app.get("/api/outfits/worn")
    def list_worn(limit: int = worn.DEFAULT_PAGE, before: str | None = None, conn=Depends(conn_dep)):
        return worn.list_outfits(conn, limit, before)

    @app.post("/api/outfits/worn", status_code=201)
    def record_worn(body: OutfitByHand, conn=Depends(conn_dep)):
        return worn.record_by_hand(conn, body.item_ids, body.worn_on)

    @app.put("/api/outfits/worn/{outfit_id}/rating")
    def rate_worn(outfit_id: str, body: OutfitRating, conn=Depends(conn_dep)):
        return worn.rate(conn, outfit_id, body.rating, body.reasons, body.note)

    @app.delete("/api/outfits/worn/{outfit_id}", status_code=204)
    def remove_worn(outfit_id: str, conn=Depends(conn_dep)):
        worn.remove(conn, outfit_id)
        return Response(status_code=204)

    @app.post("/api/items/{item_id}/laundry")
    def set_laundry(item_id: str, body: LaundryState, conn=Depends(conn_dep)):
        return wears.set_laundry(conn, item_id, body.state, body.undo)

    # where a piece is: away at the cleaner's, at the tailor's or lent out, and back (`away.py`)
    @app.put("/api/items/{item_id}/away")
    def send_away(item_id: str, body: AwayChoice, conn=Depends(conn_dep)):
        return away.send(conn, item_id, body.place, body.until, body.note, body.since)

    @app.post("/api/items/{item_id}/back")
    def come_back(item_id: str, conn=Depends(conn_dep)):
        return away.back(conn, item_id)

    @app.post("/api/items/{item_id}/back/undo")
    def undo_come_back(item_id: str, conn=Depends(conn_dep)):
        return away.undo_back(conn, item_id)

    @app.get("/api/review")
    def review_queue(conn=Depends(conn_dep)):
        return review.queue(conn, describes=state.get("profile") != "demo")

    @app.post("/api/items/{item_id}/confirm")
    def confirm_fields(item_id: str, body: Confirm, conn=Depends(conn_dep)):
        return review.confirm(conn, item_id, body.fields)

    @app.post("/api/items/{item_id}/check")
    async def check_item(item_id: str, body: Check, conn=Depends(conn_dep)):
        # a new kind redraws the item: on a worker thread, as a change on the item page is
        saved = await run_in_threadpool(review.check, conn, item_id, body.kind, body.changes, body.fields)
        _traced_soon(saved)
        return saved

    @app.get("/media/{rel:path}")
    def media(rel: str):
        root = images_dir().resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "No such image.")
        return FileResponse(target, media_type="image/webp",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    # -------------------------------------------------------------- outfits
    @app.post("/api/outfits/today")
    async def outfits_today(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        path = cfg.db_path(state.get("profile"))

        def work() -> dict:
            conn = db.connect(path)
            # Claude chooses in the owner's own closet when it is switched on; the demo closet never asks Claude
            chooses = sv.stylist if state.get("profile") != "demo" and state.get("stylist_on") else None
            try:
                answer = suggest_today(conn, state, body, chooses, path)
            except outfits.ContextError as e:
                raise HTTPException(422, str(e))
            finally:
                conn.close()
            # what the page asked with is what is asked ahead tomorrow morning; another day is not today opened
            if state.get("profile") != "demo" and not (isinstance(body, dict) and body.get("day")):
                styleahead.remember(state, body, wears.today(), styleahead.now().hour)
            return answer

        # asks Open-Meteo (a few seconds at most) and compares many outfits, so keep it off the event loop
        return await run_in_threadpool(work)

    @app.post("/api/outfits/figure")
    async def outfit_figure(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        try:
            # a piece not in the closet (a find, a piece being checked) may be worn with the owner's own
            ids, new = illustrations.figure_request(body)
        except illustrations.FigureError as e:
            raise HTTPException(422, str(e))
        path = cfg.db_path(state.get("profile"))

        def work() -> str:
            conn = db.connect(path)
            try:
                return illustrations.outfit_figure(conn, ids, new)
            except illustrations.FigureError as e:
                raise HTTPException(422, str(e))
            finally:
                conn.close()

        # drawing a whole outfit takes a few milliseconds per piece: keep it off the event loop
        svg = await run_in_threadpool(work)
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    # ----------------------------------------------------------------- gaps
    gaps_cache: dict[str, tuple[str, dict]] = {}  # profile -> (what the closet and wear log were, the answer)
    # one analysis at a time per closet: whoever asks while it is being worked out waits for that answer
    gaps_locks = {profile: threading.Lock() for profile in PROFILES}

    def gap_inputs(profile: str) -> tuple[list[dict], list[dict]]:
        return closet_inputs(cfg, profile)

    def gap_analysis(profile: str | None = None, inputs: tuple[list[dict], list[dict]] | None = None) -> dict:
        """The open closet's gaps, all of them (cut to the list's length when marked); slow the first time.

        Worked out once and kept until the closet, the wear log or how the owner lives changes. Asked again while it
        is being worked out (the Wardrobe opened, reloaded and opened again, a search's finds judged meanwhile), the
        asker waits for that answer instead of working out the same seconds again beside it: side by side, each
        would take as long as all of them together."""
        profile = profile or state.get("profile")
        rows, worn = inputs or gap_inputs(profile)
        if profile == "demo":
            answers, home = life.example()
            dismissed = True
        else:
            answers = state.get("life")
            dismissed = state.get("life_prompt_dismissed")
            home = climate.lookup(state) if answers is not None else {
                "used": False, "place": None, "shares": None, "years": [], "old": False,
                "message": "Home weather is not being used. Tell Nines how you live, and choose where you are in Settings.",
            }
        # Items, wears and life/weather context determine the answer; laundry and processing times are left out
        # so a wash or a rename's timestamp does not throw away seconds of work; the stored answer counts through
        # what the rows take from it (weight_class, the sleeve), so a new answer that changes the weight is seen
        ignore = ("laundry", "wears_since_wash", "washed_at", "updated_at", "cutout_state", "cutout_error",
                  "tag_state", "tag_error", "tag_route", "tag_model", "tag_schema_version", "tagged_at",
                  "illustration_version", "illustration_notes")   # a redrawn picture changes no outfit
        seen = hashlib.sha256(json.dumps([[{k: v for k, v in r.items() if k not in ignore} for r in rows], worn,
                                         answers, home, dismissed],
                                         sort_keys=True, default=str).encode()).hexdigest()
        with gaps_locks[profile]:
            cached = gaps_cache.get(profile)
            if cached and cached[0] == seen:
                return cached[1]
            # every gap, not only the first few: one the owner hid or wished for must not push a new one off the list
            answer = life.analyse(rows, worn, answers, home, GAPS_ALL)
            answer["context"] = {"life": answers, "prompt_dismissed": dismissed, "demo": profile == "demo",
                                 "climate": home, "taste": answer.pop("taste"), "suppressed": []}
            gaps_cache[profile] = (seen, answer)
            return answer

    @app.get("/api/gaps")
    async def get_gaps():
        profile = state.get("profile")

        def work() -> dict:
            answer = gap_analysis(profile)
            conn = db.connect(cfg.db_path(profile))
            try:
                return wishlist.mark(conn, answer, consent=state.get("life_gap_hides").get(profile, {}))
            finally:
                conn.close()

        # the engine is run over 40 kinds of day, a few seconds on a big closet: keep it off the event loop
        return await run_in_threadpool(work)

    # -------------------------------------------------------------- insights
    @app.get("/api/insights")
    def get_insights(conn=Depends(conn_dep)):
        rows = closet_rows(conn)   # with each piece's kind: what Today never offers is never "not worn"
        worn = conn.execute("SELECT item_id, worn_on FROM wears").fetchall()
        return find_insights(rows, worn, wears.today(), wishlist=shop.wish_prices(conn))
    app.include_router(wishlist.router(conn_dep, gap_analysis, state, rows=shop.on_the_list))

    def closet_for_check(profile: str) -> tuple[list[dict], list[dict], dict | None]:
        # The check is given the list the screen shows, as it is kept (`gap_analysis`): the plain analysis until the
        # owner has said how they live, the weighed list once they have (and always in the demo). Its "context"
        # carries the answers and climate the check weighs the "after" with (none for the plain list, which the
        # check then compares with the plain analysis with the piece, as before), so both sides are weighed alike.
        rows, worn = gap_inputs(profile)
        return rows, worn, gap_analysis(profile, (rows, worn))

    assert sv.tag_worker and sv.check_tagger, "build_services wires both"
    checks = wouldjobs.Checks(cfg, state, closet_for_check, sv.tag_worker.routes, sv.check_tagger,
                              sv.worker.cutter, sv.worker.is_ready)
    app.include_router(wouldjobs.router(checks))
    assert sv.shopper, "build_services wires it"
    # shop finds are judged on the same list as "Would this work?" (closet_for_check)
    sv.shopper.listed = gap_analysis
    app.include_router(shop.router(sv.shopper, state, conn_dep))
    assert sv.picker, "build_services wires it"
    app.include_router(picks.router(sv.picker, state, conn_dep))
    app.include_router(sizes.router(conn_dep))
    app.include_router(shops.router(conn_dep))
    app.include_router(plans.router(conn_dep))
    app.include_router(kept.router(conn_dep))
    # ---------------------------------------------------------------- the day in the owner's words
    def ahead_of(value: object):
        """The day ahead a note is about (Dress for another day), None for today; HTTPException when it is not one."""
        if value in (None, ""):
            return None
        try:
            return plans.check_day(value, wears.today())
        except items.ItemError as e:
            raise HTTPException(422, str(e))

    def day_answer(message: str | None = None, saved: bool | None = None, ahead=None) -> dict:
        if ahead is not None:
            note = daynote.describe(daynote.for_day(state, ahead), ahead, ahead=True)
        else:
            note = daynote.describe(daynote.shown(state, wears.today()), wears.today())
        out = {"note": note, "message": message}
        return out if saved is None else {**out, "saved": saved}

    @app.get("/api/day")
    async def get_day(day: str | None = None):
        """The note about today or the days ahead, if one holds: {note, message}. With `day`, what is said about that
        day ahead: its own word, or the note when it holds that day."""
        return day_answer(ahead=ahead_of(day))

    @app.put("/api/day")
    async def put_day(request: Request):
        """Reads a sentence about the owner's day with Claude and keeps it: {saved, note, message}. Nothing from the
        closet is sent, only the sentence, the date it is about (today's, or with `day` that day's) and the home
        place's name. `saved` false with a `message` when Claude cannot be asked or found nothing in it; the note kept
        before stays."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if isinstance(body, dict) and set(body) - {"text", "day"}:
            raise HTTPException(422, "Send the sentence as {\"text\": ...}, with the day it is about if it is not today.")
        ahead = ahead_of(body.get("day") if isinstance(body, dict) else None)
        try:
            text = daynote.check_text(body.get("text") if isinstance(body, dict) else None)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if state.get("profile") == "demo":
            return day_answer("The demo closet never asks Claude, so Nines can't read this here. "
                              "Open your own closet to describe your day.", False, ahead)
        assert sv.tag_worker, "build_services wires it"
        # the API key first when it is switched on (the owner: "opus via api"), else the plan
        usable = tuple(sorted(sv.tag_worker.routes(), key=lambda r: r != "api"))
        if not usable and getattr(sv.day_reader, "needs_route", True):   # a stand-in (the browser tests) needs none
            return day_answer("Claude can't be reached right now, so Nines couldn't read that. "
                              "You can still change where you are, or type the temperatures, under Change.", False, ahead)
        home = (state.get("place") or {}).get("name")
        about = ahead or wears.today()   # the day the sentence is about is the "today" Claude reads it for
        try:
            reading = await run_in_threadpool(sv.day_reader, text, about, home, usable)
        except CapReached:
            return day_answer(f"{spend.LIMIT_REACHED} Nines couldn't read that.", False, ahead)
        except (RouteUnavailable, Unreachable):
            return day_answer("Claude can't be reached right now, so Nines couldn't read that. Try again in a moment.",
                              False, ahead)
        except TaggingError:
            return day_answer("Claude gave no usable answer. Try again, or say it another way.", False, ahead)
        from .tagger import dayread
        if not dayread.said_something(reading):
            return day_answer(daynote.NOTHING_READ, False, ahead)
        note, message = await run_in_threadpool(daynote.make, text, reading, about)
        if ahead is not None:
            daynote.save_for(state, ahead, note, wears.today())
        else:
            daynote.save(state, note, wears.today())
        return day_answer(message, True, ahead)

    @app.delete("/api/day")
    async def delete_day(day: str | None = None):
        """Back to an ordinary day at home (with `day`: that day ahead's own word goes)."""
        ahead = ahead_of(day)
        if ahead is not None:
            daynote.clear_for(state, ahead)
        else:
            daynote.clear(state, wears.today())
        return day_answer(ahead=ahead)

    @app.post("/api/add/sort")
    async def sort_add(request: Request):
        """What each photo chosen on Add shows (one piece, several, a shoe, and which photos are the same shoe), asked
        of Claude before anything is added; the owner checks it on the page. When Claude cannot be asked, says why
        and leaves every photo a piece, for the owner to sort by hand."""
        from .tagger import addsort
        form = await request.form()
        sent = [f for f in form.getlist("photos") if not isinstance(f, str)]
        if not 1 <= len(sent) <= addsort.MAX_PHOTOS:
            raise HTTPException(422, f"Send 1 to {addsort.MAX_PHOTOS} photos to sort at a time.")
        plain = [{"kind": "piece", "shoe": 0, "view": None, "pair": False} for _ in sent]
        needed = list(addsort.SHOE_VIEWS_NEEDED)
        if state.get("profile") == "demo":
            return {"sorted": False, "photos": plain, "needed": needed,
                    "message": "The demo closet is never sent to Claude: sort the photos yourself."}
        assert sv.tag_worker, "build_services wires it"
        usable = sv.tag_worker.routes()
        if not usable and getattr(sv.add_sorter, "needs_route", True):   # a stand-in (the browser tests) needs none
            return {"sorted": False, "photos": plain, "needed": needed,
                    "message": "Claude can't be reached right now, so Nines couldn't sort these: sort them yourself."}
        try:
            sent_data = [await f.read(images.MAX_UPLOAD_BYTES + 1) for f in sent]
            # decoding a phone's photos takes a fifth of a second or more each: on a worker thread
            photos = await run_in_threadpool(lambda: [images.decode(data) for data in sent_data])
        except images.ImageError as e:
            raise HTTPException(400, str(e))
        for photo, f in zip(photos, sent, strict=True):
            photo.info["filename"] = f.filename or ""   # never sent to Claude; the browser tests' stand-in reads it
        try:
            return {"sorted": True, "photos": await run_in_threadpool(sv.add_sorter, photos, usable), "message": None,
                    "needed": needed}
        except CapReached:
            message = f"{spend.LIMIT_REACHED} Sort these yourself."
        except (RouteUnavailable, Unreachable):
            message = "Claude can't be reached right now, so Nines couldn't sort these: sort them yourself."
        except TaggingError:
            message = "Claude couldn't tell what these show: sort them yourself."
        return {"sorted": False, "photos": plain, "message": message, "needed": needed}

    app.include_router(sources.router(conn_dep, images_dir, state,
                                      sv.finder.wake if sv.finder else (lambda: None), sv.worker.wake,
                                      lambda img: sv.worker.cutter(img), lambda: sv.worker.is_ready()))

    # ---------------------------------------------------------------- weather
    @app.get("/api/places")
    async def find_places(q: str = ""):
        try:
            return {"places": await run_in_threadpool(search_places, q)}
        except WeatherError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/places/near")
    async def find_place_near(latitude: float, longitude: float):
        try:
            return {"place": await run_in_threadpool(place_near, latitude, longitude)}
        except ValueError as e:
            raise HTTPException(422, str(e))
        except WeatherError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/weather")
    async def get_weather():
        found = await run_in_threadpool(lookup, state)
        return {k: found[k] for k in ("place", "weather", "old", "is_today", "message")}

    # ---------------------------------------------------------------- trips
    async def json_body(request: Request) -> object:
        try:
            return await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")

    async def trip_work(fn: Callable, *args):
        path = cfg.db_path(state.get("profile"))

        def work():
            conn = db.connect(path)
            try:
                return fn(conn, *args)
            except savedtrips.TripError as e:
                raise HTTPException(422, str(e))
            except savedtrips.TripNotFound:
                raise HTTPException(404, "That trip is not in this closet.")
            finally:
                conn.close()

        # the weather service and the planner can each take a moment: keep them off the event loop
        return await run_in_threadpool(work)

    @app.post("/api/trips/plan")
    async def plan_trip(request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.work_out, state, body)

    @app.post("/api/trips", status_code=201)
    async def create_trip(request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.create, state, body)

    @app.get("/api/trips")
    async def list_trips():
        return {"trips": await trip_work(savedtrips.list_all)}

    @app.get("/api/trips/{trip_id}")
    async def get_trip(trip_id: str):
        return await trip_work(savedtrips.get, trip_id)

    @app.get("/api/trips/{trip_id}/weather")
    async def trip_weather(trip_id: str):
        return await trip_work(savedtrips.check_weather, state, trip_id)

    @app.patch("/api/trips/{trip_id}")
    async def patch_trip(trip_id: str, request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.patch, state, trip_id, body)

    @app.delete("/api/trips/{trip_id}", status_code=204)
    async def delete_trip(trip_id: str):
        await trip_work(savedtrips.delete, trip_id)
        return Response(status_code=204)

    # "Not on this trip today": the trip that holds today set aside for the rest of the day, and its Undo (`tripday.py`)
    @app.put("/api/trips/{trip_id}/aside")
    async def set_trip_aside(trip_id: str):
        return await trip_work(tripday.set_aside, state, trip_id, True)

    @app.delete("/api/trips/{trip_id}/aside")
    async def undo_trip_aside(trip_id: str):
        return await trip_work(tripday.set_aside, state, trip_id, False)

    # ---------------------------------------------------------------- model
    def model_payload() -> dict:
        """The first model's state, with the second's (asked as well for patterned clothes) as `second`: null when
        there is none (a cutter standing in, in tests)."""
        sv.model.refresh()
        info = sv.model.info()
        info["second"] = None
        if sv.second_model is not None:
            sv.second_model.refresh()   # also notices a file put in the models folder by hand
            info["second"] = sv.second_model.info()
        return info

    @app.get("/api/model")
    def model_info():
        return model_payload()

    @app.post("/api/model/download", status_code=202)
    def model_download():   # both models: whichever is not ready yet
        for store in (sv.model, sv.second_model):
            if store is not None:
                store.refresh()
                store.start_download()
        return model_payload()

    @app.put("/api/model/url")
    def model_url(body: ModelUrl):
        url = (body.url or "").strip() or None
        if url and not url.lower().startswith("https://"):
            raise HTTPException(422, "The download address must start with https://")
        state.update(model_url=url)
        return model_payload()

    # ------------------------------------------------------------- settings
    # What Settings shows that only changes when the owner changes it here: read once, then kept until then.
    # The key is read from the keychain (on a Mac, the `security` command); start at login from the registry or a file.
    remembered: dict[str, object] = {}
    remembered_lock = threading.Lock()
    forgotten = [0]   # counts `forget`: a value read while it was being changed is not kept

    def remember(name: str, work: Callable[[], object]) -> object:
        with remembered_lock:
            if name in remembered:
                return remembered[name]
            before = forgotten[0]
        value = work()
        with remembered_lock:
            if forgotten[0] == before:
                remembered[name] = value
        return value

    def forget(*names: str) -> None:
        with remembered_lock:
            forgotten[0] += 1
            for name in names:
                remembered.pop(name, None)

    def autostart_now() -> bool | None:
        try:
            return autostart.is_enabled() if autostart.program() else None
        except Exception:
            return None

    def background_status() -> dict:
        return background.status(cfg, sv.background_copy)

    def settings_payload(conn, request: Request) -> dict:
        """Everything Settings shows that is quick to read, so the page can be drawn at once. The slow lookups stay
        apart: whether Claude Code is signed in (`/api/tagging`), the space used (`/api/storage`) and the weather.
        `came_in` is how the device asking came in (`gate.came_in`)."""
        return {
            "version": __version__, "profile": state.get("profile"), "data_dir": str(cfg.data_dir), "port": cfg.port,
            "backup_folder": state.get("backup_folder"), "last_backup": state.get("last_backup"),
            "last_good_backup": backup.last_good(state), "pending_cutouts": jobs.pending_count(conn),
            "pending_tags": tagjobs.waiting_count(conn), "tagging_api_enabled": spend.api_allowed(state),
            "tagging_api_cap_usd": spend.cap(state), "tagging_api_off": state.get("tagging_api_off"),
            "tagging_route_order": tagjobs.route_order(state), "api_key": dict(remember("api_key", apikey.info)),
            "phone": sv.phone_info(), "came_in": gate.came_in(request.scope), "cloudflare": access.payload(state),
            "autostart": remember("autostart", autostart_now), "heic_supported": images.HEIC,
            "background": background_status(),
            "place": state.get("place"), "home_place": HOME_PLACE,
            "life": life.example()[0] if state.get("profile") == "demo" else state.get("life"),
            "life_prompt_dismissed": True if state.get("profile") == "demo" else state.get("life_prompt_dismissed"),
            "rewear": savedtrips.rewear(state),
            "laundry": wears.laundry_setting(state.get("laundry")),
            "stylist_on": bool(state.get("stylist_on")),
            "show_drawings": bool(state.get("show_drawings")),
            # each as its own endpoint answers it
            "model": model_payload(),                          # GET /api/model
            "updates": sv.updater.status() if sv.updater else None,   # GET /api/updates
            "style_profile": styleprofile.current(conn),       # GET /api/style/profile
            "sizes": sizes.current(conn),                      # GET /api/sizes
            "shops": shops.current(conn),                      # GET /api/shops
            "tagging_spend": spend.summary(cfg, state, conn),  # GET /api/tagging/spend
        }

    @app.get("/api/style/answers/{answer_id}")
    def style_answer(answer_id: str, conn=Depends(conn_dep)):
        """How a question to Claude about today's outfits stands, for the page waiting on it: {id, state, message}."""
        found = stylejobs.Stylist.get(conn, answer_id, sv.stylist.clock() if sv.stylist else None)
        if found is None:
            raise HTTPException(404, "That answer is not known. Open Today again.")
        return found

    @app.post("/api/style/answers/{answer_id}/remember")
    async def style_remember(answer_id: str, request: Request, conn=Depends(conn_dep)):
        """The owner's answer to a thing Claude offered to remember: {"index": 0, "save": true} keeps it (in Your
        style, or in the piece's "How I wear it"), {"save": false} does not. Gives the thing as it now stands."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        save, undo = remember_body(body)
        try:
            # keeping a thing in a piece's "How I wear it" redraws the piece: on a worker thread
            return await run_in_threadpool(stylejobs.settle, conn, answer_id, body.get("index"), save, undo)
        except stylejobs.Refused as e:
            raise HTTPException(422, str(e))

    def remember_body(body: object) -> tuple[bool, bool]:
        """(save, undo) from {"index", "save": true or false} or {"index", "undo": true}."""
        if isinstance(body, dict) and body.get("undo") is True:
            return False, True
        if not isinstance(body, dict) or not isinstance(body.get("save"), bool):
            raise HTTPException(422, "Say which thing (index) and whether to keep it (save: true or false).")
        return body["save"], False

    # ---------------------------------------------- the style conversation (Settings, Your style)
    def demo_now() -> bool:
        return state.get("profile") == "demo"

    def chat_state(conn) -> dict:
        if sv.chat is None:
            return stylechat.state_of(conn, wears.today(), None, "demo" if demo_now() else "off")
        return sv.chat.state(conn, wears.today(), demo_now())

    @app.get("/api/style/talk")
    def get_style_talk(conn=Depends(conn_dep)):
        """The day's style conversation: {turns, answering, question, refused}."""
        return chat_state(conn)

    @app.post("/api/style/talk")
    async def post_style_talk(request: Request, conn=Depends(conn_dep)):
        """Send a message about the owner's style: {"say": "..."}. Gives the conversation, with it being answered."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict) or "say" not in body:
            raise HTTPException(422, "Send what you want to tell Claude (say).")
        path = cfg.db_path(state.get("profile"))

        def work() -> dict:
            if sv.chat is None:
                raise HTTPException(422, stylechat.REFUSED["demo" if demo_now() else "off"])
            try:
                return sv.chat.say(conn, path, body["say"], wears.today(), demo_now())
            except (ValueError, stylejobs.Refused) as e:
                raise HTTPException(422, str(e))

        return await run_in_threadpool(work)

    @app.post("/api/style/talk/{turn_id}/remember")
    async def style_talk_remember(turn_id: str, request: Request, conn=Depends(conn_dep)):
        """The owner's answer to a line Claude offered to keep in the style conversation: {"index": 0, "save": true}
        keeps it in Your style, {"save": false} does not, {"undo": true} takes back one kept."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        save, undo = remember_body(body)
        try:
            return await run_in_threadpool(stylechat.settle, conn, turn_id, body.get("index"), save, undo)
        except stylejobs.Refused as e:
            raise HTTPException(422, str(e))

    @app.post("/api/style/questions/{question_id}")
    async def style_question(question_id: str, request: Request, conn=Depends(conn_dep)):
        """Answer a question the stylist cannot infer: {"choice": "..."} or {"text": "..."}, or {"skip": true}.
        Gives {line, question}: the line kept in Your style (None for a skip) and the next question."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict):
            raise HTTPException(422, "Send a choice, your own words (text), or skip.")

        def work() -> dict:
            try:
                if body.get("skip") is True:
                    return stylequestions.skip(conn, question_id)
                return stylequestions.answer(conn, question_id, body.get("choice"), body.get("text"))
            except LookupError as e:
                raise HTTPException(404, str(e))
            except ValueError as e:
                raise HTTPException(422, str(e))

        return await run_in_threadpool(work)

    @app.delete("/api/style/questions/{question_id}")
    def undo_style_question(question_id: str, conn=Depends(conn_dep)):
        """Take back an answer (its line comes out of Your style) or a skip: the question is asked again."""
        try:
            return stylequestions.undo(conn, question_id)
        except LookupError as e:
            raise HTTPException(404, str(e))

    # ---------------------------------------------- the lines of Your style
    async def line_text(request: Request) -> object:
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict) or "text" not in body:
            raise HTTPException(422, "Send the line (text).")
        return body["text"]

    def line_work(call, *args) -> dict:
        try:
            return call(*args)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/style/lines")
    async def add_style_line(request: Request, conn=Depends(conn_dep)):
        """Add a line of the owner's at the end of Your style: {"text": "..."}. Gives the profile."""
        text = await line_text(request)

        def add() -> dict:
            styleprofile.add_line(conn, text, "owner")
            return styleprofile.current(conn)

        return await run_in_threadpool(line_work, add)

    @app.patch("/api/style/lines/{line_id}")
    async def edit_style_line(line_id: int, request: Request, conn=Depends(conn_dep)):
        """Change one line of Your style: {"text": "..."}. Gives the profile."""
        text = await line_text(request)
        return await run_in_threadpool(line_work, styleprofile.edit_line, conn, line_id, text)

    @app.delete("/api/style/lines/{line_id}")
    def remove_style_line(line_id: int, conn=Depends(conn_dep)):
        """Take a line out of Your style. Gives the profile, with the id of the line removed (`removed`) to put back."""
        return line_work(styleprofile.remove_line, conn, line_id)

    @app.post("/api/style/lines/{line_id}/restore")
    def restore_style_line(line_id: int, conn=Depends(conn_dep)):
        """Put a removed line back where it was. Gives the profile."""
        return line_work(styleprofile.restore_line, conn, line_id)

    # ---------------------------------------------- the owner's style profile (Settings, "Your style")
    @app.get("/api/style/profile")
    def get_style_profile(conn=Depends(conn_dep)):
        return styleprofile.current(conn)

    @app.put("/api/style/profile")
    async def put_style_profile(request: Request, conn=Depends(conn_dep)):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict) or "text" not in body:
            raise HTTPException(422, "Send the text of your style.")
        try:
            return await run_in_threadpool(styleprofile.save, conn, body["text"])
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/settings")
    def get_settings(request: Request, conn=Depends(conn_dep)):
        return settings_payload(conn, request)

    @app.get("/api/settings/pictures")
    def get_pictures():
        """Settings' "Show drawings instead of photos" on its own: what every screen's small pictures follow, read when
        the closet opens without the rest of the settings (whose read is Settings' own)."""
        return {"show_drawings": bool(state.get("show_drawings"))}

    @app.put("/api/settings")
    def put_settings(body: SettingsPatch, request: Request, conn=Depends(conn_dep)):
        sent = body.model_fields_set
        door = {k: getattr(body, k) for k in CLOUDFLARE_FIELDS if k in sent}
        if door:
            # a sign-in through Cloudflare cannot move or open the door it came through (DECISIONS, "The doors from
            # outside"); checked before anything else in the request is saved
            if gate.came_in(request.scope)["via"] == "cloudflare":
                raise HTTPException(403, NOT_FROM_CLOUDFLARE)
            try:
                door = access.changes(door)
            except ValueError as e:
                raise HTTPException(422, str(e))
        if "life" in sent or "life_prompt_dismissed" in sent:
            if state.get("profile") == "demo":
                raise HTTPException(422, "The demo keeps its example answers. Switch to your own closet to change how you live.")
            try:
                answers = life.check(body.life) if "life" in sent else state.get("life")
            except ValueError as e:
                raise HTTPException(422, str(e))
            changes = {"life": answers}
            if "life_prompt_dismissed" in sent:
                if body.life_prompt_dismissed is None:
                    raise HTTPException(422, "Choose whether to leave the questions for later.")
                changes["life_prompt_dismissed"] = body.life_prompt_dismissed
            state.update(**changes)
            gaps_cache.pop("main", None)
        if "rewear" in sent:
            if body.rewear is None:
                state.update(rewear=None)   # back to the defaults
            else:
                try:
                    if not isinstance(body.rewear, dict):
                        raise trips.PlanError("Say how often each kind is worn before washing, for example {\"tops\": 1}.")
                    trips.check_rewear(body.rewear)
                    state.update(rewear=trips.check_rewear({**savedtrips.rewear(state), **body.rewear}))
                except trips.PlanError as e:
                    raise HTTPException(422, str(e))
        if "stylist_on" in sent and body.stylist_on is not None:
            state.update(stylist_on=body.stylist_on)
        if "show_drawings" in sent and body.show_drawings is not None:
            state.update(show_drawings=body.show_drawings)
        if "laundry" in sent:
            try:
                state.update(laundry=wears.check_laundry_setting(body.laundry))
            except items.ItemError as e:
                raise HTTPException(422, str(e))
        if "backup_folder" in sent:
            folder = (body.backup_folder or "").strip()
            if folder:
                path = Path(folder).expanduser()
                if not path.is_dir():
                    raise HTTPException(422, f"{path} is not a folder on this computer. Create it first, then choose it here.")
                state.update(backup_folder=str(path))
            else:
                state.update(backup_folder=None)
        if "place" in sent:
            try:
                place = check_place(body.place) if body.place is not None else dict(HOME_PLACE)   # no place: back to New York
            except ValueError as e:
                raise HTTPException(422, str(e))
            if place != state.get("place"):
                state.update(place=place, weather=None, climate=None)
                gaps_cache.pop("main", None)
        if "autostart" in sent and body.autostart is not None:
            try:
                autostart.set_enabled(body.autostart)
            except Exception as e:
                raise HTTPException(409, str(e))
            finally:
                forget("autostart")
        if "tagging_api_cap_usd" in sent or ("tagging_api_enabled" in sent and body.tagging_api_enabled is not None):
            limit = body.tagging_api_cap_usd if "tagging_api_cap_usd" in sent else spend.cap(state)
            on = body.tagging_api_enabled if body.tagging_api_enabled is not None else spend.api_allowed(state)
            if limit is not None and not (0.01 <= limit <= spend.MAX_CAP_USD):
                raise HTTPException(422, f"The monthly limit must be at least $0.01 and no more than ${spend.MAX_CAP_USD:,.0f}.")
            if on and limit is None:
                raise HTTPException(422, "Turn the API key off before removing its monthly limit." if body.tagging_api_enabled is None
                                    else "Set a monthly limit before allowing the API key.")
            changes: dict = {"tagging_api_cap_usd": round(limit, 2) if limit is not None else None, "tagging_api_enabled": on}
            if on:
                changes["tagging_api_off"] = None   # the owner has looked at why it was switched off
            state.update(**changes)
            sv.wake()   # items waiting for a route (or for the limit) may be able to go now
        if "tagging_route_order" in sent:
            order = body.tagging_route_order
            if order not in tagger_routes.ORDERS:
                raise HTTPException(422, f"Choose one of {', '.join(tagger_routes.ORDERS)}.")
            if tagger_routes.ORDERS[order][0] == "api" and not apikey.get():
                raise HTTPException(422, "Save an API key before choosing to use it first.")
            state.update(tagging_route_order=order)
            sv.wake()
        if door:
            state.update(**door)
            log.info("the Cloudflare door was changed; it is %s", "on" if access.load(state).configured else "off")
        return settings_payload(conn, request)

    @app.put("/api/settings/api-key")
    def put_api_key(body: ApiKeyBody, request: Request, conn=Depends(conn_dep)):
        """Check the key with Anthropic (free), then keep it in the computer's keychain. The key is never
        sent back, logged or written anywhere else."""
        try:
            key = apikey.clean(body.key)
        except ValueError as e:
            raise HTTPException(422, str(e))
        verdict = apikey.check(key)
        if verdict == "refused":
            raise HTTPException(422, "Anthropic did not accept that key. Check you copied all of it, and that it "
                                     "belongs to an account that is still active, then try again.")
        try:
            apikey.save(key, background.key_changed(cfg))
        except (apikey.KeychainError, ValueError) as e:
            raise HTTPException(409, str(e))
        finally:
            forget("api_key", "tagging")
        log.info("an API key was saved in the keychain")
        if (state.get("tagging_api_off") or {}).get("reason") == "key":
            state.update(tagging_api_off=None)   # that note was about the key this one replaces
        sv.wake()
        out = settings_payload(conn, request)
        out["api_key"]["checked"] = verdict is None
        return out

    @app.delete("/api/settings/api-key")
    def delete_api_key(request: Request, conn=Depends(conn_dep)):
        try:
            apikey.remove(background.key_changed(cfg))
        except apikey.KeychainError as e:
            raise HTTPException(409, str(e))
        finally:
            forget("api_key", "tagging")
        log.info("the API key was removed from the keychain")
        if tagger_routes.ORDERS[tagjobs.route_order(state)][0] == "api" and not apikey.get():
            state.update(tagging_route_order="auto")   # a choice that needs a key goes back to the plan first
        return settings_payload(conn, request)

    @app.get("/api/storage")
    async def get_storage():
        # walking a big closet takes a while; do it in a worker thread so other requests keep being answered
        return await run_in_threadpool(storage.usage, cfg, state.get("profile"))

    # `claude auth status` takes a moment and the page asks more than once: an answer younger than
    # TAGGING_FRESH_SECONDS is given again, unless the order or whether a key is set has changed since.
    def tagging_status() -> dict:
        order = tagjobs.route_order(state)
        seen = (order, bool(apikey.get()))   # the key's presence only, read live (`ANTHROPIC_API_KEY` counts too)
        kept = remembered.get("tagging")
        if kept and kept[0] == seen and time.monotonic() - kept[1] < TAGGING_FRESH_SECONDS:
            return kept[2]
        result = tagger_routes.status(order)
        with remembered_lock:
            remembered["tagging"] = (seen, time.monotonic(), result)
        return result

    @app.get("/api/tagging")
    async def get_tagging():
        # starts `claude auth status` (a few seconds at most), so keep it off the event loop
        result = await run_in_threadpool(tagging_status)
        sv.tag_worker.wake()   # the owner may just have signed in: waiting items need not wait for the next round
        return result

    @app.get("/api/tagging/spend")
    def get_tagging_spend(conn=Depends(conn_dep)):
        return spend.summary(cfg, state, conn)

    @app.post("/api/backup")
    def backup_now():
        result = backup.run_backup(cfg, state, kind="manual")
        if not result["ok"]:
            return JSONResponse(result, status_code=409)
        return result

    @app.get("/api/restore-notice")
    def get_restore_notice():
        return {"notice": backup.restore_notice(cfg)}

    @app.delete("/api/restore-notice", status_code=204)
    def dismiss_restore_notice():
        backup.dismiss_notice(cfg)
        return Response(status_code=204)

    # -------------------------------------------------------------- updates
    @app.get("/api/updates")
    def get_updates():
        return sv.updater.status()

    @app.put("/api/updates")
    def put_updates(body: UpdateChoice):
        try:
            sv.updater.set_mode(body.mode)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return sv.updater.status()

    @app.post("/api/updates/check")
    async def check_updates():
        # asks GitHub (a few seconds at most), so keep it off the event loop
        return await run_in_threadpool(sv.updater.check_now)

    @app.post("/api/updates/install", status_code=202)
    def install_update():
        try:
            return sv.updater.install_now()
        except updates.UpdateError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/profile")
    def set_profile(body: ProfileChoice):
        if body.profile not in PROFILES:
            raise HTTPException(422, "Profile must be main or demo.")
        if body.profile == "demo":
            demo.ensure(cfg)
        state.update(profile=body.profile)
        sv.wake()
        return {"profile": body.profile}

    @app.post("/api/quit", status_code=202)
    def quit_program():
        threading.Timer(0.3, sv.on_quit).start()
        return {"status": "shutting-down"}

    # ---------------------------------------------------------------- Windows keeping Nines running
    def from_computer(request: Request) -> None:
        """Windows asks for permission on the computer's own screen: from a phone or through Cloudflare it is refused."""
        if gate.came_in(request.scope)["via"] != "computer":
            raise HTTPException(403, background.FROM_COMPUTER)

    @app.get("/api/background")
    def get_background():
        return background_status()

    @app.post("/api/background/on")
    def background_on(request: Request):
        """Copy this program into Nines' own folder and have Windows run it in the background (one administrator
        prompt). This copy then hands its port over and the owner's window reopens onto the background copy."""
        from_computer(request)
        if sv.background_copy:
            raise HTTPException(409, "Windows already keeps Nines running.")
        if not background.supported():
            raise HTTPException(409, background.NOT_HERE)
        try:
            background.turn_on(cfg, sys.executable, cfg.port)
        except background.SetupError as e:
            raise HTTPException(409, str(e))
        finally:
            forget("autostart", "api_key")
        threading.Timer(0.5, sv.on_hand_over).start()
        return {**background_status(), "handing_over": True}

    @app.post("/api/background/restart")
    def background_restart(request: Request):
        """While it is on but this ordinary copy serves (the background copy did not start): hand the port over again."""
        from_computer(request)
        if sv.background_copy:
            raise HTTPException(409, "Nines is already running in the background.")
        if not background.is_set_up(cfg):
            raise HTTPException(409, "Windows does not keep Nines running yet. Turn it on first.")
        threading.Timer(0.5, sv.on_hand_over).start()
        return {**background_status(), "handing_over": True}

    @app.post("/api/background/off")
    def background_off(request: Request):
        """Stop keeping Nines running: Windows asks on the computer's screen. A background copy may run where no prompt
        can be shown, so it asks the window open onto it, in the owner's session, to do it; an ordinary copy does it
        itself."""
        from_computer(request)
        if not background.is_set_up(cfg):
            return {**background_status(), "turning_off": False}
        if sv.background_copy:
            background.clear_outcome(cfg)
            if not instance.ask_window_process(cfg, "off"):
                raise HTTPException(409, f"Open {APP_NAME} from its icon on this computer, then turn this off in its "
                                         "window.")
            return {**background_status(), "turning_off": True}
        try:
            carried = background.turn_off(cfg)
        except background.SetupError as e:
            raise HTTPException(409, str(e))
        finally:
            forget("autostart", "api_key")
        return {**background_status(), "turning_off": False, "note": carried.note}

    @app.post("/api/instance/quit", status_code=202, include_in_schema=False)
    def quit_for_newer_copy(request: Request):
        """A newer copy of the program, started on the same computer, asks this one to make way. It proves it
        can read this copy's data folder by sending the token from the lock file; nothing else is accepted."""
        if not instance.quit_token_matches(cfg, request.headers.get(instance.QUIT_HEADER)):
            raise HTTPException(403, "Not allowed.")
        log.info("a newer copy of the program asked this one to quit")
        threading.Timer(0.3, sv.on_quit).start()
        return {"status": "shutting-down"}

    @app.post("/api/instance/show", include_in_schema=False)
    def show_for_second_launch(request: Request):
        """The program, opened again while this copy runs, asks it to show its window. Like the quit above, only
        something that can read this copy's data folder can ask. `shown` is false when this copy has no window (it
        uses the browser, or runs without a tray and a window), and the program opens the browser instead."""
        if not instance.quit_token_matches(cfg, request.headers.get(instance.QUIT_HEADER)):
            raise HTTPException(403, "Not allowed.")
        return {"shown": bool(sv.on_show())}

    # ---------------------------------------------------------------- pages
    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str):
        if path.startswith(("api/", "media/")):
            raise HTTPException(404, "Not found.")
        if sv.web_dir is None:
            return HTMLResponse("<h1>Nines</h1><p>The server is running, but the web page has not been built. "
                                "Run <code>npm run build</code> in <code>frontend/</code>.</p>")
        root = sv.web_dir.resolve()
        target = (root / path).resolve()
        if path and root in target.parents and target.is_file():
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app
