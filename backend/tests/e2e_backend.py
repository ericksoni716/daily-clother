"""Starts Closet for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude. Corrections by sentence
are read by the same stand-in the backend tests use.
"""
import sys
import time

from closet import app, cli
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, FakeClaude, fake_cutter

_real_build = app.build_services


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def build_services(cfg, **kwargs):
    reader = FakeClaude()
    reader.mode = "answers"
    sv = _real_build(cfg, cutter=fake_cutter, tagger=fake_claude, routes=lambda: ("plan",), corrector=reader.correct, **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


if __name__ == "__main__":
    app.build_services = build_services
    sys.exit(cli.main(sys.argv[1:]))
