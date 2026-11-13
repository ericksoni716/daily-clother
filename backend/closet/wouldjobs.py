"""Would this work? checks, run in the background and held in memory only.

A check is started with a description typed by hand or with a photo. A photo
is described by the tagger through the same routes as an item (the Claude
plan first, the API key only when it is switched on and under its monthly
limit, each call recorded with the purpose PURPOSE). The photo is never added
to the closet and never written to disk: it is held in memory, made no larger
than the closet keeps a photo, only until its check is answered or fails, and
it is never logged. The demo closet is never sent to Claude.

Checks live in this process's memory and are gone when the program stops. At
most MAX_CHECKS are kept: a new one drops the oldest finished one, never one
that is still running; while MAX_CHECKS are running a new one is refused.
"""
from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from PIL import Image

from . import db, images, outfits, spend, tagjobs, wouldwork
from .config import Config
from .state import State
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError

log = logging.getLogger("closet.wouldjobs")

PURPOSE = "would_this_work"   # how the spending record names a photo described for a check
MAX_CHECKS = 5                # checks kept, and the most running at once (each runs on a thread of its own)

BY_HAND = "Describe it by hand instead."
DEMO = ("The demo closet never sends anything to Claude, so a photo cannot be described here. " + BY_HAND)
NO_ROUTE = ("Claude cannot be reached right now: your Claude plan is not signed in on this computer and the API key "
            "is not switched on. " + BY_HAND)
NOT_UNDERSTOOD = "Claude could not describe the piece in this photo. Try a clearer photo, or describe it by hand."
UNKNOWN_KIND = "Claude could not tell what kind of piece this is. " + BY_HAND
FAILED = "Something went wrong while checking this piece. Try again."
BUSY = (f"Closet is already checking {MAX_CHECKS} pieces. Wait for one of them to finish, then try again.")
FORGOTTEN = "This check is not known. Checks are forgotten when Closet is closed; start a new one."

# the closet to check against, for a profile: (item rows, wear log, gaps.find_gaps of it with ALL_GAPS)
Closet = Callable[[str], tuple[list[dict], list[dict], dict]]


class Refused(Exception):
    """A check that cannot start, with the sentence to show."""


def piece_from_tags(tags) -> dict:
    """The tagger's answer as a description `wouldwork.parse_piece` takes; PieceError when it is not one."""
    if tags.category not in wouldwork.CATEGORIES:
        raise wouldwork.PieceError(UNKNOWN_KIND)
    fields = tagjobs.suggested_fields(tags)
    d = tags.details
    material = " ".join(w for w in (fields["material"], *(str(v).replace("_", " ") for v in (d.fabric, d.fiber)
                                                          if v not in ("unknown", "na", None))) if w)
    piece = {"category": tags.category, "color": tags.color, "formality": tags.formality, "season": tags.season,
             "pattern": tags.pattern, "name": fields["name"], "material": material[:wouldwork.MATERIAL_MAX] or None,
             "weight_class": d.weight if d.weight in outfits.WEIGHT_CLASSES else None,
             "silhouette": fields["silhouette"]}
    row = wouldwork.candidate_row(wouldwork.parse_piece(piece))
    p = outfits._piece(row)
    piece["rain_proof"] = bool(p and outfits._rain_friendly(p))
    return wouldwork.parse_piece(piece)


