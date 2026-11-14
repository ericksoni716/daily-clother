"""Several items from one photo.

The owner lays several pieces out together (on the bed, on the floor) and takes one photo. The photo is kept once
under `images/sources/<id>/`; Claude is asked for a box around each piece (`tagger/garments.py`, through the same
routes and monthly limit as describing); the owner checks the boxes (removes, merges, adds, moves their corners);
then each box becomes an ordinary item: the box cut out of the photo is its photo, and from there it is cut out,
described, drawn and pattern-measured exactly like a single upload. Each item remembers the photo and the box.

The demo closet never asks Claude: there the owner draws the boxes.

A photo is in one of three states: `finding` (waiting for Claude), `review` (boxes ready for the owner to check,
or to draw) and `added` (its items are in the closet). Any change the owner makes to the boxes ends `finding`, so
an answer from Claude that arrives after it is dropped rather than overwriting what the owner did.
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import threading
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict

from . import db, images, items, jobs
from .config import Config
from .state import State
from .tagger.tagging import CapReached, PlanSignIn, RouteUnavailable

log = logging.getLogger("closet.sources")

FOLDER = "sources"     # under the closet's images folder: sources/<id>/photo.webp
MAX_BOXES = 20         # more pieces than this in one photo are more than anyone checks box by box
MIN_SIDE = 0.03        # a box narrower or lower than this share of the photo holds no garment
SAME_PIECE = 0.8       # two of Claude's boxes overlapping this much (shared area over joint area) are one piece
PAD = 0.02             # each piece is cut with this much of the photo around its box, so its edges are not lost
MAX_ATTEMPTS = 3       # tries at finding the pieces before the owner is asked to draw them
PREVIEW_EDGE = 480     # the cutout shown beside each box, longest side in pixels
EDGES = ("x0", "y0", "x1", "y1")

Finder = Callable[[Image.Image, tuple[str, ...]], list[dict]]   # (photo, usable routes) -> boxes as fractions

DEMO = ("The demo closet never sends photos to Claude, so draw a box around each piece yourself with "
        "\u201cAdd a box\u201d.")
NO_ROUTE = ("Claude can't be reached right now: no way to reach it is set up and working (see Settings). Closet "
            "will look for the pieces once it can, or draw a box around each one yourself.")
SIGN_IN = ("Claude Code on this computer needs you to sign in again, and the API key isn't allowed. Closet will "
           "look for the pieces once it can, or draw a box around each one yourself.")
LIMIT = ("This month's spending limit for the API key has been reached. Closet will look for the pieces when your "
         "plan can be used again, when the new month starts, or if you raise the limit in Settings; or draw a box "
         "around each one yourself.")
FAILED = ("Claude could not find the pieces in this photo. Draw a box around each one yourself with "
          "\u201cAdd a box\u201d, or forget the photo.")
NONE_FOUND = "Claude found no clothes in this photo. Draw a box around each piece yourself, or forget the photo."
ADDED = "These pieces are already in your closet."
NOT_HERE = "That photo is not waiting to be checked any more."
NO_BOX = "That box is not in this photo any more."
BAD_BOX = "That box is outside the photo or too small to hold a piece."
TOO_MANY = f"A photo can have at most {MAX_BOXES} boxes."
NO_BOXES = "Draw a box around at least one piece first."
CHANGED = "The boxes changed while the pieces were being added. Check them and press Add again."
NOT_READY = "The cutout isn't ready yet: the background model is still being set up."


# ------------------------------------------------------------------ boxes

def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def clamp(raw) -> dict | None:
    """A box cut to the photo ({x0, y0, x1, y1}, fractions of its width and height, left/top first), or None when
    it is not a box, nothing of it lies in the photo, or what does is too thin to hold a piece."""
    if not isinstance(raw, dict):
        return None
    nums = [_num(raw.get(k)) for k in EDGES]
    if any(n is None for n in nums):
        return None
    x0, x1 = sorted((nums[0], nums[2]))
    y0, y1 = sorted((nums[1], nums[3]))
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        return None
    return {"x0": round(x0, 4), "y0": round(y0, 4), "x1": round(x1, 4), "y1": round(y1, 4)}


def overlap(a: dict, b: dict) -> float:
    """The area two boxes share over the area they cover together (0 apart, 1 the same box)."""
    w = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    h = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    if w <= 0 or h <= 0:
        return 0.0
    shared = w * h
    area = lambda r: (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])  # noqa: E731
    return shared / (area(a) + area(b) - shared)


def union(a: dict, b: dict) -> dict:
    """The smallest box holding both."""
    return {"x0": min(a["x0"], b["x0"]), "y0": min(a["y0"], b["y0"]),
            "x1": max(a["x1"], b["x1"]), "y1": max(a["y1"], b["y1"])}


def _box_id() -> str:
    return uuid.uuid4().hex[:10]


def _label(raw) -> str | None:
    label = raw.get("label") if isinstance(raw, dict) else None
    return label.strip()[:80] if isinstance(label, str) and label.strip() else None


def tidy(found) -> list[dict]:
    """Claude's boxes made usable, in the order it gave them: each cut to the photo, empty and thin ones dropped,
    the same piece boxed twice kept once (the two boxes joined), at most MAX_BOXES."""
    boxes: list[dict] = []
    for raw in found if isinstance(found, list) else []:
        box = clamp(raw)
        if box is None:
            continue
        same = next((b for b in boxes if overlap(b, box) >= SAME_PIECE), None)
        if same is not None:
            same.update(union(same, box))
            continue
        boxes.append({**box, "label": _label(raw)})
    return [{"id": _box_id(), **b} for b in boxes[:MAX_BOXES]]


def crop(photo: Image.Image, box: dict) -> Image.Image:
    """The piece in `box`, with a little of the photo around it."""
    w, h = photo.size
    x0 = max(0, math.floor((box["x0"] - PAD) * w))
    y0 = max(0, math.floor((box["y0"] - PAD) * h))
    x1 = min(w, math.ceil((box["x1"] + PAD) * w))
    y1 = min(h, math.ceil((box["y1"] + PAD) * h))
    return photo.crop((x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)))


def _version(box: dict) -> str:
    return f"{zlib.crc32(json.dumps([box[k] for k in EDGES]).encode()):08x}"


# ------------------------------------------------------------------ the photos

def get(conn, source_id: str):
    row = conn.execute("SELECT * FROM source_photos WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise items.ItemError(NOT_HERE, 404)
    return row


def view(conn, row) -> dict:
    sid = row["id"]
    boxes = json.loads(row["boxes"])
    return {
        "id": sid, "state": row["state"], "note": row["note"], "found_by": row["found_by"],
        "photo_url": f"/media/{row['original_path']}", "thumb_url": f"/media/{row['thumb_path']}",
        "width": row["width"], "height": row["height"],
        "boxes": [{**b, "n": n, "cutout_url": f"/api/sources/{sid}/boxes/{b['id']}/cutout.webp?v={_version(b)}"}
                  for n, b in enumerate(boxes, 1)],
        "items": [items.summary(conn, r) for r in
                  conn.execute("SELECT * FROM items WHERE source_photo_id = ? ORDER BY rowid", (sid,))],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def open_list(conn) -> list[dict]:
    """The photos not added yet, oldest first."""
    return [view(conn, r) for r in
            conn.execute("SELECT * FROM source_photos WHERE state != 'added' ORDER BY created_at, id")]


def _same(conn, sha: str):
    row = conn.execute("SELECT * FROM source_photos WHERE source_sha256 = ? ORDER BY created_at LIMIT 1", (sha,)).fetchone()
    return ("source", row) if row is not None else ("item", items._same_photo(conn, sha))


def _duplicate(conn, found) -> dict:
    kind, row = found
    if kind == "source":
        return {"duplicate": True, "source": view(conn, row), "item": None}
    return {"duplicate": True, "source": None, "item": items.detail(conn, row)}


def create(conn, images_dir: Path, data: bytes, client_key: str | None, source_sha256: str | None,
           demo: bool) -> tuple[dict, bool]:
    """Keep a photo of several pieces. Returns ({duplicate, source, item}, created).

    A repeated `client_key` returns the photo kept the first time. A photo already kept, or already added as a
    single item, is not kept again: what was made from it comes back with `duplicate: true` (as `source` or `item`).
    """
    if client_key:
        row = conn.execute("SELECT * FROM source_photos WHERE client_key = ?", (client_key,)).fetchone()
        if row is not None:
            return {"duplicate": False, "source": view(conn, row), "item": None}, False
    sha = items.photo_hash(data, source_sha256)
    found = _same(conn, sha)
    if found[1] is not None:
        return _duplicate(conn, found), False
    sid = uuid.uuid4().hex
    stored = images.store_upload(data, images_dir, f"{FOLDER}/{sid}", "photo")
    t = db.now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        found = _same(conn, sha)   # checked again now that the database is locked
        if found[1] is not None:
            conn.execute("ROLLBACK")
            shutil.rmtree(images_dir / FOLDER / sid, ignore_errors=True)
            return _duplicate(conn, found), False
        conn.execute("INSERT INTO source_photos (id, client_key, original_path, thumb_path, width, height, bytes, sha256, "
                     "source_sha256, state, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (sid, client_key or None, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, sha, "review" if demo else "finding", DEMO if demo else None, t, t))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        shutil.rmtree(images_dir / FOLDER / sid, ignore_errors=True)
        raise
    return {"duplicate": False, "source": view(conn, get(conn, sid)), "item": None}, True


def _change(conn, sid: str, change: Callable[[list[dict]], list[dict]]) -> dict:
    """Change the boxes under the database's lock. A change by the owner ends any wait for Claude's boxes."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = get(conn, sid)
        if row["state"] == "added":
            raise items.ItemError(ADDED, 409)
        boxes = change(json.loads(row["boxes"]))
        note = row["note"] if row["note"] == DEMO else None
        conn.execute("UPDATE source_photos SET boxes = ?, state = 'review', note = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(boxes), note, db.now(), sid))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return view(conn, get(conn, sid))


def _index(boxes: list[dict], bid: str) -> int:
    for i, b in enumerate(boxes):
        if b["id"] == bid:
            return i
    raise items.ItemError(NO_BOX, 404)


def add_box(conn, sid: str, raw: dict) -> dict:
    box = clamp(raw)
    if box is None:
        raise items.ItemError(BAD_BOX)

    def change(boxes):
        if len(boxes) >= MAX_BOXES:
            raise items.ItemError(TOO_MANY)
        return [*boxes, {"id": _box_id(), **box, "label": None}]
    return _change(conn, sid, change)


def move_box(conn, sid: str, bid: str, raw: dict) -> dict:
    box = clamp(raw)
    if box is None:
        raise items.ItemError(BAD_BOX)

    def change(boxes):
        i = _index(boxes, bid)
        boxes[i] = {**boxes[i], **box}
        return boxes
    return _change(conn, sid, change)


def remove_box(conn, sid: str, bid: str) -> dict:
    def change(boxes):
        i = _index(boxes, bid)
        return boxes[:i] + boxes[i + 1:]
    return _change(conn, sid, change)


def merge_boxes(conn, sid: str, ids: list[str]) -> dict:
    """Join boxes that hold one piece into one (the first named keeps its place and its name)."""
    ids = list(dict.fromkeys(ids))
    if len(ids) < 2:
        raise items.ItemError("Choose two boxes to join.")

    def change(boxes):
        picked = [_index(boxes, bid) for bid in ids]
        first = boxes[picked[0]]
        joined = dict(first)
        for i in picked[1:]:
            joined.update(union(joined, boxes[i]))
        drop = set(picked[1:])
        return [joined if i == picked[0] else b for i, b in enumerate(boxes) if i not in drop]
    return _change(conn, sid, change)


def forget(conn, images_dir: Path, sid: str) -> None:
    """Drop a photo not added yet, and its file."""
    row = get(conn, sid)
    if row["state"] == "added":
        raise items.ItemError(ADDED, 409)
    if conn.execute("DELETE FROM source_photos WHERE id = ? AND state != 'added'", (sid,)).rowcount:
        shutil.rmtree(images_dir / FOLDER / sid, ignore_errors=True)


def _open_photo(images_dir: Path, row) -> Image.Image:
    with Image.open(images_dir / row["original_path"]) as im:
        return im.convert("RGB")


def preview(conn, images_dir: Path, sid: str, bid: str, cutter: Callable[[Image.Image], Image.Image],
            ready: Callable[[], bool]) -> Path:
    """The piece in a box cut out of its background, to show beside the box; made once for each place of the box."""
    row = get(conn, sid)
    boxes = json.loads(row["boxes"])
    box = boxes[_index(boxes, bid)]
    folder = images_dir / FOLDER / sid
    path = folder / f"cut-{bid}-{_version(box)}.webp"
    if path.exists():
        return path
    if not ready():
        raise items.ItemError(NOT_READY, 409)
    try:
        cut = cutter(crop(_open_photo(images_dir, row), box))
    except Exception as e:   # nothing found in the box: the page shows the box's part of the photo instead
        log.info("no cutout for a box: %s", type(e).__name__)
        raise items.ItemError("Nothing could be cut out of this box.", 409)
    cut.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
    for old in folder.glob(f"cut-{bid}-*.webp"):   # the box has moved: its old cutouts are not shown again
        old.unlink(missing_ok=True)
    images.save_webp(cut, path, 80)
    return path


def add_items(conn, images_dir: Path, sid: str) -> dict:
    """Make an item of each box: its photo is the box cut out of this one, and it is queued for its cutout, then
    described, drawn and pattern-measured like any new item. Pressing Add again changes nothing."""
    row = get(conn, sid)
    if row["state"] == "added":
        return view(conn, row)
    boxes = json.loads(row["boxes"])
    if not boxes:
        raise items.ItemError(NO_BOXES)
    photo = _open_photo(images_dir, row)
    made: list[tuple[str, str, images.Stored, dict]] = []
    try:
        for box in boxes:   # the pictures first, outside the lock; the database rows after, all at once
            item_id, photo_id = uuid.uuid4().hex, uuid.uuid4().hex
            made.append((item_id, photo_id, images.store_image(crop(photo, box), images_dir, item_id, photo_id), box))
        conn.execute("BEGIN IMMEDIATE")
        fresh = get(conn, sid)
        if fresh["state"] == "added" or fresh["boxes"] != row["boxes"]:
            conn.execute("ROLLBACK")
            for item_id, *_ in made:
                shutil.rmtree(images_dir / item_id, ignore_errors=True)
            if fresh["state"] == "added":
                return view(conn, fresh)
            raise items.ItemError(CHANGED, 409)
        t = db.now()
        for item_id, photo_id, stored, box in made:
            conn.execute("INSERT INTO items (id, name, location, source_photo_id, source_box, created_at, updated_at) "
                         "VALUES (?, ?, 'closet', ?, ?, ?, ?)",
                         (item_id, None, sid, json.dumps({k: box[k] for k in EDGES}), t, t))
            conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, width, height, bytes, sha256, "
                         "source_sha256, created_at) VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?, ?)",
                         (photo_id, item_id, stored.original_path, stored.thumb_path, stored.width, stored.height,
                          stored.bytes, stored.sha256, row["source_sha256"], t))
            jobs.enqueue_cutout(conn, item_id, photo_id)
        conn.execute("UPDATE source_photos SET state = 'added', note = NULL, updated_at = ? WHERE id = ?", (t, sid))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
            for item_id, *_ in made:
                shutil.rmtree(images_dir / item_id, ignore_errors=True)
        raise
    for old in (images_dir / FOLDER / sid).glob("cut-*.webp"):   # the previews are not needed any more
        old.unlink(missing_ok=True)
    return view(conn, get(conn, sid))


