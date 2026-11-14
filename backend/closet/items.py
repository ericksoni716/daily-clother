"""Reading and changing items."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import zlib
from pathlib import Path

from . import db, details, failures, history, illustrations, images, jobs, palette, patjobs, tagjobs, vocab
from .tagger.taxonomy import SHADES, nearest_shade

TEXT_FIELDS = ("name", "brand", "size", "material", "fit_notes", "acquired_on", "notes", "rating_reason", "color_hex")
ENUM_FIELDS = tuple(vocab.ENUM_FIELDS)
PATCHABLE = set(TEXT_FIELDS) | set(ENUM_FIELDS) | {"silhouette", "price_cents", "status"}
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
    return {
        "id": row["id"], "name": row["name"], "category": row["category"], "color": row["color"],
        "color_hex": row["color_hex"], "pattern": row["pattern"], "location": row["location"], "rating": row["rating"],
        "status": row["status"], "cutout_state": row["cutout_state"], "thumb_url": _media(thumb),
        "has_illustration": row["illustration_svg"] is not None, "has_photo": photo is not None,
        "illustration_url": (f"/api/items/{row['id']}/illustration.svg?v={zlib.crc32(row['illustration_svg'].encode()):08x}"
                             if row["illustration_svg"] is not None else None),
        "last_worn": worn[0], "wear_count": worn[1], "wears_since_wash": row["wears_since_wash"], "laundry": row["laundry"],
        "tag_state": row["tag_state"], "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def detail(conn, row) -> dict:
    row = illustrations.current(conn, row)
    out = summary(conn, row)
    for f in ("formality", "season", "brand", "size", "material", "fit_notes", "condition", "price_cents",
              "acquired_on", "notes", "rating_reason", "illustration_svg", "cutout_error"):
        out[f] = row[f]
    for f in ("silhouette", "confidence", "source"):
        out[f] = json.loads(row[f] or "{}")
    for f in ("tag_error", "tag_route", "tag_model", "tag_schema_version", "tagged_at"):
        out[f] = row[f]
    # the pattern measured from the photo: null (nothing to measure), waiting, working, done or failed
    out["pattern_state"], out["pattern_error"] = row["pattern_state"], row["pattern_error"]
    # its colours as measured from the pattern, largest first, each {color, hex, share}; empty when not measured
    out["pattern_colors"] = palette.shown(row)
    # why the cutout or the description failed, with the stored reason cleaned of keys and outside paths
    out["failure"] = failures.of(conn, row)
    # what the tagger saw, from its stored answer: the details, and what it saw that no field (or drawing) covers yet
    said = dict((json.loads(row["tag_answer"]) if row["tag_answer"] else {}).get("details") or {})
    out["seen_not_drawn"] = illustrations.not_drawn(row, said.pop("other_features", None) or [])
    out["details"] = said or None
    out["own_details"] = details.own(row)   # the details the owner has set, laid over Claude's when drawn
    out["shade"] = shade_of(row, {**said, **out["own_details"]})
    out["drawing_notes"] = illustrations.notes(row)
    out["photos"] = [{
        "id": p["id"], "kind": p["kind"], "url": _media(p["original_path"]), "thumb_url": _media(p["thumb_path"]),
        "cutout_url": _media(p["cutout_path"]), "cutout_thumb_url": _media(p["cutout_thumb_path"]),
        "width": p["width"], "height": p["height"],
    } for p in conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at", (row["id"],))]
    out["recent_wears"] = [r[0] for r in conn.execute(
        "SELECT worn_on FROM wears WHERE item_id = ? ORDER BY worn_on DESC LIMIT ?", (row["id"], RECENT_WEARS))]
    # the photo of several pieces this item was cut from, and its box in it (fractions); null for a photo of its own
    out["source_photo"] = None
    if row["source_photo_id"]:
        src = conn.execute("SELECT id, original_path FROM source_photos WHERE id = ?", (row["source_photo_id"],)).fetchone()
        if src is not None:
            out["source_photo"] = {"id": src["id"], "photo_url": _media(src["original_path"]),
                             "box": json.loads(row["source_box"]) if row["source_box"] else None}
    return out


def shade_of(row, said: dict) -> str | None:
    """The owner's name for the item's shade (docs/menswear-taxonomy.json, colors.shades): the one the owner or the
    tagger named when it is a shade of the item's colour, else the nearest to its measured colour."""
    color = row["color"]
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
        sql += (" AND (lower(coalesce(name,'')) LIKE ? OR lower(coalesce(brand,'')) LIKE ? OR lower(coalesce(category,'')) LIKE ?"
                " OR lower(coalesce(color,'')) LIKE ? OR lower(coalesce(notes,'')) LIKE ?)")
        args += [like] * 5
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
                      source_sha256: str | None = None) -> tuple[dict, bool]:
    """Add an item from one front photo. Returns (item, created).

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
    stored = images.store_upload(data, images_dir, item_id, photo_id)
    t = db.now()
    try:
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
    row = get(conn, item_id)
    unknown = set(changes) - PATCHABLE
    if unknown:
        raise ItemError(f"These fields cannot be changed here: {', '.join(sorted(unknown))}.")
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
    if sets:
        owner = kept = details.own(row)
        if "silhouette" in changes:   # a shape the owner sets puts aside their own matching details
            kept = details.drop_for_shape(owner, json.loads(row["silhouette"] or "{}"), json.loads(args[sets.index("silhouette = ?")]))
        if "category" in changes:   # and another kind of garment those it does not have (an undo brings them back)
            names = details.names_for(args[sets.index("category = ?")])
            kept = {k: v for k, v in kept.items() if k in names}
        if kept != owner:
            sets.append("own_details = ?")
            args.append(details.dump(kept))
        sets += ["source = ?", "confidence = ?", "updated_at = ?"]
        args += [json.dumps(source), json.dumps(confidence), db.now(), item_id]
        mine = not conn.in_transaction
        if mine:
            conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", args)
            if "pattern" in changes:
                patjobs.mark(conn, item_id)   # measured again (or no longer drawn) before it is redrawn
            if illustrations.SHOWN & changes.keys():
                illustrations.redraw(conn, item_id)
            if record:
                history.record(conn, row, get(conn, item_id), "owner", "field")
            if mine:
                conn.execute("COMMIT")
        except Exception:
            if mine and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return detail(conn, get(conn, item_id))


def delete(conn, images_dir: Path, item_id: str) -> None:
    row = get(conn, item_id)
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    shutil.rmtree(images_dir / item_id, ignore_errors=True)
    source = row["source_photo_id"]
    if source and conn.execute("SELECT 1 FROM items WHERE source_photo_id = ? LIMIT 1", (source,)).fetchone() is None:
        # the last item cut from a photo of several pieces: the photo is not kept for nothing
        if conn.execute("DELETE FROM source_photos WHERE id = ? AND state = 'added'", (source,)).rowcount:
            shutil.rmtree(images_dir / "sources" / source, ignore_errors=True)


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
