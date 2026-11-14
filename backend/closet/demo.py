"""The demo closet: about 40 sample items, kept apart from the real closet.

It has its own database and images under `demo/` in the data folder, is
never backed up, and can be opened and closed from Settings. Its photos are
open-licence pictures (credits in `demo_data/CREDITS.md`) whose cutouts were
made in advance, so the demo works before the model has been downloaded.
It is never sent to Claude: each item comes with a stored tagging answer made
by `tools/make_demo.py` from what it knows about the item. Its drawings were
made in advance by the same tool (with fills taken from the photos, or from
made-up pattern tiles for the items drawn from their tags) and are kept as they
are while the drawing code's version is the one they were made with. Outfits
worn in the last three weeks, most of them rated, two wishes with stand-in
finds from made-up shops (one has dropped in price) and a saved trip planned
for weather given in advance come with it too: nothing is looked up.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta

from PIL import Image

from . import db, images, savedtrips, wears, wouldwork
from .config import Config, bundle_dir

FIELDS = ("name", "category", "color", "color_hex", "pattern", "formality", "season", "brand", "size", "material",
          "location", "rating", "rating_reason", "price_cents", "acquired_on", "notes", "illustration_svg")
WORN_OUTFITS_MIGRATION = 10  # the migration that added worn outfits


def ensure(cfg: Config) -> int:
    """Create and fill the demo closet if it is empty. Returns how many items were added."""
    path = cfg.db_path("demo")
    applied = db.migrate(path, cfg.local_backups_dir)["applied"]
    conn = db.connect(path)
    try:
        source = bundle_dir() / "demo_data"
        data = json.loads((source / "items.json").read_text(encoding="utf-8"))
        if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]:
            _answers(conn, data)   # a demo closet made before the answers existed gets them now
            _prices(conn, data)    # and one made before the demo had prices gets those
            if WORN_OUTFITS_MIGRATION in applied:
                _outfits(conn, data)   # and one made before worn outfits were remembered gets those, once
            return _grow(cfg, conn, data)   # and one made before the demo had about 40 items gets the rest, once
        added = _add_items(cfg, conn, data, data["items"])
        _answers(conn, data)
        _outfits(conn, data)
        _wishes(conn, data)
        _trip(conn, data)
        return added
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _add_items(cfg: Config, conn, data: dict, chosen: list[dict]) -> int:
    """Add the chosen items of items.json, with their photos, kept patterns and histories."""
    source = bundle_dir() / "demo_data"
    dest = cfg.images_dir("demo")
    conn.execute("BEGIN IMMEDIATE")
    first = [it for it in data["items"] if not it.get("wave")]
    second = [it for it in data["items"] if it.get("wave")]
    for it in data["items"]:
        if it not in chosen:
            continue
        # spread created_at so the grid has a stable, sensible order; the first wave keeps the order it always had,
        # the second wave comes after it in the grid
        if it.get("wave"):
            n = second.index(it)
            created = f"2025-12-{28 - n % 28:02d}T12:{n % 60:02d}:00.000000Z"
        else:
            n = first.index(it)
            created = f"2026-01-{28 - n % 28:02d}T12:{n % 60:02d}:00.000000Z"
        src = {f: "demo" for f in ("category", "color", "pattern", "formality", "season", "silhouette") if it.get(f)}
        kept = it.get("pattern_fill")
        conn.execute(
            f"INSERT INTO items (id, {', '.join(FIELDS)}, silhouette, source, confidence, cutout_state, illustration_notes, "
            f"pattern_fill, pattern_state, created_at, updated_at) VALUES (?, {', '.join('?' for _ in FIELDS)}, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [it["id"], *[it.get(f) for f in FIELDS], json.dumps(it.get("silhouette") or {}), json.dumps(src),
             json.dumps({f: 1.0 for f in src}), "ready" if it.get("photo") else "none",
             json.dumps(it["illustration_notes"]) if it.get("illustration_notes") else None,
             json.dumps(kept) if kept else None, "done" if kept else None, created, created])
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
        # the drawing was made in advance with the drawing code of this version; kept until it is raised
        if it.get("illustration_svg"):
            conn.execute("UPDATE items SET illustration_version = ? WHERE id = ?", (data.get("drawing_version"), it["id"]))
    conn.execute("COMMIT")
    return len(chosen)


def _grow(cfg: Config, conn, data: dict) -> int:
    """Give a demo closet made before it had about 40 items (and wishes and a trip) what is new, once: the items
    of the second wave (`"wave": 2` in items.json), the outfits that can be made of what it has, the wishes and the
    trip; only when none of those is in it, so what the owner removed since is not brought back."""
    new = [it for it in data["items"] if it.get("wave") == 2]
    wish_ids = [w["id"] for w in data.get("wishes", [])]
    trip_id = (data.get("trip") or {}).get("id")
    have = {r[0] for r in conn.execute("SELECT id FROM items")}
    if (not new or {it["id"] for it in new} & have
            or (wish_ids and conn.execute(f"SELECT 1 FROM wishes WHERE id IN ({', '.join('?' for _ in wish_ids)})",
                                          wish_ids).fetchone())
            or (trip_id and conn.execute("SELECT 1 FROM trips WHERE id = ?", (trip_id,)).fetchone())):
        return 0
    added = _add_items(cfg, conn, data, new)
    _answers(conn, data)
    _outfits(conn, data, more=True)
    _wishes(conn, data)
    _trip(conn, data)
    return added


def _answers(conn, data: dict) -> None:
    """Store each demo item's answer, made in advance, as if Claude had given it (route "demo", no model).

    How sure each answer is goes onto the fields the demo still fills (not those the owner has set), so the
    review queue shows the few the answers are unsure of; an older demo closet gets them too.
    """
    conn.execute("BEGIN IMMEDIATE")
    for it in data["items"]:
        answer = it.get("answer")
        if not answer:
            continue
        conn.execute("UPDATE items SET tag_state = 'done', tag_error = NULL, tag_answer = ?, tag_schema_version = ?, "
                     "tag_route = 'demo', tag_model = NULL, tagged_at = created_at WHERE id = ? AND tag_answer IS NULL",
                     (json.dumps(answer), data.get("schema_version"), it["id"]))
        row = conn.execute("SELECT source, confidence FROM items WHERE id = ?", (it["id"],)).fetchone()
        if row is None:
            continue
        source, confidence = json.loads(row["source"] or "{}"), json.loads(row["confidence"] or "{}")
        sure = {f: answer[f"{f}_confidence"] for f, by in source.items() if by == "demo" and f"{f}_confidence" in answer}
        if any(confidence.get(f) != v for f, v in sure.items()):
            conn.execute("UPDATE items SET confidence = ? WHERE id = ?", (json.dumps({**confidence, **sure}), it["id"]))
    conn.execute("COMMIT")


def _prices(conn, data: dict) -> None:
    """Give a demo closet made before its items had prices the prices, once: only when no item has one."""
    if conn.execute("SELECT 1 FROM items WHERE price_cents IS NOT NULL LIMIT 1").fetchone():
        return
    conn.execute("BEGIN IMMEDIATE")
    for it in data["items"]:
        if it.get("price_cents") is not None:
            conn.execute("UPDATE items SET price_cents = ? WHERE id = ?", (it["price_cents"], it["id"]))
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


def _outfits(conn, data: dict, more: bool = False) -> None:
    """The worn outfits, given in days before today like the wears (not if the demo already has some, unless
    `more`: then those it lacks).

    Their pieces' wears are in each item's history; in a demo closet opened before these existed, the wears
    of an outfit are added if missing (and counted since the wash if they are newer than it).
    """
    have = {r[0] for r in conn.execute("SELECT id FROM worn_outfits")}
    if have and not more:
        return
    known = {r[0] for r in conn.execute("SELECT id FROM items")}
    today = wears.today()
    conn.execute("BEGIN IMMEDIATE")
    for o in data.get("outfits", []):
        ids = [v for k, v in o["pieces"].items() if k != "accessories" and v] + list(o["pieces"].get("accessories") or [])
        if not set(ids) <= known or o["id"] in have:
            continue
        day = (today - timedelta(days=o["days_ago"])).isoformat()
        t = f"{day}T20:00:00.000000Z"
        c = o.get("context") or {}
        conn.execute(
            "INSERT INTO worn_outfits (id, worn_on, recorded_by, low_c, high_c, rain, occasion, mood, score, reasons, warnings, "
            "rating, rating_reasons, rating_note, rated_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (o["id"], day, o.get("recorded_by", "today"), c.get("low_c"), c.get("high_c"),
             None if c.get("rain") is None else int(c["rain"]), c.get("occasion"), c.get("mood"), o.get("score"),
             json.dumps(o.get("reasons") or []), json.dumps(o.get("warnings") or []), o.get("rating"),
             json.dumps(o.get("rating_reasons") or []), o.get("rating_note"), t if o.get("rating") else None, t, t))
        places = [(k, v, 0) for k, v in o["pieces"].items() if k != "accessories" and v]
        places += [("accessory", a, n) for n, a in enumerate(o["pieces"].get("accessories") or [])]
        for place, item_id, position in places:
            conn.execute("INSERT INTO worn_outfit_pieces (outfit_id, item_id, place, position, added_wear) VALUES (?, ?, ?, ?, 1)",
                         (o["id"], item_id, place, position))
            if conn.execute("INSERT OR IGNORE INTO wears (item_id, worn_on, created_at) VALUES (?, ?, ?)", (item_id, day, t)).rowcount:
                conn.execute("UPDATE items SET wears_since_wash = wears_since_wash + 1 WHERE id = ? AND (washed_at IS NULL OR washed_at < ?)",
                             (item_id, t))
    conn.execute("COMMIT")


def _ago(n: int) -> str:
    """UTC time n days before today, in the evening, as the database keeps times."""
    return f"{(wears.today() - timedelta(days=n)).isoformat()}T18:00:00.000000Z"


def _wishes(conn, data: dict) -> None:
    """The wishes added by hand, each with what a search of (made-up) shops found and those finds' prices over
    the last days. Each find's "Would this work?" verdict was worked out against the demo closet by
    `tools/make_demo.py` (it takes several seconds), as a search would have; it shows as checked when found."""
    finds = [(w, f, wouldwork.parse_piece({**f["piece"], "name": f["name"][:wouldwork.NAME_MAX]}))
             for w in data.get("wishes", []) for f in w["finds"]]
    conn.execute("BEGIN IMMEDIATE")
    for w in data.get("wishes", []):
        found = _ago(max(f["prices"][0]["days_ago"] for f in w["finds"]))
        checked = _ago(min(f["prices"][-1]["days_ago"] for f in w["finds"]))
        conn.execute("INSERT INTO wishes (id, gap_id, name, look_for, note, price_max, price_currency, found_at, "
                     "prices_checked_at, created_at, updated_at) VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                     (w["id"], w["name"], w["note"], w["price_max"], w["currency"], found, checked,
                      _ago(w["days_ago"]), checked))
    for w, f, piece in finds:
        first, last = f["prices"][0], f["prices"][-1]
        verdict = {**f["verdict"], "checked_at": _ago(first["days_ago"])} if f.get("verdict") else None
        conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, image_url, price, currency, available, piece, "
                     "verdict, found_at, updated_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 1, ?, ?, ?, ?)",
                     (f["id"], w["id"], f["name"], f["shop"], f["url"], last["price"], w["currency"], json.dumps(piece),
                      json.dumps(verdict) if verdict else None, _ago(first["days_ago"]), _ago(last["days_ago"])))
        for h in f["prices"]:
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, 1)",
                         (f["id"], _ago(h["days_ago"]), h["price"], w["currency"]))
    conn.execute("COMMIT")


class _Settings:
    """The demo's trip is planned with the default "Before it needs washing" rules, not the owner's."""

    def get(self, key: str):
        return None


def _trip(conn, data: dict) -> None:
    """The saved trip, starting some days from today, planned for the weather given with it, its basics ticked."""
    t = data.get("trip")
    if not t:
        return
    first = wears.today() + timedelta(days=t["starts_in"])
    days = [(first + timedelta(days=n)).isoformat() for n in range(len(t["weather"]))]
    body = {"place": t["place"], "first_day": days[0], "last_day": days[-1], "occasion": t["occasion"],
            "day_occasions": {days[int(n)]: o for n, o in t["day_occasions"].items()},
            "weather": [{"date": d, **w} for d, w in zip(days, t["weather"], strict=True)]}
    if t.get("laundry"):
        body["laundry"] = t["laundry"]
    trip = savedtrips.work_out(conn, _Settings(), body)
    packed = [line for line in trip["lines"] if line.startswith(t["tick"])] if t.get("tick") else []
    now = db.now()
    conn.execute(
        "INSERT INTO trips (id, place, first_day, last_day, occasion, day_occasions, laundry, leave_out, pinned, weather,"
        " weather_message, plan, packed, planned_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (t["id"], json.dumps(trip["place"]), trip["first_day"], trip["last_day"], trip["occasion"],
         json.dumps(trip["day_occasions"]), json.dumps(trip["laundry"]) if trip["laundry"] else None,
         json.dumps(trip["leave_out"]), json.dumps(trip["pin"]), json.dumps(trip["weather"]), trip["weather_message"],
         json.dumps(trip["plan"]), json.dumps(packed), now, now, now))