# ------------------------------------------------------------------ finding the pieces

def _note_waiting(conn, note: str) -> None:
    conn.execute("UPDATE source_photos SET note = ? WHERE state = 'finding' AND coalesce(note, '') != ?", (note, note))


def find_one(conn, images_dir: Path, row, routes: tuple[str, ...], find: Finder) -> str:
    """Ask for the boxes of one photo. Returns 'done', 'failed' (tried again later, up to MAX_ATTEMPTS) or 'wait'
    (Claude can't be asked now: every waiting photo says why)."""
    try:
        found = find(_open_photo(images_dir, row), routes)
    except CapReached:
        _note_waiting(conn, LIMIT)
        return "wait"
    except PlanSignIn:
        _note_waiting(conn, SIGN_IN)
        return "wait"
    except RouteUnavailable:
        _note_waiting(conn, NO_ROUTE)
        return "wait"
    except Exception as e:
        log.warning("finding the pieces in a photo failed: %s", type(e).__name__)
        attempts = row["attempts"] + 1
        given_up = attempts >= MAX_ATTEMPTS
        conn.execute("UPDATE source_photos SET attempts = ?, state = ?, note = ?, updated_at = ? "
                     "WHERE id = ? AND state = 'finding'",
                     (attempts, "review" if given_up else "finding", FAILED if given_up else None, db.now(), row["id"]))
        return "failed"
    boxes = tidy(found)
    conn.execute("UPDATE source_photos SET boxes = ?, state = 'review', found_by = 'claude', note = ?, updated_at = ? "
                 "WHERE id = ? AND state = 'finding'",   # the owner has not started on the boxes meanwhile
                 (json.dumps(boxes), None if boxes else NONE_FOUND, db.now(), row["id"]))
    return "done"


