"""The owner's style profile: how they like to dress, in their own words (Settings, "Your style").

Claude reads it every time it chooses the outfits, and it wins over the general menswear guide (`styling.brief`).
It is kept in the closet's own database, so it is in backups and each closet (the owner's, the demo) has its own.

The profile is a list of lines (`style_lines`), each with where it came from (`SOURCES`: one of the starting lines,
written by the owner, kept from a conversation with Claude, or the owner's answer to a question) and when. The text
the stylist reads is built from the lines in order, and every change to them adds a version of that text to
`style_profile`: the newest version is the profile in force and the older ones are its history, as before the lines
existed. With no lines the starting profile (`styling.DEFAULT_PROFILE`) is in force, shown as its lines but not kept
as rows: the starting lines can be improved in an update, and an owner who never wrote their own gets the new ones.
The first change made to it keeps the starting lines that stay as rows of their own, less the line that says nothing
else is written yet (as a line kept from the conversation always did). A removed line can be put back
(`restore_line`). Nothing here asks Claude.
"""
from __future__ import annotations

from . import db, styling

MAX_TEXT = 4000           # the longest profile the owner can save (characters)
MAX_LINE = 500            # the longest line written on its own (characters)
SOURCES = ("owner", "claude")                          # who wrote a version of the text
LINE_SOURCES = ("start", "owner", "talk", "question")  # where a line came from
BULLET = "- "


def _newest(conn):
    return conn.execute("SELECT text, created_at FROM style_profile ORDER BY id DESC LIMIT 1").fetchone()


def _starting() -> list[str]:
    return [ln for ln in styling.DEFAULT_PROFILE.splitlines() if ln.strip()]


def _kept_starting() -> list[str]:
    """The starting lines that stay once the owner has a line of their own (the one that says nothing else is written
    yet goes)."""
    return [ln for ln in styling.DEFAULT_KEPT.splitlines() if ln.strip()]


def _rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, position, gap, text, source, created_at FROM style_lines "
                                          "WHERE removed_at IS NULL ORDER BY position, id")]


def plain(text: str) -> str:
    """A line as the owner reads it: without the "- " a list line starts with, and without space at either end."""
    text = text.strip()
    return text[len(BULLET):].strip() if text.startswith(BULLET.strip()) and text[1:2] in (" ", "") else text


def _in_default(conn) -> bool:
    return not _rows(conn) and not (text_for_stylist(conn) or "")


def lines(conn) -> list[dict]:
    """The lines in force, in order: [{id, text, source, created_at}]. While the starting profile is in force they
    are its lines, with ids -1, -2, ... (not rows yet: changing or removing one keeps them first) and no date."""
    rows = _rows(conn)
    if not rows and _in_default(conn):
        return [{"id": -1 - i, "text": ln, "source": "start", "created_at": None} for i, ln in enumerate(_starting())]
    return [{"id": r["id"], "text": r["text"], "source": r["source"], "created_at": r["created_at"]} for r in rows]


def current(conn) -> dict:
    """The profile in force: its text (the starting one when the owner has written none), whether that is the
    starting one, when it was last saved (None: never), the starting text, the longest text allowed, and its
    lines (`lines`)."""
    row = _newest(conn)
    own = row["text"] if row is not None else ""
    return {"text": own or styling.DEFAULT_PROFILE, "is_default": not own,
            "updated_at": row["created_at"] if row is not None else None,
            "default_text": styling.DEFAULT_PROFILE, "max_length": MAX_TEXT, "lines": lines(conn)}


