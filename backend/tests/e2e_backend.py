"""Starts Closet for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude.

With CLOSET_E2E_ROUTES=api the plan route cannot be used and the API route is
the real one (its spend recorded and kept under the owner's limit) talking to
`conftest.FakeApi` instead of Anthropic: each request reports 20,000 tokens in
and 12,000 out, $0.008 at the prices written down, so a $0.01 limit allows
exactly one. Corrections by sentence
are read by the same stand-in the backend tests use (or, with CLOSET_E2E_ROUTES=api, by the
real API route talking to `conftest.FakeApi`).

The API key box keeps keys in a stand-in keychain (never the computer's), and the check with Anthropic is a
stand-in too: a key ending in "refused" is turned down, any other well-formed key is accepted.
"""
import os
import sys
import time

from closet import apikey, app, cli
from closet.tagger import routes as tagger_routes
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, FakeApi, FakeClaude, MemoryKeychain, fake_cutter

_real_build = app.build_services


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def api_only_status(order="auto", claude_exe=None):
    routes = {"plan": {"id": "plan", "available": False, "detail": "Claude Code is not installed on this computer."},
              "api": {"id": "api", "available": True, "detail": ""}}
    return {"order": list(tagger_routes.ORDERS[order]), "routes": [routes[r] for r in tagger_routes.ORDERS[order]]}


def build_services(cfg, **kwargs):
    apikey.use_store(MemoryKeychain())
    apikey.check = lambda key: "refused" if key.endswith("refused") else None
    if os.environ.get("CLOSET_E2E_ROUTES") == "api":
        tagger_routes.status = api_only_status
        sv = _real_build(cfg, cutter=fake_cutter, api_client=FakeApi(input_tokens=20_000, output_tokens=12_000), **kwargs)
    else:
        reader = FakeClaude()
        reader.mode = "answers"
        sv = _real_build(cfg, cutter=fake_cutter, tagger=fake_claude, routes=lambda: ("plan",), corrector=reader.correct,
                         **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


if __name__ == "__main__":
    app.build_services = build_services
    sys.exit(cli.main(sys.argv[1:]))
