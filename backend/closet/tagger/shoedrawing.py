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
   and the automatic checks find nothing, and after three checks in any case.

3. **Correct** (step E, `correct`): the owner's one-line note on a drawing. Claude is shown the photos, the drawing
   as it is (its render, sheet and SVG), the owner's earlier notes and the new note, and changes only what the note
   asks and what must change with it (purpose `correct_drawing`). Then at most two checks compare the change with the
   PHOTOS and with the drawing before it: they fix anything else the change broke, never undo the owner's change, and
   say in one plain sentence when the note asks for something the photos do not show (`against_photos`): it is
   drawn as asked all the same. A drawing kept as version 1 (all in front of the leg) comes back as version 2.

Every drawing is made safe (`drawn.sanitise`) before it is rendered, checked or kept. A check call that fails keeps
the drawing made so far: it was paid for, and it is still a drawing of the shoe. The owner's notes are passed to a
later drawing from scratch ("Draw again") and to its checks, so they are not lost. The brief below is the
experiment's (`bench/experiments/shoe_drawn/BRIEF3.md`, `ARCH.md` and `CORRECT.md`) with the owner's decisions since,
in one prompt for a model that can do nothing but look at the images.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from ..drawing import drawn
from . import correcting
from .tagging import CONFIG, Meter, TaggingError, cost_usd
from .views import shown

log = logging.getLogger("closet.shoedrawing")

MODEL = CONFIG["roles"]["drawing"]
EFFORT = "high"        # the experiment's drawings were made at a high effort; lower it once it is measured in the app
MAX_TOKENS = 32_000    # the longest answer a call allows on the API route, its thinking included (streamed)
TIMEOUT = 600          # seconds one call through the plan may take
MAX_ROUNDS = 3         # check calls at most, after the drawing
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


def draw_prompt(photos: list[Photo], notes: Sequence[str] = ()) -> str:
    examples = "\n\n".join(f"{label} ({png}):\n{_example_text(name)}"
                           for name, png, label in zip(drawn.EXAMPLES, EXAMPLE_NAMES,
                                                       ("A German-army-trainer style sneaker", "A tan cap-toe dress shoe",
                                                        "A boat shoe, a low-profile shoe"), strict=True))
    return f"""Draw one shoe from the owner's wardrobe as flat clip art, from its photos, for the drawn figure that shows the owner's outfits.

## The photos of the shoe
{photo_lines(photos)}
Ignore dirt, wear, shade, highlights, the floor and the background.{notes_section(notes)}

## Three drawings the owner liked
The images {", ".join(EXAMPLE_NAMES)} show them on two legs in socks, large and at phone size (the app draws the lines thicker than written, as it will on the figure), and their SVG is below (each is all in front of the leg: nothing of them shows behind it). Look at how few shapes they use and in what order. They are examples of the STYLE and the CONSTRUCTION, not of this shoe: do not copy their shapes.

{examples}

## First: the kind of shoe
Name the most specific kind of shoe a footwear designer would call it (for example "max-cushion running shoe with a thick foam midsole", "plain-toe chukka", "court sneaker"), and write how THAT KIND of shoe looks from the front and a little above, from what you know: its outline, how the sole relates to the upper, where its bulk is. Draw that kind's front silhouette first, then fit it to this shoe: its colours, parts and proportions from the photos. The silhouette should be the kind's, corrected by the photos, never a generic rounded blob. Keep the toe box broad but not bulbous: check its outline against the photo from above.

## Then the feature sheet, from the photos
kind, archetype and archetype_front (above); silhouette; proportions; palette: the shoe's 2 to 6 TRUE colours, one material one colour; parts; signature: the 2 to 4 things that make it recognisable from the FRONT at small size; one_side_mark; and where the drawing's opening, top and instep are.

## Then the drawing
{BRIEF}

Answer with the sheet, the left shoe as its two parts, behind and front, each bare SVG elements (no <svg> around them), and the right shoe the same way or null."""


def _shoe_text(shoe: drawn.Side) -> str:
    return f"behind the leg:\n{shoe.behind or '(empty)'}\nin front of the leg:\n{shoe.front}"


def _found(problems: list[str]) -> str:
    return "\n".join(f"- {p}" for p in problems) if problems else "- none"


