"""Asking Claude to add to a garment's drawing what the owner asks, with the template's drawing as its guide.

The owner writes one line ("a small red patch on the left sleeve"); Claude is shown the item's photo, its drawing as
it is with a grid in the drawing's own coordinates (`drawing.added.gridded`), the template's shape in words
(`drawing.added.geometry`), what it drew onto the drawing before and the owner's earlier lines, and answers with every
part to lay over the template's drawing (`Adding`): the ones from before kept exactly, the new ones drawn as the note
asks. It never redraws the template's own parts; a note that asks for that is answered in words.

Then one check (`CHECKS`): Claude is shown the photo, the drawing before and after, the note, the parts and what the
automatic checks found (a part that cannot be read, a part off the garment), says good, or gives every part again,
fixed, never undoing the owner's change. Both through the same routes as describing (`correcting.ask`, the Claude
plan first), on the model of the `drawing` role, recorded with the purpose `add_to_drawing`.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from ..drawing import added, drawn
from ..drawing.fitting import points, signed_distance
from . import correcting
from .tagging import CONFIG, cost_usd

MODEL = CONFIG["roles"]["drawing"]
EFFORT = "medium"      # as a shoe's drawing (the owner's choice, 16 November)
MAX_TOKENS = 16_000    # the longest answer a call allows on the API route, its thinking included
TIMEOUT = 300          # seconds one call through the plan may take
CHECKS = 1             # checks of the parts against the photo, after they are drawn
NOTE_MAX = 200         # characters in the owner's line
NOTES_SENT = 20        # the owner's earlier lines given with a new one
OFF_BY = 4.0           # how far (drawing units) a part not cut by the garment's edge may reach past it unremarked
RENDER_PX = 800        # the width the drawings are shown to Claude at
SYSTEM = ("You add to the drawing of one item of clothing in a private wardrobe app, as its owner asks. Look at every "
          "image file named in the request with the Read tool. Answer in the required JSON format. Do nothing else.")


class Part(BaseModel):
    what: str = Field(description="What this part is, in a few plain words (\"red patch on the left sleeve\").")
    role: Literal["inlay", "mark", "stitch", "line"] = Field(description=(
        "inlay: a piece in its own colour with an edge (a patch, a panel, a pocket, a tab). mark: a small piece in its "
        "own colour with no edge (a logo's shape, a thin stripe). stitch: a dashed line of topstitching. line: a line "
        "with no fill (a seam, the edge of a flap, a zip)."))
    d: str = Field(description=(
        "The part as an SVG path in the drawing's coordinates: for inlay and mark its closed outline, for stitch and "
        "line the line itself. Only absolute M, L, Q, C and Z commands, every point written x,y."))
    color: str | None = Field(description=(
        "Its colour as #rrggbb; null for the garment's own cloth (stitching: the usual thread; line: the drawing's own "
        "line colour)."))
    clip: bool = Field(description="True when the garment's edge cuts it off (a panel running out to the edge).")


class Adding(BaseModel):
    parts: list[Part] = Field(description=(
        "Every part to draw over the drawing, in the order they are painted (later over earlier): the ones drawn before "
        "kept exactly as they were unless the note changes them, and the new ones."))
    said: str = Field(description=(
        "One or two plain sentences to the owner: what you drew, and anything the note asks that cannot be drawn this "
        "way or that the photo shows otherwise."))


class Checked(BaseModel):
    good: bool = Field(description="True when the drawing after shows what the note asks, where and as the photo "
                                   "shows it, with nothing else changed, and nothing automatic was found.")
    parts: list[Part] | None = Field(default=None, description=(
        "Null when good. Otherwise every part again, fixed, in painting order."))
    said: str = Field(default="", description=(
        "Empty when good. Otherwise the sentence to the owner again, as it now stands."))


@dataclass
class Result:
    """What came back: the parts to keep (read, `drawing.added`), what to tell the owner, and what it took."""
    parts: list[added.Added]
    said: str
    checks: int = 0
    route: str = ""
    model: str = MODEL
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    api_usd: float = 0.0       # what the calls cost, or would have cost on the API key
    seconds: float = 0.0
    left_out: list[str] = field(default_factory=list)   # parts that could not be read, and why


def clean_note(note) -> str:
    """The owner's line, on one line. Raises `ValueError` with a plain sentence when it is empty or too long."""
    text = " ".join(note.split()) if isinstance(note, str) else ""
    if not text:
        raise ValueError("Write what to add to the drawing, for example “a small red patch on the left sleeve”.")
    if len(text) > NOTE_MAX:
        raise ValueError(f"Keep it to {NOTE_MAX} characters or fewer: one thing to add or change.")
    return text


