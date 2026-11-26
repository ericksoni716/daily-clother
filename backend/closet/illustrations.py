"""Each item's drawing: made from what is known about the item and kept up to date.

The drawing is made from the item's stored tagger answer when there is one, and
from its coarse fields (category, colour, pattern, silhouette) when there is
not. Where the owner has set a field (`source[field] == "user"`), the drawing
follows the item's field, not the answer, and the details the owner has set
(`own_details`, see `details.py`) are laid over the answer's.

It is made again when tagging finishes (`tagjobs.apply_answer`), when the owner
changes a field it shows (`items.update`), and when it was made by older drawing
code than this program's (`drawing.DRAWING_VERSION`): such an item is drawn
again the first time it is asked for, so a template change never redraws a
whole closet at start-up. Drawing never fails an item: what could not be drawn
is kept, in plain words, for the item page.

A shoe Claude drew from its side (`shoedraw`, the drawing's `side` entry) is drawn from that, on the templates' card
(`drawing.drawnside`), unless the owner chose the plain drawing for it. Without it, a shoe traced from its photo
(`tracejobs`) is drawn from its trace, with the owner's fixes laid over it (`drawing.sideshoe`), again unless the
owner chose the plain drawing; a shoe not traced, or whose photo the tracing turned down, keeps the template drawing. On the outfit figure, a shoe Claude drew from its photos
(`shoedraw`) is drawn from that drawing; without one, from the template's front view for its style, traced or not.

The demo closet's drawings were made in advance by `tools/make_demo.py` (with
fills taken from the photos) and carry the version they were made with, so they
stay as they are until the owner changes a field they show.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace

from . import details, drawing, kinds, wouldwork
from .drawing import added, drawnside, sideshoe, stored, wordpattern
from .drawing import item as draw
from .drawing.figure import PLACES, Piece, as_worn, figure
from .drawing.traced import TracedShoe
from .tagger import surfaceform, taxonomy
from .tagger.schema import NAMED_HEX, SILHOUETTE_FIELDS, Details

log = logging.getLogger("closet.illustrations")

# the item's own fields the drawing is made from; changing one of them draws the item again
SHOWN = frozenset(("category", "color", "color_hex", "pattern", "silhouette"))
OWNER = "user"
# the answer's details that say more than a silhouette field, and what they say when they leave it to that field:
# where the owner has changed the field, the drawing follows the owner's word
DETAIL_FOR = {"sleeve": {"sleeve_length": "na"}, "neck": {"neckline": "na", "collar": "none"},
              "fit": {"fit_detail": "regular"}, "shoe_height": {"shoe_style": "na"}}


def _json(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def drawn_answer(row, extra: dict | None = None) -> dict | None:
    """The answer the item is drawn from: Claude's, with the owner's fields and own details laid over it (and
    `extra` details over those, for a preview). None when there is no answer and the owner has set no detail:
    the item is then drawn from its fields alone."""
    source = _json(row["source"], {})
    silhouette = _json(row["silhouette"], {})
    answer = _json(row["tag_answer"], None)
    kind = kinds.owner_kind(row)
    owner = {k: v for k, v in details.own(row).items() if kinds.applies(kind, k)}   # what the kind has not is kept, not drawn
    owner.update(extra or {})
    if not isinstance(answer, dict):
        if not owner:
            return None
        answer = details.plain_answer(row["category"], silhouette, row["color"], row["pattern"])
        if answer is None:
            return None
    said = kinds.said_kind(answer)
    answer = dict(answer)
    if source.get("pattern") == OWNER and answer.get("pattern") != row["pattern"]:
        answer.pop("surface", None)   # the owner's pattern word, not the cloth Claude described (`patjobs._surface`)
    answer.update(surfaceform.own_cloth(row))   # the cloth and lettering in the owner's own words, over Claude's
    for field in ("category", "color", "pattern"):
        if source.get(field) == OWNER:
            answer[field] = row[field]
    if source.get("silhouette") == OWNER and isinstance(silhouette, dict):
        said = answer.get("silhouette") if isinstance(answer.get("silhouette"), dict) else {}
        found = dict(answer["details"]) if isinstance(answer.get("details"), dict) else None
        for k, leave in DETAIL_FOR.items():
            if found is not None and silhouette.get(k) is not None and silhouette.get(k) != said.get(k):
                found.update(leave)
        if found is not None:
            answer["details"] = found
        # a field the owner left empty is the answer's
        answer["silhouette"] = {k: said.get(k) if silhouette.get(k) is None else silhouette.get(k) for k in SILHOUETTE_FIELDS}
    if owner and isinstance(answer.get("details"), dict):
        answer["details"] = details.lay(answer["details"], owner)   # the owner's details win over Claude's
    if kind and isinstance(answer.get("details"), dict):
        answer["details"] = kinds.conform(answer["details"], kind, said, owner)   # and the drawing follows their kind
    found = answer.get("details")
    if isinstance(found, dict) and answer.get("category") in draw.BOTTOMS:   # the hem as drawn: joggers' ribbed cuff
        hem = taxonomy.kind_hem_finish(found.get("garment"), answer["category"], found.get("hem_finish"))
        if hem != found.get("hem_finish"):
            answer["details"] = {**found, "hem_finish": hem}
    return answer


def shown_details(row) -> dict:
    """The details as the item is drawn now (Claude's, the owner's laid over them), or the plain ones."""
    try:
        answer = drawn_answer(row)
    except Exception:
        answer = None
    found = answer.get("details") if isinstance(answer, dict) else None
    return found if isinstance(found, dict) else Details.plain().model_dump(mode="json")


def describe(row, extra: dict | None = None) -> Piece:
    """What the item's drawing is made from: the answer it is drawn from (`drawn_answer`: Claude's, with the owner's
    fields and own details laid over it) and its own colour; or, with no answer, its coarse fields. The outfit
    figure draws each piece from this too, so the owner's corrections show there as well. A shoe Claude drew from its
    photos carries that drawing (`drawn_of`), which the figure draws instead of the template's front view."""
    source = _json(row["source"], {})
    silhouette = _json(row["silhouette"], {})
    answer = drawn_answer(row, extra)
    if answer is None:
        piece = Piece(row["category"], None, row["color_hex"], row["color"], row["pattern"], silhouette)
        return replace(piece, fill=pattern_fill(row, piece), graphic=pattern_graphic(row),
                       drawn=drawn_of(row), added=added_of(row))
    # the item's own colour (from the answer, the photo or the owner), unless the owner chose a colour word
    # and left a colour from before beside it
    own_hex = source.get("color_hex") == OWNER or source.get("color") != OWNER
    piece = Piece(answer.get("category"), answer, row["color_hex"] if own_hex else None, row["color"], row["pattern"],
                  silhouette)
    return replace(piece, fill=pattern_fill(row, piece), graphic=pattern_graphic(row), drawn=drawn_of(row),
                   added=added_of(row))


