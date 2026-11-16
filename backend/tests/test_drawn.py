"""A shoe drawn by Claude, made safe, shown and checked (`closet/drawing/drawn.py`): the sanitiser against everything
it must keep out, the preview on two legs and its PNG, and each automatic check passing on the liked examples and
failing on drawings made wrong on purpose. No call to Claude is made here.
"""
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from closet.drawing import drawn
from closet.drawing.drawn import DrawingError

BENCH = Path(__file__).resolve().parents[2] / "bench" / "experiments" / "shoe_drawn" / "EXAMPLES"
LOW = {"silhouette": {"height": "low"}, "opening_front_y": 32.0, "one_side_mark": False}
SHEETS = {"trainer": {**LOW, "opening_front_y": 26.0}, "dress-shoe": LOW,
          "boat-shoe": {**LOW, "silhouette": {"height": "low_profile"}, "opening_front_y": 79.0}}
# a plain low shoe in the frame: a sole band, an upper from y 40 down to the sole, its top across the leg
PLAIN = ('<path d="M20,190 C16,232 60,240 100,240 C140,240 184,232 180,190 Z" fill="#5b3822" stroke="#26221f" '
         'stroke-width="4"/><path d="M24,196 C20,140 40,100 62,60 L66,40 L134,40 L138,60 C160,100 180,140 176,196 Z" '
         'fill="#b5622f" stroke="#26221f" stroke-width="4"/>')


def sheet(height="low", opening=40.0, mark=False) -> dict:
    return {"silhouette": {"height": height}, "opening_front_y": opening, "one_side_mark": mark}


# ------------------------------------------------------------------ the worked examples

def _canon(el) -> tuple:
    return (el.tag.split("}")[-1], tuple(sorted((k, v) for k, v in el.attrib.items() if k != "id")),
            tuple(_canon(c) for c in el))


def test_the_worked_examples_are_the_bench_drawings_the_owner_liked():
    for name in ("dress-shoe", "boat-shoe"):
        assert drawn.example(name) == (BENCH / f"{name}.svg").read_text(encoding="utf-8")
    full = ET.fromstring((BENCH / "trainer-full.svg").read_text(encoding="utf-8"))
    group = next(g for g in full.iter() if g.get("id") == "shoe")
    ours = ET.fromstring(drawn.example("trainer"))
    assert _canon(ours) == _canon(group)   # the shoe group, ids (and comments) left out
    assert "id=" not in drawn.example("trainer") and "<!--" not in drawn.example("trainer")
    assert drawn.EXAMPLES == ("trainer", "dress-shoe", "boat-shoe")


@pytest.mark.parametrize("name", drawn.EXAMPLES)
def test_the_worked_examples_pass_every_check(name):
    assert drawn.checks(drawn.example(name), None, SHEETS[name]) == []


# ------------------------------------------------------------------ made safe

def test_plain_shapes_and_their_geometry_are_kept():
    text = ('<g transform="translate(10, 20) rotate(5 100 40)" stroke-linejoin="round">'
            '<path d="M0,0 L10,10 Z" fill="#AbC" stroke="#26221F" stroke-width="4" fill-rule="evenodd"/>'
            '<circle cx="5" cy="6" r="2.5" fill="none" opacity="0.5"/><ellipse cx="1" cy="2" rx="3" ry="4" fill="#123456"/>'
            '<rect x="1" y="2" width="3" height="4" rx="1" fill="#fff"/><line x1="0" y1="0" x2="5" y2="5" stroke="#000"'
            ' stroke-linecap="round" stroke-dasharray="8 5"/><polyline points="0,0 5,5 10,0" fill="none" stroke="#000"/>'
            '<polygon points="0,0 5,5 10,0" fill="#000" fill-opacity=".4" stroke-opacity="1"/></g>')
    out = drawn.sanitise(text)
    assert out.startswith('<g transform="translate(10 20) rotate(5 100 40)" stroke-linejoin="round">')
    for kept in ('d="M0,0 L10,10 Z"', 'fill="#abc"', 'stroke="#26221f"', 'stroke-width="4"', 'fill-rule="evenodd"',
                 '<circle cx="5" cy="6" r="2.5" fill="none" opacity="0.5"/>', '<ellipse', '<rect x="1"', '<line x1="0"',
                 'stroke-dasharray="8 5"', '<polyline points="0,0 5,5 10,0"', '<polygon', 'fill-opacity=".4"'):
        assert kept in out
    assert drawn.sanitise(out) == out   # what it gives is kept as it is


