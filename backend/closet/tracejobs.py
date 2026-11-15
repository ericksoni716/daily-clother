"""Tracing a shoe from its photo, in the cut-out queue (#206, shoe tracing stage 2b).

A shoe (sneakers, boots, dress shoes, sandals) waits to be traced once it has a cutout and is known to be a shoe:
when Claude's description says so (`tagjobs.apply_answer`, which also gives the photo's view and how many shoes it
shows), when the owner says it is one (`items.update`), when its photo is replaced (`jobs.run_one`, once the new
cutout is made), when the owner asks for it again ("Re-trace"), and when it was traced by older tracing code than
this program's (`TRACING_VERSION`). The cut-out queue (`jobs.Worker`) traces waiting shoes after its cutouts, one at
a time, never in a request: `drawing.trace.trace_photo` on the stored photo, through the quality gate, then
`drawing.traced.traced_shoe`. The traced shoe is kept as JSON in `items.trace` and the item is drawn again.

A photo the gate turns down keeps the template drawing ("refused"), and the item page says why in plain words
(`plain`). A trace that fails for another reason does the same ("failed"). Tracing never costs an item its drawing.

The owner's fixes (a part's colour, a mark removed or moved) are kept apart from the trace in `items.trace_fixes`
(`drawing.sideshoe` lays them over it), so a new trace keeps them wherever they still fit; `items.trace_plain` is
the owner choosing the template drawing for this shoe.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

import numpy as np
from PIL import Image

from . import illustrations
from .drawing import sideshoe
from .drawing.traced import TracedShoe

log = logging.getLogger("closet.tracejobs")

SHOES = ("sneakers", "boots", "dress_shoes", "sandals")
# Raised whenever `drawing.trace` or `drawing.traced` change what a trace finds: a shoe traced by older code is
# traced again (`stale`), in the background, the next time the queue runs.
TRACING_VERSION = 1
MAX_PHOTO = 1600   # the instant check reads the photo at most this size, as the stored photo is

FAILED = "Closet could not trace the shoe from its photo, so it's drawn from its details instead."
NO_PHOTO = "This shoe has no photo to trace."
NOT_A_SHOE = "Only shoes are traced from their photo."
TIP = "A side-on photo of one shoe, toe to the left, gives a closer drawing."

# (the photo ..., what would do better): the gate's signals and the tagger's word on the photo (`drawing.trace`'s
# GATE and TOLD), in plain words
PLAIN = {
    "pair": ("shows both shoes of a pair", "A photo of one shoe on its own, side-on, gives a closer drawing."),
    "more": ("shows more than one shoe", "A photo of one shoe on its own, side-on, gives a closer drawing."),
    "front": ("shows the shoe from the front", "A side-on photo gives a closer drawing."),
    "back": ("shows the shoe from the back", "A side-on photo gives a closer drawing."),
    "top": ("shows the shoe from above", "A side-on photo gives a closer drawing."),
    "angled": ("shows the shoe at an angle", "A side-on photo gives a closer drawing."),
    "found": ("doesn't show a shoe Closet could find",
              "A photo of one shoe against a plain background gives a closer drawing."),
    "size_px": ("shows the shoe very small", "A photo with the shoe filling most of it gives a closer drawing."),
    "sharpness": ("is blurred", "A sharp photo, with the phone held still, gives a closer drawing."),
    "contrast_de": ("shows the shoe on a background of almost the same colour",
                    "A photo against a plain background of another colour gives a closer drawing."),
    "clipped": ("is too bright or too dark on the shoe", "A photo in softer, even light gives a closer drawing."),
    "edge_touch": ("cuts off part of the shoe at its edge",
                   "A photo with the whole shoe in it, and a little space round it, gives a closer drawing."),
    "second_piece": ("shows more than the shoe (another shoe, or a hand)",
                     "A photo of one shoe on its own gives a closer drawing."),
    "solidity": ("shows something over the shoe, or its outline could not be found cleanly",
                 "A photo of the whole shoe against a plain background gives a closer drawing."),
    "aspect": ("doesn't show the shoe side-on", TIP),
    "sole_lift": ("doesn't show the shoe side-on", TIP),
    "toe_heel": ("doesn't show the shoe side-on", TIP),
    "trace_iou": ("could not be traced closely enough", "A side-on photo against a plain background gives a closer drawing."),
}

# photo, the tagger's word on it (`trace.told_from`) -> the traced shoe (None when no shoe was found) and the gate's reasons
Tracer = Callable[[Image.Image, dict], "tuple[TracedShoe | None, list[str]]"]
Masker = Callable[[Image.Image], "np.ndarray | None"]   # photo -> a soft mask, 0..255, or None when it cannot run


def wanted(category) -> bool:
    return isinstance(category, str) and category in SHOES


STATES = {   # the trace's state, as the item page says it
    "waiting": "The shoe will be traced from its photo in a moment.",
    "working": "Tracing the shoe from its photo…",
}


def shoe_of(row) -> TracedShoe | None:
    try:
        return TracedShoe.from_json(row["trace"]) if row["trace"] else None
    except (ValueError, KeyError, TypeError):
        return None


def fixes_of(row) -> dict:
    out = _json(row["trace_fixes"])
    return out if isinstance(out, dict) else {}


def shown(row) -> dict | None:
    """What the item page shows of a shoe's trace; None for anything that is not a shoe.

    state: null (not traced), waiting, working, done, refused (the photo would not trace well) or failed.
    message: what is happening or why the shoe is drawn from its details, in plain words.
    drawn: the item's drawing is the traced one. plain: the owner chose the plain drawing.
    parts and marks: what Fix the details can change, when the shoe is traced."""
    if not wanted(row["category"]):
        return None
    state = row["trace_state"]
    message = STATES.get(state) or (row["trace_error"] if state in ("refused", "failed") else None)
    out = {"state": state, "message": message, "drawn": illustrations.traced(row) is not None,
           "plain": bool(row["trace_plain"]), "parts": [], "marks": [], "fixed": False}
    shoe = shoe_of(row) if state == "done" else None
    if shoe is None:
        return out
    fixes = fixes_of(row)
    own = {k: v for k, v in (fixes.get("parts") or {}).items() if isinstance(v, str)}
    out["parts"] = [{"name": name, "title": sideshoe.PART_WORDS[name], "color": own.get(name, color), "traced": color,
                     "own": name in own} for name, color in sideshoe.parts(shoe)]
    for i, (m, f) in enumerate(zip(shoe.marks, sideshoe.mark_fixes(shoe, fixes), strict=True)):
        f = f or {}
        dx, dy = sideshoe._move(f)
        out["marks"].append({"index": i, "kind": m.kind, "title": sideshoe.MARK_WORDS.get(m.kind, "mark"),
                             "color": f.get("color") or m.color, "hidden": bool(f.get("hide")),
                             "moved": [round(dx, 2), round(dy, 2)]})
    out["fixed"] = bool(own) or bool(fixes.get("marks"))
    return out


def _json(text):
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def mark(conn, item_id: str, again: bool = True) -> None:
    """A shoe with a photo waits to be traced (again, unless `again` is False and it already was), inside the
    caller's transaction. Anything else is left as it is: an item that stops being a shoe keeps its trace and the owner's
    fixes, unused (`illustrations.traced`), and is drawn from them again if it is said to be a shoe again."""
    row = conn.execute("SELECT category, trace_state FROM items WHERE id = ?", (item_id,)).fetchone()
    if (row is not None and wanted(row["category"]) and (again or row["trace_state"] is None)
            and _front(conn, item_id) is not None):   # a shoe with no photo has nothing to trace
        conn.execute("UPDATE items SET trace_state = 'waiting', trace_error = NULL WHERE id = ?", (item_id,))


def answered(conn, item_id: str) -> None:
    """Claude has just described the item (inside the caller's transaction): a shoe not traced yet waits to be;
    one traced (or being traced) before Claude's word on its photo was known, or which Claude now sees differently,
    is traced again with it; anything else is left as it is."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return
    if not wanted(row["category"]):
        return
    if row["trace_state"] in (None, "working"):   # one being traced is traced again: its result is set aside
        conn.execute("UPDATE items SET trace_state = 'waiting', trace_error = NULL WHERE id = ?", (item_id,))
        return
    if row["trace_state"] == "waiting":
        return
    photo = _front(conn, item_id)
    try:
        before = (json.loads(row["trace"]).get("gate") or {}).get("told") or {} if row["trace"] else {}
    except (ValueError, AttributeError):
        before = {}
    if photo is not None and told(row, photo) != before:
        conn.execute("UPDATE items SET trace_state = 'waiting', trace_error = NULL WHERE id = ?", (item_id,))


def forget(conn, item_id: str) -> None:
    """The item's trace is no longer of its photo (it was replaced): it is dropped, and the drawing goes back to
    the template until the shoe is traced again. The owner's fixes stay, for the new trace."""
    conn.execute("UPDATE items SET trace = NULL, trace_version = NULL, trace_state = NULL, trace_error = NULL "
                 "WHERE id = ?", (item_id,))


def stale(conn) -> int:
    """Shoes traced by older tracing code wait to be traced again."""
    return conn.execute("UPDATE items SET trace_state = 'waiting', trace_error = NULL WHERE trace_state IN "
                        f"('done', 'refused', 'failed') AND (trace_version IS NULL OR trace_version < ?) AND category IN {SHOES}",
                        (TRACING_VERSION,)).rowcount


def recover(conn) -> None:
    """A trace interrupted by a quit starts again."""
    conn.execute("UPDATE items SET trace_state = 'waiting' WHERE trace_state = 'working'")


def waiting_count(conn) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM items WHERE trace_state IN ('waiting', 'working') AND category IN {SHOES}"
                        ).fetchone()[0]


