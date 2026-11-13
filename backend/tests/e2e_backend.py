"""Starts Closet for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude.

With CLOSET_E2E_ROUTES=api the plan route cannot be used and the API route is
the real one (its spend recorded and kept under the owner's limit) talking to
`conftest.FakeApi` instead of Anthropic: each request reports 20,000 tokens in
and 12,000 out, $0.008 at the prices written down, so a $0.01 limit allows
exactly one.
"""
import os
import sys
import time

from closet import app, cli
from closet.tagger import routes as tagger_routes
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, FakeApi, fake_cutter

_real_build = app.build_services


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def api_only_status(order="auto", claude_exe=None):
    return {"order": ["plan", "api"], "routes": [
        {"id": "plan", "available": False, "detail": "Claude Code is not installed on this computer."},
        {"id": "api", "available": True, "detail": ""}]}


def build_services(cfg, **kwargs):
    if os.environ.get("CLOSET_E2E_ROUTES") == "api":
        tagger_routes.status = api_only_status
        sv = _real_build(cfg, cutter=fake_cutter, api_client=FakeApi(input_tokens=20_000, output_tokens=12_000), **kwargs)
    else:
        sv = _real_build(cfg, cutter=fake_cutter, tagger=fake_claude, routes=lambda: ("plan",), **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


if __name__ == "__main__":
    app.build_services = build_services
    sys.exit(cli.main(sys.argv[1:]))