@pytest.mark.parametrize("bad", [
    '<script>alert(1)</script>', '<text x="1" y="2">ADIDAS</text>', '<image href="http://x/y.png" width="9" height="9"/>',
    '<a href="https://example.com"><path d="M0,0 L1,1"/></a>', '<style>path{fill:red}</style>',
    '<use href="#shoe"/>', '<defs><path id="p" d="M0,0"/></defs>', '<linearGradient id="g"/>',
    '<foreignObject><div>x</div></foreignObject>', '<clipPath><rect width="9" height="9"/></clipPath>',
    '<svg viewBox="0 0 9 9"><path d="M0,0 L1,1"/></svg>', '<other:path xmlns:other="urn:x" d="M0,0"/>',
])
def test_every_other_element_is_dropped_with_everything_inside_it(bad):
    out = drawn.sanitise(f'{bad}<path d="M0,0 L5,5" fill="#000"/>')
    assert out == '<path d="M0,0 L5,5" fill="#000"/>'


def test_every_other_attribute_and_value_is_dropped():
    out = drawn.sanitise('<path id="up" class="a" style="fill:red" onload="alert(1)" d="M0,0 L5,5" '
                         'fill="url(#g)" stroke="red" stroke-width="4px" opacity="2" transform="skewX(30)" '
                         'xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#x" filter="url(#f)" '
                         'stroke-linejoin="arcs" mask="url(#m)"/>'
                         '<rect x="javascript:1" y="2" width="3" height="4" fill="#12345"/>')
    assert out == '<path d="M0,0 L5,5"/>\n<rect y="2" width="3" height="4"/>'
    assert drawn.sanitise('<path d="M0 0 L url(#x)" fill="#000"/>') == '<path fill="#000"/>'
    assert drawn.sanitise('<path transform="translate(1) scale(2 3) matrix(1 0 0 1 0 0)" d="M0,0"/>') == \
        '<path transform="translate(1) scale(2 3) matrix(1 0 0 1 0 0)" d="M0,0"/>'
    for t in ("translate(1 2 3)", "rotate(1 2)", "matrix(1 2 3)", "translate(1) evil", "translate(a)"):
        assert "transform" not in drawn.sanitise(f'<path transform="{t}" d="M0,0"/>')


def test_svg_namespaced_shapes_are_kept_and_comments_go():
    out = drawn.sanitise('<!-- the sole --><svg:path xmlns:svg="http://www.w3.org/2000/svg" d="M0,0 L1,1"/>'
                         '<path xmlns="http://www.w3.org/2000/svg" d="M2,2 L3,3"/>')
    assert out == '<path d="M0,0 L1,1"/>\n<path d="M2,2 L3,3"/>'


@pytest.mark.parametrize("nasty,words", [
    ('<!DOCTYPE g [<!ENTITY a "aaaa">]><path d="M0,0"/>', "declares"),
    ('<!ENTITY lol "lol"><path d="M0,0"/>', "declares"),
    ('<path d="M0,0"/><![CDATA[<script>x</script>]]>', "declares"),
    ('<?xml-stylesheet href="evil.css"?><path d="M0,0"/>', "declares"),
    ('<path d="M0,0" fill="&lol;"/>', "not well-formed"),
    ('<path d="M0,0">', "not well-formed"),
    ('<path d="M0,0"/></g><g>', "not well-formed"),
    ('<text>only words</text>', "Nothing drawable"),
    ('<g><g fill="#000"/></g>', "Nothing drawable"),
    ('', "Nothing drawable"),
])
def test_nasty_input_is_refused_with_a_reason(nasty, words):
    with pytest.raises(DrawingError, match=words):
        drawn.sanitise(nasty)


