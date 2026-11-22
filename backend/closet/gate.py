"""What every request goes through before its body is read: where it came from, who it is, and a cap on its size.

Nines has no passphrase of its own: who may come in is decided by the door a request comes through (DECISIONS, "The
doors decide who comes in"). Each door has one check, and this runs it first, in this order, refusing without reading a
byte of the body:

1. **The address.** The Host header must name this computer (`127.0.0.1`, `localhost`, `[::1]`), a Tailscale name
   (`….ts.net`, which Tailscale Serve keeps when it passes the phone's requests on), or the Cloudflare hostname once
   all three Cloudflare settings are there (`access.py`), or the answer is 403. This turns away another website that
   points a name of its own at 127.0.0.1. A request Cloudflare passed on (it carries `Cf-Ray` or `Cf-Connecting-Ip`)
   under any other name is refused 403 too, so a tunnel set to rewrite the Host to 127.0.0.1 never arrives as "this
   computer". On a Tailscale name, a request Tailscale marks as coming through Funnel (the public internet) is 403.
2. **Who it is, from outside.** On the Cloudflare hostname, every request (pages and calls alike) needs a token
   Cloudflare Access signed that checks out (`access.verify`), or the answer is 401. On a Tailscale name, every request
   but the health check needs Tailscale to say who is asking (`tailnet.viewer`), or the answer is 401. On Windows that
   is believed only when Windows does not show the other end of the connection to be some other program than the
   Tailscale service (`tailnet.WindowsCheck`: believed when it is the service, refused when it positively is not, and
   believed when Windows could not be asked at all, so a failed lookup never shuts the owner's phone out). Who came in
   is kept in the request's state for the routes: `viewer` ({login, name, via} or None) and `came_in` ("computer",
   "tailscale" or "cloudflare"). Tailscale's headers by any other name are never read.
3. **The key of Nines' own window,** when one is in force (the launcher sets one; tests do not): a request by a
   local name must carry it in a cookie, or the answer is 401. Opening `/?key=…` once sets the cookie and leads on to
   the same address without the key. Requests by a Tailscale name or the Cloudflare hostname are never asked for it
   and can never get the cookie this way.
4. **Changes come from Nines' own pages.** POST, PUT, PATCH and DELETE under `/api/` need the header the page sends
   on every call (`X-Closet-Client: 1`), or the answer is 403. Another website cannot send it.
5. **The size.** Every request is counted as it streams in and answered 413 the moment it goes past its limit
   (`limits.py`), whether or not it said its length. Starlette closes the temporary file of an upload cut off this
   way, and nothing is written to the closet until the whole photo has arrived, so a refused upload leaves nothing
   behind.

`/api/health` needs nothing but the address (and, on the Cloudflare hostname, the token). `/api/instance/quit` and
`/api/instance/show` are called by another copy of the program, never by the page, and prove themselves with the token
from the lock file (`instance.py`): they need neither the key nor the header.
"""
from __future__ import annotations

import html
import json
import logging
import secrets
from collections.abc import Callable
from urllib.parse import parse_qsl, quote, urlencode

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.requests import cookie_parser

from . import access, limits, tailnet

log = logging.getLogger("closet.gate")

# The names a request may give for Closet in its Host header: this computer's own, Tailscale's (`….ts.net`), and the
# Cloudflare hostname once it is set (access.py).
LOCAL_NAMES = frozenset({"127.0.0.1", "localhost", "[::1]"})
TAILSCALE_SUFFIX = ".ts.net"

# Called by another copy of the program with the token from the lock file, never by the page (see the top).
BY_ANOTHER_COPY = frozenset({"/api/instance/quit", "/api/instance/show"})

# The header Closet's own page sends on every call (frontend/src/api.ts); changes without it are refused.
CLIENT_HEADER = "X-Closet-Client"
CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

KEY_DAYS = 400   # the longest a browser keeps a cookie

WRONG_ADDRESS = ("Nines answers only at this computer's own address, at its Tailscale address, or at the Cloudflare "
                 "address set in its Settings.")
FUNNEL = ("Nines does not answer through Tailscale Funnel, which is open to anyone. Open it on a device signed in to "
          "your Tailscale.")
NOT_THROUGH_CLOUDFLARE = "Nines answers through Cloudflare only at the address set in its Settings."
SIGN_IN_CLOUDFLARE = "Sign in through Cloudflare to use Nines at this address."
OPEN_FROM_ICON = "Open Nines from its icon to use it on this computer."
NO_TAILSCALE_VIEWER = ("Nines opens through Tailscale only when Tailscale says who you are. Open it on a device signed "
                       "in to your Tailscale, or open Nines on the computer to check that Tailscale is set up there.")
OLD_PAGE = "This page is from an older Nines. Reload the page, then try again."


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
        return (f"That photo is too large to send: Nines takes photos of up to {limits.PHOTO_BYTES // limits.MB} MB. "
                "Choose a smaller photo.")
    return "That is more than Nines reads in one request. Try again with less."


def came_in(scope) -> dict:
    """How the request came in, as the gate recorded it: {via: "computer" | "tailscale" | "cloudflare", login, name}.
    Settings shows it; `login` and `name` are None when no one was named (or Tailscale's word was not believed)."""
    state = scope.get("state") or {}
    viewer = state.get("viewer") or {}
    return {"via": state.get("came_in", "computer"), "login": viewer.get("login"), "name": viewer.get("name")}


