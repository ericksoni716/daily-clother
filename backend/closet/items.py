"""Reading and changing items."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from . import db, images, jobs, vocab

TEXT_FIELDS = ("name", "brand", "size", "material", "fit_notes", "acquired_on", "notes", "rating_reason", "color_hex")
ENUM_FIELDS = tuple(vocab.ENUM_FIELDS)
PATCHABLE = set(TEXT_FIELDS) | set(ENUM_FIELDS) | {"silhouette", "price_cents", "status"}


class ItemError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message, self.status = message, status


def _media(rel: str | None) -> str | None:
    return f"/media/{rel}" if rel else None


def _front(conn, item_id: str):
    return conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at LIMIT 1", (item_id,)).fetchone()


def summary(conn, row) -> dict:
    photo = _front(conn, row["id"])
    thumb = None
    if photo is not None:
        thumb = photo["cutout_thumb_path"] or photo["thumb_path"]
    return {
        "id": row["id"], "name": row["name"], "category": row["category"], "color": row["color"],
        "color_hex": row["color_hex"], "pattern": row["pattern"], "location": row["location"], "rating": row["rating"],
        "status": row["status"], "cutout_state": row["cutout_state"], "thumb_url": _media(thumb),
        "has_illustration": row["illustration_svg"] is not None, "has_photo": photo is not None,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def detail(conn, row) -> dict:
    out = summary(conn, row)
    for f in ("formality", "season", "brand", "size", "material", "fit_notes", "condition", "price_cents",
              "acquired_on", "notes", "rating_reason", "illustration_svg", "cutout_error"):
        out[f] = row[f]
    for f in ("silhouette", "confidence", "source"):
        out[f] = json.loads(row[f] or "{}")
    out["photos"] = [{
        "id": p["id"], "kind": p["kind"], "url": _media(p["original_path"]), "thumb_url": _media(p["thumb_path"]),
        "cutout_url": _media(p["cutout_path"]), "cutout_thumb_url": _media(p["cutout_thumb_path"]),
        "width": p["width"], "height": p["height"],
    } for p in conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at", (row["id"],))]
    return out


def get(conn, item_id: str):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ItemError("That item does not exist.", 404)
    return row


def list_items(conn, status: str = "active", category: str | None = None, q: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM items WHERE status = ?", [status]
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


def create_from_photo(conn, images_dir: Path, data: bytes, client_key: str | None, name: str | None = None) -> tuple[dict, bool]:
    """Add an item from one front photo. Returns (item, created).

    A repeated `client_key` returns the item made the first time, so an upload
    retried after a dropped connection never creates a duplicate.
    """
    if client_key:
        existing = conn.execute("SELECT * FROM items WHERE client_key = ?", (client_key,)).fetchone()
        if existing is not None:
            return detail(conn, existing), False
    item_id, photo_id = uuid.uuid4().hex, uuid.uuid4().hex
    stored = images.store_upload(data, images_dir, item_id, photo_id)
    t = db.now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO items (id, client_key, name, location, created_at, updated_at) VALUES (?, ?, ?, 'closet', ?, ?)",
                     (item_id, client_key or None, (name or "").strip() or None, t, t))
        conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, width, height, bytes, sha256, created_at) "
                     "VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, t))
        jobs.enqueue_cutout(conn, item_id, photo_id)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        shutil.rmtree(images_dir / item_id, ignore_errors=True)
        raise
    return detail(conn, get(conn, item_id)), True


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
            if value is not None and value not in vocab.ENUM_FIELDS[field]:
                raise ItemError(f"'{value}' is not a known {field}. Choose one of: {', '.join(vocab.ENUM_FIELDS[field])}.")
            if field in ("category", "color", "pattern", "formality", "season"):
                source[field], confidence[field] = "user", 1.0
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
