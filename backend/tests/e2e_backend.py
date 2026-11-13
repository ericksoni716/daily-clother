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

Searching shops for a wish is a stand-in too (`FakeShop`): after a second it "finds" a tan rain-proof coat, a
navy polo and a product with a link that is not a web address (which the app drops), and a price check sees every
price 20% lower. With CLOSET_E2E_SEED=demo the owner's own closet starts as a copy of the demo closet, so what is
found is checked against a closet with something in it (the demo closet itself never searches).

The API key box keeps keys in a stand-in keychain (never the computer's), and the check with Anthropic is a
stand-in too: a key ending in "refused" is turned down, any other well-formed key is accepted.
"""
import os
import shutil
import sqlite3
import sys
import time

from closet import apikey, app, cli, demo
from closet.tagger import routes as tagger_routes
from closet.tagger.shopping import Found, PriceAnswer, PriceSeen, ShopAnswer
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, FakeApi, FakeClaude, MemoryKeychain, fake_cutter

_real_build = app.build_services


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def api_only_status(order="auto", claude_exe=None):
    return {"order": ["plan", "api"], "routes": [
        {"id": "plan", "available": False, "detail": "Claude Code is not installed on this computer."},
        {"id": "api", "available": True, "detail": ""}]}


def _found(**kw) -> Found:
    base = dict(shop="Example Shop", image_url="", currency="USD", formality="smart_casual", season="all",
                pattern="solid", weight_class="midweight", rain_proof=False, material="")
    return Found(**{**base, **kw})


class FakeShop:
    """Stands in for Claude searching shops and looking up prices; never reaches the web."""

    def find(self, wish, routes):
        time.sleep(1)   # long enough for the page to show it searching
        return ShopAnswer(note="", finds=[
            _found(name="Tan gabardine rain coat", url="https://shop.example/tan-coat", price=180.0, category="coat",
                   color="tan", rain_proof=True, material="cotton gabardine"),
            _found(name="Navy pique polo", shop="Other Shop", url="https://other.example/polo", price=45.0,
                   category="polo", color="navy", season="warm"),
            _found(name="Not a real link", url="javascript:alert(1)", price=10.0, category="tee", color="white")])

    def prices(self, finds, routes):
        time.sleep(1)
        return PriceAnswer(prices=[PriceSeen(url=f["url"], price=round((f["price"] or 100) * 0.8, 2),
                                             currency=f["currency"], available=True) for f in finds])


def seed_from_demo(cfg):
    """The owner's own closet starts as a copy of the demo closet (only when it does not exist yet)."""
    main = cfg.db_path("main")
    if main.exists():
        return
    demo.ensure(cfg)
    src, dst = sqlite3.connect(cfg.db_path("demo")), sqlite3.connect(main)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    if cfg.images_dir("demo").exists():
        shutil.copytree(cfg.images_dir("demo"), cfg.images_dir("main"), dirs_exist_ok=True)


def build_services(cfg, **kwargs):
    if os.environ.get("CLOSET_E2E_SEED") == "demo":
        seed_from_demo(cfg)
    kwargs.setdefault("shop_asker", FakeShop())
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
