"""What a shoe's photos tell its drawing without asking Claude (`closet/drawing/photocheck.py`): the photo cut to the
shoe, and the light material's share of the upper's front checked against the front photo, only where that check
can be trusted. Made-up pictures only: no real photo is in the repository."""
import numpy as np
from PIL import Image

from closet.drawing import photocheck

SUEDE, LEATHER, GUM = (184, 172, 157), (242, 240, 234), (181, 119, 47)
PALETTE = [{"name": "grey suede", "hex": "#b8ac9d", "role": "upper"},
           {"name": "white leather", "hex": "#f2f0ea", "role": "upper"},
           {"name": "gum sole", "hex": "#b5772f", "role": "sole"}]
SHEET = {"palette": PALETTE}


def mask_of(img):
    """The 'model': everything that is not the plain grey-blue background."""
    a = np.asarray(img.convert("RGB")).astype(int)
    return np.where(np.abs(a - np.array([90, 110, 130])).sum(axis=2) > 30, 255, 0).astype(np.uint8)


def front_photo(white_share: float) -> Image.Image:
    """A made-up front photo: a shoe-shaped block on a plain background, its upper suede with a white band across
    `white_share` of it (in shade, as a photo shows white leather), on a gum sole."""
    im = np.zeros((600, 800, 3), np.uint8)
    im[:] = (90, 110, 130)
    im[150:420, 200:600] = SUEDE
    im[150:150 + int(270 * white_share), 200:600] = (205, 202, 196)   # white leather, a little grey in the shade
    im[420:480, 190:610] = GUM
    return Image.fromarray(im)


def drawing(white_share: float) -> dict:
    """A drawing laid out the same way, with the light material across `white_share` of its upper."""
    h = 160 * white_share
    return {"behind": "", "front":
            '<rect x="20" y="40" width="160" height="160" fill="#b8ac9d"/>'
            f'<rect x="20" y="40" width="160" height="{h:.0f}" fill="#f2f0ea"/>'
            '<rect x="14" y="200" width="172" height="40" fill="#b5772f"/>'}


def test_a_photo_is_cut_to_the_shoe_with_a_margin():
    photo = front_photo(0.3)
    cut = photocheck.crop(photo, mask_of)
    assert 420 < cut.width < 560 and 330 < cut.height < 420   # the shoe (420 x 330) and its margin
    assert photocheck.crop(photo, None) is photo   # no model yet: the photo as it is
    assert photocheck.crop(photo, lambda img: None) is photo
    assert photocheck.crop(photo, lambda img: (_ for _ in ()).throw(RuntimeError("no model"))) is photo


def test_the_light_material_is_checked_against_the_front_photo():
    check = photocheck.FrontCheck.of(front_photo(0.3), mask_of)
    assert check is not None
    assert check.problems(drawing(0.3), SHEET) == []   # as much white leather as the photo shows
    too_much = check.problems(drawing(0.7), SHEET)
    assert len(too_much) == 1 and "too much white leather" in too_much[0] and "about 30%" in too_much[0]
    assert "too little white leather" in photocheck.FrontCheck.of(front_photo(0.7), mask_of).problems(drawing(0.3),
                                                                                                    SHEET)[0]


def test_it_is_left_out_where_it_cannot_be_trusted():
    check = photocheck.FrontCheck.of(front_photo(0.3), mask_of)
    # near-whites only (a canvas plimsoll with an off-white toe): no large, clearly darker area to measure against
    near_white = {"palette": [{"name": "white canvas", "hex": "#f4f3ee", "role": "upper"},
                              {"name": "off-white rubber", "hex": "#dedcd3", "role": "toe cap"},
                              {"name": "rubber sole", "hex": "#eae8e1", "role": "sole"}]}
    plimsoll = {"behind": "", "front": '<rect x="20" y="40" width="160" height="160" fill="#f4f3ee"/>'
                                      '<rect x="20" y="150" width="160" height="50" fill="#dedcd3"/>'
                                      '<rect x="14" y="200" width="172" height="40" fill="#eae8e1"/>'}
    assert check.problems(plimsoll, near_white) == []
    # one colour: nothing to compare
    brown = {"palette": [{"name": "brown leather", "hex": "#6b4630", "role": "upper"},
                         {"name": "sole", "hex": "#2a201a", "role": "sole"}]}
    assert check.problems({"behind": "", "front": '<rect x="20" y="40" width="160" height="200" fill="#6b4630"/>'},
                          brown) == []
    # no model, or no shoe found: no check
    assert photocheck.FrontCheck.of(front_photo(0.3), None) is None
    assert photocheck.FrontCheck.of(Image.new("RGB", (400, 300), (90, 110, 130)), mask_of) is None
