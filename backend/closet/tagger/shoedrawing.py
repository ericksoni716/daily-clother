"""A shoe drawn by Claude from its photos, as flat clip art for the outfit figure (shoes drawn from understanding,
step C).

One drawing is one draw call and at most three check calls, through the same routes and the same monthly limit as
describing an item (`correcting.ask`, purpose `draw_shoe`), on the model of the `drawing` role in `models.json`:

1. **Draw**: Claude is shown the shoe's photos, each named with the view it was sorted into (`closet/shoeviews.py`),
   and the three drawings the owner liked as worked examples (their SVG text and renders of them on legs). It names
   the kind of shoe first, writes a feature sheet (kind, silhouette, proportions, 2 to 6 true colours, parts, what
   makes it recognisable from the front, where its opening is) and draws one shoe, toes straight at the viewer, in a
   fixed frame (`closet/drawing/drawn.py`), in two parts: what is behind the leg and what is in front of it (step D);
   a second drawing for the other foot only when a mark is on one side only.
2. **Check**: it is shown the photos again and a render of its drawing on two legs, large and at phone size
   (`drawn.check_png`), with its sheet, its SVG and what the automatic checks found (`drawn.checks`). It compares the
   drawing with the photos and either says it is good or gives the drawing fixed. This stops as soon as it says good
   and the automatic checks find nothing, and after three checks in any case. On the API route, a check whose
   drawing would be thrown away if it says good stops being read once it does (`_good_as_is`): the request is the
   same, only the copy of the drawing that follows is not waited for.

3. **Correct** (step E, `correct`): the owner's one-line note on a drawing. Claude is shown the photos, the drawing
   as it is (its render, sheet and SVG), the owner's earlier notes and the new note, and changes only what the note
   asks and what must change with it (purpose `correct_drawing`). Then at most two checks compare the change with the
   PHOTOS and with the drawing before it: they fix anything else the change broke, never undo the owner's change, and
   say in one plain sentence when the note asks for something the photos do not show (`against_photos`): it is
   drawn as asked all the same. A drawing kept as version 1 (all in front of the leg) comes back as version 2.

4. **The side** (`draw_side`, and beside the turns in `draw`): the shoe drawn exactly side-on, toe to the left, on the
   templates' card, as the item's own drawing (the closet tile, the item page): one draw call and at most two checks,
   with the front drawing's sheet so both agree, the app's plain template drawings as examples of the style only,
   proportions written down from the side photo before drawing (or measured from the shoe's trace and checked:
   `closet/drawing/drawnside.py`), and a short list of what makes the shoe itself from the side.

Every drawing is made safe (`drawn.sanitise`) before it is rendered, checked or kept. A check call that fails keeps
the drawing made so far: it was paid for, and it is still a drawing of the shoe. The owner's notes are passed to a
later drawing from scratch ("Draw again") and to its checks, so they are not lost. The brief below is the
experiment's (`bench/experiments/shoe_drawn/BRIEF3.md`, `ARCH.md` and `CORRECT.md`, now in the git history) with the owner's decisions since,
in one prompt for a model that can do nothing but look at the images.
"""
from __future__ import annotations

import io
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from ..drawing import drawn, drawnside, photocheck, turned
from . import correcting
from .tagging import CONFIG, Meter, RouteUnavailable, TaggingError, cost_usd
from .views import shown

log = logging.getLogger("closet.shoedrawing")

MODEL = CONFIG["roles"]["drawing"]
EFFORT = "medium"      # the owner's choice after comparing high, medium and Sonnet (16 November): see DECISIONS.md
MAX_TOKENS = 32_000    # the longest answer a call allows on the API route, its thinking included (streamed)
TIMEOUT = 600          # seconds one call through the plan may take
MAX_ROUNDS = 3         # check calls at most, after a drawing (straight on, or turned)
CANDIDATES = 2         # straight-on drawings made side by side, of which the judge keeps one (the owner's choice
                       # over three, 17 November 2026: see DECISIONS.md)
TURNS = 2              # turns of the kept drawing made side by side, of which the judge keeps one
CALLS_AT_ONCE = 2      # calls one drawing makes at the same time, the side's included: two, as before the side, so two
                       # shoes drawn at once (`shoedraw.AT_ONCE`) never run more than four Claude Code processes on the
                       # plan (see DECISIONS.md, "A shoe's side drawn by Claude")
FIX_NOTE_MAX = 900     # the judge's faults on the kept turn, given back as a note to fix
MAX_CORRECT_ROUNDS = 2 # check calls at most, after a correction from the owner's note
NOTE_MAX = 200         # the owner's note on a drawing, in characters
NOTES_SENT = 20        # the owner's latest notes passed on to Claude with a drawing or a correction
SENTENCE_MAX = 300     # what Claude says changed, or that the note goes against the photos, as kept and shown
SYSTEM = ("You draw one shoe from the owner's wardrobe as flat clip art for a private wardrobe app. Look at every "
          "image file named in the request with the Read tool, then answer in the required JSON format. Do nothing "
          "else.")

# How each sorted view is named to Claude (`tagger/views.py`'s VIEWS); None: not sorted.
VIEW_WORDS = {"outer": "the outer side", "inner": "the inner side", "top": "from above",
              "front": "the front (toe towards the camera)", "back": "the back (heel towards the camera)",
              "sole": "the sole", "other": "a detail or another view", None: "a view that is not known"}
OTHER_SIDE = {"outer": "inner", "inner": "outer"}


# ------------------------------------------------------------------ the answer

