"""Hem stitching stays on cloth; a shoe must not erase the sock's pattern."""
from dataclasses import replace
from xml.etree import ElementTree

import pytest

from closet.drawing import figure as fig
from closet.drawing import fitting, worn
from closet.drawing.figure import Piece

from .test_figure import TEE, answer


def outfit(length, socks):
    bottom = Piece(
        "shorts" if length == "shorts" else "trousers",
        answer("shorts" if length == "shorts" else "trousers",
               trouser_break="na" if length == "shorts" else length,
               features=["contrast_stitching"]),
        "#6f7278",
    )
    pieces = dict(base=TEE, bottom=bottom,
                  shoes=Piece("dress_shoes", answer("dress_shoes", shoe_style="loafer"), "#4e1a1d"))
    if socks:
        pieces["accessories"] = [Piece(
            "other", answer("other", accessory="socks", accessory_kind="dress_mid_calf",
                            pattern_name="argyle"), "#3b4a3a")]
    return pieces


@pytest.mark.parametrize("length", ["full", "no_break", "cropped", "shorts"])
@pytest.mark.parametrize("socks", [False, True], ids=["bare", "socks"])
def test_bottom_hem_stitches_stay_above_the_hem(length, socks):
    layout = fig.plan(outfit(length, socks))
    bottom = layout.get("bottom")
    outline = fitting.points(bottom.shape.outline)
    hem_y = min(bottom.shape.anchors[k][1] for k in ("hem_out", "hem_in"))
    stitches = [part for part in bottom.shape.parts if part.role == "stitch"
                and min(y for _, y in fitting.points(part.d)) > hem_y - 20]
    assert len(stitches) == 2
    for stitch in stitches:
        for x, y in fitting.points(stitch.d):
            left, right = sorted(bottom.shape.anchors[k][0] for k in ("hem_out", "hem_in"))
            if x > fig.CX:
                left, right = 2 * fig.CX - right, 2 * fig.CX - left
            x = max(left + 0.1, min(right - 0.1, x))
            crossings = [y0 + (x - x0) * (y1 - y0) / (x1 - x0)
                         for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1], strict=True)
                         if (x0 > x) != (x1 > x)]
            assert crossings
            assert y + 1.3 / 2 < max(crossings), (length, socks, x, y)


@pytest.mark.parametrize("pattern", ["argyle", "rugby_hoops"])
@pytest.mark.parametrize("footwear", ["loafer", "service_boot", "logger_boot"])
def test_sock_pattern_continues_into_shoe_instead_of_leaving_a_dashed_sliver(pattern, footwear):
    pieces = outfit("cropped", True)
    if footwear != "loafer":
        pieces["shoes"] = Piece("boots", answer("boots", footwear=footwear), "#765432")
    sock = pieces["accessories"][0]
    pieces["accessories"] = [replace(sock, answer=answer(
        "other", accessory="socks",
        accessory_kind="casual_crew" if pattern == "rugby_hoops" else "dress_mid_calf",
        pattern_name=pattern))]
    layout = fig.plan(pieces)
    dressed = worn.dress(layout, layout.accessories, "hem")
    assert dressed.ankle
    # The shoe paints its own ankle over the leg. Its fill must keep the same pattern,
    # not cover the diamonds/hoops with a solid patch just below the trouser hem.
    expected = 'fill="url(#hemxsp)"' if pattern == "argyle" else "<rect"
    assert expected in dressed.ankle
    root = ElementTree.fromstring(fig.figure(pieces, uid="hem"))
    shoes = next(element for element in root.iter() if element.get("id") == "hemp")
    for shoe in shoes:
        painted = [element for element in shoe.iter()
                   if element.tag.endswith("rect") and element.get("fill")]
        assert painted
        if pattern == "argyle":
            assert any(element.get("fill") == "url(#hemxsp)" for element in painted)
        else:
            assert all(element.get("fill") == worn.shade("#3b4a3a", 0.3) for element in painted)


@pytest.mark.parametrize("pattern", ["solid", "argyle", "rugby_hoops"])
def test_logger_boot_ankle_keeps_skin_above_the_true_crew_sock_top(pattern):
    pieces = outfit("shorts", True)
    pieces["shoes"] = Piece("boots", answer("boots", footwear="logger_boot"), "#765432")
    pieces["accessories"] = [Piece("other", answer(
        "other", accessory="socks", accessory_kind="casual_crew",
        **({} if pattern == "solid" else {"pattern_name": pattern})), "#3b4a3a")]
    layout = fig.plan(pieces)
    shoes = layout.get("shoes")
    top = (shoes.point(shoes.front.anchors["ankle"])[1]
           - (worn.SOCK_LENGTH["casual_crew"] - worn.SOCK_ANKLE_CM) * fig.K_PX)
    assert shoes.point(shoes.front.anchors["top"])[1] < top
    dressed = worn.dress(layout, layout.accessories, "crew")
    root = ElementTree.fromstring(f"<g>{dressed.ankle}</g>")
    assert any(element.get("fill") == fig.SKIN for element in root)
    clip = next(element for element in root.iter() if element.get("clip-path") == "url(#crewxsy)")
    assert any(element.get("fill") == "#3b4a3a" for element in clip.iter())
    parents = {child: parent for parent in root.iter() for child in parent}
    tx, ty = shoes.transforms[0][-2:]
    assert parents[clip].get("transform") == f"translate({-tx:.4f} {-ty:.4f})"
    assert clip[0].get("transform") == f"translate({tx:.4f} {ty:.4f})"
    defs = ElementTree.fromstring(f"<defs>{''.join(dressed.defs)}</defs>")
    boundary = next(element for element in defs if element.get("id") == "crewxsy")[0].get("d")
    polygon = fitting.points(boundary.split(" V", 1)[0]) + [(4000, 4000), (-4000, 4000)]
    for centre, transform in zip(fig._legs(layout)[:2], shoes.transforms, strict=True):
        sx, _, _, _, dx, dy = transform
        x = (centre - dx) / sx + tx
        assert not fitting.inside((x, top - 1 - dy + ty), polygon)
        assert fitting.inside((x, top + 2 * worn.SOCK_BOW_CM * fig.K_PX + 1 - dy + ty), polygon)
