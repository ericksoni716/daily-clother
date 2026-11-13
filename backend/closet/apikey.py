"""The owner's Anthropic API key: kept in the computer's own keychain, never in a file of ours.

Where it is kept:
- macOS: the login keychain, through Apple's `security` tool. The key is handed to it on its standard input
  (its interactive mode), never on a command line where other programs could see it.
- Windows: Credential Manager (a generic credential for this user), through the Windows API.
- Elsewhere there is no keychain Closet uses; the key can only come from `ANTHROPIC_API_KEY`.

A key saved here wins over `ANTHROPIC_API_KEY`. The key is never returned to the page, logged, written to the
settings file or a backup, and never put into the environment of a program Closet starts (Claude Code must keep
using the owner's plan).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Protocol

SERVICE = "Closet"
ACCOUNT = "anthropic-api-key"
ENV = "ANTHROPIC_API_KEY"

# what an Anthropic API key looks like: checked before it reaches the keychain or a command
KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,400}")
NOT_A_KEY = "That doesn't look like an Anthropic API key. Keys start with sk-ant- and are one long line."


class KeychainError(RuntimeError):
    """The keychain could not be used; the message is a sentence the owner can read."""


class Store(Protocol):
    where: str   # where the key is kept, in the owner's words

    def get(self) -> str | None: ...
    def set(self, key: str) -> None: ...
    def delete(self) -> None: ...


class MacKeychain:
    where = "this Mac's keychain"
    TOOL = "/usr/bin/security"
    NOT_FOUND = 44   # what `security` exits with when there is no such item

    def _run(self, args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self.TOOL, *args], input=stdin, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise KeychainError("Closet could not reach this Mac's keychain.") from e

    def get(self) -> str | None:
        proc = self._run(["find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"])
        if proc.returncode == self.NOT_FOUND:
            return None
        if proc.returncode != 0:
            raise KeychainError("Closet could not read the API key from this Mac's keychain.")
        return proc.stdout.strip() or None

    def set(self, key: str) -> None:
        if not KEY_RE.fullmatch(key):   # never let anything else reach the tool's command line
            raise ValueError(NOT_A_KEY)
        # interactive mode reads the command from standard input, so the key is not in the process list
        self._run(["-i"], stdin=f'add-generic-password -U -s {SERVICE} -a {ACCOUNT} -l "{SERVICE} API key" -w "{key}"\n')
        if self.get() != key:
            raise KeychainError("Closet could not save the API key in this Mac's keychain.")

    def delete(self) -> None:
        proc = self._run(["delete-generic-password", "-s", SERVICE, "-a", ACCOUNT])
        if proc.returncode not in (0, self.NOT_FOUND):
            raise KeychainError("Closet could not remove the API key from this Mac's keychain.")


class WindowsCredentials:
    where = "Windows Credential Manager"
    TARGET = f"{SERVICE}/{ACCOUNT}"
    GENERIC = 1              # CRED_TYPE_GENERIC
    LOCAL_MACHINE = 2        # CRED_PERSIST_LOCAL_MACHINE: this user on this computer, kept after sign-out
    NOT_FOUND = 1168         # ERROR_NOT_FOUND

    def _api(self):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        advapi.CredReadW.restype = wintypes.BOOL
        advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        advapi.CredWriteW.restype = wintypes.BOOL
        advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        advapi.CredDeleteW.restype = wintypes.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        advapi.CredFree.restype = None
        return ctypes, advapi, CREDENTIAL

    def get(self) -> str | None:
        ctypes, advapi, CREDENTIAL = self._api()
        found = ctypes.POINTER(CREDENTIAL)()
        if not advapi.CredReadW(self.TARGET, self.GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == self.NOT_FOUND:
                return None
            raise KeychainError("Closet could not read the API key from Windows Credential Manager.")
        try:
            cred = found.contents
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return blob.decode("utf-8") or None
        finally:
            advapi.CredFree(found)

    def set(self, key: str) -> None:
        if not KEY_RE.fullmatch(key):
            raise ValueError(NOT_A_KEY)
        ctypes, advapi, CREDENTIAL = self._api()
        data = key.encode("utf-8")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        cred = CREDENTIAL(Type=self.GENERIC, TargetName=self.TARGET, Comment=f"{SERVICE} API key",
                          CredentialBlobSize=len(data), CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)),
                          Persist=self.LOCAL_MACHINE, UserName=ACCOUNT)
        if not advapi.CredWriteW(ctypes.byref(cred), 0):
            raise KeychainError("Closet could not save the API key in Windows Credential Manager.")

    def delete(self) -> None:
        ctypes, advapi, _ = self._api()
        if not advapi.CredDeleteW(self.TARGET, self.GENERIC, 0) and ctypes.get_last_error() != self.NOT_FOUND:
            raise KeychainError("Closet could not remove the API key from Windows Credential Manager.")


class NoKeychain:
    where = ""

    def get(self) -> str | None:
        return None

    def set(self, key: str) -> None:
        raise KeychainError("Closet can't keep an API key on this computer. Set ANTHROPIC_API_KEY instead.")

    def delete(self) -> None:
        return None


def _default_store() -> Store:
    if sys.platform == "darwin":
        return MacKeychain()
    if sys.platform == "win32":
        return WindowsCredentials()
    return NoKeychain()


_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = _default_store()
    return _store


def use_store(s: Store | None) -> None:
    """Use `s` instead of the computer's keychain (tests); None goes back to the computer's."""
    global _store
    _store = s


def _saved() -> str | None:
    try:
        return store().get()
    except Exception:   # a keychain that cannot be read is treated as holding no key; the environment still counts
        return None


def get() -> str | None:
    """The key to use: the one saved in the keychain, else `ANTHROPIC_API_KEY`, else None."""
    return _saved() or (os.environ.get(ENV) or "").strip() or None


def info() -> dict:
    """What the Settings page may know: whether a key is set and where it comes from. Never the key itself."""
    saved = _saved()
    source = "keychain" if saved else "environment" if (os.environ.get(ENV) or "").strip() else None
    s = store()
    return {"set": source is not None, "source": source, "can_save": not isinstance(s, NoKeychain),
            "where": s.where or None}


def clean(key: str) -> str:
    """The key as typed, without spaces or line breaks around it; ValueError if it is not a key."""
    key = (key or "").strip()
    if not KEY_RE.fullmatch(key):
        raise ValueError(NOT_A_KEY)
    return key


def client(key: str | None = None, **kw):
    """An Anthropic client for the key to use; RuntimeError when there is none."""
    key = key or get()
    if not key:
        raise RuntimeError("no API key is set")
    import anthropic
    return anthropic.Anthropic(api_key=key, **kw)


def check(key: str) -> str | None:
    """Ask Anthropic whether it accepts `key`, at no cost (it lists one model). None if it does; otherwise
    "refused" when Anthropic turned it down, or "unknown" when Anthropic could not be reached."""
    import anthropic
    try:
        client(key, max_retries=0, timeout=15).models.list(limit=1)
        return None
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        return "refused"
    except anthropic.BadRequestError as e:   # e.g. "Not a valid API key for this workspace"
        return "refused" if "api key" in str(e).lower() else "unknown"
    except Exception:
        return "unknown"
