"""A shoe seen from the front on the As worn figure: the template drawn from the shoe's style words.

The figure draws this for every shoe without a drawing by Claude, traced from its photo or not (the traced front
view, #192 stage 2c, was removed: see DECISIONS.md). These tests were kept from that stage's tests, where they
covered the untraced templates: a digest of the drawings, the rules every front shoe keeps (the collar's back and
lining before the leg, nothing hiding the leg, every detail on the shoe, no horns on the collar), the no-show cut
and the low collar beside a bare ankle.
"""
import hashlib
import math
import re

import pytest

from closet.drawing import figure as fig
from closet.drawing import frontshoe
from closet.drawing.figure import K_PX, Piece, figure, plan

from .test_figure import SHORTS, TEE, TROUSERS, _clear, _flat, _inside, answer


def spec_of(category="sneakers", style="low_sneaker", bottom=SHORTS, **details):
    shoes = Piece(category, answer(category, shoe_style=style, **details), "#5a3a22")
    return plan(dict(base=TEE, bottom=bottom, shoes=shoes)).get("shoes").spec


def front(spec=None):
    return fig.front_shoe(spec or spec_of(), K_PX, uid="z", ankle=fig._ankle(), toes=fig.TOE_LINE)


# ------------------------------------------------------------------ the templates, byte for byte

UNTRACED = [("sneakers", "low_sneaker"), ("sneakers", "runner"), ("sneakers", "slip_on"), ("sneakers", "high_top"),
            ("dress_shoes", "loafer"), ("dress_shoes", "derby"), ("dress_shoes", "oxford"), ("boots", "boot"),
            ("boots", "chelsea_boot"), ("sandals", "sandal")]
# taken before stage 2c; change it only with a change meant to redraw the template shoes, and say so in the pull request
# (changed once: a Chelsea boot's pull tab, at the back of its shaft, is drawn behind the leg, not over it; and once
# when the trousers' hem moved onto the shoe: the shoes themselves, and the figures in shorts, are byte for byte the
# same; and once when a bare ankle under cropped trousers showed points on low shoes' collars: the dress shoes and
# slip-ons got #214's rounded collar, and every low shoe rounder shoulders beside the ankle)
UNTRACED_DIGEST = "2d369df536e3c91b79c6612b3d790f421b17809880c951881a609c7f47058a6e"   # taken again 19 Nov: the tee's sleeves are pressed against its body under the arm; the shoes and trousers are unchanged (taken 18 Nov when his arms came nearer his sides, 16 Nov when the tee lost its set-in armhole seam)


def test_an_untraced_shoe_is_drawn_exactly_as_before():
    h = hashlib.sha256()
    for c, s in UNTRACED:
        shoes = Piece(c, answer(c, shoe_style=s), "#5a3a22")
        for bottom in (SHORTS, TROUSERS):
            pieces = dict(base=TEE, bottom=bottom, shoes=shoes)
            h.update(figure(pieces, uid="d").encode())
            f = fig.front_shoe(plan(pieces).get("shoes").spec, K_PX, uid="z", ankle=fig._ankle(), toes=fig.TOE_LINE)
            h.update((f.outline + f.body + f.defs).encode())
    assert h.hexdigest() == UNTRACED_DIGEST


# ---- rules every front shoe keeps

LIP_CM = 1.5   # the collar's padded front, rounding up to its sides, stands this far above the opening's front edge


def every_front_shoe():
    """(name, the shoe from the front with the wearer's ankle in it) for every template but the sandal, and the
    no-show cuts."""
    for c, s in UNTRACED[:-1]:
        yield s, front(spec_of(c, s))
    for s in frontshoe.CUT_STYLES:   # cut no-show: the collar and the opening lower
        yield f"{s} no_show", front(spec_of("sneakers", s, footwear_height="no_show"))


