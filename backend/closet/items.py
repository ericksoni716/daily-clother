"""Reading and changing items."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from . import (
    additions,
    away,
    db,
    details,
    failures,
    history,
    illustrations,
    images,
    jobs,
    kinds,
    look,
    outfits,
    palette,
    patjobs,
    progress,
    shoedraw,
    shoeviews,
    tagjobs,
    tracejobs,
    vocab,
)
from .tagger import surfaceform
from .tagger.taxonomy import SHADES, nearest_shade

TEXT_FIELDS = ("name", "brand", "size", "material", "fit_notes", "wear_notes", "acquired_on", "notes", "rating_reason", "color_hex")
ENUM_FIELDS = tuple(vocab.ENUM_FIELDS)
# `shade`: one of the owner's named shades (the taxonomy's `colors.shades`), kept with the owner's details; it decides
# the colour word and the colour the item is drawn in (`_shade`), and null gives it back to Claude
PATCHABLE = set(TEXT_FIELDS) | set(ENUM_FIELDS) | {"silhouette", "price_cents", "status", "shade", "formality_also"}
# the essentials the owner goes through on every new item (with what it is: `corrections.set_kind`); changing one counts
# as having checked the item, so it leaves the review (`review.queue`)
ESSENTIALS = ("name", "brand", "price_cents")
RECENT_WEARS = 10


class ItemError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message, self.status = message, status


def _media(rel: str | None) -> str | None:
    return f"/media/{rel}" if rel else None


def _front(conn, item_id: str):
    return conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at LIMIT 1", (item_id,)).fetchone()


def summary(conn, row) -> dict:
    row = illustrations.current(conn, row)   # an item never drawn, or drawn by older drawing code, is drawn now
    photo = _front(conn, row["id"])
    worn = conn.execute("SELECT max(worn_on), count(*) FROM wears WHERE item_id = ?", (row["id"],)).fetchone()
    thumb = None
    if photo is not None:
        thumb = photo["cutout_thumb_path"] or photo["thumb_path"]
    shoe = tracejobs.wanted(row["category"])
    return {
        "id": row["id"], "name": row["name"], "category": row["category"], "color": row["color"],
        "color_hex": row["color_hex"], "pattern": row["pattern"], "location": row["location"], "rating": row["rating"],
        "status": row["status"], "cutout_state": row["cutout_state"], "thumb_url": _media(thumb),
        "has_illustration": row["illustration_svg"] is not None, "has_photo": photo is not None,
        "illustration_url": (f"/api/items/{row['id']}/illustration.svg?v={hashlib.sha256(row['illustration_svg'].encode()).hexdigest()}"
                             if row["illustration_svg"] is not None else None),
        "last_worn": worn[0], "wear_count": worn[1], "wears_since_wash": row["wears_since_wash"], "laundry": row["laundry"],
        # where it is when not in the closet ({place, since, until}: at the cleaner's, at the tailor's, lent out), or null
        "away": away.fields(row),
        "tag_state": row["tag_state"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        # why describing failed, or why it waits (the API key's monthly limit, Claude Code's sign-in): the import list
        # on Add reads the list and says it once for all the photos just added
        "tag_error": row["tag_error"],
        **kinds.summary_fields(row),   # what it is: its kind from the taxonomy, and the group it is shown in
        # a shoe drawn by Claude for the outfit figure: how far that has got, and a short hash of the drawing it has
        # (the figure on Today and a trip's days is drawn again when it changes); null for anything else
        "drawn_state": row["drawn_state"] if shoe else None,
        "drawn_version": hashlib.sha256(row["drawn"].encode()).hexdigest()[:16] if shoe and row["drawn"] else None,
        # how far the work on it has got (`progress.of`): cutting out, describing and drawing, finishing the drawing;
        # null when nothing is being done to it and nothing failed on the way
        "progress": progress.of(row),
        # what the closet's search looks in besides the above (it searches the list it holds, so it works offline): the
        # brand, the material, the owner's name for its shade and every note the item page's one notes box shows
        "brand": row["brand"], "material": row["material"],
        "shade": shade_of(row, _said(row)),
        "own_notes": own_notes(row),
    }


NOTE_FIELDS = ("wear_notes", "fit_notes", "notes", "rating_reason")


def own_notes(row) -> str:
    """Every note kept about the item, each once, one after the other: what the one notes box on its page shows
    (`look.ts`, `notesText`)."""
    seen: list[str] = []
    for f in NOTE_FIELDS:
        t = (row[f] or "").strip()
        if t and t not in seen:
            seen.append(t)
    return "\n".join(seen)


def detail(conn, row) -> dict:
    row = illustrations.current(conn, row)
    out = summary(conn, row)
    for f in ("formality", "formality_also", "season", "brand", "size", "material", "fit_notes", "wear_notes", "condition",
              "price_cents", "acquired_on", "notes", "rating_reason", "illustration_svg", "cutout_error", "checked_at"):
        out[f] = row[f]
    for f in ("confidence", "source"):
        out[f] = json.loads(row[f] or "{}")
    out.update(away.detail(conn, row))   # where it is, with the owner's note, and a return today that can be undone
    # the look, read from one place (`look`): the description the drawing was made from, with the owner's corrections
    # folded over it. `silhouette` is its coarse shape as drawn (the details decide, the coarse shape fills in) and
    # `details` its details as drawn (null when Claude has not described it), so no word on the page can disagree
    # with the drawing
    found = look.answer(row)
    out["silhouette"] = look.shape_of(found)
    for f in ("tag_error", "tag_route", "tag_model", "tag_schema_version", "tagged_at"):
        out[f] = row[f]
    # the pattern measured from the photo: null (nothing to measure), waiting, working, done or failed
    out["pattern_state"], out["pattern_error"] = row["pattern_state"], row["pattern_error"]
    # its colours as measured from the pattern, largest first, each {color, hex, share}; empty when not measured
    out["pattern_colors"] = palette.shown(row)
    # why the cutout or the description failed, with the stored reason cleaned of keys and outside paths
    out["failure"] = failures.of(conn, row)
    # what the tagger saw that no field (or drawing) covers yet
    said = (_answer_json(row["tag_answer"]) or {}).get("details")
    said = dict(said) if isinstance(said, dict) else {}
    out["seen_not_drawn"] = illustrations.not_drawn(row, said.get("other_features") or [])
    drawn = dict(found.get("details") or {}) if isinstance(found, dict) and isinstance(found.get("details"), dict) else {}
    drawn.pop("other_features", None)
    out["details"] = drawn if said and drawn else None
    out["own_details"] = details.own(row)   # the details the owner has set, laid over Claude's when drawn
    out["shade"] = shade_of(row, drawn)
    # who said what it is (the owner or Claude), how sure Claude was, and the kinds Claude's answer also fits
    kind = kinds.of_row(row)
    out["kind_by"], out["kind_confidence"] = kind["by"], kind["confidence"]
    out["kind_alternatives"] = kinds.alternatives(row, kind["kind"])
    out["drawing_notes"] = illustrations.notes(row)
    # how it sits on the outfit figure: its fit, length and sleeves (or leg), each with the detail that corrects it
    out["as_worn"] = illustrations.worn(row)
    # trousers and shorts: a small drawing from behind (back pockets, yoke, label), its address versioned like the drawing's
    back = illustrations.back(row)
    out["back_url"] = f"/api/items/{row['id']}/back.svg?v={hashlib.sha256(back.encode()).hexdigest()}" if back else None
    out["photos"] = [{
        "id": p["id"], "kind": p["kind"], "url": _media(p["original_path"]), "thumb_url": _media(p["thumb_path"]),
        "cutout_url": _media(p["cutout_path"]), "cutout_thumb_url": _media(p["cutout_thumb_path"]),
        "width": p["width"], "height": p["height"],
        # a shoe's photos: the view each shows (outer, inner, top, front, back, sole or other; null: not sorted), whether
        # that is sure, and who said so (model or owner)
        "view": p["view"], "view_sure": None if p["view_sure"] is None else bool(p["view_sure"]), "view_by": p["view_by"],
    } for p in conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at, id",
                            (row["id"],))]
    # a shoe's photos sorted into views: its state, a plain message, and the photos to choose the outside from (null:
    # not a shoe)
    out["views"] = shoeviews.shown(conn, row)
    # a shoe drawn by Claude from its photos for the outfit figure: its state, a plain message, the drawing's address
    # and what it took (null: not a shoe)
    out["drawn"] = shoedraw.shown(conn, row)
    # a shoe's trace from its photo: its state, why it was turned down, and what Fix the details can change (null: not a shoe)
    out["trace"] = tracejobs.shown(row)
    # what Claude drew onto the drawing at the owner's word: the line on its way, what was added and how to undo it
    # (null: a shoe)
    out["additions"] = additions.shown(row)
    out["recent_wears"] = [r[0] for r in conn.execute(
        "SELECT worn_on FROM wears WHERE item_id = ? ORDER BY worn_on DESC LIMIT ?", (row["id"], RECENT_WEARS))]
    # the same wears grouped by the outfit each was worn in, for the item page (`worn.of_item`)
    from . import worn  # worn reads this module
    out["worn_in"] = worn.of_item(conn, row["id"])
    # why Today would find nothing to build around it ("laundry", "away", ...), or null when it can (`outfits`)
    out["build_around"] = outfits.cannot_build_around(dict(row))
    # the photo of several pieces this item was cut from, and its box in it (fractions); null for a photo of its own
    out["source_photo"] = None
    if row["source_photo_id"]:
        src = conn.execute("SELECT id, original_path FROM source_photos WHERE id = ?", (row["source_photo_id"],)).fetchone()
        if src is not None:
            out["source_photo"] = {"id": src["id"], "photo_url": _media(src["original_path"]),
                             "box": json.loads(row["source_box"]) if row["source_box"] else None}
    return out


def _said(row) -> dict:
    """The details in Claude's answer (an empty dict when there is none, or it was stored broken)."""
    said = (_answer_json(row["tag_answer"]) or {}).get("details")
    return said if isinstance(said, dict) else {}


