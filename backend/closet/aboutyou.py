"""What "Find some" tells Claude about the owner, beside the wish: their style lines, what they love and wear in this
kind of piece, the brands they already wear, and their size (DECISIONS, "What the search is told about you").

`about` is pure and builds the block from plain data; `for_search` reads what it needs from the closet. The block is
leanings to rank the products by, never requirements: the wish and its price range come first, and the prompt says
so (`tagger/shopping.py`). It is bounded whatever the closet's size (at most STYLE_CHARS of style, PIECES pieces,
BRANDS brands, SIZE_BRANDS brands that fit differently) and in a stable order, so the same closet gives the same
words. Never a photo, an item's name or a note the owner typed: a piece is said in the closet's own words (its kind,
colour, pattern, fit and material).
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping

from . import outfits, sizes, styleprofile, taste, vocab

STYLE_CHARS = 1500     # the most of Your style that is sent, cut at a line
STYLE_LINE = 300       # ...and the most of any one line
PIECES = 5             # the loved or most-worn pieces described
PIECE_WEARS = 3        # a piece not loved is described only once worn on this many days
MATERIAL_CHARS = 60
BRANDS = 8             # the brands said, most worn and best rated first
BRAND_CHARS = sizes.MAX_BRAND
SIZE_BRANDS = 8        # the brands that fit differently, at most, across the sizes said
RATING_POINTS = {"love": 4, "like": 2, "meh": 0}   # a brand's weight from its items' ratings, beside their wears

HEADING = "About the person this is for"
LEANINGS = ("These are leanings to rank the products by, not requirements: the wish and its price range above come "
            "first, and a good match for the wish is never left out because of them.")
IN_STOCK = "When a shop lists sizes, prefer products in stock in their size."
AXIS_WORDS = (("color", "colours"), ("pattern", "patterns"), ("fit", "fits"))
_PLURAL = {"scarf": "scarves", "dress_shoes": "dress shoes"}
_ALREADY_PLURAL = ("jeans", "trousers", "shorts", "sneakers", "boots", "sandals")
GARMENTS = tuple(c for c in vocab.CATEGORY if c != "other")   # an overall look leaves accessories out below


def _plain(v: object) -> str:
    return " ".join(str(v).replace("_", " ").split())


def _plural(category: str) -> str:
    if category in _PLURAL:
        return _PLURAL[category]
    return _plain(category) if category in _ALREADY_PLURAL else f"{_plain(category)}s"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _worn_days(wears: Iterable[Mapping]) -> Counter:
    return Counter(i for i, _ in {(w.get("item_id"), w.get("worn_on")) for w in wears if w.get("item_id")})


def style_words(lines: list[str]) -> list[str]:
    """Your style's lines, in order, each cut to STYLE_LINE, until STYLE_CHARS is reached."""
    out, used = [], 0
    for line in lines:
        text = _cut(" ".join(line.split()), STYLE_LINE)
        if not text:
            continue
        if used + len(text) > STYLE_CHARS:
            break
        out.append(f"- {text}")
        used += len(text)
    return out


def _piece(row: Mapping, days: int) -> str:
    sil = row.get("silhouette") if isinstance(row.get("silhouette"), dict) else {}
    kind = _plain(row.get("kind") or row.get("category") or "piece")
    colour = _plain(row.get("color") or "")
    if row.get("pattern") and row.get("pattern") != "solid":
        colour = f"{colour} {_plain(row['pattern'])}".strip()
    words = [w for w in (colour, f"{_plain(sil['fit'])} fit" if isinstance(sil.get("fit"), str) and sil["fit"] else "",
                         _cut(_plain(row.get("material") or ""), MATERIAL_CHARS)) if w]
    why = [w for w in ("loved" if row.get("rating") == "love" else "",
                       f"worn on {days} days" if days else "") if w]
    return f"- {kind}" + (f": {', '.join(words)}" if words else "") + (f" ({', '.join(why)})" if why else "")


def pieces_words(rows: list[dict], days: Counter, categories: Iterable[str]) -> list[str]:
    """Up to PIECES pieces of these categories that are loved or worn on PIECE_WEARS days or more: loved first, then
    the most worn, then by id."""
    wanted = set(categories)
    chosen = [r for r in rows if r.get("status") != "archived" and r.get("category") in wanted
              and r.get("rating") not in ("dislike", "meh")
              and (r.get("rating") == "love" or days[r.get("id")] >= PIECE_WEARS)]
    chosen.sort(key=lambda r: (r.get("rating") != "love", -days[r.get("id")], str(r.get("id"))))
    return [_piece(r, days[r.get("id")]) for r in chosen[:PIECES]]