def test_size_caps():
    with pytest.raises(DrawingError, match="not SVG text"):
        drawn.sanitise(None)
    with pytest.raises(DrawingError, match="too long"):
        drawn.sanitise('<path d="M0,0"/>' + " " * drawn.MAX_CHARS)
    drawn.sanitise('<path d="M0,0"/>' * drawn.MAX_ELEMENTS)
    with pytest.raises(DrawingError, match="too many shapes"):
        drawn.sanitise('<path d="M0,0"/>' * (drawn.MAX_ELEMENTS + 1))
    deep = "<g>" * drawn.MAX_DEPTH + '<path d="M0,0"/>' + "</g>" * drawn.MAX_DEPTH
    assert drawn.sanitise(deep).count("<g>") == drawn.MAX_DEPTH
    with pytest.raises(DrawingError, match="deep"):
        drawn.sanitise("<g>" + deep + "</g>")


# ------------------------------------------------------------------ shown

def widths(svg: str) -> list[tuple[str, str]]:
    return re.findall(r'stroke="(#[0-9a-f]+)"[^>]*?stroke-width="([0-9.]+)"', svg)


def test_ink_lines_are_thickened_as_the_figure_will_draw_them():
    text = ('<g stroke="#26221f" stroke-width="1.6"><path d="M0,0"/><path d="M1,1" stroke="#eadfc6"/></g>'
            '<path d="M2,2" stroke="#26221f" stroke-width="10"/><path d="M3,3" stroke="#3a2a24" stroke-width="4.5"/>')
    out = drawn.thicken(drawn.sanitise(text), drawn.TODAY_LINE)
    assert f'{1.6 * drawn.TODAY_LINE:.2f}' in out
    assert 'stroke="#eadfc6" stroke-width="1.6"' in out   # a light line in an ink group keeps its width
    assert 'stroke="#26221f" stroke-width="10"' in out    # laces drawn as thick ink strokes are left as they are
    assert 'stroke="#3a2a24" stroke-width="4.5"' in out   # other colours too
    assert drawn.TODAY_LINE == pytest.approx(2.2 / (4 * 0.297))


def test_the_preview_puts_the_pair_on_two_legs():
    left = drawn.example("dress-shoe")
    svg = drawn.preview_svg(left)
    root = ET.fromstring(svg)
    assert root.get("viewBox") == "0 0 440 400"
    assert svg.count(f'fill="{drawn.PREVIEW_SOCK}"') == 2   # two socks
    assert 'translate(418,150) scale(-1,1)' in svg and svg.index(drawn.PREVIEW_SOCK) < svg.index("#b5622f")   # leg first
    assert f'stroke-width="{4 * drawn.TODAY_LINE:.2f}"' in svg and 'rotate' not in svg   # no tilt
    own = drawn.preview_svg(left, drawn.example("boat-shoe"))
    assert "scale(-1,1)" not in own and "translate(218,150)" in own and "#73523f" in own
    plain = drawn.preview_svg(left, line=1)
    assert 'stroke-width="1.6"' in plain


