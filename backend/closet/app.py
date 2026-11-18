"""The web API and the page it serves."""
from __future__ import annotations

import hashlib
import json
import logging
import re
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
    apikey,
    auth,
    autostart,
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
    kinds,
    life,
    outfits,
    patjobs,
    phone,
    review,
    savedtrips,
    shoedraw,
    shoes,
    shoeviews,
    shop,
    sources,
    spend,
    storage,
    stylejobs,
    styleprofile,
    tagjobs,
    tracejobs,
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

SEE_THROUGH = 0.2   # a cutout this see-through inside its outline is asked of the second model as well
GAPS_ALL = 100   # gaps asked of the analysis; the list shows at most gaps.MAX_GAPS not yet decided on


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
    finder: sources.Worker | None = None          # asks where each piece is in a photo of several
    views: shoeviews.Worker | None = None         # sorts a shoe's photos into views
    draws: shoedraw.Worker | None = None          # draws a shoe from its sorted photos
    add_sorter: object = None                      # says what each photo chosen on Add shows (tagger/addsort.py)
    day_reader: object = None                      # reads the day in the owner's words (tagger/dayread.py)
    stylist: stylejobs.Stylist | None = None       # Claude choosing the day's outfits (closet/stylejobs.py); None: the rules only
    on_quit: Callable[[], None] = lambda: None
    on_show: Callable[[], bool] = lambda: False   # shows Closet's own window; False when there is none (the browser is used)
    updater: updates.Updater | None = None   # new releases: checked once a day, installed when the owner says
    _phone_cache: tuple[float, dict] | None = field(default=None, repr=False)

    def start(self) -> None:
        if not self.model.ready and self.cfg.auto_download_model:
            self.model.start_download()
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
            self.second_model.start_download()
        self.scheduler.start()
        if self.updater is not None:
            self.updater.start()
        if self.price_checks:
            self.price_checks.start()

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

    def phone_info(self) -> dict:
        if self._phone_cache and time.time() - self._phone_cache[0] < 30:
            return self._phone_cache[1]
        info = phone.info(self.cfg.port)
        self._phone_cache = (time.time(), info)
        return info


def build_services(cfg: Config, cutter: jobs.Cutter | None = None, web_dir: Path | str | None = "bundled",
                   tagger: tagjobs.Tagger | None = None, routes: tagjobs.Routes | None = None, api_client=None,
                   corrector: corrections.Corrector | None = None, measurer: patjobs.Measurer | None = None,
                   landmarker: patjobs.Landmarker | None = None, shop_asker: shop.Asker | None = None,
                   finder: sources.Finder | None = None, tracer: tracejobs.Tracer | None = None,
                   sorter: shoeviews.Sorter | None = None, drawer: shoedraw.Drawer | None = None,
                   drawing_corrector: shoedraw.Corrector | None = None, add_sorter=None,
                   day_reader=None, stylist_ask: stylejobs.Asker | None = None) -> Services:
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
    they give one.
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
    finally:
        conn.close()
    holder: dict = {}
    model = ModelStore(cfg.models_dir, state, on_ready=lambda: holder["worker"].wake())

    second = ModelStore(cfg.models_dir, state, name=SECOND_MODEL, url_key="second_model_url")

    def real_cutter(img: Image.Image) -> Image.Image:
        mask = predict_mask(img, MODEL, model.path)
        if second.ready:
            from .patterns.masks import see_through  # OpenCV: loaded only once a cutout is made
            if see_through(mask) > SEE_THROUGH:   # a plaid's dark checks taken for background: ask the other model
                mask = Image.fromarray(np.maximum(np.asarray(mask), np.asarray(predict_mask(img, SECOND_MODEL, second.path))))
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
    worker = jobs.Worker(cfg, state, lambda: model.ready, cutter or real_cutter, on_done=tag_worker.wake, tracer=tracer)
    holder["worker"] = worker
    landmark_meter = spend.Meter(cfg, state, spend.PURPOSE_LANDMARKS, spend.estimate_landmarks)

    def real_landmarker(cut: Image.Image, usable: tuple[str, ...]) -> dict:
        from .tagger import landmarks
        return landmarks.ask(cut, usable, client=api_client, meter=landmark_meter)

    def real_measurer(cut, pattern, words, marks):
        from .patterns.measure import measure  # OpenCV: loaded only when a pattern is measured
        return measure(cut, pattern, words, marks)

    pattern_worker = patjobs.Worker(cfg, state, measurer or real_measurer,
                                    landmarker if landmarker is not None else (None if tagger else real_landmarker),
                                    routes or (lambda: tagjobs.usable_routes(state)))
    if measurer is None and tagger is not None:
        pattern_worker = None    # tests standing in for Claude measure no patterns unless they ask to
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
        result = stylist.ask(brief, usable, client=api_client, meter=style_meter)
        return {"looks": stylist.looks(result.answer), "read": result.answer.read, "route": result.route,
                "model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}

    # tests standing in for Claude get no stylist unless they give one: Today is then the rules engine's, as before
    choose = stylist_ask or (None if tagger is not None else real_stylist)
    draw_meter = spend.Meter(cfg, state, spend.PURPOSE_DRAW, spend.estimate_draw)

    def real_drawer(photos: list, usable: tuple[str, ...], notes=(), style=None):
        from .tagger import shoedrawing
        return shoedrawing.draw(photos, usable, client=api_client, meter=draw_meter, notes=notes, style=style,
                                mask_of=model_mask)

    def no_drawer(photos: list, usable: tuple[str, ...], notes=(), style=None):
        raise RouteUnavailable("tests standing in for Claude draw no shoes unless they ask to")

    correct_meter = spend.Meter(cfg, state, spend.PURPOSE_CORRECT_DRAWING, spend.estimate_correct_drawing)

    def real_drawing_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...]):
        from .tagger import shoedrawing
        return shoedrawing.correct(photos, kept, note, usable, client=api_client, meter=correct_meter)

    def no_drawing_corrector(photos: list, kept: dict, note: str, usable: tuple[str, ...]):
        raise RouteUnavailable("tests standing in for Claude change no drawings unless they ask to")

    draw_worker = shoedraw.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)),
                                  drawer or (no_drawer if tagger is not None else real_drawer),
                                  corrector=drawing_corrector or (no_drawing_corrector if tagger is not None
                                                                  else real_drawing_corrector))
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
                           shop_asker or shop.ClaudeAsker(cfg, state, client=api_client))
    return Services(cfg, state, model, worker, backup.Scheduler(cfg, state), web_dir, tag_worker=tag_worker,
                    pattern_worker=pattern_worker, second_model=second if cutter is None else None,
                    corrector=corrector or real_corrector,
                    check_tagger=tagger or check_tagger, shopper=shopper, price_checks=shop.PriceScheduler(shopper),
                    finder=finding, views=views_worker, draws=draw_worker, updater=updates.Updater(cfg, state),
                    add_sorter=add_sorter or (no_add_sorter if tagger is not None else real_add_sorter),
                    day_reader=day_reader or (no_day_reader if tagger is not None else real_day_reader),
                    stylist=stylejobs.Stylist(choose, routes or (lambda: tagjobs.usable_routes(state))) if choose else None)


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


