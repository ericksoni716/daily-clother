"""A shoe Claude drew from its photos, on the As worn figure (step D: `figure._drawn_pair`, `figure._on_drawing`,
`worn._socks`, `illustrations.describe`): placed on the feet, its part behind the leg drawn before the wearer and its
part in front where the front view goes, the toes turned out below a hinge, the lines thickened, the hem resting on
the drawing's opening, full-length trousers keeping their own length with the sock under them, and the front view
drawn exactly as before whenever there is no drawing it can use."""
import json
import math
import re
from dataclasses import replace
from pathlib import Path

import pytest

from closet import db
from closet.drawing import drawn
from closet.drawing import figure as fig
from closet.drawing.figure import K_PX, Piece, figure, plan
from closet.tagger.schema import Details, ItemTags, Silhouette

BENCH = Path(__file__).resolve().parents[2] / "bench" / "experiments" / "shoe_drawn" / "EXAMPLES"


def answer(category: str, style: str = "", silhouette: dict | None = None, **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**({"shoe_style": style} if style else {}), **details), details_confidence=0.9,
        brand=None, size=None, material=None, needs_shot=None).model_dump(mode="json")


def kept(left, right=None, opening=32.0, top=32.0, instep=30.0, height="low", version=2, tab=False) -> dict:
    """A drawing as `shoedraw` keeps it (`tab`: the sheet says it has a pull tab at the front)."""
    def shoe(s):
        return s if version == 1 else drawn.side(s).to_json()
    return {"version": version, "left": shoe(left), "right": shoe(right) if right else None,
            "sheet": {"silhouette": {"height": height}, "opening_front_y": opening, "top_y": top, "instep_y": instep,
                      "front_pull_tab": tab},
            "made_at": "2026-11-15T12:00:00+00:00"}


@pytest.fixture
def conn(cfg):
    path = cfg.db_path("main")
    db.migrate(path, cfg.local_backups_dir)
    c = db.connect(path)
    yield c
    c.close()


DRESS_DRAWING = kept(drawn.example("dress-shoe"))
BOAT_DRAWING = kept(drawn.example("boat-shoe"), opening=79.3, top=79.3, instep=77.3, height="low_profile")
BOOT_DRAWING = kept(drawn.split_example("boot"), opening=-32, top=-46, instep=84, height="ankle", tab=True)


def _back_tab_boot() -> drawn.Side:
    """The bench boot with its tab taken as a tab at the BACK of the shaft: behind the leg, the rest in front."""
    import xml.etree.ElementTree as ET
    els = list(ET.fromstring(f"<g>{(BENCH / 'boot.svg').read_text(encoding='utf-8')}</g>"))
    text = lambda keep: "".join(ET.tostring(el, encoding="unicode") for el in els if keep(el))  # noqa: E731
    return drawn.Side(front=text(lambda el: "tab" not in el.get("id", "")), behind=text(lambda el: "tab" in el.get("id", "")))


BACK_TAB_BOOT = kept(_back_tab_boot(), opening=-32, top=-46, instep=84, height="ankle")
RUNNER_DRAWING = kept((BENCH / "runner-left.svg").read_text(), (BENCH / "runner-right.svg").read_text(), opening=24,
                      top=16, instep=22)

