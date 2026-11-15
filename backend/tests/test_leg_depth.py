"""The lower leg stays smooth and keeps its shape inside a shoe's opening."""
import math
import re
from dataclasses import replace
from xml.etree import ElementTree

import pytest

from closet.drawing import figure as fig
from closet.drawing import frontshoe, worn

from .test_figure import SHORTS, TEE, Piece, _flat, _inside, answer


@pytest.mark.parametrize("footwear", [
    "service_boot", "logger_boot", "trail_runner", "leather_court_sneaker", "sandal",
])
def test_lower_leg_sides_are_smooth_curves_through_knee_and_calf(footwear):
    shoe = Piece("boots", answer("boots", footwear=footwear), "#765432")
    layout = fig.plan(dict(base=TEE, bottom=SHORTS, shoes=shoe))
    for leg in layout.body.legs:
        assert " C " in leg
        # Cubics must meet tangentially, rather than only rounding a polygon's stroke joins.
        previous = None
        for command, args in re.findall(r"([MLCZ])([^MLCZ]*)", leg):
            if command != "C":
                previous = None
                continue
            coords = list(map(float, re.findall(r"-?[\d.]+", args)))
            c1, c2, end = list(zip(coords[::2], coords[1::2], strict=True))
            assert min(c1[1], end[1]) <= c2[1] <= max(c1[1], end[1])
            if previous is not None:
                old_c2, start = previous
                a = (start[0] - old_c2[0], start[1] - old_c2[1])
                b = (c1[0] - start[0], c1[1] - start[1])
                cosine = sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))
                assert cosine > 0.99
            previous = c2, end
        for cm, half in ((fig.KNEE_CM, fig.KNEE_HALF_CM), (fig.CALF_CM, fig.CALF_HALF_CM)):
            points = [(x, y) for x, y in _flat(leg) if abs(y - fig._y(cm)) < 0.1]
            assert len(points) == 2
            assert abs(points[0][0] - points[1][0]) == pytest.approx(2 * half * fig.K_PX, abs=0.2)


def test_taller_boot_does_not_move_the_wearers_ankle_or_narrow_his_calf():
    spec = fig._spec(Piece("boots", answer("boots", footwear="service_boot"), "#765432"))
    low = frontshoe.front_shoe(replace(spec, params={**spec.params, "shaft": 0.4}), fig.K_PX)
    tall = frontshoe.front_shoe(replace(spec, params={**spec.params, "shaft": 0.8}), fig.K_PX)
    assert low.anchors["top"] != tall.anchors["top"]
    assert low.anchors["ankle"] == tall.anchors["ankle"]
    assert low.anchors["ankle_r"] == tall.anchors["ankle_r"]


@pytest.mark.parametrize("footwear", ["service_boot", "logger_boot", "trail_runner", "leather_court_sneaker"])
def test_shoe_opening_uses_the_same_leg_contour_as_the_wearer(footwear, monkeypatch):
    shoe = Piece("boots", answer("boots", footwear=footwear), "#765432")
    layout = fig.plan(dict(base=TEE, bottom=SHORTS, shoes=shoe))
    render = fig.front_shoe
    seen = []

    def capture(*args, **kwargs):
        result = render(*args, **kwargs)
        seen.append((kwargs.get("ankle_path"), result))
        return result

    monkeypatch.setattr(fig, "front_shoe", capture)
    fig._svg(layout, "depth")
    path, drawn = seen[-1]
    assert path is not None
    placed = layout.get("shoes")
    for actual, expected in zip(_flat(path, placed.transforms[0]), _flat(layout.body.legs[0]), strict=True):
        assert actual == pytest.approx(expected, abs=0.2)
    assert f'd="{path}"' in drawn.body
    # The back edge is behind the leg too, not a closed oval drawn across its skin.
    clip = re.search(r'<clipPath id="depthsa"><path d="([^"]+)"', drawn.body)[1]
    back_height = min(y for _, y in _flat(drawn.outline))
    assert min(y for _, y in _flat(clip)) < back_height - 10
    # Its artificial cut end belongs inside the shoe, below the front of the opening.
    assert max(y for _, y in _flat(path)) > max(y for _, y in _flat(clip)) + fig.LINE


def test_trail_runner_rear_collar_is_behind_the_leg_not_a_visible_spike(monkeypatch):
    shoe = Piece("sneakers", answer("sneakers", footwear="trail_runner"), "#765432")
    layout = fig.plan(dict(base=TEE, bottom=SHORTS, shoes=shoe))
    render = fig.front_shoe
    captured = []

    def capture(*args, **kwargs):
        drawn = render(*args, **kwargs)
        captured.append((kwargs["ankle_path"], drawn))
        return drawn

    monkeypatch.setattr(fig, "front_shoe", capture)
    fig._svg(layout, "rear")
    leg, drawn = captured[0]
    seen = re.search(r'<clipPath id="rearsa"><path d="([^"]+)"', drawn.body)[1]
    view = frontshoe._View(fig.K_PX)
    _, sole, table, _ = frontshoe.STYLES["runner"]
    sole *= 1.25   # the trail runner's lug sole
    for u in (0.0, 0.04, 0.08, 0.12, 0.18):
        rear = view(0.0, u, sole + frontshoe._interp(table, u) - 0.1)
        assert _inside(rear, _flat(leg))
        assert _inside(rear, _flat(seen))


@pytest.mark.parametrize("pattern", ["solid", "argyle", "rugby_hoops"])
def test_tall_boot_cannot_paint_short_sock_colour_above_its_top(pattern):
    sock = Piece("other", answer("other", accessory="socks", accessory_kind="casual_crew",
                                pattern_name=pattern), "#123456")
    shoe = Piece("boots", answer("boots", footwear="logger_boot"), "#765432")
    layout = fig.plan(dict(base=TEE, bottom=SHORTS, shoes=shoe, accessories=[sock]))
    dressed = worn.dress(layout, layout.accessories, "short")
    root = ElementTree.fromstring(f'<svg>{dressed.ankle.replace("{d}", "M 0,0 L 10,0 L 10,20 Z")}</svg>')
    assert any(p.get("fill") == fig.SKIN for p in root.iter())

    def check(element, clipped=False):
        clipped |= element.get("clip-path") == "url(#shortxsy)"
        if element.get("fill") == "#123456":
            assert clipped   # the same bowed sock-top boundary as on the leg
        for child in element:
            check(child, clipped)

    assert any(p.get("fill") == "#123456" for p in root.iter())
    check(root)
