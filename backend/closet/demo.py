"""The demo closet: about 30 sample items, kept apart from the real closet.

It has its own database and images under `demo/` in the data folder, is
never backed up, and can be opened and closed from Settings. Its photos are
open-licence pictures (credits in `demo_data/CREDITS.md`) whose cutouts were
made in advance, so the demo works before the model has been downloaded.
It is never sent to Claude: each item comes with a stored tagging answer made
by `tools/make_demo.py` from what it knows about the item.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta

from PIL import Image

from . import db, images, wears
from .config import Config, bundle_dir

FIELDS = ("name", "category", "color", "color_hex", "pattern", "formality", "season", "brand", "size", "material",
          "location", "rating", "rating_reason", "price_cents", "acquired_on", "notes", "illustration_svg")


def ensure(cfg: Config) -> int:
    """Create and fill the demo closet if it is empty. Returns how many items were added."""
    path = cfg.db_path("demo")
    db.migrate(path, cfg.local_backups_dir)
    conn = db.connect(path)
    try:
        source = bundle_dir() / "demo_data"
        data = json.loads((source / "items.json").read_text(encoding="utf-8"))
        if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]:
            _answers(conn, data)   # a demo closet made before the answers existed gets them now
            return 0
        dest = cfg.images_dir("demo")
        added = 0
        conn.execute("BEGIN")
        for n, it in enumerate(data["items"]):
            # spread created_at so the grid has a stable, sensible order
            created = f"2026-01-{28 - n % 28:02d}T12:{n % 60:02d}:00.000000Z"
            src = {f: "demo" for f in ("category", "color", "pattern", "formality", "season", "silhouette") if it.get(f)}
            conn.execute(
                f"INSERT INTO items (id, {', '.join(FIELDS)}, silhouette, source, confidence, cutout_state, created_at, updated_at) "
                f"VALUES (?, {', '.join('?' for _ in FIELDS)}, ?, ?, ?, ?, ?, ?)",
                [it["id"], *[it.get(f) for f in FIELDS], json.dumps(it.get("silhouette") or {}), json.dumps(src),
                 json.dumps({f: 1.0 for f in src}), "ready" if it.get("photo") else "none", created, created])
            if it.get("photo"):
                pid = it["photo"]["id"]
                folder = dest / it["id"]
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / "images" / it["photo"]["original"], folder / f"{pid}.webp")
                shutil.copyfile(source / "images" / it["photo"]["cutout"], folder / f"{pid}.cut.webp")
                with Image.open(folder / f"{pid}.webp") as im:
                    w, h = im.size
                    images.save_webp(images.thumbnail(im.convert("RGB")), folder / f"{pid}.t.webp", 80)
                with Image.open(folder / f"{pid}.cut.webp") as im:
                    images.save_webp(images.thumbnail(im), folder / f"{pid}.cut.t.webp", 80)
                conn.execute(
                    "INSERT INTO photos (id, item_id, kind, original_path, thumb_path, cutout_path, cutout_thumb_path, width, height, bytes, created_at) "
                    "VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, it["id"], f"{it['id']}/{pid}.webp", f"{it['id']}/{pid}.t.webp", f"{it['id']}/{pid}.cut.webp",
                     f"{it['id']}/{pid}.cut.t.webp", w, h, (folder / f"{pid}.webp").stat().st_size, created))
            _history(conn, it)
            added += 1
        conn.execute("COMMIT")
        _answers(conn, data)
        return added
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _answers(conn, data: dict) -> None:
    """Store each demo item's answer, made in advance, as if Claude had given it (route "demo", no model)."""
    conn.execute("BEGIN")
    for it in data["items"]:
        if it.get("answer"):
            conn.execute("UPDATE items SET tag_state = 'done', tag_error = NULL, tag_answer = ?, tag_schema_version = ?, "
                         "tag_route = 'demo', tag_model = NULL, tagged_at = created_at WHERE id = ? AND tag_answer IS NULL",
                         (json.dumps(it["answer"]), data.get("schema_version"), it["id"]))
    conn.execute("COMMIT")


def _history(conn, it: dict) -> None:
    """Wears and laundry state, given in days before today so the demo history is always recent."""
    h = it.get("history")
    if not h:
        return
    today = wears.today()
    day = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731
    for n in h["worn"]:
        conn.execute("INSERT INTO wears (item_id, worn_on, created_at) VALUES (?, ?, ?)", (it["id"], day(n), f"{day(n)}T20:00:00.000000Z"))
    washed = h.get("washed")
    since = sum(1 for n in h["worn"] if washed is None or n <= washed)
    conn.execute("UPDATE items SET laundry = ?, wears_since_wash = ?, washed_at = ? WHERE id = ?",
                 ("laundry" if h.get("laundry") else "clean", since, f"{day(washed)}T08:00:00.000000Z" if washed is not None else None, it["id"]))
