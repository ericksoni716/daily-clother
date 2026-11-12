"""One passphrase, one owner.

The passphrase is stored only as a salted scrypt hash. A successful login
sets a random session token in a cookie; the file keeps only its hash.
Repeated wrong guesses are slowed down.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from .state import State

COOKIE = "closet_session"
SESSION_DAYS = 90
MIN_LENGTH = 8
MAX_FAILURES = 5
WINDOW_SECONDS = 300
_N, _R, _P = 2 ** 15, 8, 1


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401, retry_after: int | None = None):
        super().__init__(message)
        self.message, self.status, self.retry_after = message, status, retry_after


def _hash(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024, dklen=32)


def is_set_up(state: State) -> bool:
    return state.get("passphrase") is not None


def set_passphrase(state: State, passphrase: str) -> None:
    if len(passphrase) < MIN_LENGTH:
        raise AuthError(f"Choose a passphrase of at least {MIN_LENGTH} characters.", 422)
    salt = os.urandom(16)
    state.update(passphrase={
        "salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(_hash(passphrase, salt, _N, _R, _P)).decode(),
        "n": _N, "r": _R, "p": _P}, sessions={}, failed_logins=[])


def clear_passphrase(state: State) -> None:
    state.update(passphrase=None, sessions={}, failed_logins=[])


def check_passphrase(state: State, passphrase: str) -> None:
    """Raise AuthError unless the passphrase is right; counts failures."""
    now = time.time()
    recent = [t for t in state.get("failed_logins") if now - t < WINDOW_SECONDS]
    if len(recent) >= MAX_FAILURES:
        wait = int(WINDOW_SECONDS - (now - recent[0])) + 1
        raise AuthError(f"Too many wrong attempts. Try again in {max(1, wait // 60)} minute(s).", 429, wait)
    stored = state.get("passphrase")
    if stored is None:
        raise AuthError("No passphrase has been set yet.", 409)
    got = _hash(passphrase, base64.b64decode(stored["salt"]), stored["n"], stored["r"], stored["p"])
    if not hmac.compare_digest(got, base64.b64decode(stored["hash"])):
        state.update(failed_logins=recent + [now])
        raise AuthError("That passphrase is not right.", 401)
    if recent:
        state.update(failed_logins=[])


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(state: State) -> str:
    token = secrets.token_urlsafe(32)
    expires = time.time() + SESSION_DAYS * 86400

    def add(data):
        now = time.time()
        data["sessions"] = {k: v for k, v in data["sessions"].items() if v > now}
        data["sessions"][_digest(token)] = expires
    state.mutate(add)
    return token


def session_valid(state: State, token: str | None) -> bool:
    if not token:
        return False
    expiry = state.get("sessions").get(_digest(token))
    return bool(expiry and expiry > time.time())


def end_session(state: State, token: str | None) -> None:
    if token:
        state.mutate(lambda d: d["sessions"].pop(_digest(token), None))
