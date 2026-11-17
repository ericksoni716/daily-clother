"""What each photo chosen on Add shows, asked of Claude so the owner adds everything in one place (the owner, 17
November: "clothes/shoes import could all be combined and classified to the category it is").

The owner chooses or takes any mix of photos. Before anything is added, up to `MAX_PHOTOS` small copies go to Claude
in one call, which says for each whether it shows one piece of clothing, several pieces together, or a shoe, and
which photos show the same shoe (or pair). The owner sees the answer and can change it; then each photo goes the way
it always has: one piece through the import, several through the pieces' boxes, a shoe with all its photos at once.

Asked through the same routes and the same monthly limit as describing an item (`spend.Meter`, purpose
`sort_add`), on the model of the `sorting` role, which also sorts a shoe's photos into views.
"""
from __future__ import annotations

from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from . import correcting
from .tagging import CONFIG, Meter

MODEL = CONFIG["roles"]["sorting"]
MAX_PHOTOS = 10    # photos in one call; more are sorted in several calls
MAX_EDGE = 512     # the image Claude sees, longest side in pixels: enough to tell a shoe from a shirt, cheap to send
KINDS = ("piece", "pieces", "shoe")
SYSTEM = ("You sort photos for a private wardrobe app. Look at every image file named in the request with the Read "
          "tool, then answer in the required JSON format. Do nothing else.")


class PhotoKind(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photo: int = Field(description="The photo's number: 1 for the first photo, 2 for the second, and so on.")
    kind: Literal["piece", "pieces", "shoe"] = Field(
        description="piece: one piece of clothing or one accessory; pieces: several separate pieces together; "
                    "shoe: a shoe or a pair of shoes.")
    shoe: int = Field(description="For a shoe: the same number for every photo of the same shoe or pair, starting "
                                  "at 1; 0 when the photo is not of a shoe.")


class PhotoKinds(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    photos: list[PhotoKind] = Field(description="One entry for every photo, by its number.")


def prompt(count: int) -> str:
    which = "There is one photo, photo 1." if count == 1 else \
        f"There are {count} photos, numbered 1 to {count} in the order they are given."
    return f"""These are photos the owner chose to add to their wardrobe. {which} For each, say what it shows:
- piece: one piece of clothing or one accessory (a shirt, trousers, a jacket, a bag, a belt, a hat, a scarf), on a hanger, laid flat or worn.
- pieces: several separate pieces of clothing together in one photo, for example laid out on a bed or the floor, to be added one by one.
- shoe: a shoe, or a pair of shoes, from any side.

A pair of socks or gloves is one piece. A suit's jacket and trousers in one photo are pieces.

Photos of shoes: the owner often takes several photos of the same shoe from different sides (the outer side, the inner side, from above, the front, the back, the sole). Give every photo of the same shoe or pair the same shoe number, starting at 1 for the first shoe you see; a different shoe gets the next number. Decide by the shoe itself: its colours, materials, markings and shape, not by the background. For a photo that is not of a shoe, give shoe 0.

Give one entry for every photo, by its number."""


def shown(photo: Image.Image) -> Image.Image:
    im = photo.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    return im


def ask(photos: list[Image.Image], routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL) -> list[dict]:
    """[{kind, shoe}] for the photos, in their order. A photo missing from the answer is a piece; shoe numbers are
    renumbered 1, 2, ... in order of first appearance, and a shoe photo with no number is a shoe of its own. Raises
    `RouteUnavailable` (or `CapReached`) when Claude cannot be asked, `TaggingError` when it gives no usable answer."""
    if not 1 <= len(photos) <= MAX_PHOTOS:
        raise ValueError(f"sort 1 to {MAX_PHOTOS} photos at a time")
    result = correcting.ask(prompt(len(photos)), [shown(p) for p in photos], routes, client=client, exe=exe,
                            meter=meter, answer_model=PhotoKinds, system=SYSTEM, model=model)
    return read(result.answer, len(photos))


def read(answer: PhotoKinds, count: int) -> list[dict]:
    """The answer for `count` photos, tidied (see `ask`)."""
    by = {p.photo: p for p in answer.photos if 1 <= p.photo <= count}
    out, numbers = [], {}
    for i in range(1, count + 1):
        p = by.get(i)
        if p is None or p.kind != "shoe":
            out.append({"kind": p.kind if p else "piece", "shoe": 0})
            continue
        key = p.shoe if p.shoe > 0 else ("alone", i)
        numbers.setdefault(key, len(numbers) + 1)
        out.append({"kind": "shoe", "shoe": numbers[key]})
    return out
