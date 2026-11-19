"""Each part in its own colour, letters read on the front drawn as text, and both corrected in the owner's own words
(schema 7, `items.own_cloth`). Made-up cloth only."""
import json
import re

from closet import patjobs
from closet.drawing import item as drawing_item
from closet.drawing.templates import CX_ROT
from closet.tagger import correcting, surfaceform, tagging
from closet.tagger.correcting import CorrectionAnswer, CorrectionResult
from closet.tagger.schema import NAMED_HEX
from closet.tagger.surfaceform import Lettering, Surface

from .test_corrections import described, history, svg

TWO_SLEEVES = {"kind": "blocks", "bands": [], "direction": None, "size": None, "panels": [],
               "blocks": [{"part": "left_sleeve_as_seen", "color": "#2f5a8a"}, {"part": "right_sleeve_as_seen", "color": "#b8282e"}],
               "colors": [{"color": "#24603f", "share": 8}]}
APC = [{"text": "A.P.C.", "place": "middle", "size": "large", "style": "sans", "color": "#1a1a1a"}]


def _answer(**fields) -> dict:
    from .conftest import ANSWER
    return {**ANSWER.model_dump(mode="json"), "category": "tee", **fields}


def _fills(svg_text: str, colour: str) -> list[float]:
    """The middle x of each path painted in `colour`."""
    out = []
    for d in re.findall(rf'<path d="([^"]+)" fill="{colour}"/>', svg_text):
        xs = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)[0::2]]
        out.append(sum(xs) / len(xs))
    return out


# ---- the description's form ---------------------------------------------------------------------------------------

def test_each_part_keeps_its_own_colour_and_two_sleeves_alike_are_one_part():
    found = surfaceform.block_colours(TWO_SLEEVES)
    assert found == {"left_sleeve_as_seen": surfaceform.softened("#2f5a8a"), "right_sleeve_as_seen": surfaceform.softened("#b8282e")}
    same = {**TWO_SLEEVES, "blocks": [{"part": "left_sleeve_as_seen", "color": "#b8282e"}, {"part": "right_sleeve_as_seen", "color": "#b8282e"}]}
    assert surfaceform.block_colours(same) == {"sleeves": surfaceform.softened("#b8282e")}


def test_only_letters_that_can_be_drawn_are_kept():
    said = [{"text": "  A.P.C. ", "place": "middle", "size": "large", "style": "sans", "color": "#111111"},
            {"text": "…", "place": "middle", "size": "small", "style": "sans", "color": "#111111"},   # no letter
            {"text": "x" * 31, "place": "middle", "size": "small", "style": "sans", "color": "#111111"},   # too long
            {"text": "GAP", "place": "on_the_back", "size": "small", "style": "sans", "color": "#111111"}]  # no such place
    assert [x["text"] for x in surfaceform.lettering_of(said)] == ["A.P.C."]


def test_the_colour_words_are_the_closets():
    assert surfaceform.COLOUR_WORDS == NAMED_HEX


def test_every_description_asks_for_lettering_only_when_it_can_be_read():
    text = surfaceform.FIELD_TEXT["lettering"]
    assert "read for certain" in text and "picture or a symbol" in text and "Never guess" in text
    assert text in surfaceform.NOTES and "lettering" in tagging.answer_tool()["input_schema"]["required"]


# ---- drawn ----------------------------------------------------------------------------------------------------------

def test_each_sleeve_is_drawn_in_its_own_colour_on_its_own_side():
    tags = tagging.fitted(_answer(surface=TWO_SLEEVES))
    out = drawing_item.drawing_from_answer(tags.model_dump(mode="json")).svg
    left, right = _fills(out, surfaceform.softened("#2f5a8a")), _fills(out, surfaceform.softened("#b8282e"))
    assert left and right
    assert all(x < CX_ROT[0] for x in left) and all(x > CX_ROT[0] for x in right)   # as seen, as in the photo


def test_letters_are_drawn_as_text_on_a_top_and_never_as_markup():
    tags = tagging.fitted(_answer(lettering=[{**APC[0], "text": "<b>&Co</b>"}]))
    out = drawing_item.drawing_from_answer(tags.model_dump(mode="json")).svg
    assert "&lt;b&gt;&amp;Co&lt;/b&gt;</text>" in out and "<b>" not in out
    plain = drawing_item.drawing_from_answer(tagging.fitted(_answer()).model_dump(mode="json")).svg
    assert "<text" not in plain


def test_letters_are_not_drawn_over_a_print_lifted_from_the_photo():
    from PIL import Image

    from closet.drawing import fills
    tags = tagging.fitted(_answer(lettering=APC))
    graphic = fills.Graphic(Image.new("RGBA", (20, 10), (200, 0, 0, 255)), 0.5, 0.3, 0.3, (0, 0, 20, 10))
    out = drawing_item.drawing_from_answer(tags.model_dump(mode="json"), graphic=graphic).svg
    assert "A.P.C." not in out


# ---- corrected in the owner's words ---------------------------------------------------------------------------------

def _corrector(answer: CorrectionAnswer, seen: list):
    def correct(sentence, description, allowed, images, routes):
        seen.append(description)
        return CorrectionResult(answer, routes[0], "fake")
    return correct