def off_garment(outline: str, parts: list[added.Added]) -> list[str]:
    """The parts not cut by the garment's edge that reach more than OFF_BY past it, in words for the check."""
    poly = points(outline)
    out = []
    for i, p in enumerate(parts, 1):
        if p.clip or not poly:
            continue
        pts = points(p.d)
        far = [q for q in pts if signed_distance(q, poly) < -OFF_BY]   # negative: outside
        if far and len(far) >= max(1, len(pts) // 5):
            out.append(f"part {i} ({p.what or p.role}) reaches past the garment's edge; if it is on the garment, "
                       "keep it inside, or set clip")
    return out


def _parts_json(parts: list[added.Added]) -> str:
    return json.dumps([p.as_json() for p in parts], ensure_ascii=False)


def _notes_text(notes: list[str]) -> str:
    kept = [n for n in notes if isinstance(n, str) and n.strip()][-NOTES_SENT:]
    return "\n".join(f"- “{n}”" for n in kept) if kept else "(none)"


RULES = """How to draw:
- The drawing is a flat, simple drawing of the garment, its front facing you as in the photo: the wearer's left is on your right. When the owner says left or right they most likely mean the wearer's; where the photo shows the thing, put it where the photo shows it, and read their left or right by that.
- Coordinates: x from 0 at the drawing's left to 400 at its right, y from the top down. The grid on the drawing is in these coordinates: a faint line every 10, a stronger one every 50, numbered along the top and the left.
- Draw only what the note asks, and what must come with it (a patch's stitching, a pocket's flap). Keep every part drawn before exactly as it was, with the same numbers, unless the note changes it; a note that takes something away removes its parts.
- You cannot change, move or remove the drawing's own shapes (the outline, the collar, the sleeves, its pockets and seams). If the note asks for that, draw nothing for it and say in `said` that it is changed in Fix the details, under Change the details one by one.
- Think of the garment as a 3D object, flattened into this view. Something on a sleeve lies along the sleeve, turned with it, at least 3 units inside its edges. Something on the back or inside cannot be seen from the front: say so and do not draw it.
- Size things by the garment, not by the photo: the drawing is not the photo's size. Place each part by the garment's landmarks (the neck, the shoulder points, the armholes, the hem, the placket, a pocket), as far from them as the photo shows.
- Colours from the photo, as #rrggbb.
- Keep each part on the garment, inside its outline, unless it really hangs off it (a tag, a drawstring's end); a panel that runs out to the edge sets clip.
- Flat shapes, as the rest of the drawing: no shading, no gradients, no fine detail. Letters and words are not drawn here: say they are given in “What's wrong with it?” in Fix the details. A logo that is a picture is drawn as its simple shape in its colours.
- Before drawing, check in the photo each thing the note says or takes for granted (where it is, on which side, how many, its colour and size). If the photo shows otherwise, draw it as the owner asks and say so in one sentence in `said`.
- At most 30 parts; each path at most 120 points."""


def draw_prompt(note: str, notes: list[str], geometry: str, now: list[added.Added], photo: bool) -> str:
    seen = ("The image photo.png is the item, with its background removed." if photo else
            "There is no photo of the item to look at: draw from the note alone, and say so if it matters.")
    return f"""The owner of this garment asks you to add to its drawing:
“{note}”

Their earlier lines about this drawing, which made what was drawn on it before:
{_notes_text(notes)}

{seen} The image drawing.png is the garment's drawing as it is now, with a grid.

The drawing's shape:
{geometry}

What was drawn onto the drawing before (keep each exactly, unless the note changes it):
{_parts_json(now) if now else "(nothing)"}

{RULES}"""


def check_prompt(note: str, geometry: str, parts: list[added.Added], said: str, problems: list[str], photo: bool) -> str:
    seen = "photo.png is the item, with its background removed; " if photo else "There is no photo; "
    found = "\n".join(f"- {p}" for p in problems) if problems else "(nothing)"
    return f"""You drew onto a garment's drawing what its owner asked:
“{note}”

{seen}before.png is the drawing before, and after.png the drawing with the parts below, both with a grid in the drawing's coordinates.

The parts as drawn:
{_parts_json(parts) if parts else "(none)"}

What you told the owner: “{said}”

What the automatic checks found:
{found}

The drawing's shape:
{geometry}

Check after.png against the note and the photo: is each new part there, on the right part of the garment, on the side and at the place the photo shows, the right size and colour? Did anything drawn before change that the note does not change? Say good only when all is right and the automatic checks found nothing. Otherwise give every part again, fixed, and the sentence to the owner as it now stands. Never undo or weaken what the owner asked for.

{RULES}"""


def _png(svg: str) -> Image.Image:
    import io
    return Image.open(io.BytesIO(drawn.render_png(added.gridded(svg), RENDER_PX))).convert("RGB")


def _on_white(photo: Image.Image) -> Image.Image:
    if photo.mode in ("RGBA", "LA"):
        ground = Image.new("RGB", photo.size, (255, 255, 255))
        ground.paste(photo, mask=photo.getchannel("A"))
        return ground
    return photo.convert("RGB")


def add(note: str, notes: list[str], photo: Image.Image | None, now: list[added.Added], geometry: str, outline: str,
        render: Callable[[list[added.Added]], str], routes: tuple[str, ...], client=None, exe=None,
        meter=None) -> Result:
    """Draw the note onto the drawing, then check it once. `render(parts)` is the item's drawing with those parts laid
    over it (the template's own drawing under them); `now` is what is drawn onto it already, `notes` the owner's
    earlier lines. Raises `CapReached` or `RouteUnavailable` (from `correcting.ask`) when Claude cannot be reached, and
    `ValueError` when nothing it answered can be drawn."""
    started = time.monotonic()
    out = Result([], "")
    images = ([_on_white(photo)] if photo is not None else [])
    names = (["photo.png"] if photo is not None else [])
    before = _png(render(now))

    def ask(text: str, pics: list[Image.Image], pic_names: list[str], model_shape):
        r = correcting.ask(text, pics, routes, client=client, exe=exe, meter=meter, answer_model=model_shape,
                           system=SYSTEM, model=MODEL, names=pic_names, max_tokens=MAX_TOKENS, timeout=TIMEOUT,
                           effort=EFFORT)
        out.route, out.model = r.route, r.model
        out.input_tokens += r.input_tokens
        out.output_tokens += r.output_tokens
        out.cache_read_tokens += r.cache_read_tokens
        out.cache_write_tokens += r.cache_write_tokens
        plain = max(0, r.input_tokens - r.cache_read_tokens - r.cache_write_tokens)
        out.api_usd += cost_usd(r.model, plain, r.output_tokens, r.cache_write_tokens, r.cache_read_tokens)
        return r.answer

    answer = ask(draw_prompt(note, notes, geometry, now, photo is not None), images + [before], names + ["drawing.png"],
                 Adding)
    parts, why = added.read([p.model_dump() for p in answer.parts])
    said = " ".join((answer.said or "").split())
    for _ in range(CHECKS):
        problems = why + off_garment(outline, parts)
        after = _png(render(parts))
        checked = ask(check_prompt(note, geometry, parts, said, problems, photo is not None),
                      images + [before, after], names + ["before.png", "after.png"], Checked)
        out.checks += 1
        if checked.good or checked.parts is None:
            break
        fixed, fixed_why = added.read([p.model_dump() for p in checked.parts])
        if fixed or not checked.parts:
            parts, why = fixed, fixed_why
            said = " ".join((checked.said or said).split())
    if answer.parts and not parts:
        raise ValueError("nothing Claude drew could be read: " + "; ".join(why))
    out.parts, out.said, out.left_out = parts, said, why
    out.seconds = time.monotonic() - started
    return out