class Checks:
    def __init__(self, cfg: Config, state: State, closet: Closet, routes: tagjobs.Routes, tagger: tagjobs.Tagger,
                 cutter: Callable[[Image.Image], Image.Image], cutter_ready: Callable[[], bool]):
        self.cfg, self.state, self.closet = cfg, state, closet
        self.routes, self.tagger, self.cutter, self.cutter_ready = routes, tagger, cutter, cutter_ready
        self._checks: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------- starting
    def start_by_hand(self, data: object) -> dict:
        piece = wouldwork.parse_piece(data)   # PieceError: the caller answers 422
        check = self._new("by_hand", "checking", piece)   # Refused: the caller answers 409
        self._run(check["id"], lambda: piece, self.state.get("profile"))
        return self.get(check["id"])

    def start_photo(self, data: bytes) -> dict:
        profile = self.state.get("profile")
        if profile == "demo":
            raise Refused(DEMO)
        img = images.decode(data)   # ImageError: the caller answers 400
        del data
        img.thumbnail((images.MAX_EDGE, images.MAX_EDGE))   # no larger than the closet keeps a photo
        if not self.routes():
            raise Refused(NO_ROUTE)
        check = self._new("photo", "describing", None)
        held = [img]   # the photo, held only until the check finishes; emptied on every way out

        def describe() -> dict:
            return self._describe(held[0])

        self._run(check["id"], describe, profile, held)
        return self.get(check["id"])

    def get(self, check_id: str) -> dict | None:
        with self._lock:
            check = self._checks.get(check_id)
            return dict(check) if check else None

    # ------------------------------------------------------------- the work
    def _new(self, way: str, state: str, piece: dict | None) -> dict:
        check = {"id": uuid.uuid4().hex, "state": state, "way": way, "piece": piece,
                 "piece_words": wouldwork.describe(piece) if piece else None, "answer": None, "message": None,
                 "by_hand": False, "started_at": db.now(), "finished_at": None}
        with self._lock:
            if sum(1 for c in self._checks.values() if c["finished_at"] is None) >= MAX_CHECKS:
                raise Refused(BUSY)
            self._checks[check["id"]] = check
            while len(self._checks) > MAX_CHECKS:
                oldest = next((k for k, c in self._checks.items() if c["finished_at"] is not None), None)
                if oldest is None:   # cannot happen: fewer than MAX_CHECKS are running
                    break
                del self._checks[oldest]
        return check

    def _set(self, check_id: str, **changes) -> None:
        with self._lock:
            if check_id in self._checks:
                self._checks[check_id].update(changes)

    def _run(self, check_id: str, piece: Callable[[], dict], profile: str, photo: list | None = None) -> None:
        def work() -> None:
            try:
                p = piece()
                self._set(check_id, state="checking", piece=p, piece_words=wouldwork.describe(p))
                rows, worn, before = self.closet(profile)
                answer = wouldwork.check(rows, worn, p, before)
                self._set(check_id, state="ready", answer=answer, finished_at=db.now())
            except CapReached:
                self._set(check_id, state="failed", message=f"{spend.LIMIT_REACHED} {BY_HAND}", by_hand=True,
                          finished_at=db.now())
            except RouteUnavailable:
                self._set(check_id, state="failed", message=NO_ROUTE, by_hand=True, finished_at=db.now())
            except wouldwork.PieceError as e:
                self._set(check_id, state="failed", message=str(e), by_hand=True, finished_at=db.now())
            except (TaggingError, images.ImageError):
                self._set(check_id, state="failed", message=NOT_UNDERSTOOD, by_hand=True, finished_at=db.now())
            except Exception:   # never the photo or the description in the log: only that a check failed, and where
                # the trace as text, so the log keeps no reference to the frames that held the photo
                log.error("a would-this-work check failed\n%s", traceback.format_exc())
                self._set(check_id, state="failed", message=FAILED, finished_at=db.now())
            finally:
                if photo is not None:
                    photo.clear()

        try:
            threading.Thread(target=work, name="would-this-work", daemon=True).start()
        except Exception:
            if photo is not None:
                photo.clear()
            log.exception("a would-this-work check could not start")
            self._set(check_id, state="failed", message=FAILED, finished_at=db.now())

    def _describe(self, img: Image.Image) -> dict:
        front = None
        if self.cutter_ready():
            try:
                front = self.cutter(img)
            except Exception:   # the photo as it is will do: the cutout only helps Claude see the piece
                log.warning("the cutout for a would-this-work photo failed; the photo is sent as it is")
        front = front or img.convert("RGBA")
        routes = self.routes()
        if not routes:
            raise RouteUnavailable("no route to Claude can be used right now")
        result = self.tagger([front], routes)
        return piece_from_tags(result.tags)


# ------------------------------------------------------------------ the routes
def router(checks: Checks, protected: list) -> APIRouter:
    r = APIRouter(dependencies=protected)

    @r.post("/api/would-this-work", status_code=202)
    async def start(request: Request):
        kind = request.headers.get("content-type", "")
        if kind.startswith("multipart/form-data"):
            form = await request.form()
            photo = form.get("photo")
            if photo is None or isinstance(photo, str):
                raise HTTPException(422, "Choose a photo of the piece, or describe it by hand.")
            data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
            try:
                return await run_in_threadpool(checks.start_photo, data)
            except Refused as e:
                raise HTTPException(409, str(e)) from None
            except images.ImageError as e:
                raise HTTPException(400, str(e)) from None
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "Describe the piece by hand, or send a photo of it.") from None
        if not isinstance(body, dict) or set(body) != {"piece"}:
            raise HTTPException(422, "Describe the piece by hand, or send a photo of it.")
        try:
            return checks.start_by_hand(body["piece"])
        except wouldwork.PieceError as e:
            raise HTTPException(422, str(e)) from None
        except Refused as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/api/would-this-work/{check_id}")
    def get(check_id: str):
        check = checks.get(check_id)
        if check is None:
            raise HTTPException(404, FORGOTTEN)
        return check

    return r
