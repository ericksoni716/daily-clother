"""The answer's forms, and every answer checked against the full form.

A form sent as structured output is compiled by the API into a grammar, refused when it is too large ("The compiled
grammar is too large", 400): the full form at 939 listed words (schema version 5), and a description through the API
key failed the same way after #235 cut it to 327. So the API route sends the whole form as a plain tool, which is not
compiled, and checks the answer itself (tagger/tagging.py, `answer_tool`); the plan route keeps the short form `SENT`.
"""
import json

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


def test_the_plan_routes_form_lists_few_words_and_names_the_rest():
    full, sent = transform_schema(ItemTags), transform_schema(SENT)
    assert words(full) > 900 and words(sent) < GRAMMAR_WORDS
    footwear = sent["$defs"]["DetailsSent"]["properties"]["footwear"] if "$defs" in sent else None
    text = json.dumps(sent)
    assert "One of: " in text and "chukka" in text and "desert_boot" in text   # a long list, named in its description
    if footwear is not None:
        assert "enum" not in footwear and footwear.get("type") == "string"


def test_the_api_route_sends_the_whole_form_as_a_plain_tool():
    api = FakeApi()
    tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    sent = api.requests[-1]
    # nothing the API compiles into a grammar: no structured output, no strict tool
    assert "output_format" not in sent and "format" not in sent["output_config"]
    (tool,) = sent["tools"]
    assert tool["name"] == tagging.ANSWER_TOOL and not tool.get("strict")
    # the whole form, every word of every list, written out with no references
    assert words(tool["input_schema"]) == words(transform_schema(ItemTags)) > 900
    assert "$ref" not in json.dumps(tool) and "$defs" not in json.dumps(tool)
    # asked for, not forced: some models refuse a forced tool (Opus 5.5, Sonnet 5.5)
    assert sent["tool_choice"]["type"] == "auto"
    assert tagging.ASK_FOR_TOOL in sent["messages"][0]["content"][-1]["text"]


def test_the_api_route_out_of_reach_says_so_rather_than_a_bad_answer(monkeypatch):
    import anthropic
    import httpx2 as httpx

    from closet.tagger.tagging import RouteUnavailable, Unreachable
    monkeypatch.setattr(tagging.time, "sleep", lambda s: None)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    api = FakeApi()
    api.error = anthropic.APIConnectionError(request=request)
    with pytest.raises(Unreachable) as e:
        tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert not isinstance(e.value, RouteUnavailable)   # never moved to the other route for this
    assert api.calls == 3   # its own retries, then it says so

    overloaded = anthropic.APIStatusError("Overloaded", response=httpx.Response(529, request=request), body=None)
    api = FakeApi()
    api.error = overloaded
    with pytest.raises(Unreachable):
        tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])

    # a request Anthropic turns down is still a plain failure
    api = FakeApi()
    api.error = anthropic.BadRequestError("bad image", response=httpx.Response(400, request=request), body=None)
    with pytest.raises(TaggingError) as e:
        tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert not isinstance(e.value, Unreachable)


def test_the_plan_route_out_of_reach_says_so(monkeypatch):
    import json as _json
    from types import SimpleNamespace

    from closet.tagger import claude_cli
    from closet.tagger.tagging import Unreachable
    said = {"is_error": True, "result": "API Error: Connection error."}
    monkeypatch.setattr(claude_cli.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout=_json.dumps(said), stderr=""))
    with pytest.raises(Unreachable):
        claude_cli.tag_item_cli("claude-haiku-5-5", [Image.new("RGB", (40, 40))], exe="claude")
    # an answer that is simply unusable is still a plain failure
    monkeypatch.setattr(claude_cli.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout=_json.dumps({"is_error": True, "result": "something else went wrong"}), stderr=""))
    with pytest.raises(TaggingError) as e:
        claude_cli.tag_item_cli("claude-haiku-5-5", [Image.new("RGB", (40, 40))], exe="claude")
    assert not isinstance(e.value, Unreachable)


def stray(**fields) -> dict:
    data = ANSWER.model_dump(mode="json")
    data.update(fields)
    return data


def test_a_main_field_outside_its_list_is_said_back_and_put_right():
    api = FakeApi()
    api.tag_answers = [stray(category="boat_shoe", secondary_colors=["white", "teal"]), ANSWER]
    r = tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert r.tags == ANSWER and r.attempts == 2
    asked = api.requests[1]["messages"]
    assert [m["role"] for m in asked] == ["user", "assistant", "user"]   # the same conversation, gone on
    (result,) = asked[2]["content"]
    assert result["type"] == "tool_result" and result["is_error"] is True and result["tool_use_id"] == "toolu_1"
    assert "'boat_shoe'" in result["content"] and "dress_shoes" in result["content"] and "'teal'" in result["content"]
    assert "pattern" not in result["content"]   # only the fields that were wrong


def test_a_main_field_still_outside_its_list_at_the_last_try_is_made_to_fit():
    api = FakeApi()
    api.tag_answers = [stray(category="boat_shoe")]
    r = tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))], max_attempts=2)
    assert r.tags.category == "other" and r.attempts == 2


def test_an_answer_without_the_tool_is_asked_again_from_the_start():
    api = FakeApi()
    api.tag_answers = [None, ANSWER]
    r = tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert r.tags == ANSWER and r.attempts == 2
    assert api.requests[1]["messages"] == api.requests[0]["messages"]   # the first question again, nothing added


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
    api = FakeApi()
    api.tag_answers = [stray(category_confidence=5)]   # out of its range: no word to fall back to
    with pytest.raises(TaggingError, match="outside the form"):
        tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))], max_attempts=2)
    assert api.calls == 2


def test_an_answer_with_a_word_outside_its_list_is_described():
    api = FakeApi()
    api.tag_answers = [sent_answer(footwear="moon_boot")]   # a detail: made to fit, not asked again
    r = tag_item(api, "claude-haiku-5-5", [Image.new("RGB", (40, 40))])
    assert r.tags.details.footwear == "unknown" and r.attempts == 1


def test_the_plan_routes_short_lists_stay_in_its_grammar():
    assert tagging.ENUM_IN_GRAMMAR >= 8
    sent = transform_schema(SENT)
    assert words(sent) > 100   # the short lists (category, colour, formality ...) are still enforced by the API


def test_the_plan_routes_main_fields_keep_all_their_words_in_its_grammar():
    """Loosening the main fields was tried: a boat shoe came back as category "other" (a word outside the list, made
    to fit). The closet sorts and builds outfits by these, so they keep their lists (on the API route, by asking
    again: test_a_main_field_outside_its_list_is_said_back_and_put_right)."""
    props = transform_schema(SENT)["properties"]
    for name in ("category", "color", "pattern", "formality", "season"):
        text = json.dumps(props[name])
        assert '"enum"' in text, name


def test_the_estimate_covers_the_request_with_the_whole_form():
    """The spending limit holds `spend.estimate_call` for each request: it must cover the prompt and the whole form
    sent as a tool (counted at 1 token for every 2 characters)."""
    from closet import spend
    text = len(tagging.PROMPT) + len(tagging.ASK_FOR_TOOL) + len(json.dumps(tagging.answer_tool()))
    assert text / 2 <= spend.TEXT_TOKENS