def after_the_leg(shoe) -> list[tuple[str, list[tuple[float, float]]]]:
    """What is painted after the wearer's ankle (the tongue apart: it is in front of the leg), each element's
    markup and points."""
    i = shoe.body.index('<g clip-path="url(#za)">')
    depth, j = 0, i
    for m in re.finditer(r"<g[ >]|</g>", shoe.body[i:]):
        depth += -1 if m.group() == "</g>" else 1
        if depth == 0:
            j = i + m.end()
            break
    rest = re.sub(r'<g data-part="tongue">.*?</g>', "", shoe.body[j:])
    out = []
    for el in re.findall(r"<(?:path|circle|ellipse|rect)[^>]*>", rest):
        if 'd="' in el:
            out.append((el, _flat(re.search(r'd="([^"]+)"', el).group(1))))
        elif "cx=" in el:
            out.append((el, [(float(re.search(r'cx="([-\d.]+)"', el).group(1)), float(re.search(r'cy="([-\d.]+)"', el).group(1)))]))
        else:
            x, y = (float(re.search(rf'{k}="([-\d.]+)"', el).group(1)) for k in ("x", "y"))
            out.append((el, [(x, y)]))
    return out


def test_the_collar_back_and_lining_are_painted_before_the_leg():
    for name, shoe in every_front_shoe():
        leg = shoe.body.index('clip-path="url(#za)"')
        lining = [m.start() for m in re.finditer(r'stroke-width="1.4" stroke-linejoin="round"/>', shoe.body)]
        assert lining and max(lining) < leg, name
        for el, _ in after_the_leg(shoe):
            assert 'stroke-width="1.4" stroke-linejoin="round"/>' not in el or "fill=\"none\"" in el, (name, el)


def test_nothing_of_the_shoe_hides_the_leg_above_its_opening():
    """Up the front of the ankle, from the opening's front edge to where the leg above takes over, the leg shows:
    each point is outside the upper's outline or where the leg is seen through it."""
    for name, shoe in every_front_shoe():
        view = frontshoe._View(K_PX)
        upper, rim = _flat(shoe.upper), _flat(shoe.rim)
        seen = [_flat(d) for d in shoe.seen]
        top = shoe.anchors["ankle"][1]
        bad = []
        for k in range(3, 10):   # across the middle of the ankle: its sides are behind the collar's rounded sides
            a = math.pi * k / 12
            for h in range(2, 30):
                x, y = view(frontshoe.ANKLE_HALF_CM * math.cos(a),
                            frontshoe.ANKLE_U + frontshoe.ANKLE_DEPTH_CM * math.sin(a) / frontshoe.LENGTH, h)
                near = [q[1] for q in rim if abs(q[0] - x) <= 1.8]
                if y <= top or not near or y > max(near) - LIP_CM * K_PX:
                    continue   # above where the leg takes over, or the shoe's front and the collar's lip
                if not (_inside((x, y), rim) or y < min(near)):
                    continue
                if _inside((x, y), upper) and not any(_inside((x, y), s) for s in seen):
                    bad.append((round(x), round(y)))
        assert not bad, (name, bad[:5])


def test_every_detail_lies_on_the_shoe():
    for name, shoe in every_front_shoe():
        outline = _flat(shoe.outline)
        for el, pts in after_the_leg(shoe):
            off = [q for q in pts if not _inside(q, outline) and _clear(q, [(-9e3, -9e3), (9e3, -9e3), (9e3, 9e3), (-9e3, 9e3)], 0)
                   and not any(_inside((q[0] + dx, q[1] + dy), outline) for dx in (-1.5, 0, 1.5) for dy in (-1.5, 0, 1.5))]
            assert not off, (name, el[:80], off[:3])


def turns(pts, step: float = 1.0) -> list[float]:
    """How sharply a closed outline turns, in degrees, at each `step` px along it (so a point's sharpness does not
    depend on how many points the path was written with)."""
    even, carry = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        d = math.dist(a, b)
        s = step - carry
        while d and s <= d:
            even.append((a[0] + (b[0] - a[0]) * s / d, a[1] + (b[1] - a[1]) * s / d))
            s += step
        carry = d - (s - step) if d else carry
    out = []
    for a, b, c in zip(even, even[1:] + even[:1], even[2:] + even[:2], strict=True):
        t = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]))
        out.append(abs((t + 180) % 360 - 180))
    return out


