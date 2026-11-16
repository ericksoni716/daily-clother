"""The answer's form on the API route: short enough for the API to compile, and checked against the full form.

The API compiles the form into a grammar and refuses one that is too large ("The compiled grammar is too large", 400).
The full form passed that limit at 939 listed words (schema version 5) and the owner's items could no longer be
described with an API key, so the form sent there keeps only short lists in the grammar (tagger/tagging.py, SENT).
"""
import json
from types import SimpleNamespace

import pytest
from anthropic import transform_schema
from PIL import Image

from closet.tagger import tagging
from closet.tagger.schema import ItemTags
from closet.tagger.tagging import SENT, TaggingError, fitted, tag_item

from .conftest import ANSWER, FakeApi

# The full form was refused at 939 listed words and taken at 929; the form sent keeps well below both.
GRAMMAR_WORDS = 400


def words(schema) -> int:
    if isinstance(schema, dict):
        return len(schema.get("enum", [])) + sum(words(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(words(v) for v in schema)
    return 0


def test_the_form_sent_lists_few_words_and_names_the_rest():
    full, sent = transform_schema(ItemTags), transform_schema(SENT)
    assert words(full) > 900 and words(sent) < GRAMMAR_WORDS
    footwear = sent["$defs"]["DetailsSent"]["properties"]["footwear"] if "$defs" in sent else None
    text = json.dumps(sent)
    assert "One of: " in text and "chukka" in text and "desert_boot" in text   # a long list, named in its description
    if footwear is not None:
        assert "enum" not in footwear and footwear.get("type") == "string"


def test_the_api_route_sends_the_short_form():
    api = FakeApi()
    tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert api.requests[-1]["output_format"] is SENT


def sent_answer(**details) -> object:
    data = ANSWER.model_dump(mode="json")
    data["details"].update(details)
    return SENT.model_validate(data)


def test_a_word_outside_its_list_is_made_to_fit():
    answer = sent_answer(footwear="moon_boot", fabric="spacesuit", trouser_pockets=["slash", "secret_pocket"])
    tags = fitted(answer)
    assert isinstance(tags, ItemTags)
    assert tags.details.footwear == "unknown" and tags.details.fabric == "unknown"
    assert "secret_pocket" not in tags.details.trouser_pockets
    assert fitted(sent_answer()) == ANSWER   # an answer that fits is kept as it is


def test_an_answer_that_cannot_fit_is_asked_again_then_refused():
    class Wrong(FakeApi):
        def parse(self, **kw):
            reply = super().parse(**kw)
            bad = ANSWER.model_dump(mode="json")
            bad["category_confidence"] = 5   # out of its range: no word to fall back to
            return SimpleNamespace(parsed_output=SimpleNamespace(model_dump=lambda mode=None: bad),
                                   stop_reason="end_turn", usage=reply.usage)

    api = Wrong()
    with pytest.raises(TaggingError, match="outside the form"):
        tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))], max_attempts=2)
    assert api.calls == 2


def test_an_answer_with_a_word_outside_its_list_is_described():
    class Odd(FakeApi):
        def parse(self, **kw):
            reply = super().parse(**kw)
            return SimpleNamespace(parsed_output=sent_answer(footwear="moon_boot"), stop_reason="end_turn",
                                   usage=reply.usage)

    r = tag_item(Odd(), "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert r.tags.details.footwear == "unknown" and r.attempts == 1


def test_the_short_lists_stay_in_the_grammar():
    assert tagging.ENUM_IN_GRAMMAR >= 8
    sent = transform_schema(SENT)
    assert words(sent) > 100   # the short lists (category, colour, formality ...) are still enforced by the API


def test_the_main_fields_keep_all_their_words_in_the_grammar():
    """Loosening the main fields was tried: a boat shoe came back as category "other" (a word outside the list, made
    to fit). The closet sorts and builds outfits by these, so the API keeps them to their lists."""
    props = transform_schema(SENT)["properties"]
    for name in ("category", "color", "pattern", "formality", "season"):
        text = json.dumps(props[name])
        assert '"enum"' in text, name
