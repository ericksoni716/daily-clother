"""The web API and the page it serves."""
from __future__ import annotations

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

from . import APP_NAME, __version__, auth, autostart, backup, db, demo, images, items, jobs, outfits, phone, storage, vocab
from .config import PROFILES, Config, bundle_dir
from .cutout import make_cutout, predict_mask
from .modelstore import MODEL, ModelStore
from .state import State

log = logging.getLogger("closet.app")


@dataclass
class Services:
    cfg: Config
    state: State
    model: ModelStore
    worker: jobs.Worker
    scheduler: backup.Scheduler
    web_dir: Path | None = None
    on_quit: Callable[[], None] = lambda: None
    _phone_cache: tuple[float, dict] | None = field(default=None, repr=False)

    def start(self) -> None:
        if not self.model.ready and self.cfg.auto_download_model:
            self.model.start_download()
        self.worker.start()
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()
        self.worker.stop()
        self.model.stop()

    def phone_info(self) -> dict:
        if self._phone_cache and time.time() - self._phone_cache[0] < 30:
            return self._phone_cache[1]
        info = phone.info(self.cfg.port)
        self._phone_cache = (time.time(), info)
        return info


def build_services(cfg: Config, cutter: jobs.Cutter | None = None, web_dir: Path | str | None = "bundled") -> Services:
    """Open the settings, bring the closet database up to date and wire the background workers.

    `web_dir` is the built page to serve: "bundled" looks for the one shipped
    with the program, None serves no page (tests), or give a folder.
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

    worker = jobs.Worker(cfg, state, lambda: model.ready, cutter or real_cutter)
    holder["worker"] = worker
    model.refresh()  # know the model's real state before the first request is answered
    if web_dir == "bundled":
        candidate = bundle_dir() / "web"
        web_dir = candidate if (candidate / "index.html").exists() else None
    return Services(cfg, state, model, worker, backup.Scheduler(cfg, state), web_dir)


class Passphrase(BaseModel):
    passphrase: str


class ProfileChoice(BaseModel):
    profile: str


class ModelUrl(BaseModel):
    url: str | None = None


class SettingsPatch(BaseModel):
    backup_folder: str | None = None
    autostart: bool | None = None
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

    @app.post("/api/outfits/suggest", dependencies=protected)
    async def suggest_outfits(request: Request, conn=Depends(conn_dep)):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request was not valid JSON.")
        if not isinstance(body, dict):
            raise HTTPException(422, "Send an object describing the day's weather and occasion.")
        count = body.pop("count", outfits.DEFAULT_COUNT)
        try:
            context = outfits.validate_context(body, count)
        except ValueError as e:
            raise HTTPException(422, str(e))

        def choose():
            rows = []
            for row in conn.execute("SELECT * FROM items WHERE status = 'active' ORDER BY id"):
                item = dict(row)
                item["silhouette"] = json.loads(item["silhouette"] or "{}")
                rows.append(item)
            return outfits.suggest(rows, context, count)

        return await run_in_threadpool(choose)

    @app.get("/api/items", dependencies=protected)
    def list_items(status: str = "active", category: str | None = None, q: str | None = None, conn=Depends(conn_dep)):
        if status not in ("active", "archived"):
            raise HTTPException(422, "Status must be active or archived.")
        return {"items": items.list_items(conn, status, category, q)}

    @app.post("/api/items", dependencies=protected)
    async def create_item(response: Response, photo: UploadFile = File(...), client_key: str | None = Form(None),
                          name: str | None = Form(None), conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        item, created = items.create_from_photo(conn, images_dir(), data, client_key, name)
        response.status_code = 201 if created else 200
        sv.worker.wake()
        return item

    @app.get("/api/items/{item_id}", dependencies=protected)
    def get_item(item_id: str, conn=Depends(conn_dep)):
        return items.detail(conn, items.get(conn, item_id))

    @app.get("/api/items/{item_id}/illustration.svg", dependencies=protected)
    def get_illustration(item_id: str, conn=Depends(conn_dep)):
        svg = items.get(conn, item_id)["illustration_svg"]
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

    @app.get("/media/{rel:path}", dependencies=protected)
    def media(rel: str):
        root = images_dir().resolve()
        target = (root / rel).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "No such image.")
        return FileResponse(target, media_type="image/webp",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

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
            "phone": sv.phone_info(), "autostart": auto, "heic_supported": images.HEIC,
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
        if "autostart" in sent and body.autostart is not None:
            try:
                autostart.set_enabled(body.autostart)
            except Exception as e:
                raise HTTPException(409, str(e))
        return settings_payload(conn)

    @app.get("/api/storage", dependencies=protected)
    async def get_storage():
        # walking a big closet takes a while; do it in a worker thread so other requests keep being answered
        return await run_in_threadpool(storage.usage, cfg, state.get("profile"))

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
        sv.worker.wake()
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