class Passphrase(BaseModel):
    passphrase: str


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


class Confirm(BaseModel):
    fields: list[str]
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
    model_config = {"extra": "forbid"}


def create_app(sv: Services) -> FastAPI:
    app = FastAPI(title=APP_NAME, version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    cfg, state = sv.cfg, sv.state

    # ---------------------------------------------------------------- helpers
    def token(request: Request) -> str | None:
        return request.cookies.get(auth.COOKIE)

    def refusal(session: str | None) -> str | None:
        if auth.session_valid(state, session):
            return None
        return "Log in to continue." if auth.is_set_up(state) else "Set a passphrase to get started."

    def require_auth(request: Request) -> None:
        if (refused := refusal(token(request))) is not None:
            raise HTTPException(401, refused)

    # the login and the size limits, checked before any request body is read
    app.add_middleware(gate.Gate, cookie=auth.COOKIE, refusal=refusal)

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

    def set_cookie(request: Request, response: Response, value: str) -> None:
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
        response.set_cookie(auth.COOKIE, value, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="strict",
                            secure=secure, path="/")

    def images_dir() -> Path:
        return cfg.images_dir(state.get("profile"))

    @app.exception_handler(auth.AuthError)
    async def auth_error(_: Request, e: auth.AuthError):
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        return JSONResponse({"detail": e.message}, status_code=e.status, headers=headers)

    @app.exception_handler(items.ItemError)
    async def item_error(_: Request, e: items.ItemError):
        return JSONResponse({"detail": e.message}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, e: RequestValidationError):
        if request.url.path in ("/api/setup", "/api/login"):
            return JSONResponse({"detail": "Enter the passphrase as text."}, status_code=422)
        if request.url.path == "/api/settings/api-key":
            return JSONResponse({"detail": "Enter the API key as text, with no other fields."}, status_code=422)
        if CORRECTING.match(request.url.path):
            return JSONResponse({"detail": plain_input(e)}, status_code=422)
        return await request_validation_exception_handler(request, e)

    @app.exception_handler(images.ImageError)
    async def image_error(_: Request, e: images.ImageError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    # ------------------------------------------------------- open endpoints
    @app.get("/api/health")
    def health():
        return {"app": "closet", "status": "ok", "version": __version__, "model_state": sv.model.info()["state"],
                "setup_required": not auth.is_set_up(state), "profile": state.get("profile")}

    @app.get("/api/session")
    def session(request: Request):
        return {"authenticated": auth.session_valid(state, token(request)), "setup_required": not auth.is_set_up(state),
                "version": __version__, "profile": state.get("profile")}

    @app.post("/api/setup", status_code=204)
    def setup(body: Passphrase, request: Request, response: Response):
        if auth.is_set_up(state):
            raise HTTPException(409, "A passphrase is already set. Log in instead.")
        auth.set_passphrase(state, body.passphrase)
        set_cookie(request, response, auth.new_session(state))
        response.status_code = 204

    @app.post("/api/login", status_code=204)
    def login(body: Passphrase, request: Request, response: Response):
        auth.check_passphrase(state, body.passphrase)
        set_cookie(request, response, auth.new_session(state))
        response.status_code = 204

    @app.post("/api/logout", status_code=204)
    def logout(request: Request, response: Response):
        auth.end_session(state, token(request))
        response.delete_cookie(auth.COOKIE, path="/")
        response.status_code = 204

    # ------------------------------------------------------------------ items
    protected = [Depends(require_auth)]

    @app.get("/api/vocab", dependencies=protected)
    def get_vocab():
        return {**vocab.as_dict(), "kind_groups": kinds.catalogue()["groups"]}

    @app.get("/api/kinds", dependencies=protected)
    def get_kinds():
        return kinds.catalogue()

    @app.get("/api/kinds/{kind}.svg", dependencies=protected)
    def get_kind_drawing(kind: str, color: str = kinds.TILE_HEX):
        if kind not in kinds.KINDS:
            raise HTTPException(404, "There is no such kind.")
        svg = kinds.drawing(kind, color.lower())
        if svg is None:
            raise HTTPException(404, "This kind has no drawing.")
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "private, max-age=86400", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.get("/api/items", dependencies=protected)
    def list_items(status: str = "active", category: str | None = None, q: str | None = None, laundry: str | None = None,
                   conn=Depends(conn_dep)):
        if status not in ("active", "archived"):
            raise HTTPException(422, "Status must be active or archived.")
        if laundry is not None and laundry not in wears.LAUNDRY:
            raise HTTPException(422, "The laundry filter must be clean or laundry.")
        return {"items": items.list_items(conn, status, category, q, laundry)}

    @app.post("/api/items", dependencies=protected)
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

    @app.get("/api/items/{item_id}", dependencies=protected)
    def get_item(item_id: str, conn=Depends(conn_dep)):
        return items.detail(conn, items.get(conn, item_id))

    @app.get("/api/items/{item_id}/illustration.svg", dependencies=protected)
    def get_illustration(item_id: str, v: str | None = None, conn=Depends(conn_dep)):
        svg = illustrations.current(conn, items.get(conn, item_id))["illustration_svg"]
        if svg is None:
            raise HTTPException(404, "This item has no illustration yet.")
        # Only cache the drawing under its own version, not an old address another tab still has.
        cache = "private, max-age=31536000, immutable" if v == hashlib.sha256(svg.encode()).hexdigest() else "no-store"
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": cache, "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.get("/api/items/{item_id}/back.svg", dependencies=protected)
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

    @app.patch("/api/items/{item_id}", dependencies=protected)
    async def patch_item(item_id: str, request: Request, conn=Depends(conn_dep)):
        try:
            changes = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(changes, dict):
            raise HTTPException(422, "Send an object of fields to change.")
        saved = items.update(conn, item_id, changes)
        _traced_soon(saved)
        return saved

    @app.delete("/api/items/{item_id}", status_code=204, dependencies=protected)
    def delete_item(item_id: str, conn=Depends(conn_dep)):
        items.delete(conn, images_dir(), item_id)
        return Response(status_code=204)

    @app.post("/api/items/{item_id}/retry-cutout", status_code=202, dependencies=protected)
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

    @app.post("/api/items/{item_id}/trace/fix", dependencies=protected)
    async def fix_trace(item_id: str, request: Request, conn=Depends(conn_dep)):
        return shoes.fix(conn, item_id, await shoe_body(request))

    @app.put("/api/items/{item_id}/trace/plain", dependencies=protected)
    async def plain_trace(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        return shoes.set_plain(conn, item_id, body.get("plain") if isinstance(body, dict) else None)

    @app.put("/api/items/{item_id}/trace/front", dependencies=protected)
    async def front_trace(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        if not isinstance(body, dict) or "kind" not in body:
            raise HTTPException(422, "Send the front view as {\"kind\": \"shape\"}, \"photo\" or null.")
        return shoes.set_front(conn, item_id, body["kind"])

    @app.get("/api/items/{item_id}/trace/front.svg", dependencies=protected)
    def front_preview(item_id: str, kind: str, conn=Depends(conn_dep)):
        svg = illustrations.front_preview(items.get(conn, item_id), kind)
        if svg is None:
            raise HTTPException(404, "This shoe has no front view from its trace.")
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.post("/api/items/{item_id}/retrace", status_code=202, dependencies=protected)
    def retrace(item_id: str, conn=Depends(conn_dep)):
        item = shoes.retrace(conn, item_id)
        sv.worker.wake()
        return item

    def views_soon() -> None:
        """A shoe's photos changed: traced again when the photo read for its front view changed, and sorted again."""
        sv.worker.wake()
        if sv.views:
            sv.views.wake()

    @app.post("/api/items/{item_id}/photo", dependencies=protected)
    async def replace_photo(item_id: str, photo: UploadFile = File(...), photo_sha256: str | None = Form(None),
                            conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        item = await run_in_threadpool(shoes.replace_photo, conn, images_dir(), item_id, data, photo_sha256 or None,
                                       demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.post("/api/items/{item_id}/photos", status_code=201, dependencies=protected)
    async def add_photo(item_id: str, photo: UploadFile = File(...), view: str | None = Form(None),
                        photo_sha256: str | None = Form(None), conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        item = await run_in_threadpool(shoes.add_photo, conn, images_dir(), item_id, data, view or None,
                                       photo_sha256 or None, demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.delete("/api/items/{item_id}/photos/{photo_id}", dependencies=protected)
    def remove_photo(item_id: str, photo_id: str, conn=Depends(conn_dep)):
        item = shoes.remove_photo(conn, images_dir(), item_id, photo_id, demo=state.get("profile") == "demo")
        views_soon()
        return item

    @app.put("/api/items/{item_id}/photos/{photo_id}/view", dependencies=protected)
    async def set_photo_view(item_id: str, photo_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        if not isinstance(body, dict) or "view" not in body:
            raise HTTPException(422, "Send the view as {\"view\": \"outer\"} (or inner, top, front, back, sole, other).")
        item = shoes.set_view(conn, item_id, photo_id, body["view"])
        sv.worker.wake()   # traced again when the photo read for the front view changed
        if sv.draws:
            sv.draws.wake()   # the answer may have settled the views: a shoe sorted for the first time is drawn next
        return item

    # ---------------------------------------------- a shoe drawn by Claude from its photos
    @app.post("/api/items/{item_id}/drawn", status_code=202, dependencies=protected)
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

    @app.post("/api/items/{item_id}/drawn/correct", status_code=202, dependencies=protected)
    async def correct_drawing(item_id: str, request: Request, conn=Depends(conn_dep)):
        body = await shoe_body(request)
        note = body.get("note") if isinstance(body, dict) else None
        conn.execute("BEGIN IMMEDIATE")
        try:
            shoedraw.correct(conn, item_id, note, state.get("profile") == "demo")
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        if sv.draws:
            sv.draws.wake()
        return items.detail(conn, items.get(conn, item_id))

    @app.post("/api/items/{item_id}/drawn/back", dependencies=protected)
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

    @app.get("/api/items/{item_id}/drawn.svg", dependencies=protected)
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

    @app.post("/api/items/{item_id}/retag", status_code=202, dependencies=protected)
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

    @app.get("/api/items/{item_id}/details", dependencies=protected)
    def detail_options(item_id: str, conn=Depends(conn_dep)):
        return corrections.options(items.get(conn, item_id))

    @app.get("/api/items/{item_id}/details/{name}", dependencies=protected)
    async def detail_choices(item_id: str, name: str):
        path = cfg.db_path(state.get("profile"))

        def work() -> dict:
            conn = db.connect(path)
            try:
                return corrections.choices(items.get(conn, item_id), name)
            finally:
                conn.close()
        return await run_in_threadpool(work)

    @app.put("/api/items/{item_id}/details", dependencies=protected)
    def set_details(item_id: str, body: DetailsBody, conn=Depends(conn_dep)):
        return corrections.apply(conn, item_id, body.details)

    @app.put("/api/items/{item_id}/kind", dependencies=protected)
    def set_kind(item_id: str, body: KindBody, conn=Depends(conn_dep)):
        saved = corrections.set_kind(conn, item_id, body.kind)
        _traced_soon(saved)
        return saved

    @app.post("/api/items/{item_id}/correct", dependencies=protected)
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

    @app.post("/api/items/{item_id}/correct/confirm", dependencies=protected)
    def confirm_correction(item_id: str, body: Confirmed):
        profile = state.get("profile")
        conn = db.connect(cfg.db_path(profile))
        try:
            not_in_demo(profile, conn, item_id)
            return corrections.confirm(conn, item_id, body.sentence, body.changes)
        finally:
            conn.close()

    @app.get("/api/items/{item_id}/history", dependencies=protected)
    def item_history(item_id: str, conn=Depends(conn_dep)):
        items.get(conn, item_id)
        return history.listing(conn, item_id)

    @app.post("/api/items/{item_id}/history/{change_id}/undo", dependencies=protected)
    def undo_change(item_id: str, change_id: int, conn=Depends(conn_dep)):
        saved = corrections.undo(conn, item_id, change_id)
        _traced_soon(saved["item"])
        return saved

    @app.get("/api/items/{item_id}/wears", dependencies=protected)
    def list_wears(item_id: str, conn=Depends(conn_dep)):
        return {"wears": wears.list_wears(conn, item_id)}

    @app.post("/api/items/{item_id}/wears", dependencies=protected)
    def add_wear(item_id: str, response: Response, body: WearDay | None = None, conn=Depends(conn_dep)):
        item, created = wears.add(conn, item_id, body.worn_on if body else None)
        response.status_code = 201 if created else 200
        return item

    @app.delete("/api/items/{item_id}/wears/{worn_on}", dependencies=protected)
    def remove_wear(item_id: str, worn_on: str, conn=Depends(conn_dep)):
        return wears.remove(conn, item_id, worn_on)

    @app.post("/api/wears", dependencies=protected)
    def add_wears(body: WearMany, response: Response, conn=Depends(conn_dep)):
        if body.outfit is not None:
            result = worn.wear(conn, body.item_ids, body.worn_on, body.outfit)
        else:
            result = wears.add_many(conn, body.item_ids, body.worn_on)
        response.status_code = 201 if result["recorded"] or result.get("outfit") else 200
        return result

    @app.post("/api/wears/remove", dependencies=protected)
    def remove_wears(body: WearManyDay, conn=Depends(conn_dep)):
        if body.outfit_id is not None:
            return worn.undo(conn, body.item_ids, body.worn_on, body.outfit_id)
        return wears.remove_many(conn, body.item_ids, body.worn_on)

    @app.get("/api/outfits/worn", dependencies=protected)
    def list_worn(limit: int = worn.DEFAULT_PAGE, before: str | None = None, conn=Depends(conn_dep)):
        return worn.list_outfits(conn, limit, before)

    @app.post("/api/outfits/worn", dependencies=protected, status_code=201)
    def record_worn(body: OutfitByHand, conn=Depends(conn_dep)):
        return worn.record_by_hand(conn, body.item_ids, body.worn_on)

    @app.put("/api/outfits/worn/{outfit_id}/rating", dependencies=protected)
    def rate_worn(outfit_id: str, body: OutfitRating, conn=Depends(conn_dep)):
        return worn.rate(conn, outfit_id, body.rating, body.reasons, body.note)

    @app.delete("/api/outfits/worn/{outfit_id}", dependencies=protected, status_code=204)
    def remove_worn(outfit_id: str, conn=Depends(conn_dep)):
        worn.remove(conn, outfit_id)
        return Response(status_code=204)

    @app.post("/api/items/{item_id}/laundry", dependencies=protected)
    def set_laundry(item_id: str, body: LaundryState, conn=Depends(conn_dep)):
        return wears.set_laundry(conn, item_id, body.state)

    @app.get("/api/review", dependencies=protected)
    def review_queue(conn=Depends(conn_dep)):
        return review.queue(conn, describes=state.get("profile") != "demo")

    @app.post("/api/items/{item_id}/confirm", dependencies=protected)
    def confirm_fields(item_id: str, body: Confirm, conn=Depends(conn_dep)):
        return review.confirm(conn, item_id, body.fields)

    @app.get("/media/{rel:path}", dependencies=protected)
    def media(rel: str):
        root = images_dir().resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "No such image.")
        return FileResponse(target, media_type="image/webp",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    # -------------------------------------------------------------- outfits
    @app.post("/api/outfits/suggest", dependencies=protected)
    async def suggest_outfits(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        try:
            ctx, count = outfits.parse_request(body)
        except outfits.ContextError as e:
            raise HTTPException(422, str(e))
        path = cfg.db_path(state.get("profile"))

        def work() -> dict:
            conn = db.connect(path)
            try:
                rows = closet_rows(conn)
            finally:
                conn.close()
            if ctx.build_around and not any(r["id"] == ctx.build_around for r in rows):
                raise HTTPException(422, "The item to build around is not in this closet.")
            return outfits.suggest(rows, ctx, count)

        # comparing thousands of combinations takes a moment; do it in a worker thread so other requests keep being answered
        return await run_in_threadpool(work)

    @app.post("/api/outfits/today", dependencies=protected)
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
                return suggest_today(conn, state, body, chooses, path)
            except outfits.ContextError as e:
                raise HTTPException(422, str(e))
            finally:
                conn.close()

        # asks Open-Meteo (a few seconds at most) and compares many outfits, so keep it off the event loop
        return await run_in_threadpool(work)

    @app.post("/api/outfits/figure", dependencies=protected)
    async def outfit_figure(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        try:
            ids = illustrations.figure_ids(body)
        except illustrations.FigureError as e:
            raise HTTPException(422, str(e))
        path = cfg.db_path(state.get("profile"))

        def work() -> str:
            conn = db.connect(path)
            try:
                return illustrations.outfit_figure(conn, ids)
            except illustrations.FigureError as e:
                raise HTTPException(422, str(e))
            finally:
                conn.close()

        # drawing a whole outfit takes a few milliseconds per piece: keep it off the event loop
        svg = await run_in_threadpool(work)
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    # ----------------------------------------------------------------- gaps
    gaps_cache: dict[str, tuple[str, dict]] = {}  # profile -> (what the closet and wear log were, the answer)

    def gap_inputs(profile: str) -> tuple[list[dict], list[dict]]:
        return closet_inputs(cfg, profile)

    def gap_analysis(profile: str | None = None, inputs: tuple[list[dict], list[dict]] | None = None) -> dict:
        """The open closet's gaps, all of them (cut to the list's length when marked); slow the first time."""
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
                "message": "Home weather is not being used. Tell Closet how you live, and choose where you are in Settings.",
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
        cached = gaps_cache.get(profile)
        if cached and cached[0] == seen:
            return cached[1]
        # every gap, not only the first few: one the owner hid or wished for must not push a new one off the list
        answer = life.analyse(rows, worn, answers, home, GAPS_ALL)
        answer["context"] = {"life": answers, "prompt_dismissed": dismissed, "demo": profile == "demo",
                             "climate": home, "taste": answer.pop("taste"), "suppressed": []}
        gaps_cache[profile] = (seen, answer)
        return answer

    @app.get("/api/gaps", dependencies=protected)
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
    @app.get("/api/insights", dependencies=protected)
    def get_insights(conn=Depends(conn_dep)):
        rows = conn.execute("SELECT id, name, category, color, formality, season, price_cents, status, created_at FROM items").fetchall()
        worn = conn.execute("SELECT item_id, worn_on FROM wears").fetchall()
        return find_insights(rows, worn, wears.today())
    app.include_router(wishlist.router(conn_dep, gap_analysis, protected, state))

    def closet_for_check(profile: str) -> tuple[list[dict], list[dict], dict | None]:
        # Until the owner has said how they live, the check works out the plain analysis itself, with and without
        # the piece, exactly as before. Once they have (and always in the demo, as its list), it is given the
        # weighed list the screen shows; its "context" carries the answers and climate the check weighs the
        # "after" with, so both sides are weighed alike.
        rows, worn = gap_inputs(profile)
        if profile != "demo" and state.get("life") is None:
            return rows, worn, None
        return rows, worn, gap_analysis(profile, (rows, worn))

    assert sv.tag_worker and sv.check_tagger, "build_services wires both"
    checks = wouldjobs.Checks(cfg, state, closet_for_check, sv.tag_worker.routes, sv.check_tagger,
                              sv.worker.cutter, sv.worker.is_ready)
    app.include_router(wouldjobs.router(checks, protected))
    assert sv.shopper, "build_services wires it"
    # shop finds are judged on the same list as "Would this work?" (closet_for_check)
    sv.shopper.weighed = lambda profile, inputs: (
        None if profile != "demo" and state.get("life") is None else gap_analysis(profile, inputs))
    app.include_router(shop.router(sv.shopper, state, conn_dep, protected))
    # ---------------------------------------------------------------- the day in the owner's words
    def day_answer(message: str | None = None, saved: bool | None = None) -> dict:
        out = {"note": daynote.describe(daynote.current(state, wears.today()), wears.today()), "message": message}
        return out if saved is None else {**out, "saved": saved}

    @app.get("/api/day", dependencies=protected)
    async def get_day():
        """The note about today or the days ahead, if one holds: {note, message}."""
        return day_answer()

    @app.put("/api/day", dependencies=protected)
    async def put_day(request: Request):
        """Reads a sentence about the owner's day with Claude and keeps it: {saved, note, message}. Nothing from the
        closet is sent, only the sentence, today's date and the home place's name. `saved` false with a `message`
        when Claude cannot be asked or found nothing in it; the note kept before stays."""
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        try:
            text = daynote.check_text(body.get("text") if isinstance(body, dict) else None)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if state.get("profile") == "demo":
            return day_answer("The demo closet never asks Claude, so Closet can't read this here. "
                              "Open your own closet to describe your day.", False)
        assert sv.tag_worker, "build_services wires it"
        # the API key first when it is switched on (the owner: "opus via api"), else the plan
        usable = tuple(sorted(sv.tag_worker.routes(), key=lambda r: r != "api"))
        if not usable and getattr(sv.day_reader, "needs_route", True):   # a stand-in (the browser tests) needs none
            return day_answer("Claude can't be reached right now, so Closet couldn't read that. "
                              "You can still change where you are, or type the temperatures, under Change.", False)
        home = (state.get("place") or {}).get("name")
        try:
            reading = await run_in_threadpool(sv.day_reader, text, wears.today(), home, usable)
        except CapReached:
            return day_answer(f"{spend.LIMIT_REACHED} Closet couldn't read that.", False)
        except (RouteUnavailable, Unreachable):
            return day_answer("Claude can't be reached right now, so Closet couldn't read that. Try again in a moment.", False)
        except TaggingError:
            return day_answer("Claude gave no usable answer. Try again, or say it another way.", False)
        from .tagger import dayread
        if not dayread.said_something(reading):
            return day_answer(daynote.NOTHING_READ, False)
        note, message = await run_in_threadpool(daynote.make, text, reading, wears.today())
        daynote.save(state, note)
        return day_answer(message, True)

    @app.delete("/api/day", dependencies=protected)
    async def delete_day():
        """Back to an ordinary day at home."""
        daynote.clear(state)
        return day_answer()

    @app.post("/api/add/sort", dependencies=protected)
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
                    "message": "Claude can't be reached right now, so Closet couldn't sort these: sort them yourself."}
        try:
            photos = [images.decode(await f.read(images.MAX_UPLOAD_BYTES + 1)) for f in sent]
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
            message = "Claude can't be reached right now, so Closet couldn't sort these: sort them yourself."
        except TaggingError:
            message = "Claude couldn't tell what these show: sort them yourself."
        return {"sorted": False, "photos": plain, "message": message, "needed": needed}

    app.include_router(sources.router(conn_dep, images_dir, state, protected,
                                      sv.finder.wake if sv.finder else (lambda: None), sv.worker.wake,
                                      lambda img: sv.worker.cutter(img), lambda: sv.worker.is_ready()))

    # ---------------------------------------------------------------- weather
    @app.get("/api/places", dependencies=protected)
    async def find_places(q: str = ""):
        try:
            return {"places": await run_in_threadpool(search_places, q)}
        except WeatherError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/places/near", dependencies=protected)
    async def find_place_near(latitude: float, longitude: float):
        try:
            return {"place": await run_in_threadpool(place_near, latitude, longitude)}
        except ValueError as e:
            raise HTTPException(422, str(e))
        except WeatherError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/weather", dependencies=protected)
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

    @app.post("/api/trips/plan", dependencies=protected)
    async def plan_trip(request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.work_out, state, body)

    @app.post("/api/trips", status_code=201, dependencies=protected)
    async def create_trip(request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.create, state, body)

    @app.get("/api/trips", dependencies=protected)
    async def list_trips():
        return {"trips": await trip_work(savedtrips.list_all)}

    @app.get("/api/trips/{trip_id}", dependencies=protected)
    async def get_trip(trip_id: str):
        return await trip_work(savedtrips.get, trip_id)

    @app.get("/api/trips/{trip_id}/weather", dependencies=protected)
    async def trip_weather(trip_id: str):
        return await trip_work(savedtrips.check_weather, state, trip_id)

    @app.patch("/api/trips/{trip_id}", dependencies=protected)
    async def patch_trip(trip_id: str, request: Request):
        body = await json_body(request)
        return await trip_work(savedtrips.patch, state, trip_id, body)

    @app.delete("/api/trips/{trip_id}", status_code=204, dependencies=protected)
    async def delete_trip(trip_id: str):
        await trip_work(savedtrips.delete, trip_id)
        return Response(status_code=204)

    # ---------------------------------------------------------------- model
    @app.get("/api/model", dependencies=protected)
    def model_info():
        sv.model.refresh()
        return sv.model.info()

    @app.post("/api/model/download", status_code=202, dependencies=protected)
    def model_download():
        sv.model.refresh()
        sv.model.start_download()
        return sv.model.info()

    @app.put("/api/model/url", dependencies=protected)
    def model_url(body: ModelUrl):
        url = (body.url or "").strip() or None
        if url and not url.lower().startswith("https://"):
            raise HTTPException(422, "The download address must start with https://")
        state.update(model_url=url)
        return sv.model.info()

    # ------------------------------------------------------------- settings
    def settings_payload(conn) -> dict:
        try:
            auto = autostart.is_enabled() if autostart.program() else None
        except Exception:
            auto = None
        return {
            "version": __version__, "profile": state.get("profile"), "data_dir": str(cfg.data_dir), "port": cfg.port,
            "backup_folder": state.get("backup_folder"), "last_backup": state.get("last_backup"),
            "last_good_backup": backup.last_good(state), "pending_cutouts": jobs.pending_count(conn),
            "pending_tags": tagjobs.waiting_count(conn), "tagging_api_enabled": spend.api_allowed(state),
            "tagging_api_cap_usd": spend.cap(state), "tagging_api_off": state.get("tagging_api_off"),
            "tagging_route_order": tagjobs.route_order(state), "api_key": apikey.info(),
            "phone": sv.phone_info(), "autostart": auto, "heic_supported": images.HEIC, "place": state.get("place"),
            "home_place": HOME_PLACE,
            "life": life.example()[0] if state.get("profile") == "demo" else state.get("life"),
            "life_prompt_dismissed": True if state.get("profile") == "demo" else state.get("life_prompt_dismissed"),
            "rewear": savedtrips.rewear(state),
            "laundry": wears.laundry_setting(state.get("laundry")),
            "stylist_on": bool(state.get("stylist_on")),
        }

    @app.get("/api/style/answers/{answer_id}", dependencies=protected)
    def style_answer(answer_id: str, conn=Depends(conn_dep)):
        """How a question to Claude about today's outfits stands, for the page waiting on it: {id, state, message}."""
        found = stylejobs.Stylist.get(conn, answer_id)
        if found is None:
            raise HTTPException(404, "That answer is not known. Open Today again.")
        return found

    # ---------------------------------------------- the owner's style profile (Settings, "Your style")
    @app.get("/api/style/profile", dependencies=protected)
    def get_style_profile(conn=Depends(conn_dep)):
        return styleprofile.current(conn)

    @app.put("/api/style/profile", dependencies=protected)
    async def put_style_profile(request: Request, conn=Depends(conn_dep)):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict) or "text" not in body:
            raise HTTPException(422, "Send the text of your style.")
        try:
            return styleprofile.save(conn, body["text"])
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/settings", dependencies=protected)
    def get_settings(conn=Depends(conn_dep)):
        return settings_payload(conn)

    @app.put("/api/settings", dependencies=protected)
    def put_settings(body: SettingsPatch, conn=Depends(conn_dep)):
        sent = body.model_fields_set
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
        return settings_payload(conn)

    @app.put("/api/settings/api-key", dependencies=protected)
    def put_api_key(body: ApiKeyBody, conn=Depends(conn_dep)):
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
            apikey.store().set(key)
        except (apikey.KeychainError, ValueError) as e:
            raise HTTPException(409, str(e))
        log.info("an API key was saved in the keychain")
        if (state.get("tagging_api_off") or {}).get("reason") == "key":
            state.update(tagging_api_off=None)   # that note was about the key this one replaces
        sv.wake()
        out = settings_payload(conn)
        out["api_key"]["checked"] = verdict is None
        return out

    @app.delete("/api/settings/api-key", dependencies=protected)
    def delete_api_key(conn=Depends(conn_dep)):
        try:
            apikey.store().delete()
        except apikey.KeychainError as e:
            raise HTTPException(409, str(e))
        log.info("the API key was removed from the keychain")
        if tagger_routes.ORDERS[tagjobs.route_order(state)][0] == "api" and not apikey.get():
            state.update(tagging_route_order="auto")   # a choice that needs a key goes back to the plan first
        return settings_payload(conn)

    @app.get("/api/storage", dependencies=protected)
    async def get_storage():
        # walking a big closet takes a while; do it in a worker thread so other requests keep being answered
        return await run_in_threadpool(storage.usage, cfg, state.get("profile"))

    @app.get("/api/tagging", dependencies=protected)
    async def get_tagging():
        # starts `claude auth status` (a few seconds at most), so keep it off the event loop
        result = await run_in_threadpool(tagger_routes.status, tagjobs.route_order(state))
        sv.tag_worker.wake()   # the owner may just have signed in: waiting items need not wait for the next round
        return result

    @app.get("/api/tagging/spend", dependencies=protected)
    def get_tagging_spend(conn=Depends(conn_dep)):
        return spend.summary(cfg, state, conn)

    @app.post("/api/backup", dependencies=protected)
    def backup_now():
        result = backup.run_backup(cfg, state, kind="manual")
        if not result["ok"]:
            return JSONResponse(result, status_code=409)
        return result

    @app.get("/api/restore-notice", dependencies=protected)
    def get_restore_notice():
        return {"notice": backup.restore_notice(cfg)}

    @app.delete("/api/restore-notice", status_code=204, dependencies=protected)
    def dismiss_restore_notice():
        backup.dismiss_notice(cfg)
        return Response(status_code=204)

    # -------------------------------------------------------------- updates
    @app.get("/api/updates", dependencies=protected)
    def get_updates():
        return sv.updater.status()

    @app.put("/api/updates", dependencies=protected)
    def put_updates(body: UpdateChoice):
        try:
            sv.updater.set_mode(body.mode)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return sv.updater.status()

    @app.post("/api/updates/check", dependencies=protected)
    async def check_updates():
        # asks GitHub (a few seconds at most), so keep it off the event loop
        return await run_in_threadpool(sv.updater.check)

    @app.post("/api/updates/install", status_code=202, dependencies=protected)
    def install_update():
        try:
            return sv.updater.install_now()
        except updates.UpdateError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/profile", dependencies=protected)
    def set_profile(body: ProfileChoice):
        if body.profile not in PROFILES:
            raise HTTPException(422, "Profile must be main or demo.")
        if body.profile == "demo":
            demo.ensure(cfg)
        state.update(profile=body.profile)
        sv.wake()
        return {"profile": body.profile}

    @app.post("/api/quit", status_code=202, dependencies=protected)
    def quit_program():
        threading.Timer(0.3, sv.on_quit).start()
        return {"status": "shutting-down"}

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
            return HTMLResponse("<h1>Closet</h1><p>The server is running, but the web page has not been built. "
                                "Run <code>npm run build</code> in <code>frontend/</code>.</p>")
        root = sv.web_dir.resolve()
        target = (root / path).resolve()
        if path and root in target.parents and target.is_file():
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app
