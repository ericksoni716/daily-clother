"""The background queue that asks Claude to describe each item once its cutout is ready.

Same queue and same rules as the cutouts (`jobs.py`): jobs are rows in the
`jobs` table (kind 'tag'), so nothing is lost on quit and an interrupted job
resumes; three attempts, then the item is marked failed with the reason in
plain words. When no route to Claude can be used the job waits, without using
up an attempt, and starts when one can. The routes are tried in the order
`GET /api/tagging` reports; the API key only when the owner has turned it on
and set a monthly limit, and never past that limit (`spend.py`): then the item
waits and says why.

The tagger's whole answer is kept with the item whatever happens to its
fields, and a field the owner has set is never overwritten. The demo closet is
never sent to Claude. Nothing about a photo, a key or the owner's files is
logged.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, history, illustrations, spend
from .config import Config
from .state import State
from .tagger import routes as tagger_routes
from .tagger.schema import NAMED_HEX, SCHEMA_VERSION, ItemTags
from .tagger.tagging import CONFIG, CapReached, Meter, RouteUnavailable, TagResult

log = logging.getLogger("closet.tagjobs")
KIND = "tag"
MAX_ATTEMPTS = 3   # as for cutouts
MODEL = CONFIG["roles"]["tagging"]

# photos (first: the front cutout) and the routes to try, in order -> the answer
Tagger = Callable[[list[Image.Image], tuple[str, ...]], TagResult]
Routes = Callable[[], tuple[str, ...]]   # the routes that can be used right now, in order

# the item's own fields an answer fills in, unless the owner has set them
FILLED = ("name", "category", "color", "color_hex", "pattern", "formality", "season", "silhouette", "material")
_CONFIDENCE = {"category": "category_confidence", "color": "color_confidence", "pattern": "pattern_confidence",
               "formality": "formality_confidence", "season": "season_confidence", "silhouette": "silhouette_confidence"}
FAILED = ("Claude could not describe this item after three tries. You can try again, or retake the photo "
          "against a plainer background.")
NO_PHOTO = "This item has no photo for Claude to look at."


# ------------------------------------------------------------------ the queue
def enqueue(conn, item_id: str) -> bool:
    """Queue tagging for an item, inside the caller's transaction. False if it is already queued or running."""
    if conn.execute("SELECT 1 FROM jobs WHERE kind = ? AND item_id = ? AND state IN ('queued', 'running')",
                    (KIND, item_id)).fetchone():
        return False
    t = db.now()
    conn.execute("INSERT INTO jobs (kind, item_id, created_at, updated_at) VALUES (?, ?, ?, ?)", (KIND, item_id, t, t))
    conn.execute("UPDATE items SET tag_state = 'waiting', tag_error = NULL, updated_at = ? WHERE id = ?", (t, item_id))
    return True


def waiting_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE kind = ? AND state IN ('queued', 'running')", (KIND,)).fetchone()[0]


def has_work(conn) -> bool:
    return conn.execute("SELECT 1 FROM jobs WHERE kind = ? AND state = 'queued' LIMIT 1", (KIND,)).fetchone() is not None


def recover(conn) -> int:
    """Put back jobs left 'running' by a round that stopped half-way (a crash, a locked database, or a quit
    while another closet was open). Only this worker runs tagging jobs, so between rounds none is really running.
    A job that has already used its three attempts is failed instead, so a job that keeps crashing ends."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    stale = conn.execute("SELECT id, item_id, attempts FROM jobs WHERE kind = ? AND state = 'running'", (KIND,)).fetchall()
    for job in stale:
        if job["attempts"] >= MAX_ATTEMPTS:
            conn.execute("UPDATE jobs SET state = 'failed', updated_at = ? WHERE id = ?", (t, job["id"]))
            conn.execute("UPDATE items SET tag_state = 'failed', tag_error = ?, updated_at = ? WHERE id = ?", (FAILED, t, job["item_id"]))
        else:
            conn.execute("UPDATE jobs SET state = 'queued', updated_at = ? WHERE id = ?", (t, job["id"]))
            conn.execute("UPDATE items SET tag_state = 'waiting', updated_at = ? WHERE id = ?", (t, job["item_id"]))
    conn.execute("COMMIT")
    return len(stale)


def note_limit(conn, reached: bool) -> None:
    """Tell the waiting items that the API key's monthly limit is what holds them up, or stop saying so."""
    if reached:
        conn.execute("UPDATE items SET tag_error = ? WHERE tag_state = 'waiting' AND tag_error IS NOT ?",
                     (spend.LIMIT_REACHED, spend.LIMIT_REACHED))
    else:
        conn.execute("UPDATE items SET tag_error = NULL WHERE tag_state = 'waiting' AND tag_error = ?", (spend.LIMIT_REACHED,))


