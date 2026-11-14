"""Why an item's cutout or description failed, in words that are safe to show and to log.

The real reason is the failed job's `error` in the `jobs` table. It can hold
anything an exception said, so it is cleaned before it is written there and again before it leaves the database:
anything that looks like a key or a token, an e-mail address, and file paths
outside Closet's own folder are taken out. A path inside that folder is kept,
starting from "[Closet folder]", so it does not show the owner's user name.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("closet.failures")

MAX_DETAILS = 500
HIDDEN = "[hidden]"
FOLDER = "[Closet folder]"
ELSEWHERE = "[a path outside Closet]"
_REASON = {
    "cutout": "The background could not be removed from this photo.",
    "description": "Claude could not describe this item.",
}

_KEY = re.compile(r"\bsk-[A-Za-z0-9_\-]{4,}")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[^\s\"',;)]+")
_LABELLED = re.compile(r"(?i)\b(api[_-]?key|x-api-key|access[_-]?token|auth[_-]?token|token|authorization|"
                       r"password|passwd|secret|credentials?)(\s*[:=]\s*)([\"']?)[^\s\"',;)]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG = re.compile(r"(?<![\w\-+])(?=[\w\-+]*\d)(?=[\w\-+]*[A-Za-z])[\w\-+]{32,}={0,2}")
_PATHS = (
    re.compile(r"\\\\[^\s'\"<>|;,()\[\]{}]+"),                          # \\server\share\...
    re.compile(r"\b[A-Za-z]:[\\/][^\s'\"<>|;,()\[\]{}]*"),                # C:\Users\...
    re.compile(r"(?<![\w\]:/.~\-])~?/[^\s'\"<>|:;,()\[\]{}]+"),          # /Users/... or ~/...
)


def data_folder(conn) -> Path | None:
    """Closet's data folder for the open closet: the folder of its database (the demo closet is one level down)."""
    try:
        file = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    except Exception:
        return None
    if not file:
        return None
    folder = Path(file).parent
    if folder.name == "demo" and (folder.parent / "closet.db").exists():
        folder = folder.parent
    return folder


def _forms(folder: Path) -> list[str]:
    out = set()
    for p in (folder, folder.resolve()):
        s = str(p).rstrip("\\/")
        if len(s) > 1:
            out |= {s, s.replace("\\", "/"), s.replace("/", "\\")}
    return sorted(out, key=len, reverse=True)


def clean(text: str | None, folder: Path | None = None) -> str | None:
    """The stored error with keys, tokens, e-mail addresses and paths outside `folder` taken out."""
    if not text:
        return None
    if folder is not None:
        for form in _forms(folder):
            text = text.replace(form, FOLDER)
    text = _KEY.sub(HIDDEN, text)
    text = _BEARER.sub(lambda m: f"{m[1]} {HIDDEN}", text)
    text = _LABELLED.sub(lambda m: f"{m[1]}{m[2]}{m[3]}{HIDDEN}", text)
    text = _EMAIL.sub(HIDDEN, text)
    for pattern in _PATHS:
        text = pattern.sub(ELSEWHERE, text)
    text = _LONG.sub(HIDDEN, text)
    text = text.strip()
    if len(text) > MAX_DETAILS:
        text = text[:MAX_DETAILS - 1] + "…"
    return text or None


def kept(conn, error: str | None) -> str | None:
    """The reason a failed attempt keeps in the `jobs` table: cleaned the same way before it is written, as the
    database is copied into backups."""
    return clean(error, data_folder(conn))


def _job_error(conn, kind: str, item_id: str) -> str | None:
    row = conn.execute("SELECT error FROM jobs WHERE kind = ? AND item_id = ? AND state = 'failed' ORDER BY id DESC LIMIT 1",
                       (kind, item_id)).fetchone()
    return row["error"] if row else None


def of(conn, row) -> dict | None:
    """What the item page shows for a failed item: {stage, reason, details}, or None when nothing has failed."""
    if row["cutout_state"] == "failed":
        stage, kind, reason = "cutout", "cutout", row["cutout_error"]
    elif row["tag_state"] == "failed":
        stage, kind, reason = "description", "tag", row["tag_error"]
    else:
        return None
    return {"stage": stage, "reason": reason or _REASON[stage],
            "details": clean(_job_error(conn, kind, row["id"]), data_folder(conn))}


def report(conn, item_id: str, stage: str, error: str | None) -> None:
    """Write why an item failed to the log, once, when it is marked failed. Cleaned the same way; never a photo."""
    log.warning("item %s: the %s failed: %s", item_id, stage,
                clean(error, data_folder(conn)) or "no reason was recorded")
