"""The garment's landmarks, asked of Claude for drawing its pattern in place.

A patterned top's drawing lines its plaid up with the buttons, each front on its own, and needs to know whether
a polo's chest bands continue onto its sleeves. That takes a few points on the photo: the buttons, the neck and
hem at the centre front, the shoulders and the underarms. Finding them in the image alone was tried and was
not reliable on patterned cloth (pocket edges and round shapes in a plaid were taken for buttons); Claude
finds them well (see bench/experiments/patterns/landmarks_prompt.md). The answer is checked where it is used:
an underarm point must lie on the garment's outline, or it is not trusted.

Asked through the same routes and the same monthly limit as describing an item, and only for patterned tops.
"""
from __future__ import annotations

from PIL import Image
from pydantic import BaseModel, Field

from . import correcting
from .tagging import CONFIG, Meter

SYSTEM = ("You locate points on a photo of one item of clothing for a private wardrobe app. Look at the image file "
          "named in the request with the Read tool, then answer in the required JSON format. Do nothing else.")
MAX_EDGE = 1024   # the image Claude sees, longest side in pixels; the answer is in its pixels
# the larger model: on the test shirts the tagging model put the underarms on the chest or the cuffs; the larger
# one placed every button and every underarm right (one short question per patterned top)
MODEL = CONFIG["roles"]["reasoning"]


class Point(BaseModel):
    x: float = Field(description="Pixels from the left edge of the image.")
    y: float = Field(description="Pixels from the top edge of the image.")


class Landmarks(BaseModel):
    button_line: list[Point] = Field(description="The centre of each visible front button, top to bottom; empty "
                                                 "when the front has no buttons.")
    neck_center: Point = Field(description="The centre of the neckline where the collar meets at the front.")
    hem_center: Point = Field(description="The centre of the front hem, the bottom edge below the buttons.")
    shoulder_left: Point = Field(description="Where the sleeve's top seam meets the shoulder, on the left of the image.")
    shoulder_right: Point = Field(description="The same on the right of the image.")
    underarm_left: Point = Field(description="Where the sleeve's lower seam meets the body's side seam, on the left "
                                             "of the image.")
    underarm_right: Point = Field(description="The same on the right of the image.")


PROMPT = ("The image is a top photographed from the front, its background removed. Give pixel coordinates in that "
          "image (x from the left, y from the top) of: the centre of each visible front button (button_line, top to "
          "bottom); the centre of the neckline where the collar meets at the front; the centre of the front hem; the "
          "shoulder points, where each sleeve's top seam meets the shoulder; and the underarm points, where each "
          "sleeve's lower seam meets the body's side seam. Left and right mean the left and right of the image. Be "
          "as precise as you can.")


def shown(cutout: Image.Image) -> tuple[Image.Image, float]:
    """The image Claude is shown (at most MAX_EDGE on its longest side) and the factor that turns its pixels into
    the cutout's."""
    im = cutout.copy()
    im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    return im, cutout.width / im.width


def ask(cutout: Image.Image, routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL) -> dict:
    """The landmarks in the cutout's own pixels, as a plain dict (kept with the item as JSON)."""
    im, scale = shown(cutout)
    result = correcting.ask(PROMPT, [im], routes, client=client, exe=exe, meter=meter, answer_model=Landmarks,
                            system=SYSTEM, model=model)
    raw = result.answer.model_dump()

    def sc(p):
        return {"x": round(p["x"] * scale, 1), "y": round(p["y"] * scale, 1)}
    out = {k: (sc(v) if isinstance(v, dict) else [sc(b) for b in v]) for k, v in raw.items()}
    out["route"], out["model"] = result.route, result.model
    return out
