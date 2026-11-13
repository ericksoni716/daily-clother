"""Choosing how to reach Claude: the Claude plan, the API key, or one then the other.

There are two ways in, and either can run dry: the plan has usage limits and
the API key has a credit balance. The default order tries the plan first
(nothing billed), and falls back to the API key only when the plan cannot be
used. A photo or prompt problem is never retried on the other route.
"""
from __future__ import annotations

import os

from PIL import Image

from . import claude_cli
from .tagging import RouteUnavailable, TagResult, tag_item

ORDERS = {"auto": ("plan", "api"), "plan": ("plan",), "api": ("api",), "api-first": ("api", "plan")}


class Router:
    def __init__(self, order: str = "auto", client=None, claude_exe: str | None = None):
        if order not in ORDERS:
            raise ValueError(f"unknown route order {order!r}; choose one of {', '.join(ORDERS)}")
        self.routes = ORDERS[order]
        self._client = client
        self._exe = claude_exe
        self.skipped: dict[str, str] = {}   # route -> why it was given up on, for the rest of this run

    def _api_client(self):
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RouteUnavailable("no API key is set (ANTHROPIC_API_KEY)")
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def tag(self, model: str, images: list[Image.Image]) -> TagResult:
        for route in self.routes:
            if route in self.skipped:
                continue
            try:
                if route == "plan":
                    return claude_cli.tag_item_cli(model, images, exe=self._exe)
                return tag_item(self._api_client(), model, images)
            except RouteUnavailable as e:
                self.skipped[route] = str(e)   # stop trying this route until the next run
        reasons = "; ".join(f"{r}: {why}" for r, why in self.skipped.items()) or "no route configured"
        raise RouteUnavailable(f"Claude cannot be reached right now. {reasons}")


def api_status() -> tuple[bool, str]:
    """Whether an API key is set. Only its presence is looked at; it is never read out, sent or logged."""
    if (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return True, ""
    return False, "No API key is set."


def status(order: str = "auto", claude_exe: str | None = None) -> dict:
    """Which routes exist, whether each can be used right now, and the order they are tried in.

    Asks Claude nothing and spends nothing: the plan route runs `claude auth status`
    (a few seconds at most), the API route only checks that a key is set.
    """
    checks = {"plan": lambda: claude_cli.plan_status(claude_exe), "api": api_status}
    routes = []
    for route in ORDERS[order]:
        available, detail = checks[route]()
        routes.append({"id": route, "available": available, "detail": detail})
    return {"order": list(ORDERS[order]), "routes": routes}
