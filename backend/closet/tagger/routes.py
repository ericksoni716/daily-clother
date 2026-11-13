"""Choosing how to reach Claude: the Claude plan, the API key, or one then the other.

There are two ways in, and either can run dry: the plan has usage limits and
the API key has a credit balance. The default order tries the plan first
(nothing billed), and falls back to the API key only when the plan cannot be
used. A photo or prompt problem is never retried on the other route.
"""
from __future__ import annotations

from PIL import Image

from .. import apikey
from . import claude_cli
from .tagging import ApiRefused, CapReached, Meter, PlanSignIn, RouteUnavailable, TagResult, tag_item

ORDERS = {"auto": ("plan", "api"), "plan": ("plan",), "api": ("api",), "api-first": ("api", "plan")}


class Router:
    def __init__(self, order: str = "auto", client=None, claude_exe: str | None = None, meter: Meter | None = None):
        if order not in ORDERS:
            raise ValueError(f"unknown route order {order!r}; choose one of {', '.join(ORDERS)}")
        self.routes = ORDERS[order]
        self._client = client
        self._exe = claude_exe
        self._meter = meter   # the app's spend cap and record of calls; the bench runs without one
        self.skipped: dict[str, str] = {}   # route -> why it was given up on, for the rest of this run
        self.capped = False   # the API route was given up on because of the spend cap
        self.sign_in = False  # the plan route was given up on because Claude Code's sign-in does not work

    def _api_client(self):
        if self._client is None:
            if not apikey.get():
                raise RouteUnavailable("no API key is set")
            self._client = apikey.client()
        return self._client

    def tag(self, model: str, images: list[Image.Image]) -> TagResult:
        for route in self.routes:
            if route in self.skipped:
                continue
            try:
                if route == "plan":
                    result = claude_cli.tag_item_cli(model, images, exe=self._exe)
                    if self._meter:
                        self._meter.record("plan", result.model, result.input_tokens, result.output_tokens)
                    return result
                return tag_item(self._api_client(), model, images, meter=self._meter)
            except RouteUnavailable as e:
                self.skipped[route] = str(e)   # stop trying this route until the next run
                self.capped = self.capped or isinstance(e, CapReached)
                self.sign_in = self.sign_in or isinstance(e, PlanSignIn)
                if isinstance(e, ApiRefused) and self._meter:
                    self._meter.api_refused(e.reason)
        reasons = "; ".join(f"{r}: {why}" for r, why in self.skipped.items()) or "no route configured"
        kind = CapReached if self.capped else PlanSignIn if self.sign_in else RouteUnavailable
        raise kind(f"Claude cannot be reached right now. {reasons}")


def api_status() -> tuple[bool, str]:
    """Whether an API key is set (saved in the keychain, or in `ANTHROPIC_API_KEY`). Only its presence is
    looked at; it is never read out, sent or logged."""
    if apikey.get():
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