def new_piece(piece) -> Piece:
    """A piece not in the closet (a find, a piece checked with "Would this work?"), drawn from its described values
    as a new item with them would be: its category, colour word and shape, in its colour word's colour. A striped or
    plaid piece is drawn with a plain, typical pattern of that word (`wordpattern.fill_for`; a measured pattern
    would come from a photo, which it has none of). It is drawn as the kind it carries (`kind`, Claude's word for it);
    without one, as the kind its name says in so many words (`kinds.from_words`: "Brown suede chelsea boots", or a
    "chore coat" called a coat), as the kind picker draws one. A coat or a jacket of no kind at all is drawn as one a
    person wears open over what is under it (`kinds.PLAIN_OUTER`), never as a closed tunic. `piece` is a description
    as `wouldwork.parse_piece` gives it."""
    category, color = piece["category"], piece["color"]
    silhouette = dict(piece.get("silhouette") or {})
    kind = piece.get("kind") if piece.get("kind") in kinds.KINDS else kinds.from_words(piece.get("name"), category)
    if kind is not None and category in kinds.OUTER:   # a coat's kind called a jacket is drawn as that coat
        category = kinds.category_for(kind, category)
    fill = wordpattern.fill_for(category, color, piece.get("pattern"), piece.get("name"), kind)
    kind = kind or kinds.PLAIN_OUTER.get(category)
    if kind is None:
        return Piece(category, None, None, color, None, silhouette, fill=fill)
    found = Details.plain().model_dump(mode="json")
    if kind in kinds.GARMENTS:
        found["garment"] = kind
    answer = {
        "category": category, "category_confidence": 1, "color": color if color in NAMED_HEX else "grey",
        "color_confidence": 1, "secondary_colors": [], "pattern": "solid", "pattern_confidence": 1,
        "formality": "casual", "formality_confidence": 1, "season": "all", "season_confidence": 1,
        "silhouette": {k: silhouette.get(k) for k in SILHOUETTE_FIELDS}, "silhouette_confidence": 1,
        "details": kinds.conform(found, kind, None, {}), "details_confidence": 1, "brand": None, "size": None,
        "material": None, "needs_shot": None}
    return Piece(category, answer, None, color, None, silhouette, fill=fill)