def taste_words(profile: dict | None) -> list[str]:
    """The colours, patterns and fits taste favours, where it has enough evidence (`taste.py` decides)."""
    if not profile:
        return []
    return [f"- {words.capitalize()} they favour: {', '.join(_plain(v) for v in profile['favoured'][axis])}."
            for axis, words in AXIS_WORDS if profile["favoured"].get(axis)]


def brand_names(rows: list[dict], days: Counter) -> list[str]:
    """The brands on the owner's active items (none of them disliked), most worn and best rated first, then on the
    most items, then alphabetical; spelt as on most of their items; at most BRANDS."""
    score, items, spelt = Counter(), Counter(), {}
    for r in rows:
        brand = " ".join(r["brand"].split()) if isinstance(r.get("brand"), str) else ""
        if r.get("status") == "archived" or not brand or len(brand) > BRAND_CHARS or r.get("rating") == "dislike":
            continue
        key = brand.casefold()
        score[key] += days[r.get("id")] + RATING_POINTS.get(r.get("rating"), 0)
        items[key] += 1
        spelt.setdefault(key, Counter())[brand] += 1
    order = sorted(items, key=lambda k: (-score[k], -items[k], k))[:BRANDS]
    return [min(spelt[k], key=lambda s: (-spelt[k][s], s)) for k in order]


def size_words(saved: Mapping[str, Mapping], kind: str | None, every: bool) -> list[str]:
    """The saved size for `kind` with its brands' own ("M; in Example Brand: L"), or with `every` each kind's that is
    saved; never a suggestion that was not confirmed."""
    labels = dict(sizes.KINDS)
    kinds = [k for k in sizes.KIND_KEYS if every or k == kind]
    lines, brands_left = [], SIZE_BRANDS
    for k in kinds:
        entry = saved.get(k) or {}
        parts = [entry["size"]] if entry.get("size") else []
        for b in (entry.get("brands") or [])[:max(0, brands_left)]:
            parts.append(f"in {b['brand']}: {b['size']}")
            brands_left -= 1
        if parts:
            lines.append(f"- {labels[k]}: {'; '.join(parts)}.")
    return lines


def about(rows: list[dict], wears: list[dict], style_lines: list[str], saved_sizes: Mapping[str, Mapping],
          category: str | None) -> str:
    """The block about the owner for a search, or "" when nothing is known. `category` is the wish's closet category
    (None: a wish added by hand, then the whole closet is looked at and every saved size is said)."""
    category = category if category in GARMENTS else None
    days = _worn_days(wears)
    blocks = []
    style = style_words(style_lines)
    if style:
        blocks.append("Their style, in their own words:\n" + "\n".join(style))
    accessory = category in outfits.ACCESSORY_CATEGORIES
    wide = [c for c in GARMENTS if c not in outfits.ACCESSORY_CATEGORIES]
    profile = None
    if category:
        learned = taste.learn(rows, wears)["by_category"].get(category)
        profile = learned if learned and learned["used"] else None
    where = f"in {_plural(category)}" if category else "across their clothes"
    leaning = taste_words(profile if category else taste.overall(rows, wears, wide))
    loved = pieces_words(rows, days, [category] if category else wide)
    if leaning or loved:
        text = f"What they love and wear {where}:"
        if leaning:
            text += "\n" + "\n".join(leaning)
        if loved:
            text += "\nPieces they love or wear most:\n" + "\n".join(loved)
        blocks.append(text)
    brands = brand_names(rows, days)
    if brands:
        blocks.append(f"Brands they already wear (a hint, not a filter): {', '.join(brands)}.")
    kind = sizes.kind_of(category)
    fitted = [] if accessory else size_words(saved_sizes, kind, every=category is None)
    if fitted:
        blocks.append(("Their size:" if kind else "Their sizes:") + "\n" + "\n".join(fitted) + f"\n{IN_STOCK}")
    if not blocks:
        return ""
    return f"{HEADING}\n{LEANINGS}\n\n" + "\n\n".join(blocks)


def style_lines(conn: sqlite3.Connection) -> list[str]:
    """Your style's lines as the stylist reads them; none while the starting profile is in force (it says nothing about
    the owner)."""
    profile = styleprofile.current(conn)
    if profile["is_default"]:
        return []
    return [styleprofile.plain(ln) for ln in profile["text"].splitlines() if ln.strip()]


def for_search(conn: sqlite3.Connection, rows: list[dict], wears: list[dict], wish: Mapping) -> str:
    """The block for a search for `wish`, from the closet open on `conn` and its item rows and wear log."""
    look = wish.get("look_for") if isinstance(wish.get("look_for"), dict) else {}
    return about(rows, wears, style_lines(conn), sizes.saved(conn), look.get("category"))