def test_a_sentence_about_the_sleeves_gives_each_its_colour_and_can_be_undone(client, services, claude):
    item = described(client, services, claude)
    before = svg(client, item)
    seen: list = []
    services.corrector = _corrector(CorrectionAnswer(changes=[], not_understood="", needs_photo=False,
                                                     cloth=Surface.model_validate(TWO_SLEEVES)), seen)
    body = client.post(f"/api/items/{item['id']}/correct",
                       json={"sentence": "the left arm is blue and the right one red"}).json()
    assert body["state"] == "understood"
    change, = body["changes"]
    assert change["name"] == "cloth" and change["title"] == "cloth"
    assert change["after_words"] == "plain green with blue sleeve on the left, red sleeve on the right"
    assert seen[0]["cloth"] is None or isinstance(seen[0]["cloth"], dict)   # Claude reads it as data

    done = client.post(f"/api/items/{item['id']}/correct/confirm", json={
        "sentence": body["sentence"], "changes": [{"name": "cloth", "value": change["value"], "before": change["before"]}]})
    assert done.status_code == 200
    drawn = svg(client, done.json())
    assert surfaceform.softened("#2f5a8a") in drawn and surfaceform.softened("#b8282e") in drawn
    entry = history(client, item["id"])[0]
    part, = [p for p in entry["parts"] if p["name"] == "own_cloth"]
    assert part["title"] == "cloth and lettering" and "blue sleeve on the left" in part["after_words"]

    # kept when the item is described again, as the owner's details are
    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert services.tag_worker.drain() == 1
    assert svg(client, client.get(f"/api/items/{item['id']}").json()) == drawn

    entry = next(e for e in history(client, item["id"]) if e["kind"] == "sentence")
    assert client.post(f"/api/items/{item['id']}/history/{entry['id']}/undo").status_code == 200
    assert svg(client, client.get(f"/api/items/{item['id']}").json()) == before


def test_a_sentence_about_letters_draws_them(client, services, claude):
    item = described(client, services, claude)
    services.corrector = _corrector(CorrectionAnswer(changes=[], not_understood="", needs_photo=False,
                                                     lettering=[Lettering.model_validate(APC[0])]), [])
    body = client.post(f"/api/items/{item['id']}/correct",
                       json={"sentence": "there's a logo in the middle that says A.P.C."}).json()
    change, = body["changes"]
    assert change["name"] == "lettering" and change["after_words"] == "“A.P.C.” in black across the middle"
    done = client.post(f"/api/items/{item['id']}/correct/confirm", json={
        "sentence": body["sentence"], "changes": [{"name": "lettering", "value": change["value"]}]})
    assert ">A.P.C.</text>" in svg(client, done.json())


def test_a_cloth_that_does_not_fit_the_form_is_refused(client, services, claude):
    item = described(client, services, claude)
    r = client.post(f"/api/items/{item['id']}/correct/confirm", json={
        "sentence": "red sleeves", "changes": [{"name": "cloth", "value": json.dumps({"kind": "tartan"})}]})
    assert r.status_code in (400, 422) and "could not be read" in r.json()["detail"]


def test_the_owners_cloth_is_measured_and_their_pattern_word_set_later_wins(client, services, claude, cfg):
    item = described(client, services, claude)
    plaid = {"kind": "plaid", "bands": [{"color": "#7a1f2b", "width": 5}, {"color": "#1d2b3a", "width": 3}],
             "direction": None, "size": "medium", "blocks": [], "panels": [], "colors": []}
    services.corrector = _corrector(CorrectionAnswer(changes=[], not_understood="", needs_photo=False,
                                                     cloth=Surface.model_validate(plaid),
                                                     lettering=[Lettering.model_validate(APC[0])]), [])
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it's a red and navy check"}).json()
    client.post(f"/api/items/{item['id']}/correct/confirm", json={
        "sentence": body["sentence"], "changes": [{"name": c["name"], "value": c["value"]} for c in body["changes"]]})
    from .test_patjobs import row
    r = row(cfg, item["id"])
    assert r["pattern_state"] == "waiting" and patjobs._surface(r) == plaid and patjobs.method(r) == patjobs.SURFACE

    client.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"})
    r = row(cfg, item["id"])
    assert json.loads(r["own_cloth"]) == {"lettering": APC} and patjobs.method(r) == "stripe"


def test_the_correction_prompt_says_a_picture_logo_cannot_be_drawn():
    text = correcting.prompt("there's a crocodile on the chest", {"cloth": None, "lettering": []}, {}, with_photo=False)
    assert "a logo that is a picture or a symbol cannot be drawn" in text


def test_no_lettering_said_where_there_was_none_is_no_change(client, services, claude):
    item = described(client, services, claude)
    services.corrector = _corrector(CorrectionAnswer(changes=[], not_understood="", needs_photo=False,
                                                     cloth=Surface.model_validate(TWO_SLEEVES), lettering=[]), [])
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "one sleeve is blue"}).json()
    assert [c["name"] for c in body["changes"]] == ["cloth"]