def added_of(row) -> tuple:
    """What Claude drew onto the item's drawing at the owner's word (`additions`), as the template's parts to lay over
    its own; () for none, for a shoe (whose drawing is corrected under its own drawing by Claude) and for parts that
    cannot be read."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "additions" not in keys or not row["additions"] or row["category"] in draw.SHOES:
        return ()
    kept = _json(row["additions"], None)
    return added.parts(kept.get("parts")) if isinstance(kept, dict) else ()


def worn(row) -> list[dict]:
    """How the item sits on the outfit figure, in words, each with the detail that corrects it (figure.as_worn)."""
    try:
        return as_worn(describe(row))
    except Exception:
        log.exception("telling how item %s is worn failed", row["id"])
        return []


def pattern_fill(row, piece: Piece | None = None):
    """The item's measured pattern as a fill for its drawing, or None (drawn in its colour). Not used once the
    owner has said the item is plain (pattern "solid")."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "pattern_fill" not in keys or not row["pattern_fill"] or row["pattern"] == "solid":
        return None
    base = (piece.color_hex if piece else None) or row["color_hex"] or "#888888"
    return stored.fill_from(row["pattern_fill"], base)


def pattern_graphic(row):
    """The print lifted from the item's photo (a logo, a chest print), to draw at its place, or None. Not used
    once the owner has said the item is plain."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "pattern_fill" not in keys or not row["pattern_fill"] or row["pattern"] == "solid":
        return None
    return stored.graphic_from(row["pattern_fill"])


def traced(row) -> tuple[str, str | None] | None:
    """The item's trace and the owner's fixes to it (JSON), when its drawing is the traced one: a shoe, traced, with
    no side drawn by Claude (`side_of`), and the owner has not chosen the plain drawing. None otherwise."""
    return None if side_of(row) is not None else _trace(row)


def _trace(row) -> tuple[str, str | None] | None:
    """The trace and its fixes for a shoe traced, unless the owner chose the plain drawing (whatever Claude drew)."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "trace" not in keys or not row["trace"] or row["trace_state"] != "done" or row["trace_plain"]:
        return None
    return (row["trace"], row["trace_fixes"]) if row["category"] in draw.SHOES else None


