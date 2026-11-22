"""The door through Cloudflare (closet/access.py): checking the token Cloudflare Access signs, the three settings that
turn it on, and the gate asking for the token on that hostname (closet/gate.py).

The keys are made here, never fetched: the tests hand them in through `create_app(access_keys=...)`."""
import base64
import json
import logging
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from closet import access, gate
from closet import app as app_module

TEAM = "yourteam.cloudflareaccess.com"
AUD = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
HOST = "closet.example.com"
EMAIL = "owner@example.com"
CONFIG = access.Config(team=TEAM, aud=AUD, host=HOST)

PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Keys:
    """Hands back the team's public key the way PyJWKClient does, without asking Cloudflare."""

    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=PRIVATE.public_key())


def token(key=PRIVATE, algorithm="RS256", **claims) -> str:
    now = int(time.time())
    body = {"aud": [AUD], "email": EMAIL, "iss": f"https://{TEAM}", "iat": now, "exp": now + 3600, "sub": "user-1"}
    body.update(claims)
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key, algorithm=algorithm, headers={"kid": "k1"})


def unsigned(**claims) -> str:
    """A token that says `alg: none`: a header and claims with no signature at all."""
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    now = int(time.time())
    body = {"aud": AUD, "email": EMAIL, "iss": f"https://{TEAM}", "iat": now, "exp": now + 3600, **claims}
    return f"{part({'alg': 'none', 'typ': 'JWT', 'kid': 'k1'})}.{part(body)}."


PUBLIC_PEM = PRIVATE.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def test_a_good_token_names_the_owner():
    assert access.verify(token(), CONFIG, Keys()) == {"login": EMAIL, "name": EMAIL, "via": "cloudflare"}


