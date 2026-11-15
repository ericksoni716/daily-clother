"""Which view each photo of a shoe shows, asked of Claude so the owner never has to say (shoes drawn from
understanding, step B).

A shoe has its main photo (the guided side photo) and up to five more, taken in any order. All of them go to Claude in
one call, the main photo first, through the same routes and the same monthly limit as describing an item
(`spend.Meter`, purpose `sort_views`), on the model of the `sorting` role: in the experiment it named above, front
and back right on 15 of 15 photos and flagged as unsure every photo whose outer and inner side it swapped. The
answer is applied in `closet/shoeviews.py`, where the owner's own answers always win.
"""
from __future__ import annotations

from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from . import correcting
from .tagging import CONFIG, Meter

MODEL = CONFIG["roles"]["sorting"]
VIEWS = ("outer", "inner", "top", "front", "back", "sole", "other")
SIDES = ("outer", "inner")
SYSTEM = ("You sort the photos of one shoe into views for a private wardrobe app. Look at every image file named in "
          "the request with the Read tool, then answer in the required JSON format. Do nothing else.")

View = Literal["outer", "inner", "top", "front", "back", "sole", "other"]


class PhotoView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo: int = Field(description="The photo's number: 1 for the first photo, 2 for the second, and so on.")
    view: View = Field(description="What the photo shows: outer (the outer side), inner (the inner side), top (from "
                                   "above), front (toe towards the camera), back (heel towards the camera), sole (the "
                                   "underside) or other.")
    sure: bool = Field(description="True only when you are sure of the view; false when you cannot tell.")


class ShoeViews(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photos: list[PhotoView] = Field(description="One entry for every photo, by its number.")
    sides_differ: bool = Field(description="True when the outer and inner sides look different (a logo, stripe or "
                                           "panel on one side only); false when only one side is shown, or both sides "
                                           "look alike.")


def prompt(count: int) -> str:
    which = ("There is one photo, photo 1, the main photo the owner took, usually of the side." if count == 1 else
             f"There are {count} photos, numbered 1 to {count} in the order they are given. Photo 1 is the main photo "
             "the owner took, usually of the side; the others were taken in any order.")
    return f"""These are photos of one shoe from the owner's wardrobe. {which} Say which view each photo shows:
- outer: the outer side, the whole side from toe to heel.
- inner: the inner side, the whole side from toe to heel.
- top: from above, looking down on the shoe.
- front: the toe pointing towards the camera.
- back: the heel towards the camera.
- sole: the underside, with the tread.
- other: anything else, such as a close-up of a detail, a label, the inside, or a view halfway between two of these.

Telling the outer side from the inner side: when the shoes are worn, the outer side of each shoe faces away from the other shoe, and the inner side faces the other shoe. The inner side has the arch: the sole curves in under the middle of the foot, and the shoe is often lower or straighter there. Brands usually put their main mark (a logo, stripes, a large panel) on the outer side, but not always. A left shoe seen with its toe to the left shows its outer side; a right shoe seen with its toe to the left shows its inner side.

A photo may show the pair, not one shoe: then give the view of the shoe nearest the camera, or the view both shoes are seen from.

Set sure to true only when you are sure; when you cannot tell, especially between the outer and the inner side, say so with sure false rather than guess. Two photos may show the same view.

Then say whether the outer and inner sides look different (sides_differ): true when something is on one side only, such as a logo, a stripe or a panel; false when the photos show only one side, or both sides look alike.

Give one entry for every photo, by its number."""


def shown(photo: Image.Image) -> Image.Image:
    """The image Claude is shown: at most 1024 pixels on its longest side, as for describing."""
    im = photo.convert("RGB")
    im.thumbnail((1024, 1024), Image.LANCZOS)
    return im


def ask(photos: list[Image.Image], routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL) -> ShoeViews:
    """Claude's answer for the photos, in their order (the main photo first). Raises `RouteUnavailable` (or
    `CapReached`) when Claude cannot be reached, as `correcting.ask`."""
    result = correcting.ask(prompt(len(photos)), [shown(p) for p in photos], routes, client=client, exe=exe,
                            meter=meter, answer_model=ShoeViews, system=SYSTEM, model=model)
    return result.answer
