"""A collar turns over around the ankle; its outer wall must not form horns."""
import math
import re
from dataclasses import replace

import pytest

from closet.drawing import figure as fig
from closet.drawing import frontshoe

from .test_figure import SHORTS, TEE, Piece, _flat, _inside, answer

FOOTWEAR = ["leather_court_sneaker", "trail_runner", "service_boot", "logger_boot"]


@pytest.fixture(params=FOOTWEAR)
def collar(request, monkeypatch):
    category = "boots" if "boot" in request.param else "sneakers"
    shoe = Piece(category, answer(category, footwear=request.param), "#765432")
    layout = fig.plan(dict(base=TEE, bottom=SHORTS, shoes=shoe))
    captured = []
    render = fig.front_shoe

    def capture(*args, **kwargs):
        drawn = render(*args, **kwargs)
        captured.append((drawn, kwargs["ankle_path"]))
        return drawn

    monkeypatch.setattr(fig, "front_shoe", capture)
    fig._svg(layout, "round")
    drawn, leg = captured[0]
    upper = re.search(r'<clipPath id="roundsu"><path d="([^"]+)"', drawn.defs)[1]
    seen = re.search(r'<clipPath id="roundsa"><path d="([^"]+)"', drawn.body)[1]
    rim = re.search(r'<path d="([^"]+)" fill="[^"]+" stroke="[^"]+" stroke-width="1.4"', drawn.body)[1]
    empty = render(layout.get("shoes").spec, fig.K_PX)
    return drawn, upper, _flat(rim), _flat(seen), _flat(leg), empty


def test_outer_collar_wall_cannot_project_above_the_rounded_lip(collar):
    _, upper, rim, seen, leg, _ = collar
    upper = _flat(upper)
    for side in (min(rim), max(rim)):
        # Sample the actual painted wall on both sides of the opening, including
        # the convex upper/ankle-clip intersection that used to leave a thin horn.
        # Half a centimetre allows the lip's thickness, not a raised outer crown.
        for i in range(-12, 13):
            x = side[0] + i * fig.K_PX / 12
            for j in range(7, 25):
                point = (x, side[1] - j * fig.K_PX / 12)
                painted = _inside(point, upper) and not (_inside(point, seen) and _inside(point, leg))
                assert not painted, f"upward collar projection at {point}, beside lip {side}"


def test_collar_shoulders_turn_smoothly_into_the_front_arc(collar):
    _, upper, _, _, _, _ = collar
    segments = re.findall(r"C ([^CLZ]+)", upper)
    assert len(segments) >= 4
    previous = None
    for segment in segments[:4]:
        values = list(map(float, re.findall(r"-?[\d.]+", segment)))
        c1, c2, end = list(zip(values[::2], values[1::2], strict=True))
        if previous:
            old_c2, start = previous
            incoming = (start[0] - old_c2[0], start[1] - old_c2[1])
            outgoing = (c1[0] - start[0], c1[1] - start[1])
            cosine = sum(a * b for a, b in zip(incoming, outgoing, strict=True))
            cosine /= math.hypot(*incoming) * math.hypot(*outgoing)
            assert cosine > 0.99
        previous = c2, end


def test_rounding_preserves_shoe_anchors_and_lower_width(collar):
    drawn, upper, rim, _, _, empty = collar
    assert drawn.anchors == empty.anchors
    assert drawn.bbox == empty.bbox
    assert drawn.outline == empty.outline
    plain_upper = re.search(r'<clipPath id="[^"]+u"><path d="([^"]+)"', empty.defs)[1]
    cutoff = max(y for _, y in rim) + 0.2
    assert {(x, y) for x, y in _flat(upper) if y > cutoff} == {
        (x, y) for x, y in _flat(plain_upper) if y > cutoff
    }


@pytest.mark.parametrize("shaft", [0.35, 0.36, 0.5, 0.95])
@pytest.mark.parametrize("sole,tread", [(None, None), ("thin", "city"), ("chunky", "lug"), ("chunky", "eva")])
@pytest.mark.parametrize("lacing", ["d_rings", "speed_hooks"])
def test_rounding_keeps_the_upper_beneath_existing_laces_and_hardware(shaft, sole, tread, lacing):
    spec = fig._spec(Piece("boots", answer("boots", footwear="service_boot", lacing=lacing), "#765432"))
    spec = replace(spec, params={**spec.params, "shaft": shaft, "sole": sole, "tread": tread})
    plain = fig.front_shoe(spec, fig.K_PX, uid="plain")
    drawn = fig.front_shoe(spec, fig.K_PX, uid="round", ankle=fig._ankle())
    old = _flat(re.search(r'<clipPath id="plainu"><path d="([^"]+)"', plain.defs)[1])
    new = _flat(re.search(r'<clipPath id="roundu"><path d="([^"]+)"', drawn.defs)[1])
    details = re.findall(r'<path d="([^"]+)" fill="none" stroke="([^"]+)" stroke-width="([^"]+)"', plain.body)
    for path, colour, width in details:
        if colour == frontshoe.METAL or float(width) == 2.8:
            for point in _flat(path):
                if _inside(point, old):
                    assert _inside(point, new), (shaft, sole, tread, point)


@pytest.mark.parametrize("sole,tread", [(None, None), ("chunky", "lug"), ("chunky", "eva")])
def test_short_boot_rounding_keeps_the_forward_vamp(sole, tread):
    spec = fig._spec(Piece("boots", answer("boots", footwear="service_boot"), "#765432"))
    spec = replace(spec, params={**spec.params, "shaft": 0.35, "sole": sole, "tread": tread})
    drawn = fig.front_shoe(spec, fig.K_PX, uid="round", ankle=fig._ankle())
    upper = _flat(re.search(r'<clipPath id="roundu"><path d="([^"]+)"', drawn.defs)[1])
    seen = _flat(re.search(r'<clipPath id="rounda"><path d="([^"]+)"', drawn.body)[1])
    sole_t = 2 * (1.6 if sole == "chunky" else 1) * {"lug": 1.25, "eva": 1.35}.get(tread, 1)
    for u in (0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8):
        for xs in (-0.8, -0.5, 0, 0.5, 0.8):
            point = frontshoe._surface(frontshoe._View(fig.K_PX),
                                      lambda u: frontshoe._half_width(u, 5.3, "round"),
                                      0.97, frontshoe._BOOT, sole_t, u, xs)
            assert _inside(point, upper), (sole, tread, u, xs, point)
            assert not _inside(point, seen), (sole, tread, u, xs, point)