def hmac_with_public_key() -> str:
    """The old trick: sign with HS256, using the public key (which anyone can fetch) as the secret."""
    import hashlib
    import hmac
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode()).rstrip(b"=")
    now = int(time.time())
    body = base64.urlsafe_b64encode(json.dumps({"aud": AUD, "email": EMAIL, "iss": f"https://{TEAM}", "iat": now,
                                                "exp": now + 3600}).encode()).rstrip(b"=")
    signature = hmac.new(PUBLIC_PEM, header + b"." + body, hashlib.sha256).digest()
    return (header + b"." + body + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


# named by why each is bad: a token holds the time it was made and a signature, so as a test's name it would differ
# from one test worker to the next, and the workers would not agree on which tests there are
BAD_TOKENS = [
    (token(key=OTHER), "forged: signed with another key"),
    (token(aud=["another-application"]), "for another Access application"),
    (token(iss="https://another.cloudflareaccess.com"), "issued by another team"),
    (token(exp=int(time.time()) - 60), "run out"),
    (token(email=None), "no email"),
    (token(email="not-an-email"), "an email without an @"),
    (token(iat=None), "no time it was issued"),
    (token(exp=None), "no time it runs out"),
    (unsigned(), "alg none"),
    (hmac_with_public_key(), "alg confusion: HS256 with the public key as the secret"),
    ("not-a-token", "not a token at all"),
    ("", "nothing"),
]


@pytest.mark.parametrize("bad, why", BAD_TOKENS, ids=[why for _, why in BAD_TOKENS])
def test_tokens_that_do_not_check_out_name_no_one(bad, why, caplog):
    with caplog.at_level(logging.WARNING, logger="closet.access"):
        assert access.verify(bad, CONFIG, Keys()) is None, why
    if bad:
        assert caplog.records, "every failure is logged with its reason"
        assert all(bad not in r.getMessage() for r in caplog.records), "never with the token"


def test_nothing_is_checked_until_all_three_settings_are_there():
    for partial in (access.Config(team=TEAM, aud=AUD), access.Config(aud=AUD, host=HOST), access.Config()):
        assert not partial.configured
        assert access.verify(token(), partial, Keys()) is None


def test_unreachable_keys_name_no_one(caplog):
    class Unreachable:
        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientConnectionError("no route to host")
    with caplog.at_level(logging.WARNING, logger="closet.access"):
        assert access.verify(token(), CONFIG, Unreachable()) is None
    assert "keys" in caplog.text


def test_the_keys_are_fetched_from_the_team_over_closets_own_https(monkeypatch):
    access._clients.clear()
    made = []
    monkeypatch.setattr(access.net, "ssl_context", lambda: made.append("context") or "the context")
    client = access._keys_for(access.certs_url(TEAM))
    assert client is access._keys_for(access.certs_url(TEAM)) and made == ["context"]   # one client per team, kept
    assert access.certs_url(TEAM) == f"https://{TEAM}/cdn-cgi/access/certs"
    assert client.ssl_context == "the context" and client.timeout == access.KEYS_TIMEOUT
    access._clients.clear()


def test_the_packaged_program_can_check_a_token():
    assert access.selfcheck().endswith("checked an RS256 signature")


@pytest.mark.parametrize("typed, kept", [
    ("yourteam", TEAM), (f"  {TEAM} ", TEAM), (f"https://{TEAM}/", TEAM), ("YourTeam.CloudflareAccess.com", TEAM),
])
def test_the_team_is_kept_as_its_domain(typed, kept):
    assert access.changes({access.TEAM_KEY: typed}) == {access.TEAM_KEY: kept}


@pytest.mark.parametrize("field, typed", [
    (access.TEAM_KEY, "yourteam.example.com"), (access.TEAM_KEY, "http://127.0.0.1:9999"),
    (access.TEAM_KEY, f"http://{TEAM}"), (access.TEAM_KEY, "your team"), (access.TEAM_KEY, "cloudflareaccess.com.evil.example"),
    (access.HOST_KEY, "closet example.com"), (access.HOST_KEY, "closet"), (access.HOST_KEY, "-bad-.example.com"),
    (access.HOST_KEY, "closet.example.com:8443"), (access.HOST_KEY, "127.0.0.1"), (access.HOST_KEY, "localhost"),
    (access.HOST_KEY, "closet-pc.example-tailnet.ts.net"), (access.HOST_KEY, TEAM),
    (access.AUD_KEY, "has spaces in it"), (access.AUD_KEY, "short"),
])
def test_what_is_not_a_team_a_hostname_or_an_audience_is_refused(field, typed):
    with pytest.raises(ValueError):
        access.changes({field: typed})


# ------------------------------------------------------------------ through the app

@pytest.fixture
def app(services):
    return app_module.create_app(services, access_keys=Keys())


@pytest.fixture
def local(app):
    return TestClient(app)


@pytest.fixture
def outside(app):
    return TestClient(app, base_url=f"https://{HOST}")


def turn_on(local) -> dict:
    r = local.put("/api/settings", json={"cloudflare_team": "yourteam", "cloudflare_aud": AUD,
                                         "cloudflare_host": f"https://{HOST.upper()}/"})
    assert r.status_code == 200
    return r.json()


def test_the_hostname_is_refused_until_all_three_are_set(local, outside):
    assert local.get("/api/settings").json()["cloudflare"] == {"team": None, "aud": None, "host": None, "on": False}
    local.put("/api/settings", json={"cloudflare_team": TEAM, "cloudflare_host": HOST})
    r = outside.get("/api/health", headers={"Cf-Access-Jwt-Assertion": token()})
    assert r.status_code == 403 and r.json() == {"detail": gate.WRONG_ADDRESS}
    assert turn_on(local)["cloudflare"] == {"team": TEAM, "aud": AUD, "host": HOST, "on": True}
    assert outside.get("/api/health", headers={"Cf-Access-Jwt-Assertion": token()}).status_code == 200


def test_on_the_hostname_every_request_needs_a_token_that_checks_out(local, outside):
    turn_on(local)
    r = outside.get("/api/session")
    assert r.status_code == 401 and r.json() == {"detail": gate.SIGN_IN_CLOUDFLARE}
    page = outside.get("/")
    assert page.status_code == 401 and page.headers["content-type"].startswith("text/html")
    assert "<h1>Sign in through Cloudflare first</h1>" in page.text
    assert outside.get("/api/health").status_code == 401
    for bad in (token(key=OTHER), token(aud=["another-application"]), token(exp=int(time.time()) - 60), unsigned()):
        assert outside.get("/api/session", headers={"Cf-Access-Jwt-Assertion": bad}).status_code == 401
    # the plain email header Access also adds is never believed, nor Tailscale's
    for header in ({"Cf-Access-Authenticated-User-Email": EMAIL}, {"Tailscale-User-Login": EMAIL}):
        assert outside.get("/api/session", headers=header).status_code == 401


def test_then_nothing_else_is_asked(local, outside):
    """The verified sign-in is the whole of this door: no passphrase, no session cookie of Nines' own."""
    turn_on(local)
    outside.cookies.set("CF_Authorization", token(), domain=HOST)   # the cookie Access sets works as the header does
    session = outside.get("/api/session")
    assert session.status_code == 200 and session.json()["authenticated"] is True
    assert outside.get("/api/items").status_code == 200
    assert outside.put("/api/settings", json={"stylist_on": False}).status_code == 200
    assert not [c for c in outside.cookies.jar if c.name != "CF_Authorization"]   # Nines set no cookie of its own
    settings = outside.get("/api/settings").json()
    assert settings["came_in"] == {"via": "cloudflare", "login": EMAIL, "name": EMAIL}
    assert local.get("/api/settings").json()["came_in"] == {"via": "computer", "login": None, "name": None}


def test_the_hostname_is_never_asked_for_the_windows_key_and_cannot_get_it(services):
    keyed = app_module.create_app(services, window_key="a-window-key-for-tests", access_keys=Keys())
    services.state.update(cloudflare_team=TEAM, cloudflare_aud=AUD, cloudflare_host=HOST)
    outside = TestClient(keyed, base_url=f"https://{HOST}", follow_redirects=False,
                         headers={"Cf-Access-Jwt-Assertion": token()})
    assert outside.get("/api/session").status_code == 200
    r = outside.get("/?key=a-window-key-for-tests")
    assert r.status_code != 303 and "set-cookie" not in r.headers


def test_cloudflares_headers_under_any_other_name_are_refused(local):
    turn_on(local)
    for host in ("127.0.0.1:8765", "localhost", "closet-pc.example-tailnet.ts.net"):
        for header in ({"Cf-Ray": "8f00000000000000-EWR"}, {"Cf-Connecting-Ip": "203.0.113.7"}):
            r = local.get("/api/health", headers={"host": host, **header})
            assert r.status_code == 403 and r.json() == {"detail": gate.NOT_THROUGH_CLOUDFLARE}
    page = local.get("/", headers={"Cf-Ray": "8f00000000000000-EWR"})
    assert page.status_code == 403 and "text/html" in page.headers["content-type"]


def test_the_door_cannot_be_changed_by_a_sign_in_through_it(local, outside):
    turn_on(local)
    outside.headers["Cf-Access-Jwt-Assertion"] = token()
    for change in ({"cloudflare_host": "elsewhere.example.com"}, {"cloudflare_aud": ""}, {"cloudflare_team": "another"}):
        r = outside.put("/api/settings", json={**change, "stylist_on": False})
        assert r.status_code == 403 and r.json() == {"detail": app_module.NOT_FROM_CLOUDFLARE}
    assert local.get("/api/settings").json()["cloudflare"]["host"] == HOST
    assert local.get("/api/settings").json()["stylist_on"] is True   # nothing else in that request was saved either
    assert outside.put("/api/settings", json={"stylist_on": False}).status_code == 200   # the rest of Settings is as before


def test_the_door_is_changed_on_the_computer_or_through_tailscale(local):
    phone = {"host": "closet-pc.example-tailnet.ts.net", "Tailscale-User-Login": EMAIL}
    r = local.put("/api/settings", json={"cloudflare_team": "yourteam"}, headers=phone)
    assert r.status_code == 200 and r.json()["cloudflare"]["team"] == TEAM
    r = local.put("/api/settings", json={"cloudflare_host": "nines example.com"})
    assert r.status_code == 422 and "nines.example.com" in r.json()["detail"]
    turn_on(local)
    cleared = local.put("/api/settings", json={"cloudflare_aud": ""}).json()["cloudflare"]
    assert cleared == {"team": TEAM, "aud": None, "host": HOST, "on": False}