def _answer_json(text) -> dict | None:
    try:
        found = json.loads(text) if text else None
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def shades() -> list[dict]:
    """The owner's named shades in the taxonomy's order, each with its colour and the colour word it is a shade of:
    what the item page's Colour row offers under a colour (`GET /api/vocab`)."""
    return [{"name": name, "hex": hex_, "color": color} for name, (hex_, color) in SHADES.items()]


def shade_of(row, said: dict) -> str | None:
    """The owner's name for the item's shade (docs/menswear-taxonomy.json, colors.shades): the one the owner chose,
    else the one the tagger named, when it is a shade of the item's colour; else the nearest to its measured colour.
    The owner's is read from their details as well as from `said`, since an item with nothing to draw has no
    details as drawn. A colour the owner gave without a shade (the colour word alone, or with its own colour) names
    no shade: only the colour is known, and the page does not claim a shade nobody chose."""
    color = row["color"]
    own = details.own(row).get("shade")
    if own in SHADES and SHADES[own][1] == color:
        return own
    source = json.loads((row["source"] if "source" in row.keys() else None) or "{}")
    if source.get("color_hex") == "user":
        return None
    if said.get("shade") in SHADES and SHADES[said["shade"]][1] == color:
        return said["shade"]
    return nearest_shade(row["color_hex"], color) if row["color_hex"] and color in {c for _, c in SHADES.values()} else None