OXFORD = Piece("dress_shoes", answer("dress_shoes", "oxford", toe_cap="stitched"), "#b5622f")
LOAFER = Piece("dress_shoes", answer("dress_shoes", "loafer"), "#73523f")
CHELSEA = Piece("boots", answer("boots", "chelsea_boot"), "#6e5a3f")
RUNNER = Piece("sneakers", answer("sneakers", "runner"), "#f1f0eb")
TEE = Piece("tee", answer("tee", silhouette={"sleeve": "short"}), "#f4f2ee")
SHORTS = Piece("shorts", None, "#6f7550")
FULL = Piece("trousers", answer("trousers", silhouette={"leg": "straight", "pant_length": "full"}), "#6f7278")
WIDE = Piece("trousers", answer("trousers", silhouette={"leg": "wide", "pant_length": "full"}), "#6f7278")
ANKLE = Piece("trousers", answer("trousers", silhouette={"leg": "straight", "pant_length": "ankle"}), "#6f7278")
SOCK = Piece("other", answer("other", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")


def outfit(shoes: Piece, bottom: Piece = SHORTS, socks: bool = True) -> dict:
    return {"base": TEE, "bottom": bottom, "shoes": shoes, **({"accessories": [SOCK]} if socks else {})}


def group(svg: str, gid: str) -> str:
    """The markup of the group <g id=gid>, to its closing tag."""
    start = svg.index(f'<g id="{gid}">')
    depth, at = 0, start
    for m in re.finditer(r"<g\b[^>]*?(/?)>|</g>", svg[start:]):
        if m.group(0) == "</g>":
            depth -= 1
        elif not m.group(1):
            depth += 1
        if depth == 0:
            return svg[start:start + m.end()]
        at = m.end()
    raise AssertionError(at)


def matrix(text: str) -> tuple[float, ...]:
    """An SVG transform list (matrix, translate, scale) as one matrix (a, b, c, d, e, f)."""
    out = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in re.findall(r"(matrix|translate|scale)\(([^)]*)\)", text):
        v = [float(x) for x in args.replace(",", " ").split()]
        if name == "translate":
            m = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            m = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        else:
            m = tuple(v)
        a, b, c, d, e, f = out
        out = (a * m[0] + c * m[1], b * m[0] + d * m[1], a * m[2] + c * m[3], b * m[2] + d * m[3],
               a * m[4] + c * m[5] + e, b * m[4] + d * m[5] + f)
    return out


def apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def copies(part: str) -> list[tuple[tuple[float, ...], str]]:
    """Each foot's copy in a group of drawn shoes: its placing (the figure's copy matrix, then the frame's) and what
    is inside."""
    found = list(re.finditer(r'<g transform="(matrix\([^)]*\))"><g transform="(translate\([^)]*\) scale\([^)]*\) '
                             r'translate\(-100 -240\))">', part))
    return [(matrix(m.group(1) + " " + m.group(2)), part[m.end():found[n + 1].start() if n + 1 < len(found) else None])
            for n, m in enumerate(found)]


# ------------------------------------------------------------------ drawn, or exactly as before

def test_a_drawn_shoe_is_drawn_on_both_feet_with_ids_unique():
    svg = figure(outfit(replace(OXFORD, drawn=DRESS_DRAWING)), uid="a")
    pair = group(svg, "ap")
    assert len(copies(pair)) == 2 and pair.count("#5b3822") == 4   # the sole, on each foot, above and below the hinge
    ids = re.findall(r'\bid="([^"]+)"', svg)
    assert len(ids) == len(set(ids)) and {"aju", "ajd"} <= set(ids)
    assert 'id="aq"' not in svg   # nothing of the dress shoe is behind the leg
    for ref in re.findall(r'url\(#([^)]+)\)', svg):
        assert ref in ids
    today = figure(outfit(OXFORD), uid="a")
    assert today != svg and "#5b3822" not in today


def test_two_figures_with_drawn_shoes_keep_their_ids_apart():
    one, two = (figure(outfit(replace(CHELSEA, drawn=BOOT_DRAWING), FULL), uid=u) for u in ("f1", "f2"))
    assert not set(re.findall(r'\bid="([^"]+)"', one)) & set(re.findall(r'\bid="([^"]+)"', two))


@pytest.mark.parametrize("broken", [
    None, {"left": "<text>no shapes</text>", "right": None, "sheet": DRESS_DRAWING["sheet"]},
    {**DRESS_DRAWING, "sheet": {"opening_front_y": 32.0}}, {**DRESS_DRAWING, "sheet": None}, "not a drawing",
    {**DRESS_DRAWING, "left": {"behind": "", "front": "<script>x</script>"}},
    {**DRESS_DRAWING, "sheet": {**DRESS_DRAWING["sheet"], "opening_front_y": float("nan")}},
], ids=["none", "nothing drawable", "no heights", "no sheet", "not a mapping", "a script only", "not a number"])
@pytest.mark.parametrize("bottom", [SHORTS, FULL, WIDE, ANKLE], ids=["shorts", "full", "wide", "ankle"])
def test_without_a_drawing_it_can_use_the_shoe_is_drawn_exactly_as_today(broken, bottom):
    for shoes in (OXFORD, CHELSEA):
        assert figure(outfit(replace(shoes, drawn=broken), bottom), uid="b") == figure(outfit(shoes, bottom), uid="b")


def test_a_version_1_drawing_is_all_in_front_and_still_drawn():
    one = kept(drawn.example("dress-shoe"), version=1)
    assert isinstance(one["left"], str)
    svg = figure(outfit(replace(OXFORD, drawn=one)), uid="v")
    assert svg == figure(outfit(replace(OXFORD, drawn=DRESS_DRAWING)), uid="v")
    assert 'id="vq"' not in svg and len(copies(group(svg, "vp"))) == 2


# ------------------------------------------------------------------ behind the leg and in front of it

@pytest.mark.parametrize("bottom", [SHORTS, FULL, ANKLE], ids=["shorts", "full", "ankle"])
def test_the_part_behind_the_leg_goes_before_the_wearer_and_the_part_in_front_after_the_legs(bottom):
    svg = figure(outfit(replace(CHELSEA, drawn=BACK_TAB_BOOT), bottom), uid="o")
    behind, front = group(svg, "oq"), group(svg, "op")
    order = [svg.index(f'<g id="o{g}">') for g in ("q", "m", "p", "w")]
    assert order == sorted(order)   # behind, the wearer (and his socks), the shoes' fronts, then the trousers
    assert svg.index("</g>", order[1]) < order[2]
    assert "#4a2c22" in behind and "#4a2c22" not in front   # the pull tab, behind the leg
    assert "#5e2f25" in front and "#5e2f25" not in behind   # the elastic side panels, in front
    assert len(copies(behind)) == len(copies(front)) == 2


def test_under_trousers_that_drop_over_the_shoe_both_parts_keep_to_the_legs():
    svg = figure(outfit(replace(CHELSEA, drawn=BACK_TAB_BOOT), WIDE), uid="c")
    assert fig._on_shoe({"length": "full", "leg": "wide"}, plan(outfit(replace(CHELSEA, drawn=BACK_TAB_BOOT), WIDE))
                        .get("shoes").front) == "over" and 'id="ck"' in svg
    assert group(svg, "cq").startswith('<g id="cq"><g clip-path="url(#ck)">')
    assert group(svg, "cp").startswith('<g id="cp"><g clip-path="url(#ck)">')


def test_an_open_coat_draws_the_part_behind_again_between_its_fronts():
    coat = Piece("coat", answer("coat", silhouette={"top_length": "long"}, collar="notch_lapel",
                                placket="front_placket"), "#232326")
    svg = figure({"base": TEE, "outer": coat, "bottom": FULL, "shoes": replace(CHELSEA, drawn=BACK_TAB_BOOT)}, uid="k")
    assert '<use href="#kq"/><use href="#km"/><use href="#kp"/>' in svg


# ------------------------------------------------------------------ placed on the feet

def test_the_frame_lands_on_each_ankle_its_leg_as_wide_as_the_ankle_its_ground_on_the_sole():
    shoes = plan(outfit(replace(OXFORD, drawn=DRESS_DRAWING))).get("shoes")
    a = shoes.front.anchors
    f = fig._drawn_place(shoes.front)
    assert f.k * (drawn.LEG[1] - drawn.LEG[0]) == pytest.approx(2 * (a["ankle_r"][0] - a["ankle"][0]))
    assert f.y(drawn.GROUND) == pytest.approx(shoes.front.bbox[3] - 2)
    svg = figure(outfit(replace(OXFORD, drawn=DRESS_DRAWING)), uid="p")
    for (m, _), t in zip(copies(group(svg, "pp")), shoes.transforms, strict=True):
        ankle = shoes.point(a["ankle"], shoes.transforms.index(t))
        assert apply(m, 100, drawn.GROUND)[0] == pytest.approx(ankle[0], abs=0.05)
        assert apply(m, 100, drawn.GROUND)[1] == pytest.approx(shoes.box()[3] - 2, abs=0.05)
        assert abs(m[0]) == pytest.approx(f.k, rel=1e-3) and m[3] == pytest.approx(f.k, rel=1e-3)


def test_the_right_drawing_is_used_as_drawn_and_the_left_one_mirrored_without_one():
    svg = figure(outfit(replace(RUNNER, drawn=RUNNER_DRAWING)), uid="r")
    (left, inside_l), (right, inside_r) = copies(group(svg, "rp"))
    assert left[0] > 0 and right[0] > 0   # neither foot is mirrored: the right one is drawn on its own
    # the right drawing is its own file (here the left one turned round inside it, its N drawn to read the right way)
    assert "translate(200 0) scale(-1 1)" in inside_r and "translate(200 0) scale(-1 1)" not in inside_l
    mirrored = figure(outfit(replace(RUNNER, drawn={**RUNNER_DRAWING, "right": None})), uid="r")
    (left, _), (right, _) = copies(group(mirrored, "rp"))
    assert left[0] > 0 and right[0] < 0   # the viewer's right shoe is the left one mirrored


@pytest.mark.parametrize("drawing,hinge", [(DRESS_DRAWING, 32.0), (BOOT_DRAWING, 84.0)], ids=["low shoe", "boot"])
def test_the_toe_turns_out_below_the_hinge_and_nothing_moves_above_it(drawing, hinge):
    shoes = replace(OXFORD if drawing is DRESS_DRAWING else CHELSEA, drawn=drawing)
    assert drawn.stored(drawing).hinge == hinge   # a low shoe's opening front, a boot's instep
    svg = figure(outfit(shoes), uid="h")
    assert f'<clipPath id="hju"><rect x="-1000" y="-1000" width="3000" height="{1000 + hinge + 0.6:.1f}"/>' in svg
    assert f'<clipPath id="hjd"><rect x="-1000" y="{hinge:.1f}"' in svg
    placed = plan(outfit(shoes)).get("shoes")
    toe_out = []
    for n, (m, inside) in enumerate(copies(group(svg, "hp"))):
        shear = re.search(r'clip-path="url\(#hjd\)"><g transform="(matrix\([^)]*\))"', inside).group(1)
        s = matrix(shear)
        assert apply(s, 37, hinge) == pytest.approx((37, hinge), abs=0.01)   # the hinge row stays where it is
        assert apply(s, 100, hinge - 40) != apply(s, 100, hinge)   # (the shear itself; above, the unsheared copy)
        toe = apply(m, *apply(s, 100, drawn.GROUND))
        straight = apply(m, 100, drawn.GROUND)
        toe_out.append(toe[0] - straight[0])
        # as far out as the front view's toe: the same slope from the hinge down
        a = placed.front.anchors
        slope = (a["toe"][0] - a["ankle"][0]) / (a["toe"][1] - a["ankle"][1])
        assert (toe[0] - straight[0]) / (toe[1] - apply(m, 100, hinge)[1]) == pytest.approx(slope * (1 if n == 0 else -1),
                                                                                              rel=1e-2)
    assert toe_out[0] < 0 < toe_out[1]   # the viewer's left toe goes left, the right one right


def test_a_turned_drawing_is_placed_as_drawn_without_turning_it_again():
    from closet.drawing import turned
    out = turned.turn_side(drawn.side(drawn.example("dress-shoe")), "oxford", DRESS_DRAWING["sheet"])
    drawing = {**kept(out, version=3), "view": "turned"}
    assert drawn.stored(drawing).view is drawn.TURNED
    shoes = replace(OXFORD, drawn=drawing)
    placed = plan(outfit(shoes)).get("shoes")
    assert fig._drawn_place(placed.front, drawn.stored(drawing)).shear == 0.0
    assert fig._drawn_place(placed.front, drawn.stored(DRESS_DRAWING)).shear != 0.0   # straight on: the toe slid out
    svg = figure(outfit(shoes), uid="t")
    for _, inside in copies(group(svg, "tp")):
        assert "matrix(1 0" not in inside   # no shear
    assert "translate(-100 -240)" in svg   # the turned frame's middle is x 100, as straight on
    wide = plan(outfit(shoes)).get("shoes").box()
    assert wide[2] - wide[0] > plan(outfit(replace(OXFORD, drawn=DRESS_DRAWING))).get("shoes").box()[2] - \
        plan(outfit(replace(OXFORD, drawn=DRESS_DRAWING))).get("shoes").box()[0]   # room for the wide frame


def test_the_ink_lines_are_as_thick_as_the_figures_and_the_thick_laces_are_kept():
    svg = figure(outfit(replace(LOAFER, drawn=BOAT_DRAWING)), uid="t")
    pair = group(svg, "tp")
    widths = re.findall(r'stroke="#26221f"[^>]*?stroke-width="([0-9.]+)"', pair)
    assert f"{4 * drawn.TODAY_LINE:.2f}" in widths and f"{1.6 * drawn.TODAY_LINE:.2f}" in widths
    assert "4" not in widths and "1.6" not in widths   # no ink line left at the drawing's own weight
    assert 'stroke-width="8.5"' in pair   # the bow, drawn as a thick ink stroke, as it is


# ------------------------------------------------------------------ the hem on the drawing

def test_the_hem_anchors_are_the_drawings_opening():
    shoes = plan(outfit(replace(OXFORD, drawn=DRESS_DRAWING), FULL)).get("shoes")
    f, a = fig._drawn_place(shoes.front), shoes.front.anchors
    today = plan(outfit(OXFORD, FULL)).get("shoes").front.anchors
    assert a["opening"] == pytest.approx((f.x, f.y(32.0))) and a["opening_back"] == pytest.approx((f.x, f.y(32.0)))
    assert a["instep"] == pytest.approx((f.x, f.y(30.0))) and a["sneaker_rim"] == pytest.approx((f.x, f.y(50.0)))
    for k in ("ankle", "ankle_r", "toe"):
        assert a[k] == today[k]
    assert shoes.front.width == plan(outfit(OXFORD, FULL)).get("shoes").front.width
    slim = {"length": "full", "leg": "skinny"}   # narrower than the shoe round its opening: it rests on it
    assert fig._on_shoe(slim, shoes.front) == "at"   # a low shoe: the instep above its opening
    boot = plan(outfit(replace(CHELSEA, drawn=BOOT_DRAWING), FULL)).get("shoes").front
    assert fig._on_shoe(slim, boot) == "on"          # a boot: its shaft's top, above the instep


def test_full_length_trousers_rest_on_a_dress_shoes_opening_and_keep_their_length_over_a_boat_shoe():
    dy = fig._pair(0, 0, 0)[0][5]
    dress = plan(outfit(replace(OXFORD, drawn=DRESS_DRAWING), FULL))
    rim = dress.get("shoes").front.anchors["opening"][1] + dy
    side, drop = fig._hem({"length": "full", "leg": "straight"}, dress.get("shoes").front, 10_000.0)
    assert side + drop == pytest.approx(rim + fig.HEM_FRONT_CM["none"] * K_PX)   # its front just in front of the opening

    boat = plan(outfit(replace(LOAFER, drawn=BOAT_DRAWING), FULL))
    front = boat.get("shoes").front
    side, drop = fig._hem({"length": "full", "leg": "straight"}, front, 10_000.0)
    sneaker = front.anchors["sneaker_rim"][1] + dy
    assert side + drop == pytest.approx(sneaker + fig.HEM_FRONT_CM["none"] * K_PX)   # as long as for a sneaker...
    assert side + drop < front.anchors["opening"][1] + dy - 2 * K_PX                   # ...so a gap over the boat shoe


def test_over_a_low_drawn_shoe_the_sock_shows_between_the_hem_and_the_shoe():
    svg = figure(outfit(replace(LOAFER, drawn=BOAT_DRAWING), FULL), uid="s")
    assert 'id="sxsy"' in svg   # the sock is drawn on the legs, under the trousers
    wearer, pair = svg.index('<g id="sm">'), svg.index('<g id="sp">')
    assert wearer < svg.index('clip-path="url(#sxsy)"') < pair < svg.index('<g id="sw">')
    # without a sock, nothing is drawn there but the leg; under trousers over the front view, no sock as today
    assert 'id="sxsy"' not in figure(outfit(replace(LOAFER, drawn=BOAT_DRAWING), FULL, socks=False), uid="s")
    assert 'id="sxsy"' not in figure(outfit(LOAFER, FULL), uid="s")
    assert 'id="sxsy"' in figure(outfit(LOAFER, SHORTS), uid="s")


def test_a_drawn_shoe_never_buries_the_hem_below_an_ordinary_sneakers_collar():
    for shoes in (replace(OXFORD, drawn=DRESS_DRAWING), replace(LOAFER, drawn=BOAT_DRAWING),
                  replace(RUNNER, drawn=RUNNER_DRAWING), replace(CHELSEA, drawn=BOOT_DRAWING)):
        front = plan(outfit(shoes, FULL)).get("shoes").front
        side, drop = fig._hem({"length": "full", "leg": "straight"}, front, 10_000.0)
        dy = fig._pair(0, 0, 0)[0][5]
        assert side + drop <= front.anchors["sneaker_rim"][1] + dy + fig.HEM_FRONT_CM["none"] * K_PX + 1e-6
        assert side + drop <= front.anchors["opening"][1] + dy + fig.HEM_FRONT_CM["none"] * K_PX + 1e-6


def test_ankle_length_trousers_stop_above_the_back_of_the_drawings_opening():
    shoes = replace(CHELSEA, drawn=BOOT_DRAWING)
    front = plan(outfit(shoes, ANKLE)).get("shoes").front
    dy = fig._pair(0, 0, 0)[0][5]
    side, drop = fig._hem({"length": "ankle", "leg": "straight"}, front, 10_000.0)
    assert drop == 0 and side == pytest.approx(front.anchors["opening_back"][1] + dy - fig.CROP_GAP_CM * K_PX)


# ------------------------------------------------------------------ the item and the app

def test_illustrations_give_the_shoe_its_drawing_whatever_is_happening_to_it_now(conn):
    from closet import illustrations

    conn.execute("INSERT INTO items (id, category, color_hex, created_at, updated_at) "
                 "VALUES ('s1', 'dress_shoes', '#b5622f', 'x', 'x')")
    row = lambda: conn.execute("SELECT * FROM items WHERE id = 's1'").fetchone()   # noqa: E731
    assert illustrations.describe(row()).drawn is None
    for state in ("done", "drawing", "waiting", "failed"):   # a redraw keeps the drawing it has until it is done
        conn.execute("UPDATE items SET drawn = ?, drawn_state = ? WHERE id = 's1'", (json.dumps(DRESS_DRAWING), state))
        assert illustrations.describe(row()).drawn == DRESS_DRAWING
    conn.execute("UPDATE items SET drawn = NULL, drawn_state = 'failed' WHERE id = 's1'")   # the first drawing failed
    assert illustrations.describe(row()).drawn is None
    conn.execute("UPDATE items SET drawn = 'not json', drawn_state = 'done' WHERE id = 's1'")
    assert illustrations.describe(row()).drawn is None
    conn.execute("UPDATE items SET drawn = ?, category = 'tee' WHERE id = 's1'", (json.dumps(DRESS_DRAWING),))
    assert illustrations.describe(row()).drawn is None   # only a shoe


def test_a_pull_tab_at_the_front_shows_in_front_of_the_leg():
    """The owner (16 November): a boot's pull tab at the FRONT shows, in front of the leg, an exception to the rule
    that nothing of a shoe hides the leg above its opening. The owner's boots have a tab at each end."""
    svg = figure(outfit(replace(CHELSEA, drawn=BOOT_DRAWING), SHORTS), uid="t")
    assert "#4a2c22" in group(svg, "tp") and '<g id="tq">' not in svg   # the tab in front; nothing behind
    sheet = BOOT_DRAWING["sheet"]
    assert drawn.checks(drawn.split_example("boot"), None, sheet) == []
    # without the sheet saying it is a front tab, the same drawing hides the leg above its opening: found
    found = drawn.checks(drawn.split_example("boot"), None, {**sheet, "front_pull_tab": False})
    assert any("hides the leg above its opening" in p for p in found)
    # a front tab still may not rise far above the opening
    tall = drawn.Side(front=drawn.split_example("boot").front.replace("-73", "-120").replace("-64", "-111"))
    assert any("pull tab at the front rises too high" in p for p in drawn.checks(tall, None, sheet))


def test_the_split_boot_is_the_bench_boot_the_owner_liked():
    import xml.etree.ElementTree as ET

    def shapes(text: str) -> list[tuple]:
        return sorted(tuple(sorted((k, v) for k, v in el.attrib.items() if k != "id"))
                      for el in ET.fromstring(f"<g>{text}</g>"))
    bench = (BENCH / "boot.svg").read_text(encoding="utf-8")
    behind = (drawn.EXAMPLES_DIR / "boot.behind.svg").read_text(encoding="utf-8")
    front = (drawn.EXAMPLES_DIR / "boot.front.svg").read_text(encoding="utf-8")
    # every shape of the bench file, once, nothing else: all in front, its pull tab the one at the front (the owner's
    # boots have one at each end; the one at the back is hidden behind the leg, so not drawn)
    assert behind.strip() == "" and shapes(front) == shapes(bench)
    assert drawn.checks(drawn.split_example("boot"), None, BOOT_DRAWING["sheet"]) == []


def test_the_demo_boot_is_drawn_on_the_figure(client):
    from closet.config import bundle_dir

    items = json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))["items"]
    drawn_shoes = [i for i in items if i.get("drawn")]
    assert [i["name"] for i in drawn_shoes] == ["Brown boots"]
    boot = drawn_shoes[0]
    assert boot["drawn"]["version"] == drawn.VERSION == 3 and boot["drawn"]["route"] == "demo"
    assert boot["drawn"]["view"] == "front" and drawn.stored(boot["drawn"]).view is drawn.FRONT   # drawn straight on
    assert drawn.side(boot["drawn"]["left"]) == drawn.split_example("boot") and boot["drawn"]["right"] is None
    from closet.tagger.shoedrawing import Sheet
    Sheet.model_validate(boot["drawn"]["sheet"])   # a whole feature sheet, as Claude would write one
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shown = client.get(f"/api/items/{boot['id']}").json()
    assert shown["drawn"]["state"] == "done" and shown["drawn"]["url"] and shown["drawn"]["message"]
    assert shown["drawn_version"] and shown["drawn_state"] == "done"
    assert client.get(shown["drawn"]["url"]).status_code == 200
    svg = client.post("/api/outfits/figure", json={"base": None, "shoes": boot["id"], "bottom": next(
        i["id"] for i in items if i["name"] == "Dark indigo jeans")}).text
    assert '<g id="fq">' not in svg and "#4a2c22" in group(svg, "fp") and "#5e2f25" in group(svg, "fp")


