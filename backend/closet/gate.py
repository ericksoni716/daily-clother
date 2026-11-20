"""What every request goes through before its body is read: the login, and a cap on how much it may send.

FastAPI reads a request's body (and writes an uploaded photo to a temporary file) before it runs the route's
dependencies, so the login check on a route comes too late to stop a large upload from someone who is not logged
in. This runs first: a call under `/api/` that needs the login is answered 401 without reading a byte of its body,
and every request is counted as it streams in and answered 413 the moment it goes past its limit (`limits.py`),
whether or not it said its length. Starlette closes the temporary file of an upload cut off this way, and nothing
is written to the closet until the whole photo has arrived, so a refused upload leaves nothing behind.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.requests import cookie_parser

from . import limits

# Calls that work without the login (as in docs/API.md); everything else under /api/ needs it.
OPEN = frozenset({"/api/health", "/api/session", "/api/setup", "/api/login", "/api/logout", "/api/instance/quit",
                  "/api/instance/show"})


class TooLarge(Exception):
    """The request went past its limit while being read."""


def too_large_message(limit: int) -> str:
    if limit >= limits.UPLOAD_BYTES:
        return (f"That photo is too large to send: Nines takes photos of up to {limits.PHOTO_BYTES // limits.MB} MB. "
                "Choose a smaller photo.")
    return "That is more than Nines reads in one request. Try again with less."


class Gate:
    """ASGI middleware. `refusal(cookie)` is None when the request's session is valid, else the sentence for 401."""

    def __init__(self, app, cookie: str, refusal: Callable[[str | None], str | None]):
        self.app = app
        self.cookie = cookie
        self.refusal = refusal

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        headers = Headers(scope=scope)
        if path.startswith("/api/") and path not in OPEN:
            refused = self.refusal(cookie_parser(headers.get("cookie", "")).get(self.cookie))
            if refused is not None:
                await _answer(send, 401, refused)
                return
        limit = limits.limit_for(method, path)
        declared = headers.get("content-length", "")
        if declared.strip().isdigit() and int(declared) > limit:
            await _answer(send, 413, too_large_message(limit))
            return

        read = 0
        over = False
        started = False

        async def counted() -> dict:
            nonlocal read, over
            if over:
                raise TooLarge()
            message = await receive()
            if message["type"] == "http.request":
                read += len(message.get("body", b""))
                if read > limit:
                    over = True
                    raise TooLarge()
            return message

        async def guarded(message: dict) -> None:
            nonlocal started
            if over:   # whatever the app answers to a body cut short, the answer is 413
                if not started:
                    started = True
                    await _answer(send, 413, too_large_message(limit))
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, guarded)
        except TooLarge:
            if not started:
                started = True
                await _answer(send, 413, too_large_message(limit))


async def _answer(send, status: int, detail: str) -> None:
    """Answers at once and asks the client to close the connection, so the rest of a body it did not read is not
    waited for."""
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})