def get(conn, item_id: str):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ItemError("That item does not exist.", 404)
    return row


def list_items(conn, status: str = "active", category: str | None = None, q: str | None = None,
               laundry: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM items WHERE status = ?", [status]
    if laundry:
        sql += " AND laundry = ?"
        args.append(laundry)
    if category:
        sql += " AND category = ?"
        args.append(category)
    if q:
        like = f"%{q.strip().lower()}%"
        # the notes in every box they may be kept in: the item page writes them all into `wear_notes` once edited
        sql += (" AND (lower(coalesce(name,'')) LIKE ? OR lower(coalesce(brand,'')) LIKE ? OR lower(coalesce(category,'')) LIKE ?"
                " OR lower(coalesce(color,'')) LIKE ? OR lower(coalesce(notes,'')) LIKE ? OR lower(coalesce(wear_notes,'')) LIKE ?"
                " OR lower(coalesce(fit_notes,'')) LIKE ? OR lower(coalesce(rating_reason,'')) LIKE ?)")
        args += [like] * 8
    sql += " ORDER BY created_at DESC, id"
    return [summary(conn, r) for r in conn.execute(sql, args)]


def photo_hash(data: bytes, given: str | None) -> str:
    """The SHA-256 of the file the owner picked: as the browser sent it (checked), or else of the bytes received."""
    if given is None:
        return hashlib.sha256(data).hexdigest()
    given = given.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", given):
        raise ItemError("photo_sha256 must be the file's SHA-256 as 64 hexadecimal characters.")
    return given


def _same_photo(conn, source_sha256: str):
    """The item, archived or not, that already has a photo made from this file."""
    return conn.execute("SELECT items.* FROM photos JOIN items ON items.id = photos.item_id WHERE photos.source_sha256 = ? "
                        "ORDER BY items.created_at LIMIT 1", (source_sha256,)).fetchone()


def _duplicate(conn, row) -> dict:
    return {**detail(conn, row), "duplicate": True}


def create_from_photo(conn, images_dir: Path, data: bytes, client_key: str | None, name: str | None = None,
                      source_sha256: str | None = None, shoe: bool = False, demo: bool = False) -> tuple[dict, bool]:
    """Add an item from one front photo. Returns (item, created).

    `shoe`: added from "A shoe" on Add, so its photos are sorted into views once Claude has said it is a shoe
    (`shoeviews`; in the demo closet, never).

    A repeated `client_key` returns the item made the first time, so an upload
    retried after a dropped connection never creates a duplicate.

    A photo already in the closet is not added again: `source_sha256` is the
    hash of the file the owner picked (the browser sends it, since it shrinks
    the photo before sending); without it, the hash of the bytes received is
    used. The existing item comes back with `duplicate: true`.
    """
    if client_key:
        existing = conn.execute("SELECT * FROM items WHERE client_key = ?", (client_key,)).fetchone()
        if existing is not None:
            return {**detail(conn, existing), "duplicate": False}, False
    source_sha256 = photo_hash(data, source_sha256)
    same = _same_photo(conn, source_sha256)
    if same is not None:
        return _duplicate(conn, same), False
    _refuse_waiting_source(conn, source_sha256)
    item_id, photo_id = uuid.uuid4().hex, uuid.uuid4().hex
    t = db.now()
    try:
        stored = images.store_upload(data, images_dir, item_id, photo_id)
        conn.execute("BEGIN IMMEDIATE")
        # checked again now that the database is locked, in case the same photo arrived meanwhile
        same = _same_photo(conn, source_sha256)
        if same is not None:
            conn.execute("ROLLBACK")
            shutil.rmtree(images_dir / item_id, ignore_errors=True)
            return _duplicate(conn, same), False
        _refuse_waiting_source(conn, source_sha256)
        conn.execute("INSERT INTO items (id, client_key, name, location, created_at, updated_at) VALUES (?, ?, ?, 'closet', ?, ?)",
                     (item_id, client_key or None, (name or "").strip() or None, t, t))
        conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, width, height, bytes, sha256, "
                     "source_sha256, created_at) VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, source_sha256, t))
        jobs.enqueue_cutout(conn, item_id, photo_id)
        if shoe:
            shoeviews.changed(conn, item_id, demo)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        shutil.rmtree(images_dir / item_id, ignore_errors=True)
        raise
    return {**detail(conn, get(conn, item_id)), "duplicate": False}, True


WAITING_SOURCE = ("This photo is already on Add as a photo of several pieces, waiting for them to be checked. "
                  "Add its pieces from there, or forget it first to add it as one item.")


def _refuse_waiting_source(conn, source_sha256: str) -> None:
    """A photo kept as several pieces and not added yet would otherwise give its pieces twice."""
    if conn.execute("SELECT 1 FROM source_photos WHERE source_sha256 = ? AND state != 'added'", (source_sha256,)).fetchone():
        raise ItemError(WAITING_SOURCE, 409)


def update(conn, item_id: str, changes: dict, record: bool = True) -> dict:
    """Change the item's own fields. A change to what describes it is kept in its history unless `record` is
    False (the caller records it, with other changes, as one)."""
    mine = not conn.in_transaction
    if mine:
        conn.execute("BEGIN IMMEDIATE")
    try:
        result = _update(conn, item_id, changes, record)
        if mine:
            conn.execute("COMMIT")
        return result
    except Exception:
        if mine and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


_KEEP = object()


def _shade(changes: dict):
    """The shade asked for, taken out of `changes`: a shade's name, whose colour word and colour are then put into
    `changes` over any sent with it (the shade decides them); None to give it back to Claude; or `_KEEP` when none
    was asked for."""
    if "shade" not in changes:
        return _KEEP
    shade = changes.pop("shade")
    if isinstance(shade, str):
        shade = shade.strip() or None
    if shade in (None, "unknown"):
        return None
    if shade not in SHADES:
        raise ItemError(f"'{shade}' is not one of the shades." if isinstance(shade, str) else "The shade must be a word.")
    changes["color_hex"], changes["color"] = SHADES[shade]
    return shade


def _with_shade(owner: dict, shade, row, changes: dict) -> dict:
    """The owner's details with the shade they chose (`_shade`). Without one, a colour or colour shade they set puts
    aside a shade they chose before, unless it is still that shade's (the latest word wins)."""
    out = dict(owner)
    if shade is None:
        out.pop("shade", None)
    elif shade is not _KEEP:
        out["shade"] = shade
    elif out.get("shade") in SHADES:
        hex_, color = SHADES[out["shade"]]
        if changes.get("color", row["color"]) != color or changes.get("color_hex", row["color_hex"]) != hex_:
            out.pop("shade")
    return out


def _update(conn, item_id: str, changes: dict, record: bool) -> dict:
    row = get(conn, item_id)
    unknown = set(changes) - PATCHABLE
    if unknown:
        raise ItemError(f"These fields cannot be changed here: {', '.join(sorted(unknown))}.")
    changes = dict(changes)
    shade = _shade(changes)
    if "formality" in changes or "formality_also" in changes:
        changes = {**changes, **_formality(row, changes)}
    sets, args = [], []
    source = json.loads(row["source"] or "{}")
    confidence = json.loads(row["confidence"] or "{}")
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        if field in ENUM_FIELDS:
            if field == "location" and value == "laundry":
                raise ItemError("The laundry is not where an item lives. Use “Put in the laundry” on the item instead.")
            if value is not None and value not in vocab.ENUM_FIELDS[field]:
                raise ItemError(f"'{value}' is not a known {field}. Choose one of: {', '.join(vocab.ENUM_FIELDS[field])}.")
            if field in ("category", "color", "pattern", "formality", "season"):
                source[field], confidence[field] = "user", 1.0
        elif field == "formality_also":   # set with the formality (`_formality`): the owner's word, as the formality is
            if value is None:
                source.pop(field, None)
            else:
                source[field] = "user"
        elif field in tagjobs.FILLED and field != "silhouette":
            if value is not None and not isinstance(value, str):
                raise ItemError(f"{field} must be text.")
            source[field] = "user"   # tagging never overwrites what the owner set
        elif field == "status":
            if value not in ("active", "archived"):
                raise ItemError("Status must be active or archived.")
        elif field == "price_cents":
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ItemError("Price must be a whole number of cents, zero or more.")
        elif field == "silhouette":
            if not isinstance(value, dict):
                raise ItemError("Silhouette must be an object.")
            merged = json.loads(row["silhouette"] or "{}")
            for k, v in value.items():
                if k not in vocab.SILHOUETTE:
                    raise ItemError(f"'{k}' is not a silhouette field.")
                if v is None:
                    merged.pop(k, None)
                elif v not in vocab.SILHOUETTE[k]:
                    raise ItemError(f"'{v}' is not a known {k}. Choose one of: {', '.join(vocab.SILHOUETTE[k])}.")
                else:
                    merged[k] = v
            value = json.dumps(merged)
            source["silhouette"], confidence["silhouette"] = "user", 1.0
        elif value is not None and not isinstance(value, str):
            raise ItemError(f"{field} must be text.")
        sets.append(f"{field} = ?")
        args.append(value)
    if sets or shade is not _KEEP:
        owner = kept = details.own(row)
        if "silhouette" in changes:   # a shape the owner sets puts aside their own matching details
            kept = details.drop_for_shape(owner, json.loads(row["silhouette"] or "{}"), json.loads(args[sets.index("silhouette = ?")]))
        if shade is not _KEEP or "color" in changes or "color_hex" in changes:   # the shade they chose, or put aside
            kept = _with_shade(kept, shade, row, dict(zip((s.split(" ")[0] for s in sets), args, strict=True)))
        if "category" in changes:   # and another kind of garment those it does not have (an undo brings them back)
            category = args[sets.index("category = ?")]
            names = details.names_for(category)
            kept = {k: v for k, v in kept.items() if k in names}
            if kept.get("garment") in kinds.KINDS and kinds.category_for(kept["garment"], category) != category:
                kept.pop("garment")   # a kind the item no longer is
        if kept != owner:
            sets.append("own_details = ?")
            args.append(details.dump(kept))
        cloth = surfaceform.own_cloth(row)
        if "pattern" in changes and "surface" in cloth:   # a pattern word set now wins over a cloth said before
            cloth.pop("surface")
            sets.append("own_cloth = ?")
            args.append(json.dumps(cloth, sort_keys=True) if cloth else None)
        if any(f in changes for f in ESSENTIALS):
            sets.append("checked_at = ?")
            args.append(db.now())
        sets += ["source = ?", "confidence = ?", "updated_at = ?"]
        args += [json.dumps(source), json.dumps(confidence), db.now(), item_id]
        conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", args)
        if "pattern" in changes:
            patjobs.mark(conn, item_id)   # measured again (or no longer drawn) before it is redrawn
        if "category" in changes:
            tracejobs.mark(conn, item_id, again=False)   # said to be a shoe: traced from its photo, if it never was
        if illustrations.SHOWN & changes.keys() or kept != owner:
            illustrations.redraw(conn, item_id)
        if record:
            history.record(conn, row, get(conn, item_id), "owner", "field")
    return detail(conn, get(conn, item_id))


def _formality(row, changes: dict) -> dict:
    """The formality and the level it can also be, as they will be kept. A formality sent alone is one level (a
    second level the item had is cleared); a second level sent alone goes with the formality the item has. Only
    levels next to each other (`vocab.formality_span`). The formality's own source protects both from a new answer
    (`tagjobs.who`), so a single level the owner sets leaves no trace of the second."""
    def word(value):
        if isinstance(value, str):
            value = value.strip() or None
        if value is not None and value not in vocab.FORMALITY:
            raise ItemError(f"'{value}' is not a known formality. Choose one of: {', '.join(vocab.FORMALITY)}.")
        return value

    level = word(changes["formality"] if "formality" in changes else row["formality"])
    try:
        level, also = vocab.formality_span(level, word(changes.get("formality_also")))
    except ValueError as e:
        raise ItemError(str(e)) from None
    if "formality_also" in changes or row["formality_also"] is not None:
        return {"formality": level, "formality_also": also}
    return {"formality": level}


def delete(conn, images_dir: Path, item_id: str) -> None:
    row = get(conn, item_id)
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    shutil.rmtree(images_dir / item_id, ignore_errors=True)
    if _drop_unused_source(conn, row["source_photo_id"]):
        shutil.rmtree(images_dir / "sources" / row["source_photo_id"], ignore_errors=True)


def _drop_unused_source(conn, source: str | None) -> bool:
    """No item is cut from this photo of several pieces any more: its row goes (the photo is not kept for nothing).
    True when the caller should remove its folder."""
    if not source or conn.execute("SELECT 1 FROM items WHERE source_photo_id = ? LIMIT 1", (source,)).fetchone():
        return False
    return bool(conn.execute("DELETE FROM source_photos WHERE id = ? AND state = 'added'", (source,)).rowcount)


# ------------------------------------------------------------------ a new main photo ("Retake the photo")

RUNNING_CUTOUT = "The photo is still being cut out; try again in a moment."
ELSEWHERE = "This photo is already in the closet, as another item."


def locked(conn, work) -> None:
    """Run `work` under the database's write lock, all of it or nothing."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        work()
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def store_photo(images_dir: Path, item_id: str, data: bytes):
    """The uploaded photo's files, stored under a new photo id: (photo_id, images.Stored)."""
    photo_id = uuid.uuid4().hex
    return photo_id, images.store_upload(data, images_dir, item_id, photo_id)


def remove_photo_files(images_dir: Path, photo) -> None:
    for key in ("original_path", "thumb_path", "cutout_path", "cutout_thumb_path"):
        if photo[key]:
            (images_dir / photo[key]).unlink(missing_ok=True)


def refuse_elsewhere(conn, item_id: str, source_sha256: str) -> None:
    """A photo already in the closet as another item is not given to this one too."""
    other = conn.execute("SELECT item_id FROM photos WHERE source_sha256 = ? AND item_id != ? LIMIT 1",
                         (source_sha256, item_id)).fetchone()
    if other is not None:
        raise ItemError(ELSEWHERE, 409)


def replace_front(conn, images_dir: Path, item_id: str, data: bytes, source_sha256: str | None, check,
                  then=None, demo: bool = False) -> dict:
    """A new main photo in place of the old one, for a shoe (`shoes.replace_photo`) or anything else
    (`replace_photo`). `check(row, source_sha256)` refuses what the caller does not allow, before the photo is
    stored and again under the lock; `then(row)` runs under the lock once the new photo is in, before its cutout is
    queued. The old main photo goes, rows and files; a queued cutout of it is dropped; refused while its cutout
    runs, and for a photo already in the closet as another item. The trace of the old photo goes (a shoe is traced
    again from the new cutout), and photos sorted into views (or waiting to be) are sorted again with the new one.
    Once the new cutout is ready the item is described again (`jobs._described_since`), not in the demo closet."""
    source_sha256 = photo_hash(data, source_sha256)
    check(get(conn, item_id), source_sha256)
    photo_id, stored = store_photo(images_dir, item_id, data)
    old: list = []

    def work():
        row = get(conn, item_id)
        check(row, source_sha256)
        if conn.execute("SELECT 1 FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'running'",
                        (item_id,)).fetchone():
            raise ItemError(RUNNING_CUTOUT, 409)
        refuse_elsewhere(conn, item_id, source_sha256)
        old.extend(conn.execute("SELECT * FROM photos WHERE item_id = ? AND kind = 'front'", (item_id,)).fetchall())
        conn.execute("DELETE FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'queued'", (item_id,))
        conn.execute("DELETE FROM photos WHERE item_id = ? AND kind = 'front'", (item_id,))
        conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, width, height, bytes, sha256, "
                     "source_sha256, created_at) VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, source_sha256, db.now()))
        tracejobs.forget(conn, item_id)
        if row["views_state"] is not None or row["views_error"] is not None:   # its photos were sorted, or meant to be
            shoeviews.changed(conn, item_id, demo)
        if then is not None:
            then(row)
        jobs.enqueue_cutout(conn, item_id, photo_id)
        illustrations.redraw(conn, item_id)

    try:
        locked(conn, work)
    except Exception:
        for name in (stored.original_path, stored.thumb_path):
            (images_dir / name).unlink(missing_ok=True)
        raise
    for p in old:
        remove_photo_files(images_dir, p)
    return detail(conn, get(conn, item_id))


def replace_photo(conn, images_dir: Path, item_id: str, data: bytes, source_sha256: str | None = None,
                  demo: bool = False) -> dict:
    """A new photo of a piece of clothing (anything but a shoe) in place of its photo: the item page's "Retake the
    photo", offered when the background could not be removed or the pattern could not be measured. The item keeps
    its id, wears, rating, laundry, history and everything the owner set; its background is removed from the new
    photo, Claude describes it again (fields and details the owner set stay theirs, as always) and its pattern is
    measured again from the new cutout once described.

    What was measured from the old photo goes at once, so nothing about the old photo is shown as if it were about
    the new one: the measured pattern and its state (a "could not measure" note included) and Claude's landmarks.
    The pattern waits for the new description, which marks it for measuring (`patjobs.mark`); measuring it before
    would only be thrown away. An item cut from a photo of several pieces is no longer: the new photo is its own,
    so it leaves that photo (which goes once no item is cut from it). The demo closet is never sent to Claude, so
    there it is cut out again and keeps its description."""
    dropped: list[str] = []

    def check(row, sha):
        _refuse_waiting_source(conn, sha)

    def then(row):
        conn.execute("UPDATE items SET pattern_state = NULL, pattern_error = NULL, pattern_fill = NULL, "
                     "landmarks = NULL, source_photo_id = NULL, source_box = NULL WHERE id = ?", (item_id,))
        if _drop_unused_source(conn, row["source_photo_id"]):
            dropped.append(row["source_photo_id"])

    out = replace_front(conn, images_dir, item_id, data, source_sha256, check, then, demo)
    for source in dropped:
        shutil.rmtree(images_dir / "sources" / source, ignore_errors=True)
    return out


def retry_cutout(conn, item_id: str) -> dict:
    row = get(conn, item_id)
    photo = _front(conn, item_id)
    if photo is None:
        raise ItemError("This item has no photo to process.", 409)
    if row["cutout_state"] in ("pending", "processing"):
        return detail(conn, row)
    conn.execute("BEGIN IMMEDIATE")
    if conn.execute("SELECT 1 FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state IN ('queued', 'running')",
                    (item_id,)).fetchone() is None:   # never a second job for the same item
        jobs.enqueue_cutout(conn, item_id, photo["id"])
    conn.execute("COMMIT")
    return detail(conn, get(conn, item_id))


def retag(conn, item_id: str) -> dict:
    """Queue the item to be described again. Fields the owner has set stay as they are."""
    row = get(conn, item_id)
    if _front(conn, item_id) is None:
        raise ItemError("This item has no photo for Claude to look at.", 409)
    if row["cutout_state"] in ("pending", "processing"):
        return detail(conn, row)   # it is described as soon as its cutout is ready
    if row["cutout_state"] != "ready":
        raise ItemError("Claude describes an item once its background has been removed. Try the cutout again first.", 409)
    conn.execute("BEGIN IMMEDIATE")
    tagjobs.enqueue(conn, item_id)
    conn.execute("COMMIT")
    return detail(conn, get(conn, item_id))