def test_the_figure_is_asked_for_again_when_a_shoe_is_drawn_again(conn):
    from closet import items as items_module

    conn.execute("INSERT INTO items (id, category, color_hex, created_at, updated_at) "
                 "VALUES ('s2', 'dress_shoes', '#b5622f', 'x', 'x'), ('t2', 'tee', '#ffffff', 'x', 'x')")
    get = lambda i: items_module.summary(conn, conn.execute("SELECT * FROM items WHERE id = ?", (i,)).fetchone())  # noqa: E731
    assert get("s2")["drawn_version"] is None and get("t2")["drawn_version"] is None and get("t2")["drawn_state"] is None
    conn.execute("UPDATE items SET drawn = ?, drawn_state = 'done' WHERE id = 's2'", (json.dumps(DRESS_DRAWING),))
    first = get("s2")["drawn_version"]
    conn.execute("UPDATE items SET drawn = ?, drawn_state = 'done' WHERE id = 's2'",
                 (json.dumps({**DRESS_DRAWING, "made_at": "2026-11-16T09:00:00+00:00"}),))
    assert first and get("s2")["drawn_version"] not in (None, first) and get("s2")["drawn_state"] == "done"


def test_the_preview_and_the_check_image_draw_behind_then_the_leg_then_in_front():
    boot = _back_tab_boot()
    svg = drawn.preview_svg(boot)
    left = svg[svg.index('translate(22,150)'):svg.index('translate(418,150)')]
    assert left.index("#4a2c22") < left.index(drawn.PREVIEW_SOCK) < left.index("#5e2f25")   # the tab, the sock, the panels
    check = drawn.check_svg(boot)
    assert check.index("#4a2c22") < check.index(drawn.PREVIEW_SOCK) < check.index("#5e2f25")
    assert math.isclose(drawn.TODAY_LINE, 2.2 / (4 * 0.297))