def side_of(row) -> str | None:
    """Claude's drawing of a shoe from its side (its kept drawing's `side` entry), when the item's drawing is that: a
    shoe whose drawing has a side, and the owner has not chosen the plain drawing. None otherwise. It wins over the
    trace, which stays for when it cannot be made or read."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "trace_plain" in keys and row["trace_plain"]:
        return None
    d = drawn_of(row)
    side = d.get("side") if d else None
    svg = side.get("svg") if isinstance(side, dict) else None
    return svg if isinstance(svg, str) and svg.strip() else None


def drawn_of(row) -> dict | None:
    """The drawing Claude made of a shoe from its photos (`shoedraw`), as kept with the item, whatever is happening to
    it now (a shoe being drawn again keeps the drawing it has until the new one is done, also when that fails); None
    for anything else or a shoe never drawn. The figure reads it (`drawn.stored`) and falls back to the front view
    when it cannot be drawn."""
    keys = row.keys() if hasattr(row, "keys") else row
    if "drawn" not in keys or not row["drawn"] or row["category"] not in draw.SHOES:
        return None
    d = _json(row["drawn"], None)
    return d if isinstance(d, dict) else None


def make(row, extra: dict | None = None) -> draw.Drawing:
    """The drawing for an item row as it stands now (with `extra` details laid over it, for a preview). Never raises."""
    try:
        side = side_of(row)
        if side is not None:
            try:
                return draw.Drawing(drawnside.card_svg(side), ())
            except Exception:   # a side that cannot be read: the trace, or the template drawing
                log.exception("could not draw a shoe's side drawn by Claude")
        shoe = _trace(row)   # no side, or one that could not be read
        if shoe is not None:
            try:
                return draw.Drawing(sideshoe.drawing(TracedShoe.from_json(shoe[0]), _json(shoe[1], None), uid=row["id"][:8]), ())
            except Exception:   # a trace that cannot be read: the template drawing, as for a shoe not traced
                log.exception("could not draw a traced shoe")
        piece = describe(row, extra)
        uid = row["id"][:8]
        fill = piece.fill
        if piece.answer is None:
            return draw.drawing_from_fields(piece.category, piece.color_hex, piece.pattern, piece.silhouette,
                                            color=piece.color, uid=uid, fill=fill, graphic=piece.graphic,
                                            added=piece.added)
        return draw.drawing_from_answer(piece.answer, piece.color_hex, uid=uid, fill=fill, graphic=piece.graphic,
                                        added=piece.added)
    except Exception:   # never fail an item
        log.exception("could not draw an item")
        return draw.Drawing(None, (draw.NOT_MADE,))


def back(row) -> str | None:
    """The item page's small drawing of a pair of trousers or shorts from behind, made from the same answer and
    fill as its drawing; None when nothing on its back is known (or with no answer to draw it from). Never raises."""
    try:
        piece = describe(row)
        if piece.answer is None:
            return None
        return draw.back_from_answer(piece.answer, piece.color_hex, uid=row["id"][:8] + "b", fill=piece.fill)
    except Exception:
        log.exception("could not draw the back of an item")
        return None


def _store(conn, item_id: str, made: draw.Drawing) -> None:
    conn.execute("UPDATE items SET illustration_svg = ?, illustration_version = ?, illustration_notes = ? WHERE id = ?",
                 (made.svg, drawing.DRAWING_VERSION, json.dumps(list(made.not_drawn)) if made.not_drawn else None, item_id))


def redraw(conn, item_id: str) -> None:
    """Draw the item again from what it is now and keep it, inside the caller's transaction if there is one."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is not None:
        _store(conn, item_id, make(row))


def current(conn, row):
    """The item row with an up-to-date drawing: drawn now if it never was, or was drawn by older drawing code."""
    version = row["illustration_version"]
    if version is not None and version >= drawing.DRAWING_VERSION:
        return row
    made = make(row)
    try:
        _store(conn, row["id"], made)
    except sqlite3.Error:   # the closet is busy: shown now, kept the next time it is asked for
        log.warning("could not keep an item's new drawing; it is made again next time")
    return {**dict(row), "illustration_svg": made.svg, "illustration_version": drawing.DRAWING_VERSION,
            "illustration_notes": json.dumps(list(made.not_drawn)) if made.not_drawn else None}


def notes(row) -> list[str]:
    """What the item's drawing leaves out or shows only roughly, in plain words."""
    out = _json(row["illustration_notes"], [])
    return [n for n in out if isinstance(n, str)] if isinstance(out, list) else []


