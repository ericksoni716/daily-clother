"""Outbound HTTPS for the packaged program.

A packaged Python has no certificate store of its own on macOS, so a plain
`urlopen("https://...")` fails there even with a working internet connection.
`ssl_context()` trusts what the computer itself trusts (the macOS keychain, the
Windows certificate store, the system bundle on Linux), which also covers a
work computer whose network adds its own certificate. If that is not available
it falls back to the certificate bundle shipped inside the program.
"""
from __future__ import annotations

import ssl


def ssl_context() -> ssl.SSLContext:
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # not installed, or the platform's store cannot be opened
        pass
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def trust_source() -> str:
    """Which certificates `ssl_context()` uses, for the self-check report."""
    try:
        import truststore  # noqa: F401
        return "system certificates"
    except Exception:
        pass
    try:
        import certifi  # noqa: F401
        return "bundled certificates"
    except Exception:
        return "python default certificates"


def is_certificate_error(exc: BaseException) -> bool:
    """True when a connection failed because the server's certificate could not be verified."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        exc = getattr(exc, "reason", None) if isinstance(getattr(exc, "reason", None), BaseException) else exc.__cause__
    return False