def _right_text(right: drawn.Side | None) -> str:
    return _shoe_text(right) if right else "null (the app mirrors the left drawing for the other foot)"


def check_prompt(photos: list[Photo], sheet: dict, left: drawn.Side, right: drawn.Side | None,
                 problems: list[str], notes: Sequence[str] = ()) -> str:
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
{BRIEF}"""


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
                   notes: Sequence[str] = (), whole: bool = False) -> str:
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
{BRIEF}

Answer with changed, against_photos, the sheet, the left shoe as its two parts, behind and front, each bare SVG elements (no <svg> around them), and the right shoe the same way or null."""


def correct_check_prompt(photos: list[Photo], sheet: Mapping, left: drawn.Side, right: drawn.Side | None,
                         problems: list[str], note: str, notes: Sequence[str] = ()) -> str:
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
{BRIEF}"""


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

    @property
    def route(self) -> str:
        return self.calls[0].route if self.calls else ""

    def totals(self) -> dict:
        return {"input_tokens": sum(c.input_tokens for c in self.calls),
                "cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
                "output_tokens": sum(c.output_tokens for c in self.calls),
                "cost_usd": round(sum(c.cost_usd for c in self.calls), 6)}

    def to_json(self, photo_ids: list[str], made_at: str, notes: Sequence[Mapping] = ()) -> dict:
        """As kept with the item (`items.drawn`): version 2, each shoe {behind, front}. `notes`: the owner's notes on
        the drawing it replaces (`notes_of`), carried on so a later drawing keeps to them; they are also the sheet's
        `owner_notes`."""
        notes = [dict(n) for n in notes]
        sheet = {**self.sheet, "owner_notes": [n["note"] for n in notes]} if notes else self.sheet
        return {"version": drawn.VERSION, "left": self.left.to_json(),
                "right": self.right.to_json() if self.right else None, "sheet": sheet, "rounds": self.rounds,
                "seconds": round(self.seconds, 1), "good": self.good, "problems": self.problems,
                "calls": [{**asdict(c), "cost_usd": round(c.cost_usd, 6), "seconds": round(c.seconds, 1)}
                          for c in self.calls],
                **self.totals(), "route": self.route, "made_at": made_at, "photo_ids": list(photo_ids),
                "notes": notes}


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
    """What the API key would charge for a call, at the prices in `models.json`, whichever route made it. The API
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
            clock: Callable[[], float], calls: list[Call]):
    """One call to Claude on the drawing model, recorded in `calls` with its tokens, cost and seconds."""
    def ask(kind: str, text: str, images: list[Image.Image], image_names: list[str], answer_model):
        t = clock()
        result = asker(text, images, routes, client=client, exe=exe, meter=meter, answer_model=answer_model,
                       system=SYSTEM, model=MODEL, names=image_names, max_tokens=MAX_TOKENS, timeout=TIMEOUT,
                       effort=EFFORT)
        cached = getattr(result, "cache_read_tokens", 0) or 0
        calls.append(Call(kind, result.route, result.model, result.input_tokens, cached, result.output_tokens,
                          api_cost(result.model, result.input_tokens, cached, result.output_tokens), clock() - t))
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


def _check(ask, left: drawn.Side, right: drawn.Side | None, sheet: dict, max_rounds: int,
           prompt: Callable[[dict, drawn.Side, drawn.Side | None, list[str]], str],
           images: Callable[[drawn.Side, drawn.Side | None], tuple[list[Image.Image], list[str]]],
           answer_model) -> _Checked:
    """The check rounds: each shows Claude the drawing and what the automatic checks found, and takes its fix. They
    stop as soon as Claude says good and the automatic checks find nothing, and after `max_rounds` in any case. A check
    that fails keeps the drawing so far; a fix that cannot be used is set aside and the drawing before it is checked
    again."""
    problems, note = drawn.checks(left, right, sheet), []
    rounds, good, answers = 0, False, []
    while rounds < max_rounds:
        shots, names = images(left, right)
        try:
            answer = ask("check", prompt(sheet, left, right, problems + note), shots, names, answer_model)
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
            problems = drawn.checks(left, right, sheet)
        except drawn.DrawingError as e:   # the fix cannot be used: the drawing before it is checked again
            note = [f"The drawing you gave last could not be used ({e}) This is the drawing before it: fix it again, "
                    "or say good if it needs nothing."]
    return _Checked(left, right, sheet, rounds, good, problems, answers)


