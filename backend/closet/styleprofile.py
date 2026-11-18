"""The owner's style profile: how they like to dress, in their own words (Settings, "Your style").

Claude reads it every time it chooses the outfits, and it wins over the general menswear guide (`styling.brief`).
It is kept in the closet's own database, so it is in backups and each closet (the owner's, the demo) has its own.
Every save adds a row to `style_profile`; the newest row is the profile in force and the older ones are its
history. An empty text means the starting profile (`styling.DEFAULT_PROFILE`) is in force: saving one is how the
owner goes back to it. Nothing here asks Claude.
"""
from __future__ import annotations

from . import db, styling

MAX_TEXT = 4000           # the longest profile the owner can save (characters)
SOURCES = ("owner", "claude")


def _newest(conn):
    return conn.execute("SELECT text, created_at FROM style_profile ORDER BY id DESC LIMIT 1").fetchone()


def current(conn) -> dict:
    """The profile in force: its text (the starting one when the owner has written none), whether that is the
    starting one, when it was last saved (None: never), the starting text and the longest text allowed."""
    row = _newest(conn)
    own = row["text"] if row is not None else ""
    return {"text": own or styling.DEFAULT_PROFILE, "is_default": not own,
            "updated_at": row["created_at"] if row is not None else None,
            "default_text": styling.DEFAULT_PROFILE, "max_length": MAX_TEXT}


def tidy(text: object) -> str:
    """The text as kept: without space at either end, with every line break as "\\n" and the owner's breaks kept.
    The starting text itself is kept as an empty one, so the starting profile stays in force."""
    if not isinstance(text, str):
        raise ValueError("Your style must be written as text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > MAX_TEXT:
        raise ValueError(f"Your style can be at most {MAX_TEXT:,} characters long; this is {len(text):,}.")
    return "" if text == styling.DEFAULT_PROFILE.strip() else text


def save(conn, text: object, source: str = "owner") -> dict:
    """Keep a new version of the profile and give back the one in force. An empty text goes back to the starting
    profile; a text the same as the one in force adds nothing."""
    if source not in SOURCES:
        raise ValueError("A style profile is written by the owner or by Claude.")
    text = tidy(text)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = _newest(conn)
        if text != (row["text"] if row is not None else ""):
            conn.execute("INSERT INTO style_profile (text, source, created_at) VALUES (?, ?, ?)", (text, source, db.now()))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return current(conn)


def text_for_stylist(conn) -> str | None:
    """The owner's own profile for `styling.brief(profile=...)`, or None while the starting one is in force."""
    row = _newest(conn)
    return (row["text"] or None) if row is not None else None