def not_drawn(row, seen: list) -> list:
    """What the tagger saw that no field covers, less the words the drawing now shows."""
    drawn = set(draw.words_drawn(drawn_answer(row)))
    return [w for w in seen if w not in drawn]


class FigureError(ValueError):
    """The request for an outfit figure cannot be answered; the message says why, in plain words."""


MAX_ACCESSORIES = 8   # an outfit's accessories, as many as one request may name


def figure_request(body) -> tuple[dict[str, str | list[str]], dict | None]:
    """From a request for an outfit figure: the item ids by place, places as the outfit engine names them (base, mid,
    outer, bottom, shoes), each an item id or null, and "accessories", a list of up to MAX_ACCESSORIES item ids (or
    null); and the piece not in the closet that is worn with them, if any. A request may also give "piece", a
    description as `wouldwork.parse_piece` takes it, worn wherever a place (or the accessories) names
    `wouldwork.CANDIDATE_ID`, as "Would this work?"'s example outfits name it."""
    if not isinstance(body, dict):
        raise FigureError("Send the items by place, for example {\"base\": \"…\", \"bottom\": \"…\"}.")
    piece = None
    if body.get("piece") is not None:
        try:
            piece = wouldwork.parse_piece(body["piece"])
        except wouldwork.PieceError as e:
            raise FigureError(str(e)) from None
    body = {k: v for k, v in body.items() if k != "piece"}
    unknown = [k for k in body if k not in PLACES and k != "accessories"]
    if unknown:
        raise FigureError(f"Unknown place: {unknown[0]}. The places are {', '.join(PLACES)} and accessories.")
    ids: dict[str, str | list[str]] = {}
    for place, value in body.items():
        if value is None:
            continue
        if place == "accessories":
            if not isinstance(value, list) or len(value) > MAX_ACCESSORIES or \
                    not all(isinstance(v, str) and v and len(v) <= 64 for v in value):
                raise FigureError(f"The accessories must be a list of at most {MAX_ACCESSORIES} item ids.")
            if value:
                ids[place] = list(dict.fromkeys(value))
            continue
        if not isinstance(value, str) or not value or len(value) > 64:
            raise FigureError(f"The {place} must be an item id or null.")
        ids[place] = value
    if not ids:
        raise FigureError("Say which items to draw.")
    named = any(v == wouldwork.CANDIDATE_ID for value in ids.values()
                for v in (value if isinstance(value, list) else [value]))
    if named and piece is None:
        raise FigureError("Describe the piece that is not in the closet, as \"piece\".")
    return ids, piece if named else None


def outfit_figure(conn, ids: dict[str, str | list[str]], new: dict | None = None) -> str:
    """The outfit drawn as worn, from the open closet's items. Each piece is drawn from what its own drawing is
    made from (`describe`), so the owner's corrections show here too. `new` is a piece not in the closet (a find),
    drawn from its description (`new_piece`) wherever `ids` names `wouldwork.CANDIDATE_ID`: it takes its place
    among the owner's layers as any garment does."""
    wanted = [(place, v) for place, value in ids.items() for v in (value if isinstance(value, list) else [value])]
    owned = [v for _, v in wanted if not (new is not None and v == wouldwork.CANDIDATE_ID)]
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT * FROM items WHERE id IN ({','.join('?' * len(owned))})", owned)} if owned else {}
    for place, item_id in wanted:
        if item_id not in rows and not (new is not None and item_id == wouldwork.CANDIDATE_ID):
            raise FigureError(f"The {'accessory' if place == 'accessories' else place} is not in this closet.")
    pieces: dict = {}
    for place, item_id in wanted:
        try:
            piece = new_piece(new) if item_id not in rows else describe(rows[item_id])
        except Exception:   # a piece that cannot be read is left out; the rest are still drawn
            log.exception("could not read an item for an outfit figure")
            continue
        if place == "accessories":
            pieces.setdefault(place, []).append(piece)
        else:
            pieces[place] = piece
    return figure(pieces)