def _photos(conn, images_dir: Path, item_id: str) -> list[Image.Image]:
    """The front photo's cutout first (what the prompt expects), then any other photos of the item."""
    out = []
    for n, p in enumerate(conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at",
                                       (item_id,)).fetchall()):
        cutout = n == 0 and p["cutout_path"]
        with Image.open(images_dir / (p["cutout_path"] if cutout else p["original_path"])) as im:
            out.append(im.convert("RGBA") if cutout else im.convert("RGB"))   # WebP drops an alpha that is all opaque
    if not out:
        raise LookupError(NO_PHOTO)
    return out


def run_one(conn, images_dir: Path, routes: tuple[str, ...], tagger: Tagger) -> str:
    """Describe the oldest waiting item. Returns 'empty' (nothing waits), 'done' (a job was worked on)
    or 'blocked' (no route could be used after all; the job waits again and keeps its attempts)."""
    conn.execute("BEGIN IMMEDIATE")
    job = conn.execute("SELECT * FROM jobs WHERE kind = ? AND state = 'queued' ORDER BY id LIMIT 1", (KIND,)).fetchone()
    if job is None:
        conn.execute("COMMIT")
        return "empty"
    t = db.now()
    conn.execute("UPDATE jobs SET state = 'running', attempts = attempts + 1, updated_at = ? WHERE id = ?", (t, job["id"]))
    conn.execute("UPDATE items SET tag_state = 'working', updated_at = ? WHERE id = ?", (t, job["item_id"]))
    conn.execute("COMMIT")
    attempts = job["attempts"] + 1
    try:
        result = tagger(_photos(conn, images_dir, job["item_id"]), routes)
        if not isinstance(result.tags, ItemTags):
            raise TypeError("the tagger did not return a tagging answer")
    except RouteUnavailable as e:
        # nothing is wrong with the item: Claude cannot be reached right now, so it waits without losing an attempt
        log.info("tagging job %s is waiting: no route to Claude can be used right now", job["id"])
        t = db.now()
        conn.execute("UPDATE jobs SET state = 'queued', attempts = attempts - 1, updated_at = ? WHERE id = ?", (t, job["id"]))
        conn.execute("UPDATE items SET tag_state = 'waiting', updated_at = ? WHERE id = ?", (t, job["item_id"]))
        # every waiting item waits for the same reason; say so when it is the monthly limit
        note_limit(conn, isinstance(e, CapReached))
        return "blocked"
    except Exception as e:  # any failure is recorded against the job, never lost; only its kind is logged
        log.warning("tagging job %s failed (attempt %s): %s", job["id"], attempts, type(e).__name__)
        t = db.now()
        missing = isinstance(e, (LookupError, OSError))
        if attempts < MAX_ATTEMPTS and not missing:
            conn.execute("UPDATE jobs SET state = 'queued', error = ?, updated_at = ? WHERE id = ?", (str(e)[:500], t, job["id"]))
            conn.execute("UPDATE items SET tag_state = 'waiting', tag_error = NULL, updated_at = ? WHERE id = ?", (t, job["item_id"]))
        else:
            conn.execute("UPDATE jobs SET state = 'failed', error = ?, updated_at = ? WHERE id = ?", (str(e)[:500], t, job["id"]))
            conn.execute("UPDATE items SET tag_state = 'failed', tag_error = ?, updated_at = ? WHERE id = ?",
                         (NO_PHOTO if missing else FAILED, t, job["item_id"]))
        return "done"
    conn.execute("BEGIN IMMEDIATE")
    try:
        apply_answer(conn, job["item_id"], result.tags, route=result.route, model=result.model)
        note_limit(conn, False)   # Claude could be reached: the others are no longer held up by the limit
        conn.execute("UPDATE jobs SET state = 'done', error = NULL, updated_at = ? WHERE id = ?", (db.now(), job["id"]))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return "done"


# ------------------------------------------------------------- the answer
def suggest_name(tags: ItemTags) -> str:
    """A short name from the answer, e.g. "Navy polo", "Grey plaid shirt", "Light blue jeans"."""
    words = [] if tags.color == "multi" else [tags.color.replace("_", " ")]
    if tags.pattern in ("stripe", "plaid", "floral", "camo", "graphic"):
        words.append({"stripe": "striped"}.get(tags.pattern, tags.pattern))
    noun = {"tee": "tee", "dress_shoes": "dress shoes", "other": "item"}.get(tags.category, tags.category)
    if tags.category == "tee" and tags.details.neckline == "henley":
        noun = "henley"
    text = " ".join(words + [noun])
    return text[:1].upper() + text[1:]


def suggested_fields(tags: ItemTags) -> dict:
    """What the answer says each of the item's own fields should be (None: nothing to say)."""
    return {
        "name": suggest_name(tags), "category": tags.category, "color": tags.color, "color_hex": NAMED_HEX.get(tags.color),
        "pattern": tags.pattern, "formality": tags.formality, "season": tags.season,
        "silhouette": {k: v for k, v in tags.silhouette.model_dump().items() if v is not None},
        "material": tags.material,
    }