def test_the_check_png_shows_the_preview_large_and_at_phone_size():
    data = drawn.check_png(drawn.example("dress-shoe"))
    im = Image.open(io.BytesIO(data))
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and im.size == (730, 509)
    px = im.convert("RGB")
    assert px.getpixel((10, 10)) == (241, 238, 232)        # the large one's background
    assert px.getpixel((650, 10)) == (255, 255, 255)       # above the small one: blank
    assert px.getpixel((620, 500)) != (255, 255, 255)      # the small one, at the bottom right
    assert drawn.example_png("trainer")[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------------ checked

def test_a_plain_low_shoe_passes():
    assert drawn.checks(PLAIN, None, sheet()) == []


def test_a_shoe_off_the_ground_is_found():
    lifted = f'<g transform="translate(0 -20)">{PLAIN}</g>'
    found = drawn.checks(lifted, None, sheet(opening=20))
    assert len(found) == 1 and "does not stand on the ground" in found[0] and "y 222" in found[0]
    sunk = f'<g transform="translate(0 12)">{PLAIN}</g>'
    assert "does not stand on the ground" in drawn.checks(sunk, None, sheet(opening=52))[0]


def test_a_shoe_out_of_the_frame_is_found():
    wide = f'<g transform="translate(100 240) scale(1.25 1) translate(-100 -240)">{PLAIN}</g>'
    found = drawn.checks(wide, None, sheet())
    assert len(found) == 1 and "out of the frame" in found[0]


def test_a_shoe_too_tall_is_found_by_its_height():
    tall = f'<g transform="translate(100 240) scale(1 1.25) translate(-100 -240)">{PLAIN}</g>'   # its top at y -10
    found = drawn.checks(tall, None, sheet(opening=-10))
    assert len(found) == 1 and "too tall" in found[0] and "low shoe" in found[0]
    assert drawn.checks(tall, None, sheet("ankle", opening=-10)) == []   # a boot may come up to y -90
    taller = f'<g transform="translate(100 240) scale(1 1.75) translate(-100 -240)">{PLAIN}</g>'   # top at y -110
    found = drawn.checks(taller, None, sheet("boot", opening=-110))
    assert len(found) == 1 and "boot's top" in found[0]


def test_a_leg_showing_through_the_shoe_is_found():
    ring = PLAIN.replace('fill="#b5622f"', 'fill="none"')   # an upper drawn as an outline only
    found = drawn.checks(ring, None, sheet())
    assert any("leg is not inside the shoe" in f for f in found)
    hole = PLAIN + '<rect x="90" y="120" width="20" height="40" fill="none" stroke="#26221f" stroke-width="1"/>'
    assert drawn.checks(hole, None, sheet()) == []   # lines on the upper do not let the leg through


TAB = '<path d="M88,60 L88,-10 L112,-10 L112,60 Z" fill="#f2f0ea" stroke="#26221f" stroke-width="1.6"/>'


def test_a_shoe_hiding_the_leg_above_its_opening_is_found_for_every_kind_unless_it_is_behind_the_leg():
    """Step D: the rule was for low shoes only; now nothing in FRONT of the leg may cover it more than 25 units above
    the opening front, for a boot too (above the front of its shaft's top). What is behind the leg (a pull tab at the
    back) is drawn before the leg, which covers it, so it is not counted."""
    tongue = PLAIN + TAB
    for height in ("low", "low_profile", "ankle", "boot"):
        found = drawn.checks(tongue, None, sheet(height, opening=40))
        assert any("hides the leg above its opening" in f for f in found), height
        assert not any("hides the leg" in f for f in drawn.checks({"behind": TAB, "front": PLAIN}, None,
                                                                    sheet(height, opening=40))), height
    collar = PLAIN + '<path d="M62,60 L64,20 L72,60 Z M138,60 L136,20 L128,60 Z" fill="#b5622f"/>'   # beside the leg
    assert drawn.checks(collar, None, sheet(opening=40)) == []


def test_an_opening_the_sheet_puts_elsewhere_is_found():
    found = drawn.checks(drawn.example("dress-shoe"), None, {**LOW, "opening_front_y": 48.0})
    assert len(found) == 1 and "opening_front_y is 48" in found[0] and "about y 30" in found[0]


def test_a_mark_on_one_side_needs_a_right_drawing_which_is_checked_too():
    found = drawn.checks(PLAIN, None, sheet(mark=True))
    assert len(found) == 1 and "no right drawing" in found[0]
    lifted = f'<g transform="translate(0 -20)">{PLAIN}</g>'
    found = drawn.checks(PLAIN, lifted, sheet(mark=True))
    assert any(f.startswith("The right shoe: It does not stand on the ground") for f in found)


def test_nothing_painted_in_the_frame_is_found():
    far = '<rect x="400" y="400" width="10" height="10" fill="#000"/>'
    assert drawn.checks(far, None, sheet()) == ["Nothing of it is painted inside the frame."]


def test_a_drawing_resvg_cannot_render_is_refused_with_a_reason(monkeypatch):
    import resvg_py

    def refuse(**kw):
        raise ValueError("render failure")
    monkeypatch.setattr(resvg_py, "svg_to_bytes", refuse)
    with pytest.raises(DrawingError, match="could not be rendered"):
        drawn.check_png(PLAIN)
    with pytest.raises(DrawingError, match="could not be rendered"):
        drawn.checks(PLAIN, None, sheet())


def test_a_shoe_that_never_covers_the_leg_is_not_also_said_to_have_its_opening_elsewhere():
    found = drawn.checks('<rect x="0" y="230" width="40" height="10" fill="#000"/>', None, sheet())
    assert any("leg is not inside the shoe" in f for f in found) and not any("opening_front_y" in f for f in found)


# ------------------------------------------------------------------ behind the leg and in front (step D)

def test_a_shoe_has_a_part_behind_the_leg_and_a_part_in_front_both_made_safe():
    s = drawn.side({"behind": '<path d="M0,0" onclick="x()"/><script>x</script>', "front": PLAIN})
    assert s.behind == '<path d="M0,0"/>' and s.front == drawn.sanitise(PLAIN)
    assert drawn.side(PLAIN) == drawn.Side(drawn.sanitise(PLAIN), "")   # one text (version 1): all in front
    assert drawn.side(s) == s and s.to_json() == {"behind": s.behind, "front": s.front}
    assert drawn.side({"behind": "<text>tab</text>", "front": PLAIN}).behind == ""   # nothing drawable behind: none
    assert drawn.side({"front": PLAIN}).behind == ""
    with pytest.raises(DrawingError, match="Nothing drawable"):
        drawn.side({"behind": PLAIN, "front": "<text/>"})   # the front must have something
    with pytest.raises(DrawingError, match="not SVG text"):
        drawn.side({"behind": 3, "front": PLAIN})
    with pytest.raises(DrawingError, match="too long"):   # one drawing's caps hold for both parts together
        drawn.side({"behind": '<path d="M0,0"/>' + " " * (drawn.MAX_CHARS // 2), "front": PLAIN + " " * (drawn.MAX_CHARS // 2)})
    half = '<path d="M0,0"/>' * (drawn.MAX_ELEMENTS // 2 + 1)
    with pytest.raises(DrawingError, match="too many shapes"):
        drawn.side({"behind": half, "front": half})


def test_the_leg_covers_what_is_behind_it_in_the_checks():
    # a back the leg covers is not "the leg showing through", nor counted as hiding the leg
    back = '<path d="M60,30 L140,30 L140,200 L60,200 Z" fill="#3a2a24"/>'
    assert drawn.checks({"behind": back, "front": PLAIN}, None, sheet()) == []
    ring = PLAIN.replace('fill="#b5622f"', 'fill="none"')   # an upper with nothing in front of the leg
    assert any("leg is not inside the shoe" in f for f in drawn.checks({"behind": back, "front": ring}, None, sheet()))
    m = drawn.measure({"behind": TAB, "front": PLAIN})
    assert m["box"][1] == pytest.approx(-11, abs=1.5)   # its height counts what is behind too
    assert m["front"].sum() < m["painted"].sum()


def test_a_kept_drawing_is_read_for_the_figure_with_its_opening_from_the_sheet():
    kept = {"version": 2, "left": {"behind": TAB, "front": PLAIN}, "right": None,
            "sheet": {"silhouette": {"height": "low"}, "opening_front_y": 40, "top_y": 38, "instep_y": 37}}
    s = drawn.stored(kept)
    assert s.left == drawn.side(kept["left"]) and s.right is None and s.low and s.hinge == 40
    assert (s.opening, s.top, s.instep) == (40, 38, 37)
    # the instep keeps to its side of the opening by kind: above a low shoe's opening front, below a boot's
    assert drawn.stored({**kept, "sheet": {**kept["sheet"], "instep_y": 60}}).instep == 39
    boot = drawn.stored({**kept, "sheet": {**kept["sheet"], "silhouette": {"height": "ankle"}, "opening_front_y": -30,
                                           "instep_y": -40}})
    assert not boot.low and boot.instep == -29 and boot.hinge == -29
    # no height named: a boot when its instep is below its opening
    assert not drawn.stored({**kept, "sheet": {"opening_front_y": -30, "top_y": -40, "instep_y": 90}}).low
    one = drawn.stored({**kept, "version": 1, "left": PLAIN, "right": PLAIN})
    assert one.left == drawn.Side(drawn.sanitise(PLAIN)) and one.right == one.left
    for bad in ({**kept, "sheet": {**kept["sheet"], "top_y": None}}, {**kept, "sheet": {**kept["sheet"], "top_y": True}},
                {**kept, "sheet": {**kept["sheet"], "top_y": 900}}, {**kept, "left": None}, {"left": PLAIN}, []):
        with pytest.raises(DrawingError):
            drawn.stored(bad)
