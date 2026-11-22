"""The way in from outside without Tailscale: Cloudflare Tunnel with Cloudflare Access in front of it.

The owner can give Nines an address of its own on a domain they own: Cloudflare's connector on this computer opens a
connection out to Cloudflare and passes on what arrives at that address to Nines on 127.0.0.1, and Cloudflare Access
asks whoever opens the address to sign in (a code by email) and lets through only the email its policy names. Every
request it passes on carries a token Access signed. This module checks that token: the signature against the team's
published keys, that it is meant for the owner's Access application (the audience), that the owner's team issued it,
and that it has not run out. Who is asking comes from that token only, never from the plain email header Access also
adds, which anything that reaches Nines could send.

The door is off until all three settings are there (Settings, Other devices): the team's domain, the application's audience
tag and the public hostname. They are program-wide, in `settings.json` (`state.py`), not in a closet. `gate.py` asks
for the token on that hostname, before anything else is read.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from . import net

log = logging.getLogger("closet.access")

# What Cloudflare Access sends and publishes, in one place.
TOKEN_HEADER = "cf-access-jwt-assertion"
TOKEN_COOKIE = "CF_Authorization"
CERTS_PATH = "/cdn-cgi/access/certs"
TEAM_DOMAIN = "cloudflareaccess.com"
ALGORITHMS = ["RS256"]
EMAIL_CLAIM = "email"
REQUIRED_CLAIMS = ["exp", "iat", EMAIL_CLAIM]
# Headers Cloudflare adds to every request it passes on, whatever the browser sent.
FORWARDED_HEADERS = ("cf-ray", "cf-connecting-ip")
KEYS_LIFESPAN = 3600     # seconds to keep the team's keys before asking for them again
KEYS_TIMEOUT = 10        # seconds to wait for them
USER_AGENT = "Nines (sign-in check)"

# The three settings, as kept in settings.json (state.DEFAULTS).
TEAM_KEY, AUD_KEY, HOST_KEY = "cloudflare_team", "cloudflare_aud", "cloudflare_host"


class SigningKeys(Protocol):
    """What `verify` needs from `jwt.PyJWKClient`, so a test (and the self-check) can hand in keys of its own."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


@dataclass(frozen=True)
class Config:
    team: str | None = None
    aud: str | None = None
    host: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.team and self.aud and self.host)


def load(state) -> Config:
    return Config(team=state.get(TEAM_KEY), aud=state.get(AUD_KEY), host=state.get(HOST_KEY))


def payload(state) -> dict:
    """What Settings shows: the three values, and whether the door is on."""
    config = load(state)
    return {"team": config.team, "aud": config.aud, "host": config.host, "on": config.configured}


def team_url(team: str) -> str:
    return f"https://{team}"


def certs_url(team: str) -> str:
    return team_url(team) + CERTS_PATH


_clients: dict[str, jwt.PyJWKClient] = {}


def _keys_for(url: str) -> SigningKeys:
    """One key client per team, kept for the life of the program, so the keys are not fetched on every request. It
    reaches Cloudflare over HTTPS the way the rest of Nines does (`net.ssl_context`): a packaged Python has no
    certificates of its own on a Mac."""
    client = _clients.get(url)
    if client is None:
        client = _clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=KEYS_LIFESPAN, timeout=KEYS_TIMEOUT,
                                                 headers={"User-Agent": USER_AGENT}, ssl_context=net.ssl_context())
    return client


def verify(token: str, config: Config, keys: SigningKeys | None = None) -> dict[str, str] | None:
    """Who a token from Cloudflare Access names ({login, name, via}), or None when it does not check out.

    It may fetch the team's keys, so it is called off the event loop. Every failure is logged with its reason, never
    with the token itself.
    """
    if not config.configured or not token:
        return None
    assert config.team and config.aud
    try:
        keys = keys or _keys_for(certs_url(config.team))
        signing_key = keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=ALGORITHMS, audience=config.aud,
                            issuer=team_url(config.team), options={"require": REQUIRED_CLAIMS})
    except jwt.PyJWKClientError as exc:
        log.warning("Could not get the Cloudflare Access keys to check a sign-in: %s", exc)
        return None
    except jwt.InvalidTokenError as exc:
        log.warning("Turned away a Cloudflare Access sign-in that did not check out: %s", exc)
        return None
    except Exception as exc:  # anything else about a token from outside still means no
        log.warning("Turned away a Cloudflare Access sign-in that could not be checked: %s", type(exc).__name__)
        return None
    email = claims.get(EMAIL_CLAIM)
    if not isinstance(email, str) or "@" not in email:
        log.warning("Turned away a Cloudflare Access sign-in with no email in it.")
        return None
    return {"login": email, "name": email, "via": "cloudflare"}