def fill(tags: ItemTags, field: str, current, by: str | None, suggested: dict | None = None) -> tuple | None:
    """What an answer does to one of the item's fields, which is `current` and was set by `by`: None when it leaves
    it as it is, else (value, who set it, how sure). A value of None clears the field (who set it is then None).

    A field is filled when the owner has not set it (`by` is "user" for those) and it is either empty or was filled
    by an earlier answer. Undoing a change uses the same rule (`corrections.undo`), so a field given back to the
    tagger is what the answer the item has now says.
    """
    value = (suggested or suggested_fields(tags))[field]
    if by == "user" or (current not in (None, "", {}) and by != "ai"):
        return None
    if value in (None, "", {}):
        return (None, None, None) if by == "ai" else None
    return value, "ai", getattr(tags, _CONFIDENCE[field]) if field in _CONFIDENCE else None


def apply_answer(conn, item_id: str, tags: ItemTags, route: str, model: str | None) -> None:
    """Store the whole answer and fill in the item's fields, inside the caller's transaction.

    A field is filled when the owner has not set it (`source` says "user" for those) and it is either
    empty or was filled by an earlier answer. A name given at upload is the owner's too, so it stays.
    """
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:   # deleted while Claude was looking at it
        return
    source = json.loads(row["source"] or "{}")
    confidence = json.loads(row["confidence"] or "{}")
    sets: dict = {}
    suggested = suggested_fields(tags)
    for field in suggested:
        current = json.loads(row["silhouette"] or "{}") if field == "silhouette" else row[field]
        filled = fill(tags, field, current, source.get(field), suggested)
        if filled is None:
            continue
        value, by, sure = filled
        sets[field] = (json.dumps(value) if value else "{}") if field == "silhouette" else value
        if by is None:   # the earlier answer said something this one does not: clear it
            source.pop(field, None)
            confidence.pop(field, None)
            continue
        source[field] = by
        if sure is not None:
            confidence[field] = sure
    confidence["details"] = tags.details_confidence
    t = db.now()
    sets.update(source=json.dumps(source), confidence=json.dumps(confidence), tag_state="done", tag_error=None,
                tag_answer=json.dumps(tags.model_dump(mode="json")), tag_schema_version=SCHEMA_VERSION,
                tag_route=route, tag_model=model, tagged_at=t, updated_at=t)
    conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
    illustrations.redraw(conn, item_id)   # the drawing follows the new answer (and the owner's own fields and details)
    history.record(conn, row, conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone(), "claude", "answer",
                   always=True)


# ------------------------------------------------------- reaching Claude
def usable_routes(state: State) -> tuple[str, ...]:
    """The routes that can be used now, in the order part 1 reports them.

    The API key is billed, so it is only used when the owner has turned it on and set a monthly limit.
    Whether the limit leaves room is checked before each request (`spend.Meter`), so an item can say why it waits.
    """
    allowed = []
    for r in tagger_routes.status()["routes"]:
        if r["available"] and (r["id"] != "api" or spend.api_allowed(state)):
            allowed.append(r["id"])
    return tuple(allowed)


def claude_tagger(images: list[Image.Image], routes: tuple[str, ...], meter: Meter | None = None, client=None) -> TagResult:
    """Ask Claude, trying `routes` in order; a route that turns out unusable is skipped.

    The API route still refuses to run without a key (`Router`), whatever it is told. `meter` records each call
    and keeps the API key under its limit; `client` stands in for the API in tests.
    """
    order = next((name for name, seq in tagger_routes.ORDERS.items() if seq == routes), None)
    if order is None:
        raise RouteUnavailable("no route to Claude can be used right now")
    return tagger_routes.Router(order, client=client, meter=meter).tag(MODEL, images)


class Worker:
    """One thread that describes the open closet's waiting items whenever a route to Claude can be used."""

    def __init__(self, cfg: Config, state: State, routes: Routes, tagger: Tagger, idle: float = 60):
        self.cfg, self.state, self.routes, self.tagger, self.idle = cfg, state, routes, tagger, idle
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="tag-worker", daemon=True)
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
            try:
                self.drain()
            except Exception:  # keep the worker alive; the next wake retries
                log.exception("tagging worker error")
            self._wake.wait(timeout=self.idle)   # also how a route that becomes usable is noticed
            self._wake.clear()

    def drain(self) -> int:
        """Describe waiting items until none are left or Claude cannot be reached. Returns how many were worked on."""
        done = 0
        profile = self.state.get("profile")
        if profile == "demo":   # the demo closet is never sent to Claude
            return done
        path = self.cfg.db_path(profile)
        if not path.exists():
            return done
        conn = db.connect(path)
        try:
            recover(conn)
            while not self._stop.is_set() and has_work(conn):
                # asked again before each item, so turning the API key off (or a plan limit) takes effect at once
                routes = self.routes()
                if not routes:
                    note_limit(conn, False)   # nothing can be tried at all: the limit is not what they wait for
                    break
                if run_one(conn, self.cfg.images_dir(profile), routes, self.tagger) != "done":
                    break
                done += 1
        finally:
            conn.close()
        return done