@pytest.mark.parametrize("style", ["low_sneaker", "runner", "slip_on"])
def test_a_no_show_cut_lowers_the_collar_and_the_opening(style):
    """`footwear_height=no_show` (a low-cut runner or slip-on): the collar stands lower round the ankle, and the
    opening dips further below the ankle bones, lowest at its sides, so more of the ankle shows above it. The
    shoe's front (the toe, the laces) stays where it was."""
    plain = front(spec_of("sneakers", style))
    cut = front(spec_of("sneakers", style, footwear_height="no_show"))
    rim, low = _flat(plain.rim), _flat(cut.rim)
    # every point of the opening's edge is lower on the drawing (y down), its sides the most
    assert all(b[1] > a[1] + 0.8 * K_PX for a, b in zip(rim, low, strict=True))
    sides = [i for i, q in enumerate(rim) if q[0] in (min(x for x, _ in rim), max(x for x, _ in rim))]
    assert all(low[i][1] - rim[i][1] > min(b[1] - a[1] for a, b in zip(rim, low, strict=True)) for i in sides)
    # the top of the shoe beside the ankle is lower too; its toe and sole are not
    assert min(y for _, y in _flat(cut.upper)) > min(y for _, y in _flat(plain.upper)) + 0.8 * K_PX
    # a trouser hem meets the opening where it now is, lower; every other anchor stays
    moved = ("opening", "opening_back")
    assert {k: v for k, v in cut.anchors.items() if k not in moved} == {k: v for k, v in plain.anchors.items() if k not in moved}
    assert all(cut.anchors[k][1] > plain.anchors[k][1] + 0.8 * K_PX for k in moved)
    toe = lambda s: [q for q in _flat(s.outline) if q[1] > s.anchors["ball"][1]]   # noqa: E731
    assert toe(cut) == toe(plain)
    # the leg is seen down to the lower opening: more of the ankle shows
    assert max(y for d in cut.seen for _, y in _flat(d)) > max(y for d in plain.seen for _, y in _flat(d))


def test_the_shoes_outline_has_no_points_or_horns():
    """The collar's top edge is a smooth arc: the outline turns no more sharply anywhere than at #214's rounded
    collar joins (about 60 degrees a pixel)."""
    for name, shoe in every_front_shoe():
        assert max(turns(_flat(shoe.upper))) < 65, name


CROPPED = Piece("trousers", answer("trousers", {"pant_length": "ankle"}, leg_shape="slim", trouser_break="cropped"),
                "#6f7278")


@pytest.mark.parametrize("c, s", [("sneakers", "low_sneaker"), ("sneakers", "runner"), ("sneakers", "slip_on"),
                                  ("dress_shoes", "loafer"), ("dress_shoes", "derby"), ("dress_shoes", "oxford")])
def test_no_point_of_a_low_collar_sticks_up_beside_the_bare_ankle(c, s):
    """Under cropped trousers the ankle shows, and where the collar's top edge meets the leg what shows of the shoe
    is a rounded shoulder: on a small circle there, at least a quarter of it is shoe. A dress shoe's raw crown once
    left a sliver standing up beside the ankle in a point (#223 review)."""
    lay = plan(dict(base=TEE, bottom=CROPPED, shoes=Piece(c, answer(c, shoe_style=s), "#5a3a22")))
    shoes = lay.get("shoes")
    t = shoes.transforms[0]
    path = fig._moved(lay.body.legs[0], (t[0], 0.0, 0.0, 1.0, -t[0] * t[4], -t[5]))
    shoe = fig.front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, uid="z", ankle=fig._ankle(),
                          ankle_path=path, toes=fig.TOE_LINE)
    upper, leg, seen = _flat(shoe.upper), _flat(path), [_flat(d) for d in shoe.seen]
    covered = lambda p: _inside(p, leg) and any(_inside(p, q) for q in seen)   # noqa: E731
    pts = []
    for a, b in zip(upper, upper[1:] + upper[:1], strict=True):
        n = max(1, int(math.dist(a, b) / 0.5))
        pts += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
    meets = [b for a, b in zip(pts[-1:] + pts[:-1], pts, strict=True) if covered(a) != covered(b)]
    assert meets, s
    for x, y in meets:
        ring = [(x + 4 * math.cos(math.radians(d)), y + 4 * math.sin(math.radians(d))) for d in range(360)]
        shown = sum(_inside(q, upper) and not covered(q) for q in ring)
        assert shown >= 90, (s, round(x, 1), round(y, 1), shown)