def token_of(headers, cookies: dict) -> str | None:
    """The token Access added to a request: its header, or else its cookie."""
    return headers.get(TOKEN_HEADER) or cookies.get(TOKEN_COOKIE) or None


def forwarded(headers) -> bool:
    """Whether Cloudflare passed this request on (it marks everything it forwards)."""
    return any(h in headers for h in FORWARDED_HEADERS)


def selfcheck() -> str:
    """For `Nines selfcheck`: sign a token with an RSA key made here and check it as a request's token is checked,
    keys handed in rather than fetched. Proves the packaged program has PyJWT with RSA (cryptography) in it."""
    from types import SimpleNamespace

    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = Config(team=f"selfcheck.{TEAM_DOMAIN}", aud="selfcheck-audience", host="closet.example.com")
    now = int(time.time())
    token = jwt.encode({"aud": config.aud, "iss": team_url(config.team or ""), "iat": now, "exp": now + 60,
                        "email": "owner@example.com"}, key, algorithm="RS256")

    class Keys:
        def get_signing_key_from_jwt(self, token: str):
            return SimpleNamespace(key=key.public_key())

    if verify(token, config, Keys()) is None:
        raise RuntimeError("a token signed here did not check out (the reason is in nines.log)")
    return f"PyJWT {jwt.__version__} checked an RS256 signature"


# ------------------------------------------------------------------ the settings, as typed in Settings
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

TEAM_EXAMPLE = "Type your team's domain like yourteam.cloudflareaccess.com."
HOST_EXAMPLE = "Type the address Cloudflare gives Nines, like closet.example.com."


def _is_hostname(value: str) -> bool:
    labels = value.split(".")
    return len(value) <= 253 and len(labels) >= 2 and all(_LABEL.match(label) for label in labels)


def _bare(value: str) -> str:
    """The hostname part of what was typed, in lower case, without a scheme, a path or a trailing dot."""
    rest = value.split("://", 1)[1] if "://" in value else value
    return rest.split("/", 1)[0].lower().rstrip(".")


def clean_team(value: str) -> str:
    """"yourteam", "yourteam.cloudflareaccess.com" and "https://yourteam.cloudflareaccess.com/" are all kept as the
    domain. Only a team under cloudflareaccess.com is taken: the keys are fetched from it."""
    if any(c.isspace() for c in value):
        raise ValueError("Type the team's domain without spaces. " + TEAM_EXAMPLE)
    if "://" in value and not value.lower().startswith("https://"):
        raise ValueError(TEAM_EXAMPLE)
    team = _bare(value)
    if "." not in team:
        team = f"{team}.{TEAM_DOMAIN}"
    if not team.endswith("." + TEAM_DOMAIN) or not _is_hostname(team):
        raise ValueError("That does not look like your Cloudflare team. " + TEAM_EXAMPLE)
    return team


def clean_host(value: str) -> str:
    if any(c.isspace() for c in value):
        raise ValueError("Type the address without spaces. " + HOST_EXAMPLE)
    host = _bare(value)
    local = host == "localhost" or re.fullmatch(r"[0-9.]+", host) is not None   # this computer, or an address in numbers
    if not _is_hostname(host) or local or host.endswith(".ts.net") or host.endswith("." + TEAM_DOMAIN):
        raise ValueError("That does not look like a web address of your own. " + HOST_EXAMPLE)
    return host


def clean_aud(value: str) -> str:
    if any(c.isspace() for c in value) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
        raise ValueError("The audience tag is one long run of letters and numbers, without spaces. Copy it from the "
                         "Access application's overview in Cloudflare.")
    return value


def changes(sent: dict[str, str | None]) -> dict[str, str | None]:
    """The settings to keep from what was typed ({state key: value}); an empty value clears one. Raises ValueError
    with a sentence for the owner."""
    out: dict[str, str | None] = {}
    for key, clean in ((TEAM_KEY, clean_team), (AUD_KEY, clean_aud), (HOST_KEY, clean_host)):
        if key in sent:
            value = (sent[key] or "").strip()
            out[key] = clean(value) if value else None
    return out