def tidy(text: object) -> str:
    """The text as kept: without space at either end, with every line break as "\\n" and the owner's breaks kept.
    The starting text itself is kept as an empty one, so the starting profile stays in force."""
    if not isinstance(text, str):
        raise ValueError("Your style must be written as text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"Your style can be at most {MAX_TEXT:,} characters long; this is {len(text):,}.")
    return "" if text == styling.DEFAULT_PROFILE.strip() else text


def tidy_line(text: object) -> str:
    """One line as written on its own (Settings, "Add a line", or a line changed): one line, without space at either
    end."""
    if not isinstance(text, str):
        raise ValueError("A line of your style must be written as text.")
    text = " ".join(text.split())
    if not text:
        raise ValueError("Write something first.")
    if len(text) > MAX_LINE:
        raise ValueError(f"A line can be at most {MAX_LINE:,} characters long; this is {len(text):,}.")
    return text


def _split(text: str) -> list[tuple[int, str]]:
    """A text as (empty lines before it, line) for each line that is not empty."""
    out, gap = [], 0
    for ln in text.split("\n"):
        if ln.strip():
            out.append((gap, ln))
            gap = 0
        else:
            gap += 1
    return out


def _built(rows: list[dict]) -> str:
    return "\n".join("\n" * r["gap"] + r["text"] for r in rows)


def _transaction(conn, work):
    """Runs `work()` in a transaction of its own, or inside the caller's (the caller then commits, as
    `items.update`)."""
    mine = not conn.in_transaction
    if mine:
        conn.execute("BEGIN IMMEDIATE")
    try:
        got = work()
        if mine:
            conn.execute("COMMIT")
        return got
    except Exception:
        if mine and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _materialise(conn, every: bool = False) -> list[int]:
    """While the starting profile is in force, keep its lines as rows, so a first change can be made to them, and
    give their ids (called inside a transaction). `every`: all of them, for a change to one of them; else those that
    stay once the owner has a line of their own."""
    if not _in_default(conn):
        return []
    now, ids = db.now(), []
    for i, ln in enumerate(_starting() if every else _kept_starting()):
        ids.append(conn.execute("INSERT INTO style_lines (position, gap, text, source, created_at) "
                                "VALUES (?, 0, ?, 'start', ?)", (i, ln, now)).lastrowid)
    return ids


def _write(conn, source: str) -> None:
    """Keep a new version of the text built from the lines, when it differs from the one in force (called inside a
    transaction). Refused, with a sentence, when the text would be too long."""
    text = _built(_rows(conn))
    if len(text) > MAX_TEXT:
        raise ValueError(f"Your style can be at most {MAX_TEXT:,} characters long; this is {len(text):,}.")
    text = "" if text == styling.DEFAULT_PROFILE.strip() else text
    row = _newest(conn)
    if text != (row["text"] if row is not None else ""):
        conn.execute("INSERT INTO style_profile (text, source, created_at) VALUES (?, ?, ?)", (text, source, db.now()))


def _next_position(conn) -> int:
    return int(conn.execute("SELECT coalesce(max(position), -1) + 1 FROM style_lines").fetchone()[0])


def save(conn, text: object, source: str = "owner") -> dict:
    """Keep the whole text as the profile (Settings, "Edit the text") and give back the one in force. Each line that
    was there before keeps where it came from; a new or changed line is the owner's (or Claude's, `source`), from now.
    An empty text goes back to the starting profile; a text the same as the one in force adds nothing."""
    if source not in SOURCES:
        raise ValueError("A style profile is written by the owner or by Claude.")
    text = tidy(text)

    def work():
        row = _newest(conn)
        if text == (row["text"] if row is not None else ""):
            return
        old = _rows(conn) or [{"id": None, "text": ln, "source": "start", "created_at": None} for ln in _starting()]
        now, kept = db.now(), set()
        conn.execute("UPDATE style_lines SET removed_at = ? WHERE removed_at IS NULL", (now,))
        for position, (gap, ln) in enumerate(_split(text)):
            same = next((i for i, r in enumerate(old) if i not in kept and r["text"] == ln), None)
            if same is not None and old[same]["id"] is not None:
                kept.add(same)
                conn.execute("UPDATE style_lines SET removed_at = NULL, position = ?, gap = ? WHERE id = ?",
                             (position, gap, old[same]["id"]))
                continue
            if same is not None:   # one of the starting lines, kept as it was
                kept.add(same)
            conn.execute("INSERT INTO style_lines (position, gap, text, source, created_at) VALUES (?, ?, ?, ?, ?)",
                         (position, gap, ln, "start" if same is not None else "talk" if source == "claude" else "owner",
                          now))
        # the text is kept as written (it is the lines put back together, and the starting text is kept as empty)
        conn.execute("INSERT INTO style_profile (text, source, created_at) VALUES (?, ?, ?)", (text, source, now))

    _transaction(conn, work)
    return current(conn)


def has_line(conn, text: str) -> bool:
    """Whether a line saying just this is in the profile in force (not merely inside a longer one)."""
    want = plain(text)
    return any(plain(ln["text"]) == want for ln in lines(conn))


def add_line(conn, text: object, source: str = "owner") -> dict:
    """Add a line at the end of the profile, as a list line ("- ..."), and give it back: {id, text, source,
    created_at}. `source`: owner (Settings, "Add a line"), talk (kept from a conversation) or question (an answer).
    Raises ValueError with a sentence when it cannot be kept."""
    if source not in LINE_SOURCES or source == "start":
        raise ValueError("A line is written by the owner, kept from a conversation or answered to a question.")
    text = tidy_line(text)

    def work():
        _materialise(conn)
        cur = conn.execute("INSERT INTO style_lines (position, gap, text, source, created_at) VALUES (?, 0, ?, ?, ?)",
                           (_next_position(conn), BULLET + plain(text), source, db.now()))
        _write(conn, "claude" if source == "talk" else "owner")
        return cur.lastrowid

    line_id = _transaction(conn, work)
    return _line(conn, line_id)


def _line(conn, line_id: int) -> dict:
    r = conn.execute("SELECT id, text, source, created_at FROM style_lines WHERE id = ?", (line_id,)).fetchone()
    return dict(r)


def _find(conn, line_id: object, removed: bool = False):
    """The row of a line (inside a transaction). A starting line while the starting profile is in force (-1, -2, ...)
    is kept as a row first, with the other starting lines."""
    if isinstance(line_id, bool) or not isinstance(line_id, int):
        raise LookupError("That line is no longer in your style.")
    if line_id < 0 and not removed:
        ids = _materialise(conn, every=True)
        if not 0 <= -1 - line_id < len(ids):
            raise LookupError("That line is no longer in your style.")
        line_id = ids[-1 - line_id]
    r = conn.execute(f"SELECT * FROM style_lines WHERE id = ? AND removed_at IS {'NOT ' if removed else ''}NULL",
                     (line_id,)).fetchone()
    if r is None:
        raise LookupError("That line is no longer in your style." if not removed else "That line can't be put back.")
    return r


def edit_line(conn, line_id: int, text: object) -> dict:
    """Change one line; it is the owner's from now, and keeps its place and its "- " when it had one. Gives back
    the profile. Raises LookupError for a line not in force, ValueError with a sentence when it cannot be kept."""
    text = tidy_line(text)

    def work():
        row = _find(conn, line_id)
        line_id_ = row["id"]
        was = row["text"].strip()
        written = BULLET + plain(text) if was.startswith(BULLET.strip()) and was[1:2] in (" ", "") else plain(text)
        if written == row["text"]:
            return
        conn.execute("UPDATE style_lines SET text = ?, source = 'owner', created_at = ? WHERE id = ?",
                     (written, db.now(), line_id_))
        _write(conn, "owner")

    _transaction(conn, work)
    return current(conn)


def remove_line(conn, line_id: int, source: str = "owner") -> dict:
    """Take a line out of the profile (it can be put back with `restore_line`). With no lines left the starting
    profile is in force. Gives back the profile; raises LookupError for a line not in force."""
    def work():
        row = _find(conn, line_id)
        conn.execute("UPDATE style_lines SET removed_at = ? WHERE id = ?", (db.now(), row["id"]))
        _write(conn, source)
        return row["id"]

    removed = _transaction(conn, work)
    return {**current(conn), "removed": removed}


def take_back(conn, line_id: int, source: str = "owner") -> None:
    """Undo a line added by `add_line` (Undo on a line kept from a conversation, or on an answer): it is removed, and
    when what is left is only the starting lines kept for that first change, the starting profile is in force again,
    as it was before. Raises LookupError for a line not in force."""
    def work():
        remove_line(conn, line_id, source)
        left = _rows(conn)
        if left and all(r["source"] == "start" for r in left) and [r["text"] for r in left] == _kept_starting():
            conn.execute("UPDATE style_lines SET removed_at = ? WHERE removed_at IS NULL", (db.now(),))
            _write(conn, source)

    _transaction(conn, work)


def restore_line(conn, line_id: int) -> dict:
    """Put a removed line back where it was, with where it came from. Gives back the profile; raises LookupError for
    a line that was not removed, ValueError when the text would grow too long."""
    def work():
        _find(conn, line_id, removed=True)
        conn.execute("UPDATE style_lines SET removed_at = NULL WHERE id = ?", (line_id,))
        _write(conn, "owner")

    _transaction(conn, work)
    return current(conn)


def text_for_stylist(conn) -> str | None:
    """The owner's own profile for `styling.brief(profile=...)`, or None while the starting one is in force."""
    row = _newest(conn)
    return (row["text"] or None) if row is not None else None