def _front(conn, item_id: str):
    return conn.execute("SELECT * FROM photos WHERE item_id = ? AND kind = 'front' ORDER BY created_at LIMIT 1",
                        (item_id,)).fetchone()


def told(row, photo) -> dict:
    """The tagger's word on the photo (how many shoes, from where), when its answer was given for this photo: an
    answer older than the photo (it was replaced and is being described again) says nothing about it."""
    from .drawing.trace import told_from
    if not row["tag_answer"] or not row["tagged_at"] or row["tagged_at"] < photo["created_at"]:
        return {}
    try:
        answer = json.loads(row["tag_answer"])
    except ValueError:
        return {}
    return told_from(answer) if isinstance(answer, dict) else {}


def run_one(conn, images_dir, tracer: Tracer) -> str:
    """Trace the oldest waiting shoe whose cutout is ready. Returns 'empty' or 'done'."""
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(f"SELECT * FROM items WHERE trace_state = 'waiting' AND cutout_state = 'ready' "
                       f"AND category IN {SHOES} ORDER BY updated_at, id LIMIT 1").fetchone()
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id = row["id"]
    conn.execute("UPDATE items SET trace_state = 'working' WHERE id = ?", (item_id,))
    conn.execute("COMMIT")
    shoe, state, error = None, "failed", FAILED
    try:
        photo = _front(conn, item_id)
        if photo is None:
            error = NO_PHOTO
        else:
            with Image.open(images_dir / photo["original_path"]) as im:
                img = im.convert("RGB")
            shoe, reasons = tracer(img, told(row, photo))
            if shoe is not None and shoe.gate.get("ok"):
                state, error = "done", None
            elif reasons:
                state, error = "refused", plain(reasons)
    except Exception as e:   # never lost: the item says why and keeps its template drawing
        log.warning("tracing a shoe failed: %s", type(e).__name__, exc_info=True)
        shoe = None
    conn.execute("BEGIN IMMEDIATE")
    try:
        now = conn.execute("SELECT trace_state FROM items WHERE id = ?", (item_id,)).fetchone()
        if now is None or now["trace_state"] != "working":
            conn.execute("COMMIT")   # deleted, its photo replaced or asked to be traced again meanwhile
            return "done"
        conn.execute("UPDATE items SET trace = ?, trace_version = ?, trace_state = ?, trace_error = ? WHERE id = ?",
                     (shoe.to_json() if shoe is not None else None, TRACING_VERSION, state, error, item_id))
        illustrations.redraw(conn, item_id)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return "done"


