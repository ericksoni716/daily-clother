"""What every request goes through before its body is read: where it came from, the login, and a cap on its size.

FastAPI reads a request's body (and writes an uploaded photo to a temporary file) before it runs the route's
dependencies, so the login check on a route comes too late to stop a large upload from someone who is not logged
in. This runs first, in this order, and refuses without reading a byte of the body:

1. **The address.** The Host header must name this computer (`127.0.0.1`, `localhost`, `[::1]`) or a Tailscale name
   (`….ts.net`, which Tailscale Serve keeps when it passes the phone's requests on), or the answer is 403. This turns
   away another website that points a name of its own at 127.0.0.1.
2. **The key of Closet's own window,** when one is in force (the launcher sets one; tests do not): a request by a
   local name must carry it in a cookie, or the answer is 401. Opening `/?key=…` once sets the cookie and leads on to
   the same address without the key. Requests by a Tailscale name are never asked for it and can never get the cookie
   this way; they go on to the passphrase as before.
3. **Changes come from Closet's own pages.** POST, PUT, PATCH and DELETE under `/api/` need the header the page sends
   on every call (`X-Closet-Client: 1`), or the answer is 403. Another website cannot send it.
4. **The login.** A call under `/api/` that needs it is answered 401 without the passphrase's session.
5. **The size.** Every request is counted as it streams in and answered 413 the moment it goes past its limit
   (`limits.py`), whether or not it said its length. Starlette closes the temporary file of an upload cut off this
   way, and nothing is written to the closet until the whole photo has arrived, so a refused upload leaves nothing
   behind.

`/api/health` needs nothing but the address. `/api/instance/quit` and `/api/instance/show` are called by another copy
of the program, never by the page, and prove themselves with the token from the lock file (`instance.py`): they need
neither the key nor the header.
"""
from __future__ import annotations

import html
import json
import secrets
from collections.abc import Callable
from urllib.parse import parse_qsl, quote, urlencode

from starlette.datastructures import Headers
from starlette.requests import cookie_parser

from . import limits

# Calls that work without the login (as in docs/API.md); everything else under /api/ needs it.
OPEN = frozenset({"/api/health", "/api/session", "/api/setup", "/api/login", "/api/logout", "/api/instance/quit",
                  "/api/instance/show"})

# The names a request may give for Closet in its Host header: this computer's own, and Tailscale's (`….ts.net`).
LOCAL_NAMES = frozenset({"127.0.0.1", "localhost", "[::1]"})
TAILSCALE_SUFFIX = ".ts.net"

# Called by another copy of the program with the token from the lock file, never by the page (see the top).
BY_ANOTHER_COPY = frozenset({"/api/instance/quit", "/api/instance/show"})

# The header Closet's own page sends on every call (frontend/src/api.ts); changes without it are refused.
CLIENT_HEADER = "X-Closet-Client"
CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

KEY_DAYS = 400   # the longest a browser keeps a cookie

WRONG_ADDRESS = "Closet answers only at this computer's own address, or at its Tailscale address."
OPEN_FROM_ICON = "Open Closet from its icon to use it on this computer."
OLD_PAGE = "This page is from an older Closet. Reload the page, then try again."


def host_name(host: str) -> str:
    """The name in a Host header, without the port, in lower case: `[::1]` for `[::1]:8765`."""
    host = host.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[:end + 1] if end > 0 else host
    return host.rsplit(":", 1)[0]


def on_tailscale(name: str) -> bool:
    return name.endswith(TAILSCALE_SUFFIX) and len(name) > len(TAILSCALE_SUFFIX)


def key_cookie(port: int) -> str:
    """The key's cookie is named for the port, because a browser keeps cookies by name and not by port."""
    return f"closet_key_{port}"


def window_key(state) -> str:
    """The key of Closet's own window, made the first time and kept in the program-wide settings from then on, so a
    browser tab opened once from the icon keeps working after Closet restarts."""
    def ensure(data: dict) -> str:
        if not data.get("window_key"):
            data["window_key"] = secrets.token_urlsafe(32)
        return data["window_key"]
    return state.mutate(ensure, save_if_changed=True)


def keyed_url(url: str, key: str | None) -> str:
    """The address the program opens for the owner: `url` with the key, which the server swaps for a cookie."""
    return f"{url}?{urlencode({'key': key})}" if key else url


def _same(given: str | None, key: str) -> bool:
    return bool(given) and secrets.compare_digest(given.encode(), key.encode())


class TooLarge(Exception):
    """The request went past its limit while being read."""


