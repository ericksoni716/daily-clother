"""Whether two drawings are the same drawing, for the tests that compare one made now with one kept in the demo closet.

A drawing can carry a small picture cut from the item's photo, as PNG text. On the system the demo closet was made
on (Linux), drawing the item again gives the same text to the letter, and that is what is checked there. On another
system (Windows in CI) the picture's bytes need not match: the compression library is a different build, and
resampling the photo can round a value one step the other way. There the drawings are the same when everything
around the pictures matches to the letter and each picture has the same size and nearly the same pixels."""
import base64
import io
import re
import sys

from PIL import Image, ImageChops

PICTURE = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=]+)")
STEP = 3   # how far one channel of one pixel may differ on another system


def same(made: str, kept: str, platform: str | None = None) -> bool:
    if made == kept:
        return True
    if (platform or sys.platform) == "linux":
        return False
    if PICTURE.sub("", made) != PICTURE.sub("", kept):
        return False
    a, b = PICTURE.findall(made), PICTURE.findall(kept)
    return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))


def _close(a: str, b: str) -> bool:
    x, y = (Image.open(io.BytesIO(base64.b64decode(s))).convert("RGBA") for s in (a, b))
    if x.size != y.size:
        return False
    return max(high for _, high in ImageChops.difference(x, y).getextrema()) <= STEP