def draw(photos: list[Photo], routes: tuple[str, ...], client=None, exe: str | None = None,
         meter: Meter | None = None, asker: Asker = correcting.ask, clock: Callable[[], float] = time.monotonic,
         notes: Sequence[str] = ()) -> Drawn:
    """Draw the shoe from its photos (the main one first) and check it, at most `MAX_ROUNDS` times. `notes`: the
    owner's notes on earlier drawings of the shoe, kept to by the drawing and its checks. Raises `RouteUnavailable`
    (or `CapReached`) when Claude cannot be reached for the drawing, `TaggingError` when it gives no usable answer,
    `drawn.DrawingError` when its drawing cannot be used. `asker` stands in for `correcting.ask` (tests, the browser
    tests' stand-in)."""
    start = clock()
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    ask = _caller(routes, client, exe, meter, asker, clock, calls)
    notes = list(notes)

    examples = [_png(drawn.example_png(name)) for name in drawn.EXAMPLES]
    first = ask("draw", draw_prompt(photos, notes), shots + examples, names + EXAMPLE_NAMES, DrawAnswer)
    left, right = _drawing(first)
    done = _check(ask, left, right, first.sheet.model_dump(), MAX_ROUNDS,
                  lambda sheet, lf, rt, found: check_prompt(photos, sheet, lf, rt, found, notes),
                  lambda lf, rt: (shots + [_png(drawn.check_png(lf, rt))], names + ["drawing.png"]), CheckAnswer)
    return Drawn(done.left, done.right, done.sheet, done.rounds, clock() - start, calls, done.good, done.problems)


def correct(photos: list[Photo], kept: Mapping, note: str, routes: tuple[str, ...], client=None,
            exe: str | None = None, meter: Meter | None = None, asker: Asker = correcting.ask,
            clock: Callable[[], float] = time.monotonic) -> Corrected:
    """Change a drawing kept with the item (`kept`, as `items.drawn`: version 1 or 2) as the owner's one-line `note`
    asks, then check the change against the photos and the drawing before it, at most `MAX_CORRECT_ROUNDS` times. The
    owner's earlier notes (`kept`'s notes) are kept to. Raises as `draw` does; `drawn.DrawingError` too when the
    drawing kept cannot be read."""
    if not isinstance(kept, Mapping) or not isinstance(kept.get("sheet"), Mapping):
        raise drawn.DrawingError("The drawing to change has no sheet.")
    note = clean_note(note)
    start = clock()
    left0 = drawn.side(kept.get("left"))
    right0 = drawn.side(kept["right"]) if kept.get("right") else None
    whole = isinstance(kept.get("left"), str)   # kept as version 1: all in front of the leg
    earlier = [n["note"] for n in notes_of(kept)]
    shots = [shown(p.image) for p in photos]
    names = photo_names(len(photos))
    calls: list[Call] = []
    ask = _caller(routes, client, exe, meter, asker, clock, calls)

    before = _png(drawn.check_png(left0, right0))
    first = ask("correct", correct_prompt(photos, kept["sheet"], left0, right0, note, earlier, whole),
                shots + [before], names + ["drawing.png"], CorrectAnswer)
    left, right = _drawing(first)
    done = _check(ask, left, right, first.sheet.model_dump(), MAX_CORRECT_ROUNDS,
                  lambda sheet, lf, rt, found: correct_check_prompt(photos, sheet, lf, rt, found, note, earlier),
                  lambda lf, rt: (shots + [before, _png(drawn.check_png(lf, rt))],
                                   names + ["before.png", "drawing.png"]),
                  CorrectCheckAnswer)
    # the last check looked at the change beside the photos, so its word on them is the one kept
    against = _sentence(done.answers[-1].against_photos if done.answers else first.against_photos)
    return Corrected(done.left, done.right, done.sheet, done.rounds, clock() - start, calls, done.good, done.problems,
                     note=note, changed=_sentence(first.changed), against_photos=against)