class Gate:
    """ASGI middleware. `key` is the key of Closet's own window, or None when none is in force; `key_cookie` names its cookie.
    `cloudflare()` gives the Cloudflare settings as they are now (`access.Config`), and `keys` the team's signing keys
    (None: fetched from Cloudflare; tests hand in their own). `tailscale_check(client host, client port, server port)`
    says whether the other end of a connection is the Tailscale service (True), positively is not (False), or could not
    be told (None); the check itself is None where there is no way to ask."""

    def __init__(self, app, key: str | None = None, key_cookie: str = "",
                 cloudflare: Callable[[], access.Config] = access.Config, keys: access.SigningKeys | None = None,
                 tailscale_check: tailnet.Check | None = None):
        self.app = app
        self.key = key
        self.key_cookie = key_cookie
        self.cloudflare = cloudflare
        self.keys = keys
        self.tailscale_check = tailscale_check
        self._warned = False
        self._warned_unsure = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        headers = Headers(scope=scope)
        api = path.startswith("/api/")
        name = host_name(headers.get("host", ""))
        config = self.cloudflare()
        tailscale = on_tailscale(name)
        cloudflare = config.configured and name == config.host
        if name not in LOCAL_NAMES and not tailscale and not cloudflare:
            await _refuse(send, api, 403, WRONG_ADDRESS)
            return
        if not cloudflare and access.forwarded(headers):
            await _refuse(send, api, 403, NOT_THROUGH_CLOUDFLARE)
            return
        if tailscale and tailnet.funnel(headers):
            await _refuse(send, api, 403, FUNNEL)
            return
        cookies = cookie_parser(headers.get("cookie", ""))
        viewer = None
        if cloudflare:
            # checking the token may mean fetching the team's keys, so it runs off the event loop
            viewer = await run_in_threadpool(access.verify, access.token_of(headers, cookies) or "", config, self.keys)
            if viewer is None:
                await _refuse(send, api, 401, SIGN_IN_CLOUDFLARE)
                return
        elif tailscale and path != "/api/health":
            viewer = await self._tailscale_viewer(scope, headers)
            if viewer is None:
                await _refuse(send, api, 401, NO_TAILSCALE_VIEWER)
                return
        scope.setdefault("state", {}).update(
            viewer=viewer, came_in="cloudflare" if cloudflare else "tailscale" if tailscale else "computer")
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


    async def _tailscale_viewer(self, scope, headers: Headers) -> dict | None:
        """Who Tailscale says is asking, unless Windows shows it was not Tailscale that said so.

        The check's three answers: True (the Tailscale service) and None (Windows could not be asked) believe the
        headers; False (Windows shows some other program, or no Tailscale service running) does not. A failed lookup
        is not a reason to shut the owner out when Tailscale's headers are there; a positive answer that it was not
        Tailscale is (DECISIONS, "The doors decide who comes in")."""
        viewer = tailnet.viewer(headers)
        if viewer is None or self.tailscale_check is None:
            return viewer
        client, server = scope.get("client"), scope.get("server")
        if not (client and server):
            return None   # no connection to ask about: never the case for a request Tailscale Serve passed on
        answer = await run_in_threadpool(self.tailscale_check, client[0], client[1], server[1])
        if answer is False:
            if not self._warned:
                log.warning("A request named someone the way Tailscale does, but did not come from Tailscale; "
                            "it was refused.")
                self._warned = True
            return None
        if answer is None and not self._warned_unsure:
            log.warning("Windows could not say whether a request came from Tailscale; who Tailscale's headers named "
                        "was believed.")
            self._warned_unsure = True
        return viewer


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
<title>Nines</title>
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
    OPEN_FROM_ICON: ("Open Nines from its icon",
                     ["On this computer, Nines opens from its own icon: on the desktop or in the Start menu, or in "
                      "Applications on a Mac. Open it from there and you will see your closet.",
                      "Your closet is safe, and nothing in it has changed."]),
    WRONG_ADDRESS: ("Nines is not at this address",
                    ["Nines answers only at this computer's own address, at its Tailscale address on your phone, or "
                     "at the Cloudflare address set in its Settings."]),
    NO_TAILSCALE_VIEWER: ("Nines could not tell who you are",
                          ["Through Tailscale, Nines opens only when Tailscale says who is asking, and this visit did "
                           "not say. Open Nines on a device signed in to your Tailscale.",
                           "If this device is signed in, open Nines on the computer it runs on and check that "
                           "Tailscale is set up there. Your closet is safe."]),
    SIGN_IN_CLOUDFLARE: ("Sign in through Cloudflare first",
                         ["Nines opens at this address only after Cloudflare has checked who you are, and this visit "
                          "did not come with Cloudflare's sign-in.",
                          "If you set this address up yourself, check that a Cloudflare Access application covers it. "
                          "The README has the steps."]),
    NOT_THROUGH_CLOUDFLARE: ("Nines is not at this address",
                             ["Nines answers through Cloudflare only at the address set in its Settings. Check the "
                              "address Cloudflare passes on to Nines."]),
    FUNNEL: ("Nines is not on the open internet",
             ["Nines does not answer through Tailscale Funnel, which is open to anyone.",
              "Open it on a device signed in to your Tailscale, at the address Settings shows on the computer."]),
}


async def _page(send, status: int, detail: str) -> None:
    title, lines = PAGES.get(detail, ("Nines", [detail]))
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