def _keys(reasons: list[str]) -> list[str]:
    """The gate's reasons (`drawing.trace.Gate.reasons`) as the keys of PLAIN, in order, once each."""
    from .drawing.trace import GATE, TOLD
    out: list[str] = []
    for r in reasons:
        key = next((v for (_, v), why in TOLD.items() if r == why), None)
        key = key or next((name for name, (_, _, why) in GATE.items() if r.startswith(why)), None)
        if key and key in PLAIN and key not in out:
            out.append(key)
    return out


def plain(reasons: list[str]) -> str:
    """Why the shoe is drawn from its details, in plain words: the first reason the gate gave, and what would do
    better."""
    keys = _keys(reasons)
    if not keys:
        return f"The photo could not be traced well, so it's drawn from its details instead. {TIP}"
    what, better = PLAIN[keys[0]]
    return f"The photo {what}, so it's drawn from its details instead. {better}"


def check(img: Image.Image, maskers: list[tuple[str, Masker]]) -> dict:
    """The instant check of a photo before it is added (the Add screen): the quality gate on its cut-out, without
    tracing it. Returns {"ok": bool, "reasons": [plain sentences]}. The tagger's word is not known yet, so only what
    the photo itself shows is checked."""
    from .drawing import trace as T
    img = img.convert("RGB")
    img.thumbnail((MAX_PHOTO, MAX_PHOTO), Image.LANCZOS)
    rgb = np.asarray(img)
    best = None
    for _, cut in maskers:
        soft = cut(img)
        if soft is None:
            continue
        signals, mask = T.photo_signals(rgb, soft)
        if signals["found"]:
            signals.update(T.work_signals(T.orient(rgb, mask)))
        g = T.gate(signals)
        if best is None or len(g.reasons) < len(best.reasons):
            best = g
        if g.ok:
            break
    if best is None:
        return {"ok": False, "reasons": [_sentence("found")]}
    return {"ok": best.ok, "reasons": [_sentence(k) for k in _keys(best.reasons)] or
            ([] if best.ok else ["This photo may not trace well. " + TIP])}


def _sentence(key: str) -> str:
    what, better = PLAIN[key]
    return f"The photo {what}. {better}"


def tracer(model: Masker | None = None) -> Tracer:
    """The app's tracer: the cut-out model first when it can run (`model` returns None when it cannot), then
    GrabCut; OpenCV is loaded only when a shoe is traced."""
    def run(img: Image.Image, told_: dict):
        from .drawing import trace as T
        from .drawing import traced
        maskers = ([("model", model)] if model else []) + [("grabcut", T.grabcut_mask)]
        reading = T.trace_photo(img, maskers, told=told_)
        return traced.traced_shoe(reading), list(reading.gate.reasons)
    return run