def too_large_message(limit: int) -> str:
    if limit >= limits.UPLOAD_BYTES:
        return (f"That photo is too large to send: Closet takes photos of up to {limits.PHOTO_BYTES // limits.MB} MB. "
                "Choose a smaller photo.")
    return "That is more than Closet reads in one request. Try again with less."


class Gate:
    """ASGI middleware. `refusal(cookie)` is None when the request's session is valid, else the sentence for 401.
    `key` is the key of Closet's own window, or None when none is in force; `key_cookie` names its cookie."""

    def __init__(self, app, cookie: str, refusal: Callable[[str | None], str | None], key: str | None = None,
                 key_cookie: str = ""):
        self.app = app
        self.cookie = cookie
        self.refusal = refusal
        self.key = key
        self.key_cookie = key_cookie

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        headers = Headers(scope=scope)
        api = path.startswith("/api/")
        name = host_name(headers.get("host", ""))
        if name not in LOCAL_NAMES and not on_tailscale(name):
            await _refuse(send, api, 403, WRONG_ADDRESS)
            return
        cookies = cookie_parser(headers.get("cookie", ""))
        if self.key and name in LOCAL_NAMES and path != "/api/health" and path not in BY_ANOTHER_COPY:
            query = parse_qsl(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
            offered = [v for k, v in query if k == "key"]
            if offered and method == "GET" and not api:
                if not _same(offered[0], self.key):
                    await _refuse(send, api, 401, OPEN_FROM_ICON)
                    return
                rest = urlencode([(k, v) for k, v in query if k != "key"])
                # one leading slash, so the address led on to is always this server's own
                location = quote("/" + path.lstrip("/")) + (f"?{rest}" if rest else "")
                await _key_accepted(send, location, self.key_cookie, self.key)
                return
            if not _same(cookies.get(self.key_cookie), self.key):
                await _refuse(send, api, 401, OPEN_FROM_ICON)
                return
        if api and method in CHANGES and path not in BY_ANOTHER_COPY and headers.get(CLIENT_HEADER) != "1":
            await _answer(send, 403, OLD_PAGE)
            return
        if api and path not in OPEN:
            refused = self.refusal(cookies.get(self.cookie))
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


async def _refuse(send, api: bool, status: int, detail: str) -> None:
    """A refusal: a sentence for the page under `/api/`, and a small page of its own for anything a browser opens."""
    if api:
        await _answer(send, status, detail)
    else:
        await _page(send, status, detail)


# What an old bookmark or a wrong address shows in a browser, in the page's own colours and type (styles.css).
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Closet</title>
<style>
:root { --ink: #26231f; --bg: #f6f2ea; --muted: #5f5950; }
@media (prefers-color-scheme: dark) { :root { --ink: #eeeae3; --bg: #1b1916; --muted: #b8b2a8; } }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, Roboto, 'Helvetica Neue', Arial, sans-serif; }
main { box-sizing: border-box; max-width: 34rem; margin: 12vh auto 0; padding: 24px 16px; }
h1 { font-size: 25px; line-height: 1.25; margin: 0 0 12px; }
p { margin: 0 0 12px; }
p + p { color: var(--muted); }
</style></head>
<body><main><h1>{title}</h1>{body}</main></body></html>
"""

PAGES = {
    OPEN_FROM_ICON: ("Open Closet from its icon",
                     ["On this computer, Closet opens from its own icon: on the desktop or in the Start menu, or in "
                      "Applications on a Mac. Open it from there and you will see your closet.",
                      "Your closet is safe, and nothing in it has changed."]),
    WRONG_ADDRESS: ("Closet is not at this address",
                    ["Closet answers only at this computer's own address, or at its Tailscale address on your phone."]),
}


async def _page(send, status: int, detail: str) -> None:
    title, lines = PAGES.get(detail, ("Closet", [detail]))
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    page = PAGE.replace("{title}", html.escape(title)).replace("{body}", body).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(page)).encode()),
        (b"cache-control", b"no-store"), (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": page})


async def _key_accepted(send, location: str, cookie: str, key: str) -> None:
    """The key was right: keep it in a cookie that only this server's own pages send, and go on without it in the
    address."""
    set_cookie = f"{cookie}={key}; Max-Age={KEY_DAYS * 86400}; Path=/; HttpOnly; SameSite=Strict"
    await send({"type": "http.response.start", "status": 303, "headers": [
        (b"location", location.encode("latin-1")), (b"set-cookie", set_cookie.encode()),
        (b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer"), (b"content-length", b"0")]})
    await send({"type": "http.response.body", "body": b""})


async def _answer(send, status: int, detail: str) -> None:
    """Answers at once and asks the client to close the connection, so the rest of a body it did not read is not
    waited for."""
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})