class Worker:
    """One thread that asks for the boxes of the open closet's waiting photos, one at a time. Never the demo's."""

    def __init__(self, cfg: Config, state: State, routes: Callable[[], tuple[str, ...]], find: Finder, idle: float = 60):
        self.cfg, self.state, self.routes, self.find, self.idle = cfg, state, routes, find, idle
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="garment-finder", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                self.drain()
            except Exception:
                log.exception("garment finder error")
            self._wake.wait(timeout=self.idle)

    def drain(self) -> int:
        """Find the pieces in every waiting photo of the open closet. Returns how many were answered."""
        profile = self.state.get("profile")
        if profile == "demo":
            return 0
        conn = db.connect(self.cfg.db_path(profile))
        done = 0
        try:
            while not self._stop.is_set():
                row = conn.execute("SELECT * FROM source_photos WHERE state = 'finding' "
                                   "ORDER BY created_at, id LIMIT 1").fetchone()
                if row is None:
                    break
                routes = self.routes()
                if not routes:
                    _note_waiting(conn, NO_ROUTE)
                    break
                status = find_one(conn, self.cfg.images_dir(profile), row, routes, self.find)
                if status == "wait":
                    break
                done += status == "done"
        finally:
            conn.close()
        return done


# ------------------------------------------------------------------ endpoints

class BoxBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x0: float
    y0: float
    x1: float
    y1: float


class MergeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str]


def router(conn_dep, images_dir: Callable[[], Path], state: State, protected, wake_finder: Callable[[], None],
           wake_cutouts: Callable[[], None], cutter: Callable[[Image.Image], Image.Image],
           cutter_ready: Callable[[], bool]) -> APIRouter:
    r = APIRouter(dependencies=protected)

    @r.post("/api/sources")
    async def upload(response: Response, photo: UploadFile = File(...), client_key: str | None = Form(None),
                     photo_sha256: str | None = Form(None), conn=Depends(conn_dep)):
        data = await photo.read(images.MAX_UPLOAD_BYTES + 1)
        out, created = create(conn, images_dir(), data, client_key, photo_sha256 or None,
                              state.get("profile") == "demo")
        response.status_code = 201 if created else 200
        if created:
            wake_finder()
        return out

    @r.get("/api/sources")
    def list_open(conn=Depends(conn_dep)):
        return {"sources": open_list(conn)}

    @r.get("/api/sources/{source_id}")
    def get_one(source_id: str, conn=Depends(conn_dep)):
        return view(conn, get(conn, source_id))

    @r.delete("/api/sources/{source_id}", status_code=204)
    def forget_one(source_id: str, conn=Depends(conn_dep)):
        forget(conn, images_dir(), source_id)
        return Response(status_code=204)

    @r.post("/api/sources/{source_id}/boxes")
    def new_box(source_id: str, body: BoxBody, conn=Depends(conn_dep)):
        return add_box(conn, source_id, body.model_dump())

    @r.post("/api/sources/{source_id}/boxes/merge")
    def merge(source_id: str, body: MergeBody, conn=Depends(conn_dep)):
        return merge_boxes(conn, source_id, body.ids)

    @r.put("/api/sources/{source_id}/boxes/{box_id}")
    def put_box(source_id: str, box_id: str, body: BoxBody, conn=Depends(conn_dep)):
        return move_box(conn, source_id, box_id, body.model_dump())

    @r.delete("/api/sources/{source_id}/boxes/{box_id}")
    def delete_box(source_id: str, box_id: str, conn=Depends(conn_dep)):
        return remove_box(conn, source_id, box_id)

    @r.get("/api/sources/{source_id}/boxes/{box_id}/cutout.webp")
    def box_cutout(source_id: str, box_id: str, conn=Depends(conn_dep)):
        path = preview(conn, images_dir(), source_id, box_id, cutter, cutter_ready)
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @r.post("/api/sources/{source_id}/add")
    def add(source_id: str, conn=Depends(conn_dep)):
        out = add_items(conn, images_dir(), source_id)
        wake_cutouts()
        return out

    return r

