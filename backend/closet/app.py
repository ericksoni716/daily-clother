"""The web API and the page it serves."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from . import (
    APP_NAME,
    __version__,
    auth,
    autostart,
    backup,
    db,
    demo,
    illustrations,
    images,
    items,
    jobs,
    outfits,
    phone,
    review,
    spend,
    storage,
    tagjobs,
    vocab,
    wears,
    wishlist,
    worn,
)
from .config import PROFILES, Config, bundle_dir
from .cutout import make_cutout, predict_mask
from .gaps import find_gaps
from .insights import find_insights
from .modelstore import MODEL, ModelStore
from .state import State
from .tagger import routes as tagger_routes
from .today import closet_rows
from .today import suggest as suggest_today
from .weather import WeatherError, check_place, lookup, search_places

log = logging.getLogger("closet.app")

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
    on_quit: Callable[[], None] = lambda: None
    _phone_cache: tuple[float, dict] | None = field(default=None, repr=False)

    def start(self) -> None:
        if not self.model.ready and self.cfg.auto_download_model:
            self.model.start_download()
        self.worker.start()
        if self.tag_worker:
            self.tag_worker.start()
        self.scheduler.start()

    def wake(self) -> None:
        """Nudge both queues (a new item, another closet opened)."""
        self.worker.wake()
        if self.tag_worker:
            self.tag_worker.wake()

    def stop(self) -> None:
        self.scheduler.stop()
        if self.tag_worker:
            self.tag_worker.stop()
        self.worker.stop()
        self.model.stop()

    def phone_info(self) -> dict:
        if self._phone_cache and time.time() - self._phone_cache[0] < 30:
            return self._phone_cache[1]
        info = phone.info(self.cfg.port)
        self._phone_cache = (time.time(), info)
        return info


def build_services(cfg: Config, cutter: jobs.Cutter | None = None, web_dir: Path | str | None = "bundled",
                   tagger: tagjobs.Tagger | None = None, routes: tagjobs.Routes | None = None, api_client=None) -> Services:
    """Open the settings, bring the closet database up to date and wire the background workers.

    `web_dir` is the built page to serve: "bundled" looks for the one shipped
    with the program, None serves no page (tests), or give a folder. `tagger`
    and `routes` stand in for Claude in tests; by default the real routes are used, each call recorded and the
    API key kept under its monthly limit. `api_client` stands in for the API alone (tests), behind that same limit.
    """
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    state = State(cfg.state_path)
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

    def real_cutter(img: Image.Image) -> Image.Image:
        return make_cutout(img, predict_mask(img, MODEL, model.path))[0]

    meter = spend.Meter(cfg, state)

    def real_tagger(images: list[Image.Image], usable: tuple[str, ...]):
        return tagjobs.claude_tagger(images, usable, meter=meter, client=api_client)

    tag_worker = tagjobs.Worker(cfg, state, routes or (lambda: tagjobs.usable_routes(state)), tagger or real_tagger)
    worker = jobs.Worker(cfg, state, lambda: model.ready, cutter or real_cutter, on_done=tag_worker.wake)
    holder["worker"] = worker
    model.refresh()  # know the model's real state before the first request is answered
    if web_dir == "bundled":
        candidate = bundle_dir() / "web"
        web_dir = candidate if (candidate / "index.html").exists() else None
    return Services(cfg, state, model, worker, backup.Scheduler(cfg, state), web_dir, tag_worker=tag_worker)


class Passphrase(BaseModel):
    passphrase: str


class ProfileChoice(BaseModel):
    profile: str


class ModelUrl(BaseModel):
    url: str | None = None


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


class SettingsPatch(BaseModel):
    backup_folder: str | None = None
    autostart: bool | None = None
    tagging_api_enabled: bool | None = None
    tagging_api_cap_usd: float | None = None
    place: dict | None = None
    model_config = {"extra": "forbid"}


def create_app(sv: Services) -> FastAPI:
    app = FastAPI(title=APP_NAME, version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    cfg, state = sv.cfg, sv.state

    # ---------------------------------------------------------------- helpers
    def token(request: Request) -> str | None:
        return request.cookies.get(auth.COOKIE)

    def require_auth(request: Request) -> None:
        if not auth.session_valid(state, token(request)):
            raise HTTPException(401, "Log in to continue." if auth.is_set_up(state) else "Set a passphrase to get started.")

    def conn_dep():
        conn = db.connect(cfg.db_path(state.get("profile")))
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
        return vocab.as_dict()

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
                          name: str | None = Form(None), photo_sha256: str | None = Form(None), conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        item, created = items.create_from_photo(conn, images_dir(), data, client_key, name, photo_sha256 or None)
        response.status_code = 201 if created else 200
        sv.worker.wake()
        return item

    @app.get("/api/items/{item_id}", dependencies=protected)
    def get_item(item_id: str, conn=Depends(conn_dep)):
        return items.detail(conn, items.get(conn, item_id))

    @app.get("/api/items/{item_id}/illustration.svg", dependencies=protected)
    def get_illustration(item_id: str, conn=Depends(conn_dep)):
        svg = illustrations.current(conn, items.get(conn, item_id))["illustration_svg"]
        if svg is None:
            raise HTTPException(404, "This item has no illustration yet.")
        # the address carries a version, so the drawing can be cached until it changes
        return Response(svg, media_type="image/svg+xml", headers={
            "Cache-Control": "private, max-age=31536000, immutable", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})

    @app.patch("/api/items/{item_id}", dependencies=protected)
    async def patch_item(item_id: str, request: Request, conn=Depends(conn_dep)):
        try:
            changes = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(changes, dict):
            raise HTTPException(422, "Send an object of fields to change.")
        return items.update(conn, item_id, changes)

    @app.delete("/api/items/{item_id}", status_code=204, dependencies=protected)
    def delete_item(item_id: str, conn=Depends(conn_dep)):
        items.delete(conn, images_dir(), item_id)
        return Response(status_code=204)

    @app.post("/api/items/{item_id}/retry-cutout", status_code=202, dependencies=protected)
    def retry_cutout(item_id: str, conn=Depends(conn_dep)):
        item = items.retry_cutout(conn, item_id)
        sv.worker.wake()
        return item

    @app.post("/api/items/{item_id}/retag", status_code=202, dependencies=protected)
    def retag(item_id: str, conn=Depends(conn_dep)):
        if state.get("profile") == "demo":
            items.get(conn, item_id)
            raise HTTPException(409, "The demo closet is never sent to Claude; its descriptions were made in advance.")
        item = items.retag(conn, item_id)
        sv.wake()
        return item

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
            try:
                return suggest_today(conn, state, body)
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

    def gap_analysis(profile: str | None = None) -> dict:
        """The open closet's gaps, all of them (cut to the list's length when marked); slow the first time."""
        profile = profile or state.get("profile")
        conn = db.connect(cfg.db_path(profile))
        try:
            rows = closet_rows(conn)
            worn = [{"item_id": r["item_id"], "worn_on": r["worn_on"]}
                    for r in conn.execute("SELECT item_id, worn_on FROM wears ORDER BY item_id, worn_on")]
        finally:
            conn.close()
        # the answer only depends on the items and the wear log; the laundry state and times are left out
        # so a wash or a rename's timestamp does not throw away seconds of work; the stored answer counts through
        # what the rows take from it (weight_class, the sleeve), so a new answer that changes the weight is seen
        ignore = ("laundry", "wears_since_wash", "washed_at", "updated_at", "created_at", "cutout_state", "cutout_error",
                  "tag_state", "tag_error", "tag_route", "tag_model", "tag_schema_version", "tagged_at",
                  "illustration_version", "illustration_notes")   # a redrawn picture changes no outfit
        seen = hashlib.sha256(json.dumps([[{k: v for k, v in r.items() if k not in ignore} for r in rows], worn],
                                         sort_keys=True, default=str).encode()).hexdigest()
        cached = gaps_cache.get(profile)
        if cached and cached[0] == seen:
            return cached[1]
        # every gap, not only the first few: one the owner hid or wished for must not push a new one off the list
        answer = find_gaps(rows, worn, {"max_gaps": GAPS_ALL})
        gaps_cache[profile] = (seen, answer)
        return answer

    @app.get("/api/gaps", dependencies=protected)
    async def get_gaps():
        profile = state.get("profile")

        def work() -> dict:
            answer = gap_analysis(profile)
            conn = db.connect(cfg.db_path(profile))
            try:
                return wishlist.mark(conn, answer)
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
    app.include_router(wishlist.router(conn_dep, gap_analysis, protected))

    # ---------------------------------------------------------------- weather
    @app.get("/api/places", dependencies=protected)
    async def find_places(q: str = ""):
        try:
            return {"places": await run_in_threadpool(search_places, q)}
        except WeatherError as e:
            raise HTTPException(502, str(e))

    @app.get("/api/weather", dependencies=protected)
    async def get_weather():
        found = await run_in_threadpool(lookup, state)
        return {k: found[k] for k in ("place", "weather", "old", "is_today", "message")}

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
            "phone": sv.phone_info(), "autostart": auto, "heic_supported": images.HEIC, "place": state.get("place"),
        }

    @app.get("/api/settings", dependencies=protected)
    def get_settings(conn=Depends(conn_dep)):
        return settings_payload(conn)

    @app.put("/api/settings", dependencies=protected)
    def put_settings(body: SettingsPatch, conn=Depends(conn_dep)):
        sent = body.model_fields_set
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
                place = check_place(body.place) if body.place is not None else None
            except ValueError as e:
                raise HTTPException(422, str(e))
            if place != state.get("place"):
                state.update(place=place, weather=None)
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
        return settings_payload(conn)

    @app.get("/api/storage", dependencies=protected)
    async def get_storage():
        # walking a big closet takes a while; do it in a worker thread so other requests keep being answered
        return await run_in_threadpool(storage.usage, cfg, state.get("profile"))

    @app.get("/api/tagging", dependencies=protected)
    async def get_tagging():
        # starts `claude auth status` (a few seconds at most), so keep it off the event loop
        result = await run_in_threadpool(tagger_routes.status)
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
