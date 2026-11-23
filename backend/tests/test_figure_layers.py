"""How much of a layer worn under an open jacket or coat shows, read from the figure drawn as a picture
(closet/drawing/figure.py, `_worn_closed`). Pure image tests that take about a second each: marked slow."""
import io

import numpy as np
import pytest

from closet.drawing.figure import K_PX, figure, plan

from .test_figure import BOOTS, COAT, FASTENED_MIDS, JACKET, JEANS, OVERSHIRT, TEE

pytestmark = pytest.mark.slow

MID_RGB = (0xC0, 0x39, 0x2B)   # every layer under the coat is this red, which nothing else in the figure is
# The least of the middle layer's own colour that shows inside the outer layer's outline, above its hem, in cm² on
# him: about a hand (a palm 8 cm across and 19 cm long), the least that reads as a garment of its own, its colour
# and its fastening, at phone size (a figure about 300px tall shows it about 7 by 16 px). Worn open under the coat
# as it was before 23 November, the most any of these showed was about 107 cm² (a zip hoodie's hem and the bottom
# of its zip, under a long coat); under a jacket none showed at all.
FLOOR_CM2 = 150.0


def _shown(pieces) -> float:
    import resvg_py
    from PIL import Image

    layout = plan(pieces)
    svg = figure(pieces, uid="m")
    x, y, w, _ = layout.view
    width = 360
    px = width / w
    im = np.asarray(Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width)))).convert("RGB"))
    outer = layout.get("outer")
    x0, y0, x1, _ = outer.box(outer.shape.body_box)
    hem = outer.point(outer.shape.anchors["hem"])[1]
    sub = im[int((y0 - y) * px):int((hem - y) * px), int((x0 - x) * px):int((x1 - x) * px)].astype(int)
    red = np.all(np.abs(sub - np.array(MID_RGB)) < 40, axis=-1)
    return float(red.sum()) / (px * K_PX) ** 2


@pytest.mark.parametrize("outer", [COAT, JACKET], ids=["coat", "jacket"])
@pytest.mark.parametrize("mid", list(FASTENED_MIDS) + ["overshirt"])
def test_the_layer_under_an_open_outer_layer_shows_as_a_garment_of_its_own(mid, outer):
    under = FASTENED_MIDS.get(mid, OVERSHIRT)
    under = type(under)(under.category, under.answer, "#c0392b", silhouette=under.silhouette)
    assert _shown(dict(base=TEE, mid=under, outer=outer, bottom=JEANS, shoes=BOOTS)) >= FLOOR_CM2
