"""Reading and changing items."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import zlib
from pathlib import Path

from . import db, illustrations, images, jobs, tagjobs, vocab

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
    # what the tagger saw, from its stored answer: the details, and what it saw that no field (or drawing) covers yet
    details = dict((json.loads(row["tag_answer"]) if row["tag_answer"] else {}).get("details") or {})
    out["seen_not_drawn"] = details.pop("other_features", None) or []
    out["details"] = details or None
    out["drawing_notes"] = illustrations.notes(row)
    out["photos"] = [{
        "id": p["id"], "kind": p["kind"], "url": _media(p["original_path"]), "thumb_url": _media(p["thumb_path"]),
        "cutout_url": _media(p["cutout_path"]), "cutout_thumb_url": _media(p["cutout_thumb_path"]),
        "width": p["width"], "height": p["height"],
    } for p in conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at", (row["id"],))]
    out["recent_wears"] = [r[0] for r in conn.execute(
        "SELECT worn_on FROM wears WHERE item_id = ? ORDER BY worn_on DESC LIMIT ?", (row["id"], RECENT_WEARS))]
    return out


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
    if source_sha256 is not None:
        source_sha256 = source_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            raise ItemError("photo_sha256 must be the file's SHA-256 as 64 hexadecimal characters.")
    else:
        source_sha256 = hashlib.sha256(data).hexdigest()
    same = _same_photo(conn, source_sha256)
    if same is not None:
        return _duplicate(conn, same), False
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


def update(conn, item_id: str, changes: dict) -> dict:
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
        sets += ["source = ?", "confidence = ?", "updated_at = ?"]
        args += [json.dumps(source), json.dumps(confidence), db.now(), item_id]
        conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", args)
        if illustrations.SHOWN & changes.keys():
            illustrations.redraw(conn, item_id)
    return detail(conn, get(conn, item_id))


def delete(conn, images_dir: Path, item_id: str) -> None:
    get(conn, item_id)
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    shutil.rmtree(images_dir / item_id, ignore_errors=True)


def retry_cutout(conn, item_id: str) -> dict:
    row = get(conn, item_id)
    photo = _front(conn, item_id)
    if photo is None:
        raise ItemError("This item has no photo to process.", 409)
    if row["cutout_state"] in ("pending", "processing"):
        return detail(conn, row)
    conn.execute("BEGIN IMMEDIATE")
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