class Colour(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(description="A plain name for the colour, such as 'gum brown' or 'off-white leather'.")
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$", description="The colour as #rrggbb, as it truly is (not as lit).")
    role: str = Field(description="What is this colour: 'upper', 'sole', 'laces', 'toe piece', ...")


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    part: str = Field(description="The part, such as 'toe cap', 'eyelet stays', 'midsole', 'elastic side panel'.")
    colour: str = Field(description="Its colour, by its name in the palette.")
    where: str = Field(description="Where it is on the shoe, in a few words.")
    seen_from_front: bool = Field(description="True when it shows from the front and a little above.")


class Silhouette(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    toe: str = Field(description="round, almond, pointed, square or wide.")
    bulk: str = Field(description="slim, regular or chunky.")
    height: Literal["low", "low_profile", "ankle", "boot"] = Field(
        description="low (a sneaker, a derby, an oxford); low_profile (a boat shoe, a loafer, a ballet flat, a "
                    "slipper, a driving moc: lower and narrower); ankle (an ankle boot, a chukka); boot (taller).")
    sole: str = Field(description="thin, medium or thick; and flat, wedge, rocker, heeled or lug.")


class Sheet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str = Field(description="What it is; the model or style family if you recognise it, and how sure you are.")
    archetype: str = Field(description="The most specific kind of shoe a footwear designer would call it.")
    archetype_front: str = Field(description="Three or four sentences: how that kind of shoe looks from the front and "
                                             "a little above: its outline, how the sole relates to the upper, where "
                                             "its bulk is.")
    silhouette: Silhouette
    proportions: str = Field(description="By eye, from the photos from the front and from above: how thick the sole's "
                                         "front edge is against the toe box above it; whether the sole stands out "
                                         "past the upper and by how much; how the toe's outline runs from above.")
    palette: list[Colour] = Field(min_length=2, max_length=6, description="The shoe's 2 to 6 true colours.")
    parts: list[Part]
    signature: list[str] = Field(min_length=2, max_length=4,
                                 description="The 2 to 4 things that make it recognisable from the front at small "
                                             "size.")
    one_side_mark: bool = Field(description="True when a logo, stripe or panel is on one side of the shoe only.")
    front_pull_tab: bool = Field(default=False,
                                 description="True when the shoe has a pull tab or loop at the FRONT of its collar or "
                                             "shaft (many pull-on boots have one at the front and one at the back): "
                                             "it is drawn in the front part, centred on the leg, and may rise above "
                                             "the opening.")
    opening_front_y: float = Field(ge=-200, le=240,
                                   description="In the drawing: the height (y) where the shoe's front first covers "
                                               "the middle of the leg (x 100): the tongue top or the collar's front "
                                               "for a low shoe, the shaft's top edge at the front for a boot (not a "
                                               "pull tab at the front above it).")
    top_y: float = Field(ge=-200, le=240,
                         description="In the drawing: the height (y) of the back of its opening: the top of the "
                                     "collar's back for a low shoe, the top of the shaft at the back for a boot (not a "
                                     "pull tab above it).")
    instep_y: float = Field(ge=-200, le=240,
                            description="In the drawing: for a boot, the height (y) where the shaft meets the instep; "
                                        "for a low shoe, just above its opening's front (a little smaller y).")


class Shoe(BaseModel):
    """One shoe of the drawing, in its two parts: the app draws `behind`, then the leg over it, then `front`."""
    model_config = ConfigDict(extra="forbid", strict=True)
    behind: str = Field(description="What of the shoe is BEHIND the leg, seen from the front: the back of the collar "
                                    "or of a boot's shaft where it shows beside the leg, a pull tab or loop at the back, "
                                    "the lining seen inside the opening. Bare SVG elements in the frame; an empty "
                                    "string when nothing behind the leg shows.")
    front: str = Field(description="Everything else, in front of the leg: bare SVG elements in the frame, nothing "
                                   "around them.")


class DrawAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sheet: Sheet
    left: Shoe = Field(description="The viewer's left shoe, behind and in front of the leg.")
    right: Shoe | None = Field(description="Only when one_side_mark is true: the viewer's right shoe, drawn on its "
                                           "own in the same frame, behind and in front of the leg; otherwise null.")


class CheckAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    good: bool = Field(description="True only when the drawing is right as it is and no automatic problem is left.")
    problems: list[str] = Field(description="What was wrong and is fixed in this answer, in short plain sentences; "
                                            "empty when good.")
    sheet: Sheet
    left: Shoe = Field(description="The viewer's left shoe as it should be, behind and in front of the leg (the same "
                                   "drawing when good).")
    right: Shoe | None = Field(description="The viewer's right shoe when one_side_mark is true; otherwise null.")


class CorrectAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    changed: str = Field(description="What you changed, in one short plain sentence for the owner, such as 'The "
                                     "elastic side panels are wider.'")
    against_photos: str | None = Field(description="null; or, only when the note asks for something the photos do not "
                                                   "show, one short plain sentence for the owner saying so, such as "
                                                   "'The photos show the toe rubber lower than your note asks; drawn "
                                                   "as you asked.'")
    sheet: Sheet
    left: Shoe = Field(description="The viewer's left shoe, changed as the note asks, behind and in front of the leg.")
    right: Shoe | None = Field(description="The viewer's right shoe when one_side_mark is true; otherwise null.")


class CorrectCheckAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    good: bool = Field(description="True only when the change is right as it is and no automatic problem is left.")
    problems: list[str] = Field(description="What was wrong and is fixed in this answer, in short plain sentences; "
                                            "empty when good.")
    against_photos: str | None = Field(description="null; or, only when the owner's note asks for something the photos "
                                                   "do not show, one short plain sentence for the owner saying so, "
                                                   "such as 'The photos show the toe rubber lower than your note asks; "
                                                   "drawn as you asked.'")
    sheet: Sheet
    left: Shoe = Field(description="The viewer's left shoe as it should be, behind and in front of the leg (the same "
                                   "drawing when good).")
    right: Shoe | None = Field(description="The viewer's right shoe when one_side_mark is true; otherwise null.")


# The same forms for a drawing turned out (`turned`): what was "seen from the front" is seen in this view.
IN_VIEW = (f"in this view (from in front and a little above, the foot turned out {turned.TURN:g} degrees, the toe, the "
           "vamp and the inner side showing)")


class TurnedPart(Part):
    seen_from_front: bool = Field(description=f"True when it shows {IN_VIEW}.")


class TurnedSheet(Sheet):
    archetype_front: str = Field(description=f"Three or four sentences: how that kind of shoe looks {IN_VIEW}: its "
                                             "outline, how the sole relates to the upper, where its bulk is.")
    parts: list[TurnedPart]
    signature: list[str] = Field(min_length=2, max_length=4,
                                 description=f"The 2 to 4 things that make it recognisable {IN_VIEW} at small size.")


class TurnedDrawAnswer(DrawAnswer):
    sheet: TurnedSheet


class TurnedCheckAnswer(CheckAnswer):
    sheet: TurnedSheet


class TurnedCorrectAnswer(CorrectAnswer):
    sheet: TurnedSheet


class TurnedCorrectCheckAnswer(CorrectCheckAnswer):
    sheet: TurnedSheet


class Verdict(BaseModel):
    """The judge's answer: which of several drawings of the shoe is most faithful to its photos."""
    model_config = ConfigDict(extra="forbid", strict=True)
    observations: str = Field(description="First, from the photos alone: what the judging turns on (each panel of the "
                                          "shoe's front and sides, its colour, its shape and where its edges meet the "
                                          "others; each mark). Plain sentences.")
    faults: list[str] = Field(description="For each candidate, in order A, B, C, ...: one line '<letter>: ...' naming "
                                          "every place where it differs from the photos, or '<letter>: none'.")
    best: str = Field(description="The letter of the candidate that matches the photos best.")
    ranking: list[str] = Field(description="All letters, best first.")


# ------------------------------------------------------------------ the prompts

BRIEF = """## The frame (about 17 units to a centimetre)
- x 0 to 200, centred on x = 100; the shoe at most about 180 wide. The ground is y = 240: the sole's lowest point.
- The app draws the part of your shoe behind the leg first, then a leg (x 62 to 138, in a sock) over it, then the part in front of the leg over that, so the leg goes into the shoe.
- A low shoe (a sneaker, a derby, an oxford): the whole shoe sits between about y = 40 and y = 240, and its tongue top or collar front crosses the leg at about y = 40 to 60. The liked examples are about as tall as they are wide: do not make a low shoe taller.
- A low-profile shoe (a boat shoe, a loafer, a ballet flat, a slipper, a driving moc) sits lower and narrower: its vamp or collar front at about y = 75 to 90, and about 145 wide, so trousers long enough to just touch an ordinary sneaker leave the sock showing above it.
- An ankle boot: the toe box and instep fill about y = 110 to 240, and the shaft rises behind them to a top edge at about y = -30 to -50 (a chukka's at about y = 0), a little wider than the leg and narrower than the toe box. A taller boot's top stays below y = -90.

## The view: a 3D object, flattened
ONE shoe, the viewer's left, its toe pointing straight at the viewer, seen from the front and a little above. Do not tilt it or turn the toe out, and do not thicken its lines: the app turns the toes out and matches the line weight itself.
The toe is nearest the viewer, so it is the lowest and the largest thing in the picture. Everything further back sits higher and is partly hidden by what is in front of it:
- at the bottom, the sole's front edge: a band that follows the toe's outline;
- above it, the TOE BOX: its front face and its top surface, a broad dome. This is the biggest shape;
- above that, the vamp and the lacing (or the plain instep) sloping up and away, getting narrower;
- then the tongue top or the collar's front edge, where the leg goes in;
- a boot is NOT a tube: it is the same toe box and instep in front, with the shaft rising BEHIND them, narrower than the toe box, starting where the instep meets the leg. From the front you see the toe box below and the shaft above, with a clear break (the instep's slope, a crease or seam line) between them.

## The opening: the leg goes INTO the shoe
Draw the opening's front edge as a curve dipping across the leg, and bring the collar's (or shaft's) sides up a little higher at each side of the leg than in the middle, so the leg sits IN the shoe. From just below that front edge down to the sole, the shoe covers the leg completely. Nothing in front of the leg covers its middle higher than about 25 units above the opening's front edge (for a boot, the front of the shaft's top), for any kind of shoe, except a pull tab at the front (below).

## Behind the leg and in front of it: two parts
The shoe is a 3D object round the foot, so seen from the front some of it is BEHIND the leg. Give each shoe in two parts:
- behind: what is behind the leg: the back of the collar or of a boot's shaft where it shows beside the leg, a pull tab or loop at the back, the lining seen inside the opening. The app draws it first, so the leg covers it wherever the leg is in front. Leave it empty ("") when nothing behind the leg shows (the three liked drawings have nothing behind the leg).
- front: everything else, the whole shoe in front of the leg, built as below. Never put a part that is at the back of the shoe (a heel pull tab, the back of the collar) in front: drawn over the leg it would hide the leg and sock.
- A pull tab or loop at the FRONT of the collar or shaft (many pull-on boots have one at the front and one at the back: look at the side photos) is in front of the leg: draw it in the front part, centred on the leg, narrow (at most about 26 units wide), rising no more than about 60 units above the opening's front edge, and set front_pull_tab true. The one at the back goes in the behind part.

## How to build it (the order the liked examples use)
1. The sole's front edge: one crescent band along the bottom, in the sole's colour, with the bold outline.
2. The upper's whole silhouette on top of it, in the main colour, with the bold outline.
3. The few panels of another colour, each one closed shape with a thin outline, lying inside the silhouette.
4. The seams that define the shoe (a toe cap line, a moccasin seam, a boot's instep seam): thin lines.
5. The tongue and the lacing, last, in front of the leg.
6. The upper's bold outline once more over everything.

## Style (strict)
- Flat fills in the palette's hex values. No gradients, shadows, textures or highlights. No lettering: draw a letter-shaped logo as a shape, so the letter reads the right way round.
- Bold outline: stroke #26221f, stroke-width 4, stroke-linejoin round. Inner lines: stroke-width 1.6.
- Few shapes: draw a detail only if it shows from the front AND helps someone recognise the shoe.
- Keep to what the photos show. The sole's front edge is as thick as it looks from the front, no thicker. A sole stands out past the upper only as far as it does from above. Outsole rubber climbs the toe only as far as the front shows it.
- It must still read at 45 pixels tall.
- Use only these elements: g, path, circle, ellipse, rect, line, polyline, polygon; and only these attributes: d, cx, cy, r, rx, ry, x, y, width, height, x1, y1, x2, y2, points, fill, stroke, stroke-width, stroke-linejoin, stroke-linecap, stroke-dasharray, stroke-opacity, fill-opacity, opacity, fill-rule, transform (translate, scale, rotate or matrix). Colours as #rrggbb or none. No ids, no style attributes, no text, no comments, no defs, no url(). Anything else is removed before the drawing is shown.

## Left and right
In the left drawing (the viewer's left shoe), the shoe's outer side is the side nearer x = 0. Only when a logo, stripe or panel is on one side of the shoe only (one_side_mark), also draw the viewer's right shoe, on its own in the same frame (x 0 to 200, centred on 100): its outer side is the side nearer x = 200, its mark on that side and reading the right way round, not a mirror image. Otherwise give no right drawing: the app mirrors the left one.

## Where it is (in the sheet, in the drawing's own y)
- opening_front_y: where the shoe's front first covers the middle of the leg (x 100): the tongue top or the collar's front for a low shoe; the shaft's top edge at the front for a boot.
- top_y: the back of the opening: the top of the collar's back for a low shoe, the top of the shaft at the back for a boot (not a pull tab above it). Cropped trousers stop above it.
- instep_y: for a boot, where the shaft meets the instep; for a low shoe, just above its opening's front."""


def photo_names(count: int) -> list[str]:
    return [f"photo-{n}.jpg" for n in range(1, count + 1)]


EXAMPLE_NAMES = [f"example-{name}.png" for name in drawn.EXAMPLES]


def view_words(view: str | None, sure: bool | None) -> str:
    """How a photo's view is named to Claude: a side Claude was not sure of is named as unsure."""
    words = VIEW_WORDS.get(view, VIEW_WORDS[None])
    if view in OTHER_SIDE and sure is False:
        return f"{words}, or possibly the {OTHER_SIDE[view]} side (not sure which)"
    if view is not None and sure is False:
        return f"probably {words} (not sure)"
    return words


def photo_lines(photos: list[Photo]) -> str:
    return "\n".join(f"- Photo {n} ({name}): {view_words(p.view, p.sure)}."
                     for n, (p, name) in enumerate(zip(photos, photo_names(len(photos)), strict=True), 1))


def _example_text(name: str) -> str:
    return re.sub(r'\s+id="[^"]*"', "", drawn.example(name)).strip()


def _note_lines(notes: Sequence[str]) -> str:
    return "\n".join(f"- \"{n}\"" for n in list(notes)[-NOTES_SENT:])


def notes_section(notes: Sequence[str]) -> str:
    """The owner's notes on earlier drawings of the shoe, for a drawing or its check; empty when there are none."""
    if not notes:
        return ""
    lines = _note_lines(notes)
    return f"""

## The owner's notes on earlier drawings of this shoe
The owner corrected earlier drawings of this shoe with these notes. They are the owner's word: keep to them, even where the photos seem to show otherwise.
{lines}"""


OWN_PHOTOS = ("The three drawings show how to draw, not what this shoe looks like: its panels, their sizes, their shapes "
              "and their colours come from its own photos, even when it is the same kind of shoe as one of them.")
RUNNER = """## A running shoe
A running shoe's character is its midsole. Read its profile from the side photos before you draw:
- how thick the midsole is under the heel and under the ball (thicker at the heel: the drop), and how it flares out wider than the upper at the heel and under the forefoot, so the upper sits down IN it;
- the rocker: the sole's bottom curves up from under the ball to the toe, so the toe tip is lifted off the ground; where the front photo shows the toe's underside (the outsole, often a darker rubber) as a crescent under the toe tip, it shows in the drawing too;
- the midsole's top edge, where the upper sits, climbs round the toe and at the heel, cupping the foot;
- marks on the midsole (a stripe, a wave of colour) follow its curve.
Draw the midsole as one big shape that does all of this, and the upper slim and low on top of it."""
SHARES = """## How much of the front each colour covers
Before drawing, look at the front photo (and the photo from above) and note, for each colour, how much of the shoe's front it covers and where: for example "grey suede: the toe, the lacing area and the sides up to the collar, about two thirds; white leather: two small wedges either side above the toe; gum: the sole". The drawing's colours cover the same shares in the same places. A shoe made of one material under overlays of another is drawn as the photos show it, not as it is built: when overlays cover most of the front, most of the drawing is the overlays' colour, and the colour underneath shows only where the photo shows it."""
SIDE_MARKS = """## Marks on the sides
A logo, stripe or panel on the side of the shoe shows from the front only where the side shows: as a thin sliver along the outline, about as much as the front photo shows, at its true place along the shoe. A logo on the middle of the side shows, if at all, only at the outline beside the back of the vamp, never on the toe box. Never bring a side mark round to the front."""
SHARE_QUESTION = "Does each colour cover the same share of the front, in the same places, as in the front photo? "


def _straight_extra(style: str | None) -> str:
    """The sections added to the straight-on prompts: a running shoe's midsole (when the item is one), how much of
    the front each colour covers, and where marks on the sides show."""
    return (RUNNER + "\n\n" if style == "runner" else "") + SHARES + "\n\n" + SIDE_MARKS + "\n\n"


def draw_prompt(photos: list[Photo], notes: Sequence[str] = (), style: str | None = None) -> str:
    examples = "\n\n".join(f"{label} ({png}):\n{_example_text(name)}"
                           for name, png, label in zip(drawn.EXAMPLES, EXAMPLE_NAMES,
                                                       ("A sneaker", "A tan cap-toe dress shoe",
                                                        "A boat shoe, a low-profile shoe"), strict=True))
    return f"""Draw one shoe from the owner's wardrobe as flat clip art, from its photos, for the drawn figure that shows the owner's outfits.

## The photos of the shoe
{photo_lines(photos)}
Ignore dirt, wear, shade, highlights, the floor and the background.{notes_section(notes)}

## Three drawings the owner liked
The images {", ".join(EXAMPLE_NAMES)} show them on two legs in socks, large and at phone size (the app draws the lines thicker than written, as it will on the figure), and their SVG is below (each is all in front of the leg: nothing of them shows behind it). Look at how few shapes they use and in what order. They are examples of the STYLE and the CONSTRUCTION, not of this shoe: do not copy their shapes. {OWN_PHOTOS}

{examples}

## First: the kind of shoe
Name the most specific kind of shoe a footwear designer would call it (for example "max-cushion running shoe with a thick foam midsole", "plain-toe chukka", "court sneaker"), and write how THAT KIND of shoe looks from the front and a little above, from what you know: its outline, how the sole relates to the upper, where its bulk is. Draw that kind's front silhouette first, then fit it to this shoe: its colours, parts and proportions from the photos. The silhouette should be the kind's, corrected by the photos, never a generic rounded blob. Keep the toe box broad but not bulbous: check its outline against the photo from above.

## Then the feature sheet, from the photos
kind, archetype and archetype_front (above); silhouette; proportions; palette: the shoe's 2 to 6 TRUE colours, one material one colour; parts; signature: the 2 to 4 things that make it recognisable from the FRONT at small size; one_side_mark; and where the drawing's opening, top and instep are.

{_straight_extra(style)}## Then the drawing
{BRIEF}

Answer with the sheet, the left shoe as its two parts, behind and front, each bare SVG elements (no <svg> around them), and the right shoe the same way or null."""


def _shoe_text(shoe: drawn.Side) -> str:
    return f"behind the leg:\n{shoe.behind or '(empty)'}\nin front of the leg:\n{shoe.front}"


def _found(problems: list[str]) -> str:
    return "\n".join(f"- {p}" for p in problems) if problems else "- none"


def _right_text(right: drawn.Side | None) -> str:
    return _shoe_text(right) if right else "null (the app mirrors the left drawing for the other foot)"


def check_prompt(photos: list[Photo], sheet: dict, left: drawn.Side, right: drawn.Side | None,
                 problems: list[str], notes: Sequence[str] = (), style: str | None = None) -> str:
    """The check of a straight-on drawing: also how much of the front each colour covers."""
    p = _check_text(photos, sheet, left, right, problems, notes, BRIEF)
    return (p.replace("Is the toe box the biggest, nearest shape?", SHARE_QUESTION + "Is the toe box the biggest, nearest "
                      "shape?", 1).replace("The rules the drawing follows:", _straight_extra(style) + "The rules the "
                                           "drawing follows:", 1))


def _check_text(photos: list[Photo], sheet: dict, left: drawn.Side, right: drawn.Side | None,
                problems: list[str], notes: Sequence[str], brief: str) -> str:
    found, right_text = _found(problems), _right_text(right)
    return f"""You drew this shoe from its photos as flat clip art for the drawn figure that shows the owner's outfits. Now check the drawing against the PHOTOS, not only against your sheet, and fix it if it needs it.

## The photos of the shoe
{photo_lines(photos)}{notes_section(notes)}

## Your drawing
drawing.png shows it on two legs in socks, large and at phone size, with its lines drawn thicker than written, as the app will draw them on the figure (do not thin them to make up for it): each shoe's part behind the leg first, then the leg, then its part in front. Its sheet:
{json.dumps(sheet, indent=1)}

The left shoe, {_shoe_text(left)}

The right shoe, {right_text}

## What the automatic checks found (each must be fixed)
{found}

## Look
Compare drawing.png with the photos. Is it the same kind of shoe, with the same silhouette, proportions and true colours? Is the toe box the biggest, nearest shape? Is the sole no thicker and no wider than the photos show? Does the leg go into the opening, with whatever is at the back of the shoe behind the leg and not over it? Does it have the simplicity of a few flat shapes? Would a stranger name the same shoe from the photos and from the drawing, at phone size too?

If it is right and the automatic checks found nothing, say good, with no problems, and give the drawing and the sheet back unchanged. Otherwise say what was wrong in problems and give the drawing fixed: change what is wrong and what must change with it, and keep everything else as it is (the same shapes where possible). Correct the sheet too where it was wrong, and keep its opening_front_y, top_y and instep_y true to the drawing.

The rules the drawing follows:
{brief}"""


# ------------------------------------------------------------------ the turned view

def turned_brief(style: str, a: float = turned.TURN) -> str:
    """The rules for a drawing turned out `a` degrees, for a shoe of `style` (`turned.STYLES`): the wide frame, the view,
    the guide's lines (an ordinary shoe of the style, from the 3D solid), what shows from the nearest part to the
    furthest, the straight-on brief's opening and two parts, building on the surfaces, the style, left and right, and
    where the opening is."""
    words = turned.WORDS[style]
    frame = """## The frame (about 16 units to a centimetre)
- x -100 to 300. The leg is at x 62 to 138, centred on x = 100. The ground is y = 240: the sole's lowest point, under the toe.
- The app draws the part of your shoe behind the leg first, then a leg (in a sock) over it, then the part in front of the leg over that, so the leg goes into the shoe.
- The guide below gives the shoe's size and place for its kind: fit it to the photos.
- Nothing goes left of x -98 or right of x 298."""
    view = f"""## The view: turned out {a:g} degrees, seen from in front and a little above
ONE shoe: the viewer's left one, the wearer's RIGHT foot. The camera is in front of the wearer and a little above; the foot is turned out {a:g} degrees, as a man stands: the toe points towards the viewer and a little to the viewer's LEFT, and the heel is behind the leg.

## The guide: draw ON it
guide.png is the true shape of an ordinary {words} in exactly this view and this frame, made from a 3D model of a shoe, with the leg (x 62 to 138) as a pale band. Its lines, in the frame's coordinates:
{turned.guide_text(style, a)}
Use it as your underdrawing. Your sole band, your upper's silhouette, your opening and your lacing's centre line keep the guide's perspective. Change them only where the photos show this shoe differs from an ordinary {words} (a longer, rounder or squarer toe; a thicker or thinner sole; a higher or lower collar; a chunkier or slimmer shape), and only by that difference. Never flatten what the guide shows rising: the heel is further away than the toe, so everything along the inner side climbs towards the heel.

## What you see, from the nearest part to the furthest
- The sole: one band along the bottom, deepest under the toe. It curves round the toe and runs back along the inner side, climbing steeply towards the heel (as the guide's does) until the leg hides it; on the outer side (the left) only its edge shows.
- The toe box: the nearest, lowest and largest shape, at the lower left. Its top is a broad dome that rolls round into the inner side with no edge or corner between them.
- The inner side (the arch side): a narrow strip of the upper above the sole, on the right, climbing with the sole towards the heel. Panels, overlays, logos, stripes and elastic that are on the inner side show here, narrowed by the turn and sloping with the strip, as they wrap round the shoe; draw them as the inner side photo has them (as the outer side has them when there is no inner photo).
- The vamp and the lacing (or the plain instep): up and back from the toe box along the guide's centre line. The lacing follows that line: its rows are square to it, not to the page, and get shorter and closer together further back.
- The opening, round the leg at the top: its front edge (the tongue top or the collar's front) crosses the leg; the collar's back and the heel counter are behind the leg, so they go in the part behind it.
- The heel: the furthest part, on the right, mostly behind the leg. Its outline is the guide's: down from the collar and round into the sole, with no sharp corner where the collar or the sole meets it.
The turn is about the vertical, so nothing leans: a boot's shaft stands upright round the leg. Do not tilt it and do not thicken its lines: the app does not turn it any further and matches the line weight itself."""
    rest = BRIEF[BRIEF.index("## The opening"):BRIEF.index("## How to build it")].strip()
    build = """## How to build it
1. The sole band: the guide's, fitted to the photos' thickness, in the sole's colour, with the bold outline.
2. The upper's whole silhouette on top of it: the guide's, fitted to the photos, in the main colour, with the bold outline.
3. The few panels of another colour, each one closed shape with a thin outline, lying ON the surfaces they cover (the toe box's dome, the inner side's strip, the vamp), so their edges curve and slope with those surfaces: a toe cap's seam is a curve across the dome; a side panel is a band that narrows and climbs with the strip.
4. The seams that define the shoe (a toe cap line, a moccasin seam, a boot's instep seam): thin lines, on the surfaces too.
5. The tongue and the lacing, last, in front of the leg, along the centre line.
6. The upper's bold outline once more over everything."""
    style_rules = (BRIEF[BRIEF.index("## Style (strict)"):BRIEF.index("## Left and right")].strip()
                   .replace("draw a detail only if it shows from the front AND", "draw a detail only if it shows in this view AND")
                   .replace("The sole's front edge is as thick as it looks from the front, no thicker.",
                            "The sole's edge is as thick as it looks in the photos, no thicker.")
                   .replace("Outsole rubber climbs the toe only as far as the front shows it.",
                            "Outsole rubber climbs the toe and the side only as far as the photos show it."))
    left_right = f"""## Left and right
The app mirrors the left drawing for the other foot, which turns its toe out the other way with its inner side towards the viewer too: right for most shoes. Only when a mark would read the wrong way round mirrored (a letter-shaped logo) or the two shoes differ, also draw the viewer's right shoe on its own (the wearer's LEFT foot), in the same frame: its toe turned {a:g} degrees to the viewer's RIGHT (towards x 300), its inner side face running from the toe box back along the lower LEFT of the shoe, its heel and collar back to the LEFT of the leg, and every mark reading the right way round. Set one_side_mark true exactly when you give a right drawing."""
    where = BRIEF[BRIEF.index("## Where it is"):].strip()
    return "\n\n".join([frame, view, rest, build, style_rules, left_right, where])


RUNNER_TURNED = """
- On the inner side's strip, the midsole shows its profile: thickest at the heel, thinning to the ball, then curving up to the lifted toe, flaring out past the upper, with its marks following its curve."""


def turn_prompt(photos: list[Photo], sheet: Mapping, left: drawn.Side, right: drawn.Side | None, style: str,
                notes: Sequence[str] = (), a: float = turned.TURN) -> str:
    """Turning the straight-on drawing: the details are the computed turn's (turned.png), the outline is drawn by eye,
    and the inner side that comes into view is drawn from its photo."""
    words = turned.WORDS[style]
    fr, md = turned.inner_region(style, a, 0.65, 0.92), turned.inner_region(style, a)
    runner = RUNNER_TURNED if style == "runner" else ""
    runner_section = (RUNNER + "\n\n") if style == "runner" else ""
    return f"""You drew this shoe from its photos as flat clip art, straight on (straight.png). Now draw it turned out {a:g} degrees, as a man stands, for the drawn figure that shows the owner's outfits. You have two references for the turn.

- turned.png (its SVG is below) is your straight-on drawing turned by the app with a 3D model of a shoe. Its DETAILS are exactly right: every seam, panel edge, lacing row, stitch line, logo and stripe is where it goes on the turned shoe, tilted as it turns.
- Its OUTLINES are not right, and must not be copied. An outline is not drawn on the shoe: it is where the shoe's surface turns away from you, so when the shoe turns, a different part of the surface becomes the outline. Turned as if painted on, the outline comes out squashed into a straight edge on the outer side (the left), with the inner side (the right) left open, where the leg shows through.

## The photos of the shoe
{photo_lines(photos)}
Ignore dirt, wear, shade, highlights, the floor and the background.{notes_section(notes)}

## The turned drawing (its details are right, its outlines are not)
Its sheet (from the straight-on drawing):
{_sheet_text(sheet)}

The left shoe, {_shoe_text(left)}

The right shoe, {_right_text(right)}

## How to draw it
1. The outline is yours. Draw the upper's silhouette and the sole band's outer edge as the real shoe turned {a:g} degrees looks, by eye, as you would turn your straight-on drawing yourself: smooth, and round wherever the shoe is round; the toe box still a broad dome, as wide as in straight.png (the shoe gets wider only by the inner side that comes into view); the toe moved down and to the left as in turned.png; the inner side closing the shoe on the right, climbing towards the heel, as guide.png's right panel shows for an ordinary {words}. From just below the opening down to the sole, the shoe covers the leg completely.
2. The details are turned.png's. Copy every seam, panel, lacing row, stitch line, logo and stripe from its SVG, with the same coordinates and tilts. Where a detail or a panel reaches the outline, trim or extend it to meet your outline; a panel whose edge is partly the outline (a toe cap, the sole band, a side panel) keeps turned.png's seams and takes your outline for its outer edge.
3. On the inner side that comes into view, draw what the inner side photo shows there (panels, overlays, logos, stripes, elastic, the midsole's marks), narrowed and sloping with the strip; shapes that wrap onto it continue in the same colour with no new seam.
4. Add nothing the photos do not show: every panel and mark you draw is one you can point to in a photo, in the same place.
5. What of the inner side shows, from a 3D model of an ordinary {words} turned this way: its FRONT third (from the ball forward, beside the toe box) shows as a band about {fr[2]-fr[0]:.0f} units wide, at about x {fr[0]:.0f} to {fr[2]:.0f}, y {fr[1]:.0f} to {fr[3]:.0f}; its MIDDLE third only as a sliver about {md[2]-md[0]:.0f} units wide at the edge, x {md[0]:.0f} to {md[2]:.0f}; its back third is hidden. Draw on each part what the inner side photo shows there. The shoe's SIGNATURE marks on the inner side (its logo, the main panel or stripe that makes it recognisable) are drawn a little more than this strict view shows, as an illustrator would, so they still read: a logo in the middle of the side shows as its front part, narrowed to about 16 units wide, at the edge of the band nearest the heel (about x {md[0]-12:.0f} to {md[2]:.0f}), cut by the outline and reading the right way round; a panel or stripe that runs along the side shows across the band, narrowed and sloping with it. Other marks keep the strict view's size. A side mark that straight.png or turned.png shows on the toe box or at the front of the shoe is in the wrong place: leave it out there. In a right drawing (the other foot), the inner side is on the LEFT: mirror these x values (x becomes 200 - x).{runner}
- On the inner side the sole's edge shows as a band below and beside the upper, climbing steeply towards the heel, as guide.png's right panel shows. Its top end, at the heel, is rounded and curves back behind the upper. The upper's own outline on the inner side stays one smooth curve from the toe box up to the collar: never step the outline out sideways to meet the sole, and never leave a notch, corner or lump where the two meet.
- The back of the collar and a pull tab at the back are behind the leg: they go in the part behind it. A boot's shaft stands upright round the leg.
- Give the sheet back for the turned drawing: one_side_mark, opening_front_y, top_y and instep_y true to it.

{runner_section}## The rules the drawing follows
{turned_brief(style, a)}

Answer with the sheet, the left shoe as its two parts, behind and front, each bare SVG elements (no <svg> around them), and the right shoe the same way or null."""


def turned_check_prompt(photos: list[Photo], sheet: dict, left: drawn.Side, right: drawn.Side | None,
                        problems: list[str], style: str, notes: Sequence[str] = (), a: float = turned.TURN) -> str:
    """The check of a turned drawing, against straight.png, turned.png and the photos."""
    p = _check_text(photos, sheet, left, right, problems, notes, turned_brief(style, a))
    first = p.split("\n", 1)[0]
    p = p.replace(first, f"You turned your straight-on drawing of this shoe (straight.png) out {a:g} degrees: the outline "
                         "drawn by eye, smooth and round, and the details placed as turned.png (turned by a 3D model) places "
                         "them. Now check the drawing against turned.png and the PHOTOS, and fix it if it needs it: the "
                         "details keep turned.png's places and tilts; the outline is smooth and round, not turned.png's "
                         "squashed one; the toe box is as wide as in straight.png; the inner side shows what the inner side "
                         "photo shows, and nothing is drawn that the photos do not show; the shoe covers the leg below the "
                         "opening.", 1)
    return p.replace("Is the toe box the biggest, nearest shape?",
                     f"Is the shoe turned out {a:g} degrees (the toe box at the lower left, the inner side showing as a "
                     "foreshortened side face), not pointing straight at the viewer? Is the toe box the biggest, nearest "
                     "shape? Do the inner side's panels and marks match the photos?", 1)


# ------------------------------------------------------------------ the judge

JUDGE_SYSTEM = ("You compare drawings of a shoe with its photos. Look at every image file named in the request with the "
                "Read tool, then answer in the required JSON format. Do nothing else.")
SIDE_RULE = ("A logo or mark in the middle of the shoe's side shows from the front only as a thin sliver at the outline, "
             "or not at all; a candidate that draws a side logo on the toe box or the front is wrong there. ")
LETTERS = "abcdefgh"


def candidate_names(n: int) -> list[str]:
    return [f"candidate-{LETTERS[i]}.png" for i in range(n)]


def judge_prompt(photos: list[Photo], n: int, turned_view: bool = False, a: float = turned.TURN,
                 notes: Sequence[str] = ()) -> str:
    """Which of `n` drawings (candidate-a.png, ...) is most faithful to the photos: straight-on drawings, or turned ones
    (then straight.png, the chosen straight-on drawing, is shown too). `notes`: the owner's notes on earlier drawings
    of the shoe, which a candidate is right to follow."""
    named = ", ".join(photo_names(len(photos)))
    cands = ", ".join(candidate_names(n))
    if turned_view:
        head = f"""These are photos of one shoe ({named}), its drawing as flat clip art straight on (straight.png, already checked against the photos), and {n} candidate drawings of the same shoe turned out {a:g} degrees, as a man stands ({cands} for candidates {", ".join(LETTERS[:n].upper())}; each shows the pair on two legs, large and at phone size).

Turned, the shoe should keep every panel, colour and detail of straight.png, moved with the turn, with smooth, rounded outlines; and the inner side that comes into view on the right of the viewer's left shoe (on the left of the right shoe) should show what the inner side photo shows there, at its true place along the shoe and narrowed by the turn, with nothing added that the photos do not show. {SIDE_RULE}Which candidate does this best? Judge faithfulness and cleanness (no stray shapes, slivers, spikes, gaps or lumps), not style. First describe what the inner side shows in the photos; then list each candidate's faults; then choose."""
    else:
        head = f"""These are photos of one shoe ({named}) and {n} candidate drawings of it as flat clip art seen from the front and a little above ({cands} for candidates {", ".join(LETTERS[:n].upper())}; each shows the pair on two legs, large and at phone size).

Which candidate is most faithful to the photos: the same panels, in the same colours, with the same shapes and the same edges where they meet, the same marks, in the same places, as they would show from the front? {SIDE_RULE}Judge faithfulness to THIS shoe, not drawing quality or style. First describe the shoe's panels from the photos alone; then list each candidate's faults; then choose."""
    owner = ""
    if notes:
        owner = f"""

## The owner's notes on earlier drawings of this shoe
The owner corrected earlier drawings of this shoe with these notes. They are the owner's word: a candidate that keeps to them is right there, even where the photos seem to show otherwise, and one that goes against them has a fault.
{_note_lines(notes)}"""
    return f"""{head}

## The photos of the shoe
{photo_lines(photos)}{owner}"""


def _note_text(note: str) -> str:
    return f"\"{note}\""


def _earlier(notes: Sequence[str]) -> str:
    if not notes:
        return ""
    lines = _note_lines(notes)
    return f"""

## The owner's earlier notes on this shoe (still to be kept)
{lines}"""


def _sheet_text(sheet: Mapping) -> str:
    return json.dumps({k: v for k, v in sheet.items() if k != "owner_notes"}, indent=1)


def correct_prompt(photos: list[Photo], sheet: Mapping, left: drawn.Side, right: drawn.Side | None, note: str,
                   notes: Sequence[str] = (), whole: bool = False, brief: str | None = None) -> str:
    """The owner's one-line note on a drawing: change only what it asks. `whole`: the drawing was kept as version 1,
    all of it in front of the leg."""
    kept = ("\nThis drawing was kept before drawings had two parts, so all of it is given as in front of the leg. Give "
            "it back in the two parts, behind and front, as the rules below say; that alone is not a change.\n"
            if whole else "")
    return f"""The owner looked at your drawing of this shoe, as flat clip art for the drawn figure that shows the owner's outfits, and wrote a one-line note on what is wrong with it. Change the drawing as the note asks, starting from the drawing as it is.

## The owner's note
{_note_text(note)}{_earlier(notes)}

## The photos of the shoe
{photo_lines(photos)}
Ignore dirt, wear, shade, highlights, the floor and the background.

## The drawing as it is
drawing.png shows it on two legs in socks, large and at phone size, with its lines drawn thicker than written, as the app will draw them on the figure (do not thin them to make up for it): each shoe's part behind the leg first, then the leg, then its part in front. Its sheet:
{_sheet_text(sheet)}

The left shoe, {_shoe_text(left)}

The right shoe, {_right_text(right)}
{kept}
## Change ONLY what the note asks
- Start from the drawing as it is: copy its SVG and change only the shapes the note is about and whatever must change with them (a panel made wider moves the seam beside it). Keep every other shape as it is, with the same coordinates and colours, and keep to the owner's earlier notes.
- First check, in every photo (the side photos show both ends of the shoe), each thing the note says or takes for granted about the shoe: where a part is (at the front or the back, on which side), how many there are, its colour, size and height. A note can be wrong about the shoe: a part can be at both ends or on one side only, a sole's rubber can climb higher at one side.
- Then draw it as the note asks. The note is the owner's word: if it asks for something the photos do not show, or takes for granted something the photos show otherwise (a part higher, larger, in another place, one part where there are two, another colour), still draw it as the owner asks, and say so in against_photos in one short plain sentence to the owner naming what the photos show, such as "The side photos show the stripes on the outer side only; drawn as you asked." Otherwise against_photos is null.
- Copy the sheet, changing only what the note changes (a colour, a part, a signature, or opening_front_y, top_y and instep_y when the drawing's opening moves).
- changed: what you changed, in one short plain sentence for the owner, such as "The elastic side panels are wider."

## The rules the drawing follows
{brief or BRIEF}

Answer with changed, against_photos, the sheet, the left shoe as its two parts, behind and front, each bare SVG elements (no <svg> around them), and the right shoe the same way or null."""


def correct_check_prompt(photos: list[Photo], sheet: Mapping, left: drawn.Side, right: drawn.Side | None,
                         problems: list[str], note: str, notes: Sequence[str] = (), brief: str | None = None) -> str:
    """A check of a drawing changed from the owner's note, against the photos and the drawing before the change."""
    return f"""You changed your drawing of this shoe as the owner's one-line note asked. Now check the change against the PHOTOS, not only against the note, and fix it if it needs it.

## The owner's note
{_note_text(note)}{_earlier(notes)}

## The photos of the shoe
{photo_lines(photos)}

## The drawing before the note, and after it
before.png shows the drawing as it was before the note, and drawing.png as it is now, each on two legs in socks, large and at phone size, with its lines drawn thicker than written, as the app will draw them on the figure (do not thin them to make up for it): each shoe's part behind the leg first, then the leg, then its part in front. The drawing now, its sheet:
{_sheet_text(sheet)}

The left shoe, {_shoe_text(left)}

The right shoe, {_right_text(right)}

## What the automatic checks found (each must be fixed)
{_found(problems)}

## Look
Compare drawing.png with before.png and with the photos.
- The owner's change stays. The note is the owner's word: never undo it or weaken it, even where the photos look different.
- Nothing else changes. Anything the note did not ask for that differs from before.png, or that the change broke (a shape moved or lost, a colour changed, the leg no longer going into the opening, something at the back of the shoe drawn over the leg), is put back as it was in before.png.
- Against the photos: is it still the same kind of shoe, with the same silhouette, proportions and true colours, at phone size too?
- Check the note itself against every photo (the side photos show both ends of the shoe): where the part it is about really is, how many there are, its colour, size and height. A note can be wrong about the shoe.
- against_photos: when the note asks for something the photos do not show, or takes for granted something the photos show otherwise, say so in one short plain sentence to the owner naming what the photos show, such as "The side photos show the stripes on the outer side only; drawn as you asked."; otherwise null.

If it is right and the automatic checks found nothing, say good, with no problems, and give the drawing and the sheet back unchanged. Otherwise say what was wrong in problems and give the drawing fixed: change what is wrong and keep everything else as it is. Keep the sheet's opening_front_y, top_y and instep_y true to the drawing.

The rules the drawing follows:
{brief or BRIEF}"""


# ------------------------------------------------------------------ the calls

@dataclass
class Photo:
    """One photo of the shoe, as sent: the image, the view it was sorted into and whether that was sure."""
    image: Image.Image
    view: str | None = None
    sure: bool | None = None


@dataclass
class Call:
    kind: str           # "draw" or "check"
    route: str
    model: str
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cost_usd: float     # what the API key would charge for it
    seconds: float
    cache_write_tokens: int = 0   # of input_tokens, those written to the prompt cache (the API route)
    cut_short: bool = False       # a check whose answer stopped being read once it said good (`_good_as_is`):
                                  # output_tokens is then an estimate that errs high (`correcting.cut_output`)


@dataclass
class Drawn:
    """A finished drawing: the left and right shoes (sanitised, each behind and in front of the leg), the sheet, how
    many checks were made, the calls with their tokens and what the API key would charge, the seconds it all took,
    whether the last check said good and what the automatic checks still find."""
    left: drawn.Side
    right: drawn.Side | None
    sheet: dict
    rounds: int
    seconds: float
    calls: list[Call] = field(default_factory=list)
    good: bool = False
    problems: list[str] = field(default_factory=list)
    view: str = drawn.FRONT.name           # "turned": drawn turned out, as the figure shows it
    style: str | None = None              # the 3D solid it was turned with (`turned.STYLES`)
    straight: dict | None = None          # the straight-on drawing it was turned from: {left, right, sheet}
    side: Sided | None = None             # the shoe drawn from its side (`draw_side`), when it could be made

    @property
    def route(self) -> str:
        return self.calls[0].route if self.calls else ""

    def totals(self) -> dict:
        return {"input_tokens": sum(c.input_tokens for c in self.calls),
                "cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
                "output_tokens": sum(c.output_tokens for c in self.calls),
                "cost_usd": round(sum(c.cost_usd for c in self.calls), 6)}

    def to_json(self, photo_ids: list[str], made_at: str, notes: Sequence[Mapping] = ()) -> dict:
        """As kept with the item (`items.drawn`): version 3, its view, each shoe {behind, front}. `notes`: the owner's notes on
        the drawing it replaces (`notes_of`), carried on so a later drawing keeps to them; they are also the sheet's
        `owner_notes`. `side`: the side drawing made with it (`Sided.to_json`), or None; its calls are among `calls` and
        in the totals."""
        notes = [dict(n) for n in notes]
        sheet = {**self.sheet, "owner_notes": [n["note"] for n in notes]} if notes else self.sheet
        return {"version": drawn.VERSION, "view": self.view, "style": self.style, "straight": self.straight,
                "left": self.left.to_json(),
                "right": self.right.to_json() if self.right else None, "sheet": sheet, "rounds": self.rounds,
                "seconds": round(self.seconds, 1), "good": self.good, "problems": self.problems,
                "calls": [{**asdict(c), "cost_usd": round(c.cost_usd, 6), "seconds": round(c.seconds, 1)}
                          for c in self.calls],
                **self.totals(), "route": self.route, "made_at": made_at, "photo_ids": list(photo_ids),
                "notes": notes, "side": self.side.to_json(made_at) if self.side else None}


@dataclass
class Corrected(Drawn):
    """A drawing changed from the owner's note: as `Drawn` (its calls, seconds and cost are this change's), with the
    note, what Claude says changed, and, when the note asks for something the photos do not show, one plain sentence
    saying so (`against_photos`; it is drawn as asked all the same)."""
    note: str = ""
    changed: str | None = None
    against_photos: str | None = None

    def to_json(self, photo_ids: list[str], made_at: str, notes: Sequence[Mapping] = ()) -> dict:
        """As `Drawn.to_json`, with this change's note added to the notes as {note, at, against_photos, changed} and
        `corrected`: this drawing is the one before it changed from that note."""
        entry = {"note": self.note, "at": made_at, "against_photos": self.against_photos, "changed": self.changed}
        return {**super().to_json(photo_ids, made_at, [*notes, entry]), "corrected": True}


def notes_of(kept) -> list[dict]:
    """The owner's notes on a drawing kept with the item, oldest first: {note, at, against_photos, changed}."""
    notes = kept.get("notes") if isinstance(kept, Mapping) else None
    if not isinstance(notes, list):
        return []
    return [{"note": n["note"], "at": n.get("at"), "against_photos": n.get("against_photos"),
             "changed": n.get("changed")} for n in notes
            if isinstance(n, Mapping) and isinstance(n.get("note"), str) and n["note"].strip()]


def clean_note(note) -> str:
    """The owner's note on one line. Raises `ValueError` with a plain sentence when it is empty or too long."""
    text = " ".join(str(note or "").split()) if isinstance(note, str) else ""
    if not text:
        raise ValueError("Write what is wrong with the drawing, for example “the elastic sides should be wider”.")
    if len(text) > NOTE_MAX:
        raise ValueError(f"Keep the note to {NOTE_MAX} characters or fewer: it says one thing to change.")
    return text


def _sentence(text) -> str | None:
    """What Claude said in one plain sentence, on one line and not too long; None when it said nothing."""
    if not isinstance(text, str):
        return None
    t = " ".join(text.split())
    if not t or t.strip(".").lower() in ("null", "none", "n/a"):
        return None
    return t if len(t) <= SENTENCE_MAX else t[:SENTENCE_MAX - 1].rstrip() + "…"


def api_cost(model: str, input_tokens: int, cache_read_tokens: int, output_tokens: int) -> float:
    """What the API key would charge for a call made through the plan, at the prices in `models.json`. The API
    route sends everything once; through the plan, Claude Code reads its earlier context again from its cache on each
    step (`cache_read_tokens`), which the API route would not do, so those are left out."""
    return cost_usd(model, max(0, input_tokens - cache_read_tokens), output_tokens)


def _png(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as im:
        return im.convert("RGB")


def _drawing(answer) -> tuple[drawn.Side, drawn.Side | None]:
    return drawn.side(answer.left.model_dump()), drawn.side(answer.right.model_dump()) if answer.right else None


Asker = Callable[..., correcting.CorrectionResult]


def _caller(routes: tuple[str, ...], client, exe: str | None, meter: Meter | None, asker: Asker,
            clock: Callable[[], float], calls: list[Call], cache_photos: int = 0):
    """One call to Claude on the drawing model, recorded in `calls` with its tokens, cost and seconds. `cache_photos`:
    every call's images start with the shoe's photos, this many: on the API route the request is cached up to the
    last of them, so each later call reads them back from the cache."""
    def ask(kind: str, text: str, images: list[Image.Image], image_names: list[str], answer_model,
            cut_short: correcting.CutShort | None = None):
        t = clock()
        extra = {"cut_short": cut_short} if cut_short is not None else {}
        result = asker(text, images, routes, client=client, exe=exe, meter=meter, answer_model=answer_model,
                       system=SYSTEM, model=MODEL, names=image_names, max_tokens=MAX_TOKENS, timeout=TIMEOUT,
                       effort=EFFORT, cache_photos=cache_photos, **extra)
        cached = getattr(result, "cache_read_tokens", 0) or 0
        written = getattr(result, "cache_write_tokens", 0) or 0
        if result.route == "api":   # what it cost, the cache's writes and reads at their own prices
            cost = cost_usd(result.model, max(0, result.input_tokens - cached - written), result.output_tokens,
                            written, cached)
        else:
            cost = api_cost(result.model, result.input_tokens, cached, result.output_tokens)
        calls.append(Call(kind, result.route, result.model, result.input_tokens, cached, result.output_tokens, cost,
                          clock() - t, written, bool(getattr(result, "cut_short", False))))
        return result.answer
    return ask


@dataclass
class _Checked:
    left: drawn.Side
    right: drawn.Side | None
    sheet: dict
    rounds: int
    good: bool
    problems: list[str]
    answers: list = field(default_factory=list)   # each check's answer, in turn


def _good_as_is(answer_model, left: drawn.Side, right: drawn.Side | None, sheet: dict) -> correcting.CutShort:
    """A check's answer may stop being read once it says good, when that answer's drawing would be thrown away
    anyway. In each check's schema, `good` and `problems` (and, in a check of a correction, `against_photos`) come
    before `sheet`, and structured output keeps the schema's order, so they are whole once `"sheet"` has started; what
    follows is the drawing written out again. When those fields say good, the answer is made of them and the drawing
    already held (`left`, `right`, `sheet`). Not good, a field missing or one more, or anything that does not fit the
    schema: None, and the answer is read to its end. Claude's own `problems` do not matter here, as they do not in
    `_check`: a good answer with no automatic problem ends the checks either way."""
    asked = set(answer_model.model_fields) - {"sheet", "left", "right"}

    def answer(fields: dict):
        if fields.get("good") is not True or set(fields) != asked:
            return None
        return answer_model.model_validate({**fields, "sheet": sheet, "left": left.to_json(),
                                            "right": right.to_json() if right else None})
    return correcting.CutShort("sheet", answer)


def _check(ask, left: drawn.Side, right: drawn.Side | None, sheet: dict, max_rounds: int,
           prompt: Callable[[dict, drawn.Side, drawn.Side | None, list[str]], str],
           images: Callable[[drawn.Side, drawn.Side | None], tuple[list[Image.Image], list[str]]],
           answer_model, checker: Callable[[drawn.Side, drawn.Side | None, dict], list[str]] = drawn.checks,
           ) -> _Checked:
    """The check rounds: each shows Claude the drawing and what the automatic checks (`checker`) found, and takes its
    fix. They stop as soon as Claude says good and the automatic checks find nothing, and after `max_rounds` in any
    case. A check that fails keeps the drawing so far; a fix that cannot be used is set aside and the drawing before it
    is checked again. When the automatic checks found nothing and no fix was set aside, a good answer's drawing would
    be thrown away, so its reading stops once it says good (`_good_as_is`; the API route only)."""
    problems, note = checker(left, right, sheet), []
    rounds, good, answers = 0, False, []
    while rounds < max_rounds:
        shots, names = images(left, right)
        try:
            cut = _good_as_is(answer_model, left, right, sheet) if not problems and not note else None
            answer = ask("check", prompt(sheet, left, right, problems + note), shots, names, answer_model, cut_short=cut)
        except TaggingError as e:   # Claude out of reach, or no usable answer: the drawing so far is kept
            log.info("checking a shoe's drawing stopped after %s rounds: %s", rounds, type(e).__name__)
            break
        rounds += 1
        answers.append(answer)
        if answer.good and not problems:
            good = True
            break
        try:
            left, right = _drawing(answer)
            sheet, note = answer.sheet.model_dump(), []
            problems = checker(left, right, sheet)
        except drawn.DrawingError as e:   # the fix cannot be used: the drawing before it is checked again
            note = [f"The drawing you gave last could not be used ({e}) This is the drawing before it: fix it again, "
                    "or say good if it needs nothing."]
    return _Checked(left, right, sheet, rounds, good, problems, answers)


def style_of(sheet: Mapping, hint: str | None = None) -> str | None:
    """The shoe style whose 3D solid turns the drawing (`turned.STYLES`): the item's own (`hint`, from its
    description) when it has one, else read from the drawing's sheet. None for a sandal: it is kept straight on."""
    if hint == "sandal":
        return None
    if hint in turned.STYLES:
        return hint
    text = " ".join(str(sheet.get(k) or "") for k in ("kind", "archetype")).lower()
    height = ((sheet.get("silhouette") or {}) if isinstance(sheet.get("silhouette"), Mapping) else {}).get("height")
    if any(w in text for w in ("sandal", "slide", "flip-flop", "flip flop")):
        return None
    if height in ("ankle", "boot"):
        return "chelsea_boot" if any(w in text for w in ("chelsea", "elastic", "gusset", "gore", "pull-on")) else "boot"
    if height == "low_profile":
        return "loafer"
    if any(w in text for w in ("running", "runner", "jogging")):
        return "runner"
    if any(w in text for w in ("derby", "blucher")):
        return "derby"
    if any(w in text for w in ("oxford", "balmoral", "brogue", "wingtip", "cap-toe", "dress shoe")):
        return "oxford"
    if any(w in text for w in ("high-top", "high top", "hi-top")):
        return "high_top"
    if any(w in text for w in ("slip-on", "slip on")):
        return "slip_on"
    return "low_sneaker"


def _kept_turn_checks(kept: Mapping, style: str):
    """A kept turned drawing's automatic checks, with its shaft measured against the turn of the straight-on drawing
    it was made from (`straight`); the turned view's own checks when that drawing cannot be read."""
    try:
        st = kept.get("straight") or {}
        sheet = st["sheet"]
        left = turned.turn_side(drawn.side(st["left"]), style, sheet)
        right = turned.turn_side(drawn.side(st["right"]), style, sheet, mirror=True) if st.get("right") else None
    except (KeyError, TypeError, drawn.DrawingError):
        return None
    return _upright_checks(_Computed(left, right, []), sheet)


def _measured_clean(made: list[_Checked]) -> list[int]:
    """Which drawings the judge may choose: those the automatic checks find nothing wrong with, when there are any;
    else all of them. A measured fault (off the ground, the leg hidden, the light material's share against the front
    photo, a boot's shaft leaning) is certain where the judge's eye is not; the judge still sees them all."""
    clean = [i for i, m in enumerate(made) if not m.problems]
    return clean or list(range(len(made)))


def _parallel(n: int, job: Callable[[int], object]) -> tuple[list, list[BaseException]]:
    """`job(0)` ... `job(n - 1)` side by side: what came back, in order (None where it failed), and what failed."""
    from concurrent.futures import ThreadPoolExecutor

    def run(i):
        try:
            return job(i), None
        except BaseException as e:   # recorded; whether it matters is the caller's to say
            return None, e
    if n == 1:
        got = [run(0)]
    else:
        with ThreadPoolExecutor(max_workers=n) as pool:
            got = list(pool.map(run, range(n)))
    return [g for g, _ in got], [e for _, e in got if e is not None]


def _judge(ask, photos: list[Photo], shots: list[Image.Image], names: list[str],
           cands: list[tuple[drawn.Side, drawn.Side | None]], view: drawn.View,
           straight: tuple[drawn.Side, drawn.Side | None] | None = None,
           notes: Sequence[str] = (), allowed: Sequence[int] | None = None) -> tuple[int, list[str]]:
    """Which candidate the judge finds most faithful to the photos (its index), and its faults in plain words. The
    judge sees them all; the choice is its best-ranked one among `allowed` (all, by default). The first allowed one,
    with no faults known, when there is one candidate or the judge cannot answer."""
    allowed = [i for i in (allowed if allowed is not None else range(len(cands))) if 0 <= i < len(cands)] or [0]
    if len(cands) == 1:
        return 0, []
    images = [_png(drawn.check_png(lf, rt, view)) for lf, rt in cands]
    extra, extra_names = [], []
    if straight is not None:
        extra, extra_names = [_png(drawn.check_png(*straight))], ["straight.png"]
    try:
        v = ask("judge", judge_prompt(photos, len(cands), turned_view=straight is not None, notes=notes),
                shots + extra + images, names + extra_names + candidate_names(len(cands)), Verdict)
    except TaggingError as e:   # Claude out of reach, or no usable answer: the first is kept
        log.info("judging a shoe's drawings stopped: %s", type(e).__name__)
        return allowed[0], []
    order = []
    for said in [v.best or ""] + list(v.ranking or []):
        letter = said.strip().lower()[:1]
        i = LETTERS.find(letter) if letter else -1
        if 0 <= i < len(cands) and i not in order:
            order.append(i)
    if not order:
        return allowed[0], []
    i = next((k for k in order if k in allowed), allowed[0])
    letter = LETTERS[i]
    faults = [f.split(":", 1)[1].strip() if ":" in f else f.strip() for f in v.faults
              if f.strip().lower().startswith(letter)]
    return i, [f for f in faults if f and f.strip(" .").lower() != "none"]


def _straight(ask, photos: list[Photo], shots: list[Image.Image], names: list[str], notes: Sequence[str],
              style: str | None, front: photocheck.FrontCheck | None) -> _Checked:
    """One straight-on drawing and its check rounds (the photo check, where it applies, among the automatic checks)."""
    examples = [_png(drawn.example_png(name)) for name in drawn.EXAMPLES]
    first = ask("draw", draw_prompt(photos, notes, style), shots + examples, names + EXAMPLE_NAMES, DrawAnswer)
    left, right = _drawing(first)

    def checker(lf, rt, sheet):
        return drawn.checks(lf, rt, sheet) + (front.problems(lf, sheet) if front is not None else [])
    return _check(ask, left, right, first.sheet.model_dump(), MAX_ROUNDS,
                  lambda sheet, lf, rt, found: check_prompt(photos, sheet, lf, rt, found, notes, style),
                  lambda lf, rt: (shots + [_png(drawn.check_png(lf, rt))], names + ["drawing.png"]), CheckAnswer, checker)


def _turned_checks(left, right, sheet):
    return drawn.checks(left, right, sheet, drawn.TURNED)


def _upright_checks(computed: _Computed, sheet: Mapping) -> Callable[[drawn.Side, drawn.Side | None, dict], list[str]]:
    """The turned view's automatic checks, and whether a boot's shaft stands where the computed turn leaves it
    (`turned.upright_problems`), against the straight-on drawing's sheet the turn was made with."""
    def check(left, right, found_sheet):
        found = _turned_checks(left, right, found_sheet) + turned.upright_problems(left, computed.left, sheet)
        if right is not None and computed.right is not None:
            found += turned.upright_problems(right, computed.right, sheet, which="right")
        return found
    return check


@dataclass
class _Computed:
    """The straight-on drawing turned by the 3D solid, and the pictures the turn is drawn from."""
    left: drawn.Side
    right: drawn.Side | None
    refs: list[Image.Image]


REF_NAMES = ["straight.png", "turned.png", "guide.png"]


def _computed(straight: _Checked, style: str) -> _Computed:
    left1 = turned.turn_side(straight.left, style, straight.sheet)
    right1 = turned.turn_side(straight.right, style, straight.sheet, mirror=True) if straight.right else None
    refs = [_png(drawn.check_png(straight.left, straight.right)), _png(drawn.check_png(left1, right1, drawn.TURNED)),
            _png(turned.guide_png(style))]
    return _Computed(left1, right1, refs)


def _turn(ask, photos: list[Photo], shots: list[Image.Image], names: list[str], notes: Sequence[str], style: str,
          straight: _Checked, computed: _Computed) -> _Checked:
    """The straight-on drawing turned out: the computed turn (`turned.turn_side`) shown as turned.png beside the
    straight-on drawing and the guide; Claude draws the outline and the inner side, then checks."""
    left1, right1, refs, ref_names = computed.left, computed.right, computed.refs, REF_NAMES
    first = ask("turn", turn_prompt(photos, straight.sheet, left1, right1, style, notes), shots + refs,
                names + ref_names, TurnedDrawAnswer)
    left, right = _drawing(first)
    return _check(ask, left, right, first.sheet.model_dump(), MAX_ROUNDS,
                  lambda sheet, lf, rt, found: turned_check_prompt(photos, sheet, lf, rt, found, style, notes),
                  lambda lf, rt: (shots + refs + [_png(drawn.check_png(lf, rt, drawn.TURNED))],
                                  names + ref_names + ["drawing.png"]), TurnedCheckAnswer,
                  _upright_checks(computed, straight.sheet))


def _correcting(ask, photos: list[Photo], shots: list[Image.Image], names: list[str], sheet: Mapping,
                left0: drawn.Side, right0: drawn.Side | None, note: str, earlier: Sequence[str], whole: bool,
                view: drawn.View, style: str | None, max_rounds: int, checker=None):
    """A drawing changed as `note` asks, then checked against the photos and the drawing before it: (the change's
    answer, the checks). In the turned view, with its brief and forms. `checker`: the automatic checks, when not the
    view's own."""
    turned_view = view is drawn.TURNED
    brief = turned_brief(style) if turned_view else None
    before = _png(drawn.check_png(left0, right0, view))
    first = ask("correct", correct_prompt(photos, sheet, left0, right0, note, earlier, whole, brief=brief),
                shots + [before], names + ["drawing.png"], TurnedCorrectAnswer if turned_view else CorrectAnswer)
    left, right = _drawing(first)
    done = _check(ask, left, right, first.sheet.model_dump(), max_rounds,
                  lambda sh, lf, rt, found: correct_check_prompt(photos, sh, lf, rt, found, note, earlier, brief=brief),
                  lambda lf, rt: (shots + [before, _png(drawn.check_png(lf, rt, view))],
                                  names + ["before.png", "drawing.png"]),
                  TurnedCorrectCheckAnswer if turned_view else CorrectCheckAnswer,
                  checker or (_turned_checks if turned_view else drawn.checks))
    return first, done


def draw_straight(photos: list[Photo], routes: tuple[str, ...], client=None, exe: str | None = None,
                  meter: Meter | None = None, asker: Asker = correcting.ask, clock: Callable[[], float] = time.monotonic,
                  notes: Sequence[str] = (), style: str | None = None, front: photocheck.FrontCheck | None = None) -> Drawn:
    """One straight-on drawing of the shoe and its checks, at most `MAX_ROUNDS` (one candidate of `draw`, kept straight
    on). Raises as `draw` does."""
    start = clock()
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    ask = _caller(routes, client, exe, meter, asker, clock, calls, cache_photos=len(shots))
    done = _straight(ask, photos, shots, names, list(notes), style, front)
    return Drawn(done.left, done.right, done.sheet, done.rounds, clock() - start, calls, done.good, done.problems)


def draw(photos: list[Photo], routes: tuple[str, ...], client=None, exe: str | None = None,
         meter: Meter | None = None, asker: Asker = correcting.ask, clock: Callable[[], float] = time.monotonic,
         notes: Sequence[str] = (), style: str | None = None, mask_of: photocheck.MaskOf | None = None,
         measures=None, side: bool = True) -> Drawn:
    """Draw the shoe from its photos (the main one first) as the figure shows it, turned out `turned.TURN` degrees.

    1. The photos are cut to the shoe (`photocheck.crop`, with the app's background model `mask_of` when there is
       one).
    2. CANDIDATES straight-on drawings are made side by side, each checked at most MAX_ROUNDS times (with the photo
       check, `photocheck.FrontCheck`, where it applies), and the judge keeps the one most faithful to the photos.
    3. TURNS turns of it are made side by side (`_turn`), and the judge keeps the best; its faults are given back as a
       note to fix (`_correcting`), and the fixed turn is kept only when the judge prefers it.
    4. At the same time as the turns, the shoe is drawn from its side (`_side`, with the chosen straight-on drawing's
       sheet, and `measures` from its trace when it has one), unless `side` is False. Its calls and the turns' share
       the drawing's `CALLS_AT_ONCE` places (`_limited`), so the drawing never has more than two calls under way. A side that fails, for whatever
       reason, is left out (`Drawn.side` None): it never costs the front drawing.

    `style`: the item's shoe style, from its description (`style_of` reads the sheet when there is none); a sandal is
    kept straight on. `notes`: the owner's notes on earlier drawings of the shoe, kept to throughout. Raises
    `RouteUnavailable` (or `CapReached`) when Claude cannot be reached for a drawing, `TaggingError` when no candidate
    gives a usable answer, `drawn.DrawingError` when none can be used. A turn or a fix that fails keeps what was made
    before it. `asker` stands in for `correcting.ask` (tests, the browser tests' stand-in)."""
    start = clock()
    photos = [Photo(photocheck.crop(p.image, mask_of), p.view, p.sure) for p in photos]
    front_photo = next((p for p in photos if p.view == "front" and p.sure is not False), None)
    front = photocheck.FrontCheck.of(front_photo.image, mask_of) if front_photo is not None else None
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    slots = threading.BoundedSemaphore(CALLS_AT_ONCE)
    ask = _limited(_caller(routes, client, exe, meter, asker, clock, calls, cache_photos=len(shots)), slots)
    notes = list(notes)

    made, failed = _parallel(CANDIDATES, lambda i: _straight(ask, photos, shots, names, notes, style, front))
    cands = [m for m in made if m is not None]
    if not cands:
        raise failed[0]
    i, _ = _judge(ask, photos, shots, names, [(c.left, c.right) for c in cands], drawn.FRONT, notes=notes,
                  allowed=_measured_clean(cands))
    straight = cands[i]
    rounds = sum(c.rounds for c in cands)
    side_calls: list[Call] = []
    wait_side = (_side_job(_limited(_caller(routes, client, exe, meter, asker, clock, side_calls,
                                            cache_photos=len(shots)), slots), side_calls, photos, shots, names, straight.sheet, notes, measures, clock)
                 if side else (lambda: None))
    try:
        made = _turned_or_straight(ask, photos, shots, names, notes, style, straight, rounds, start, clock, calls)
    finally:
        made_side = wait_side()   # also when the turns raised: the side's thread is never left running
        calls.extend(side_calls)   # paid for, kept or not
    made.side = made_side
    made.seconds = clock() - start
    return made


def _limited(ask, slots: threading.BoundedSemaphore):
    """`ask`, made to wait for one of a drawing's `CALLS_AT_ONCE` places before each call: the turns and the side then
    share two places, as the turns alone had them."""
    def limited(*args, **kwargs):
        with slots:
            return ask(*args, **kwargs)
    return limited


def _turned_or_straight(ask, photos: list[Photo], shots: list[Image.Image], names: list[str], notes: list[str],
                        style: str | None, straight: _Checked, rounds: int, start: float, clock, calls: list[Call]
                        ) -> Drawn:
    """`draw`'s step 3: the chosen straight-on drawing turned out and judged, or kept straight on (a sandal, a drawing
    too long to turn, turns that all failed). Raises `RouteUnavailable` when no turn could reach Claude."""
    kind = style_of(straight.sheet, style)
    if kind is None:   # a sandal: kept straight on
        return Drawn(straight.left, straight.right, straight.sheet, rounds, clock() - start, calls, straight.good,
                     straight.problems)
    try:
        computed = _computed(straight, kind)
    except drawn.DrawingError as e:   # too long to turn: kept straight on, which the figure turns itself
        log.info("turning a shoe's drawing failed (%s): kept straight on", e)
        return Drawn(straight.left, straight.right, straight.sheet, rounds, clock() - start, calls, straight.good,
                     straight.problems)
    turns, failed = _parallel(TURNS, lambda i: _turn(ask, photos, shots, names, notes, kind, straight, computed))
    turns = [t for t in turns if t is not None]
    if not turns:
        if any(isinstance(e, RouteUnavailable) for e in failed):
            raise next(e for e in failed if isinstance(e, RouteUnavailable))
        log.info("turning a shoe's drawing failed (%s): kept straight on", type(failed[0]).__name__)
        return Drawn(straight.left, straight.right, straight.sheet, rounds, clock() - start, calls, straight.good,
                     straight.problems)
    pair = (straight.left, straight.right)
    j, faults = _judge(ask, photos, shots, names, [(t.left, t.right) for t in turns], drawn.TURNED, straight=pair,
                       notes=notes, allowed=_measured_clean(turns))
    chosen = turns[j]
    rounds += sum(t.rounds for t in turns)
    if faults:
        note = ("Fix only these faults, found by comparing the turned drawing with the photos and with the drawing "
                "straight on: " + " ".join(faults))[:FIX_NOTE_MAX]
        try:
            _, fixed = _correcting(ask, photos, shots, names, chosen.sheet, chosen.left, chosen.right, note, notes,
                                   False, drawn.TURNED, kind, MAX_CORRECT_ROUNDS,
                                   checker=_upright_checks(computed, straight.sheet))
            rounds += fixed.rounds
            if fixed.problems and not chosen.problems:   # the fix broke what was measured right: the turn is kept
                raise drawn.DrawingError("the fix has automatic problems the turn before it had not")
            k, _ = _judge(ask, photos, shots, names, [(chosen.left, chosen.right), (fixed.left, fixed.right)],
                          drawn.TURNED, straight=pair, notes=notes)
            if k == 1:
                chosen = fixed
        except (TaggingError, drawn.DrawingError, RouteUnavailable) as e:   # the turn as it was is kept
            log.info("fixing a shoe's turned drawing stopped: %s", type(e).__name__)
    return Drawn(chosen.left, chosen.right, chosen.sheet, rounds, clock() - start, calls, chosen.good, chosen.problems,
                 view=drawn.TURNED.name, style=kind,
                 straight={"left": straight.left.to_json(), "right": straight.right.to_json() if straight.right else None,
                           "sheet": straight.sheet})


def correct(photos: list[Photo], kept: Mapping, note: str, routes: tuple[str, ...], client=None,
            exe: str | None = None, meter: Meter | None = None, asker: Asker = correcting.ask,
            clock: Callable[[], float] = time.monotonic) -> Corrected:
    """Change a drawing kept with the item (`kept`, as `items.drawn`: version 1, 2 or 3) as the owner's one-line
    `note` asks, then check the change against the photos and the drawing before it, at most `MAX_CORRECT_ROUNDS`
    times, in the drawing's own view (a turned drawing stays turned). The owner's earlier notes (`kept`'s notes) are
    kept to. Raises as `draw` does; `drawn.DrawingError` too when the drawing kept cannot be read."""
    if not isinstance(kept, Mapping) or not isinstance(kept.get("sheet"), Mapping):
        raise drawn.DrawingError("The drawing to change has no sheet.")
    note = clean_note(note)
    start = clock()
    left0 = drawn.side(kept.get("left"))
    right0 = drawn.side(kept["right"]) if kept.get("right") else None
    whole = isinstance(kept.get("left"), str)   # kept as version 1: all in front of the leg
    view = drawn.VIEWS.get(kept.get("view") or "front", drawn.FRONT)
    style = (kept.get("style") if kept.get("style") in turned.STYLES else style_of(kept["sheet"])) \
        if view is drawn.TURNED else None
    if view is drawn.TURNED and style is None:
        view = drawn.FRONT
    earlier = [n["note"] for n in notes_of(kept)]
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    ask = _caller(routes, client, exe, meter, asker, clock, calls, cache_photos=len(shots))
    first, done = _correcting(ask, photos, shots, names, kept["sheet"], left0, right0, note, earlier, whole, view, style,
                              MAX_CORRECT_ROUNDS, checker=_kept_turn_checks(kept, style) if view is drawn.TURNED else None)
    # the last check looked at the change beside the photos, so its word on them is the one kept
    against = _sentence(done.answers[-1].against_photos if done.answers else first.against_photos)
    return Corrected(done.left, done.right, done.sheet, done.rounds, clock() - start, calls, done.good, done.problems,
                     view=view.name, style=style, straight=kept.get("straight") if view is drawn.TURNED else None,
                     note=note, changed=_sentence(first.changed), against_photos=against)


# ------------------------------------------------------------------ the side (the item's own drawing)
#
# The shoe drawn from its side, as the closet tile, the Wardrobe's Drawings view and the item page show it, on the
# templates' card (`closet/drawing/drawnside.py`): one draw call and at most two check calls, through the same routes,
# model, effort, purpose and monthly limit as the front. It is drawn with the front drawing's sheet, so the two agree,
# and, when the shoe has a finished trace, with its proportions measured from the side photo (`drawnside.Measures`).

MAX_SIDE_ROUNDS = 2   # check calls at most, after a side drawing
FEATURES_MAX = 6      # what makes the shoe itself from the side, as kept and shown
FEATURE_MAX = 120     # one of them, in characters
SIDE_STYLE_NAMES = ["style-sneaker.png", "style-boot.png"]


class SideProportions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sole_heel: float = Field(ge=0, le=0.6, description="The sole's thickness under the heel, as a share of the shoe's "
                                                       "length (toe tip to back of heel).")
    sole_toe: float = Field(ge=0, le=0.6, description="The sole's thickness under the toe, as a share of the length.")
    toe_box: float = Field(ge=0, le=1.5, description="The upper's top above the ground at the toe box, 15% of the "
                                                     "length back from the toe tip, as a share of the length.")
    throat: float = Field(ge=0, le=1.5, description="The top above the ground at the throat, where the lacing or the "
                                                    "vamp meets the opening, as a share of the length.")
    collar_dip: float = Field(ge=0, le=1.5, description="The top above the ground at the collar's lowest point, as a "
                                                        "share of the length.")
    heel: float = Field(ge=0, le=1.5, description="The top above the ground at the heel (the collar's back, or a "
                                                  "boot's shaft), as a share of the length.")


class SideAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str = Field(description="The most specific kind of shoe a footwear designer would call it.")
    proportions: SideProportions = Field(description="Read from the side photo before drawing, its perspective "
                                                     "corrected (or the measures given, when there are any).")
    colours: list[Colour] = Field(min_length=2, max_length=6, description="The shoe's 2 to 6 true colours.")
    features: list[str] = Field(min_length=2, max_length=FEATURES_MAX,
                                description="What makes THIS shoe itself from the side and not just any shoe of its "
                                            "kind, one short plain line each, such as 'perforated toe box' or 'orange "
                                            "mark sweeping from the heel to under the lacing'.")
    svg: str = Field(description="The drawing: bare SVG elements in the frame, nothing around them.")


class SideCheckAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    good: bool = Field(description="True only when the drawing is right as it is and no automatic problem is left.")
    problems: list[str] = Field(description="What was wrong and is fixed in this answer, in short plain sentences; "
                                            "empty when good.")
    features: list[str] = Field(min_length=2, max_length=FEATURES_MAX,
                                description="What makes this shoe itself from the side, one short plain line each "
                                            "(the same when nothing about them changed).")
    svg: str = Field(description="The drawing as it should be (the same drawing when good): bare SVG elements.")


SIDE_BRIEF = f"""## The frame
- The drawing is bare SVG elements (no <svg> around them) on a card 400 wide and 460 tall. The app paints the card behind it: draw no background.
- The shoe is seen exactly side-on and level, its OUTER side towards you, the toe pointing LEFT, standing on the ground line y = {drawnside.GROUND:g} (the sole's lowest point).
- The toe tip is at x = {drawnside.TOE_X:g} and the back of the heel at x = {drawnside.HEEL_X:g}, whatever the photo's angle or direction: when the toe points right in the photo, draw it mirrored.
- The shoe's length is 320 units, so a height of a share s of its length is s × 320 units above the ground: a heel 0.3 of the length tall reaches y = 330 − 96 = 234. Nothing goes above y = {drawnside.TOP_MIN:g}.

## A 3D object, flattened
Think of the shoe as the solid object it is, then flatten it into this view: the sole under the whole foot, the upper's panels wrapped round it and overlapping each other in layers (toe cap or mudguard, vamp, eyestay, quarter, heel counter, collar), the tongue rising behind the lacing, the laces crossing between the eyelets on the near side. Correct the photo's perspective: a shoe photographed from a little in front or behind looks shorter and taller than it is, and one photographed from above looks flatter. Draw the true side view.

## How to build it
1. The sole: the outsole and the midsole as their own closed shapes, with their true thickness along the length (as measured), its toe spring, and the sidewall lines or tread edge that make the sole recognisable.
2. The upper's whole silhouette on top, in the main colour, with the toe as round and as high as the photo shows it: most toes are a blunt rounded curve, not a point.
3. Each panel of the upper as one closed shape with a thin outline where the photo shows it, even when it is the same colour as the upper: its seam is what one recognises.
4. Marks and logos as shapes, in their true place, size, outline and colours. No lettering: draw a letter-shaped logo as a shape, so it reads the right way round.
5. The lacing (as many eyelets as the photo shows), the tongue, perforations and stitching that defines a panel.
6. The bold outline of the whole shoe over everything.

## Style (strict)
- Flat fills in the colours' hex values. No gradients, shadows, textures or highlights.
- Bold outline: {drawnside.STYLE}; stroke-linejoin round.
- Smooth curves (C and Q path commands), not polygons. Draw a detail only where it helps someone recognise the shoe: it must still read at the size of a closet tile, 120 pixels wide.
- Use only these elements: g, path, circle, ellipse, rect, line, polyline, polygon; and only these attributes: d, cx, cy, r, rx, ry, x, y, width, height, x1, y1, x2, y2, points, fill, stroke, stroke-width, stroke-linejoin, stroke-linecap, stroke-dasharray, stroke-opacity, fill-opacity, opacity, fill-rule, transform (translate, scale, rotate or matrix). Colours as #rrggbb or none. No ids, no style attributes, no text, no comments, no defs, no clipPath, no url(). Anything else is removed before the drawing is shown."""


def _front_sheet_text(sheet: Mapping | None) -> str:
    keep = ("kind", "archetype", "silhouette", "palette", "parts", "signature", "one_side_mark")
    return json.dumps({k: sheet[k] for k in keep if k in sheet}, indent=1) if isinstance(sheet, Mapping) else ""


def _measured_section(measures: drawnside.Measures | None) -> str:
    if measures is None:
        return ""
    return f"""

## Measured from your photo
The app measured this shoe's outline in its side photo. Its heights, as shares of its length:
{drawnside.measures_text(measures)}
Take these for your proportions and draw to them: they are more exact than a reading by eye. They come from the outline only: the panels, marks and colours are yours to read from the photos."""


def side_prompt(photos: list[Photo], sheet: Mapping | None = None, notes: Sequence[str] = (),
                measures: drawnside.Measures | None = None) -> str:
    """Drawing the shoe from its side: the photos by their views, the front drawing's sheet (so both agree), the
    owner's notes, the two plain templates as examples of the style only, proportions written down before drawing (or
    measured from the trace), and what makes the shoe itself."""
    front = ""
    if sheet:
        front = f"""

## The drawing you made of it from the front
You drew this shoe from the front for the figure that shows the owner's outfits. Its sheet:
{_front_sheet_text(sheet)}
The side drawing must agree with it: the same kind of shoe, the same colours (its palette's hex values), the same parts, now seen from the side."""
    return f"""Draw one shoe from the owner's wardrobe as flat clip art seen from its side, from its photos. It is the picture that stands for the shoe in a private wardrobe app, wherever the shoe is shown, beside the app's other drawings in the same clean style. A name tells similar shoes apart, but the drawing must still carry what is particular to THIS shoe: its panels, marks, sole and proportions.

## The photos of the shoe
{photo_lines(photos)}
The side photos matter most, the outer side above all: draw from them. The others show what a side photo cannot (the toe's shape from above, the heel from behind). Ignore dirt, wear, shade, highlights, a hand holding it, the floor and the background.{front}{notes_section(notes)}

## Two of the app's plain drawings, for the STYLE only
{" and ".join(SIDE_STYLE_NAMES)} are the app's own side drawings of an ordinary sneaker and an ordinary boot, made from nothing more than their kind and a colour, on the card the app paints behind every drawing. They show the line weights, the flat colours, the frame and how few shapes a drawing needs. They are not this shoe and they are plain because they know nothing about it: do not copy their shapes.

## First, in words
1. kind: the most specific kind of shoe a footwear designer would call it.
2. proportions: before drawing, read from the side photo, its perspective corrected, each as a share of the shoe's length from the toe tip to the back of the heel: the sole's thickness under the heel and under the toe; and the upper's top above the ground at the toe box (15% of the length back from the toe tip), at the throat (where the lacing or the vamp meets the opening), at the collar's lowest point, and at the heel. For scale, an ordinary low sneaker stands about 0.3 of its length tall at the heel and about 0.15 at the toe box; read this shoe's own.
3. colours: the shoe's 2 to 6 TRUE colours, one material one colour.
4. features: what makes THIS shoe itself and not just any shoe of its kind, seen from the side, one short line each: its silhouette (the toe's shape, the sole's thickness at heel and toe, the collar's height), each panel and where its edges run, the sole's layers, marks and logos and exactly where they sit, the lacing, perforations, stitching that defines a panel.{_measured_section(measures)}

## Then the drawing
Draw it to your proportions, so its heights match them.

{SIDE_BRIEF}

Answer with kind, proportions, colours, features, and the drawing as bare SVG elements."""


def side_check_prompt(photos: list[Photo], answer: Mapping, svg: str, problems: list[str],
                      notes: Sequence[str] = (), measures: drawnside.Measures | None = None) -> str:
    """The check of a side drawing against the photos: its render on the card, large and at a closet tile's size, what
    was written for it, its SVG and what the automatic checks found."""
    written = json.dumps({k: answer[k] for k in ("kind", "proportions", "features") if k in answer}, indent=1)
    measured = ("\nMeasured from the photo's outline, as shares of the length:\n" + drawnside.measures_text(measures)
                if measures is not None else "")
    return f"""You drew this shoe from its side as flat clip art, from its photos. Now check the drawing against the PHOTOS, not only against what you wrote, and fix it if it needs it.

## The photos of the shoe
{photo_lines(photos)}
The side photos matter most.{notes_section(notes)}

## Your drawing
drawing.png shows it on its card, large and at the size of a closet tile. What you wrote for it:
{written}{measured}

Its SVG:
{svg}

## What the automatic checks found (each must be fixed)
{_found(problems)}

## Look
Compare drawing.png with the side photos. Is it the same kind of shoe, seen exactly side-on with the toe on the left? Is it as tall for its length as the shoe, at the toe box, the throat, the collar and the heel? Is the toe as round and as high as the photo's? Is the sole as thick at the heel and at the toe? Does each feature show, in its place, with its true shape, outline and colour? Is it a few clean flat shapes? Would someone who knows the shoe pick it out at the size of a closet tile?

If it is right and the automatic checks found nothing, say good, with no problems, and give the drawing back unchanged. Otherwise say what was wrong in problems and give the drawing fixed: change what is wrong and what must change with it, and keep everything else as it is (the same shapes where possible).

The rules the drawing follows:
{SIDE_BRIEF}"""


@dataclass
class Sided:
    """A finished side drawing: its SVG (made safe), what makes the shoe itself from the side, the proportions written
    for it, how many checks were made, whether the last said good and what the automatic checks still find, its calls
    and seconds."""
    svg: str
    features: list[str]
    proportions: dict
    rounds: int
    seconds: float
    calls: list[Call] = field(default_factory=list)
    good: bool = False
    problems: list[str] = field(default_factory=list)
    measured: bool = False   # drawn and checked against measures from the shoe's trace

    @property
    def route(self) -> str:
        return self.calls[0].route if self.calls else ""

    def to_json(self, made_at: str) -> dict:
        """As kept with the item, in its drawing's `side` entry."""
        return {"svg": self.svg, "features": list(self.features), "proportions": self.proportions,
                "rounds": self.rounds, "seconds": round(self.seconds, 1), "good": self.good, "problems": self.problems,
                "measured": self.measured,
                "calls": [{**asdict(c), "cost_usd": round(c.cost_usd, 6), "seconds": round(c.seconds, 1)}
                          for c in self.calls],
                "input_tokens": sum(c.input_tokens for c in self.calls),
                "cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
                "output_tokens": sum(c.output_tokens for c in self.calls),
                "cost_usd": round(sum(c.cost_usd for c in self.calls), 6), "route": self.route, "made_at": made_at}


def _features(lines) -> list[str]:
    out = []
    for line in lines or []:
        t = " ".join(str(line).split()) if isinstance(line, str) else ""
        if t:
            out.append(t if len(t) <= FEATURE_MAX else t[:FEATURE_MAX - 1].rstrip() + "…")
    return out[:FEATURES_MAX]


def _style_images() -> list[Image.Image]:
    return [_png(drawn.render_png(svg, 400, 460)) for svg in drawnside.style_svgs().values()]


def _side_good_as_is(svg: str) -> correcting.CutShort:
    """A side check's answer may stop being read once it says good, as a check of the front does (`_good_as_is`): in
    its schema `good`, `problems` and `features` come before `svg`, and a good answer with no automatic problem ends
    the checks with the drawing already held, so its copy of the drawing is not waited for. Not good, or a field
    missing or one more: None, and the answer is read to its end."""
    asked = set(SideCheckAnswer.model_fields) - {"svg"}

    def answer(fields: dict):
        if fields.get("good") is not True or set(fields) != asked:
            return None
        return SideCheckAnswer.model_validate({**fields, "svg": svg})
    return correcting.CutShort("svg", answer)


def _side(ask, photos: list[Photo], shots: list[Image.Image], names: list[str], sheet: Mapping | None,
          notes: Sequence[str], measures: drawnside.Measures | None, clock: Callable[[], float],
          calls: list[Call]) -> Sided:
    """One side drawing and its check rounds, at most `MAX_SIDE_ROUNDS`: they stop as soon as Claude says good and the
    automatic checks (`drawnside.checks`, with the measures) find nothing; when they found nothing and no fix was set
    aside, a good answer stops being read there (`_side_good_as_is`; the API route only). A check that fails keeps the
    drawing made so far; a fix that cannot be used is set aside and the drawing before it is checked again. `calls` collects this
    side's calls (the caller's `ask` records every call it makes in its own list too)."""
    start = clock()
    first_at = len(calls)
    answer = ask("side", side_prompt(photos, sheet, notes, measures), shots + _style_images(),
                 names + SIDE_STYLE_NAMES, SideAnswer)
    svg = drawnside.sanitise(answer.svg)
    written = {"kind": answer.kind, "proportions": answer.proportions.model_dump(), "features": _features(answer.features)}
    problems, note, rounds, good = drawnside.checks(svg, measures), [], 0, False
    while rounds < MAX_SIDE_ROUNDS:
        try:
            cut = _side_good_as_is(svg) if not problems and not note else None
            got = ask("side-check", side_check_prompt(photos, written, svg, problems + note, notes, measures),
                      shots + [_png(drawnside.check_png(svg))], names + ["drawing.png"], SideCheckAnswer,
                      cut_short=cut)
        except TaggingError as e:   # Claude out of reach, or no usable answer: the drawing so far is kept
            log.info("checking a shoe's side drawing stopped after %s rounds: %s", rounds, type(e).__name__)
            break
        rounds += 1
        if got.good and not problems:
            good = True
            break
        try:
            fixed = drawnside.sanitise(got.svg)
            found = drawnside.checks(fixed, measures)
        except drawn.DrawingError as e:   # the fix cannot be used: the drawing before it is checked again
            note = [f"The drawing you gave last could not be used ({e}) This is the drawing before it: fix it again, "
                    "or say good if it needs nothing."]
            continue
        svg, problems, note = fixed, found, []
        written = {**written, "features": _features(got.features) or written["features"]}
    return Sided(svg, written["features"], written["proportions"], rounds, clock() - start, calls[first_at:], good,
                 problems, measured=measures is not None)


def _side_job(ask, calls: list[Call], photos: list[Photo], shots: list[Image.Image], names: list[str], sheet: Mapping,
              notes: Sequence[str], measures, clock: Callable[[], float]) -> Callable[[], Sided | None]:
    """The side drawn in a thread of its own, beside the turns and sharing their places (`_limited`), through `ask`,
    which records its calls in `calls`: a function that waits for it and gives it, or None when it
    failed for whatever reason (logged by its kind)."""

    got: dict = {}
    m = drawnside.Measures.from_json(measures)

    def run():
        try:
            got["side"] = _side(ask, photos, shots, names, sheet, notes, m, clock, calls)
        except Exception as e:   # the front is never lost to the side
            log.info("drawing a shoe's side failed: %s", type(e).__name__)

    t = threading.Thread(target=run, name="shoe-side", daemon=True)
    t.start()

    def wait() -> Sided | None:
        t.join()
        return got.get("side")
    return wait


def draw_side(photos: list[Photo], routes: tuple[str, ...], client=None, exe: str | None = None,
              meter: Meter | None = None, asker: Asker = correcting.ask, clock: Callable[[], float] = time.monotonic,
              sheet: Mapping | None = None, notes: Sequence[str] = (), measures=None,
              mask_of: photocheck.MaskOf | None = None) -> Sided:
    """Draw the shoe from its side by itself (a shoe drawn before the side was, or a side that failed with its
    drawing): one draw call and at most `MAX_SIDE_ROUNDS` checks. `sheet`: the front drawing's sheet, so both agree
    (none: the side is drawn from the photos alone); `notes`: the owner's notes on the drawing; `measures`: from the
    shoe's trace (`drawnside.Measures`, or its JSON). Raises `RouteUnavailable` (or `CapReached`) when Claude cannot be
    reached, `TaggingError` when it gives no usable answer, `drawn.DrawingError` when the drawing cannot be used."""
    photos = [Photo(photocheck.crop(p.image, mask_of), p.view, p.sure) for p in photos]
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    ask = _caller(routes, client, exe, meter, asker, clock, calls, cache_photos=len(shots))
    return _side(ask, photos, shots, names, sheet, list(notes), drawnside.Measures.from_json(measures), clock, calls)
