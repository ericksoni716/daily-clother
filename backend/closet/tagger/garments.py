"""Where each garment is in a photo of several, asked of Claude so each can become an item of its own.

The owner lays several pieces out together (on the bed, on the floor) and takes one photo. Claude is asked for a
box around every separate piece; the boxes are checked and tidied where they are used (`closet/sources.py`: a
box outside the photo is cut to it, an empty one dropped, the same piece boxed twice kept once), and the owner
checks them before anything is added.

Asked through the same routes and the same monthly limit as describing an item (`spend.Meter`, purpose
`find_garments`), on the larger model, as the landmarks are: placing points and edges on a photo is where the
tagging model was weakest.
"""
from __future__ import annotations

from PIL import Image
from pydantic import BaseModel, Field

from . import correcting
from .tagging import CONFIG, Meter

SYSTEM = ("You find the separate pieces of clothing in a photo for a private wardrobe app. Look at the image file "
          "named in the request with the Read tool, then answer in the required JSON format. Do nothing else.")
MAX_EDGE = 1024   # the image Claude sees, longest side in pixels; the answer is in its pixels
MODEL = CONFIG["roles"]["reasoning"]


class Garment(BaseModel):
    name: str = Field(description="A few plain words for the piece, such as 'navy polo' or 'grey wool trousers'.")
    x0: float = Field(description="The left edge of the box around the piece, in pixels from the left of the image.")
    y0: float = Field(description="The top edge of the box, in pixels from the top of the image.")
    x1: float = Field(description="The right edge of the box, in pixels from the left of the image.")
    y1: float = Field(description="The bottom edge of the box, in pixels from the top of the image.")


class Garments(BaseModel):
    garments: list[Garment] = Field(description="One box per separate piece, top to bottom and left to right; "
                                                "empty when the photo shows no clothing.")


PROMPT = ("The image is one photo of several pieces of clothing laid out or hung together, for example on a bed or "
          "the floor. Give one box for each separate piece: the smallest rectangle that holds all of the piece that "
          "shows, in pixel coordinates of this image (x from the left, y from the top). A pair of shoes, socks or "
          "gloves is one piece. A suit's jacket and its trousers are two pieces. A piece partly covered by another "
          "is still one piece: box all of it that shows, even where the boxes overlap. Leave out people, hangers, "
          "furniture, bedding and anything that is not clothing, shoes or an accessory (bag, belt, hat, scarf, tie). "
          "Name each piece in a few plain words. Be as precise as you can.")


def shown(photo: Image.Image) -> Image.Image:
    """The image Claude is shown: at most MAX_EDGE on its longest side."""
    im = photo.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    return im


def ask(photo: Image.Image, routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL) -> list[dict]:
    """The boxes Claude gives, as fractions of the photo's width and height ({x0, y0, x1, y1, label}), as they came:
    the caller clamps and tidies them."""
    im = shown(photo)
    result = correcting.ask(PROMPT, [im], routes, client=client, exe=exe, meter=meter, answer_model=Garments,
                            system=SYSTEM, model=model)
    w, h = float(im.width), float(im.height)
    return [{"x0": g.x0 / w, "y0": g.y0 / h, "x1": g.x1 / w, "y1": g.y1 / h, "label": g.name}
            for g in result.answer.garments]
