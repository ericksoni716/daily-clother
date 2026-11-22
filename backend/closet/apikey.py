"""The owner's Anthropic API key: kept in the computer's own keychain.

Where it is kept:
- macOS: the login keychain, through Apple's `security` tool. The key is handed to it on its standard input
  (its interactive mode), never on a command line where other programs could see it.
- Windows: Credential Manager (a generic credential for this user), through the Windows API. While Nines is kept
  running by Windows (closet/background.py), the key is also kept in a file in the data folder sealed by Windows to
  this computer (`SEALED_FILE`, below), because a copy started before anyone signs in most likely cannot read
  Credential Manager. That file is read only when Credential Manager gives no key.
- Elsewhere there is no keychain Nines uses; the key can only come from `ANTHROPIC_API_KEY`.

A key saved here wins over `ANTHROPIC_API_KEY`. The key is never returned to the page, logged, written to the
settings file or a backup, and never put into the environment of a program Nines starts (Claude Code must keep
using the owner's plan).

The entry is named Nines. Up to 0.13.0 it was named Closet: a key found only there is saved under Nines and the old
entry removed, once, at start (`carry_over`); until that has worked, the key is read from the old entry.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol

SERVICE = "Nines"
OLD_SERVICE = "Closet"   # the entry's name up to 0.13.0; carried over at start (`carry_over`)
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

    def __init__(self, service: str = SERVICE):
        self.service = service

    def _run(self, args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self.TOOL, *args], input=stdin, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise KeychainError("Nines could not reach this Mac's keychain.") from e

    def get(self) -> str | None:
        proc = self._run(["find-generic-password", "-s", self.service, "-a", ACCOUNT, "-w"])
        if proc.returncode == self.NOT_FOUND:
            return None
        if proc.returncode != 0:
            raise KeychainError("Nines could not read the API key from this Mac's keychain.")
        return proc.stdout.strip() or None

    def set(self, key: str) -> None:
        if not KEY_RE.fullmatch(key):   # never let anything else reach the tool's command line
            raise ValueError(NOT_A_KEY)
        # interactive mode reads the command from standard input, so the key is not in the process list
        self._run(["-i"], stdin=f'add-generic-password -U -s {self.service} -a {ACCOUNT} -l "{self.service} API key" '
                                f'-w "{key}"\n')
        if self.get() != key:
            raise KeychainError("Nines could not save the API key in this Mac's keychain.")

    def delete(self) -> None:
        proc = self._run(["delete-generic-password", "-s", self.service, "-a", ACCOUNT])
        if proc.returncode not in (0, self.NOT_FOUND):
            raise KeychainError("Nines could not remove the API key from this Mac's keychain.")


class WindowsCredentials:
    where = "Windows Credential Manager"
    GENERIC = 1              # CRED_TYPE_GENERIC
    LOCAL_MACHINE = 2        # CRED_PERSIST_LOCAL_MACHINE: this user on this computer, kept after sign-out
    NOT_FOUND = 1168         # ERROR_NOT_FOUND

    def __init__(self, service: str = SERVICE):
        self.service = service
        self.TARGET = f"{service}/{ACCOUNT}"

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
            raise KeychainError("Nines could not read the API key from Windows Credential Manager.")
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
        cred = CREDENTIAL(Type=self.GENERIC, TargetName=self.TARGET, Comment=f"{self.service} API key",
                          CredentialBlobSize=len(data), CredentialBlob=ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte)),
                          Persist=self.LOCAL_MACHINE, UserName=ACCOUNT)
        if not advapi.CredWriteW(ctypes.byref(cred), 0):
            raise KeychainError("Nines could not save the API key in Windows Credential Manager.")

    def delete(self) -> None:
        ctypes, advapi, _ = self._api()
        if not advapi.CredDeleteW(self.TARGET, self.GENERIC, 0) and ctypes.get_last_error() != self.NOT_FOUND:
            raise KeychainError("Nines could not remove the API key from Windows Credential Manager.")


class NoKeychain:
    where = ""

    def get(self) -> str | None:
        return None

    def set(self, key: str) -> None:
        raise KeychainError("Nines can't keep an API key on this computer. Set ANTHROPIC_API_KEY instead.")

    def delete(self) -> None:
        return None


def _default_store(service: str = SERVICE) -> Store:
    if sys.platform == "darwin":
        return MacKeychain(service)
    if sys.platform == "win32":
        return WindowsCredentials(service)
    return NoKeychain()


_store: Store | None = None
_old_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = _default_store()
    return _store


def old_store() -> Store:
    """The entry named Closet, where the key was kept up to 0.13.0."""
    global _old_store
    if _old_store is None:
        _old_store = _default_store(OLD_SERVICE)
    return _old_store


def use_store(s: Store | None, old: Store | None = None) -> None:
    """Use `s` instead of the computer's keychain, and `old` instead of its old entry, or none (tests); None goes back to
    the computer's."""
    global _store, _old_store
    _store = s
    _old_store = None if s is None else old or NoKeychain()


def keychain_key() -> str | None:
    """The key in the keychain: under Nines, else under Closet, where it stays until `carry_over` has moved it. Raises
    KeychainError when the keychain cannot be read."""
    key = store().get()
    if key is None:
        try:
            key = old_store().get()
        except Exception:   # the old entry is only a fallback
            key = None
    return key


def carry_over() -> bool:
    """At start: a key kept under Closet (up to 0.13.0) is saved under Nines, checked, and only then removed from Closet.
    When saving or checking it fails, the old entry is kept and read as before, and the next start tries again. When
    both hold a key, the one under Nines is the owner's latest and the old one is removed. Never raises; True when it
    moved a key. The key is never logged."""
    try:
        old = old_store()
        if isinstance(old, NoKeychain):
            return False
        key = old.get()
        if not key:
            return False
        new = store()
        if new.get() is not None:
            old.delete()
            return False
        new.set(key)
        if new.get() != key:
            new.delete()   # what is there is not the key: the old entry stays the one read
            return False
        old.delete()
        return True
    except Exception:   # a keychain that cannot be reached (a copy started before sign-in): left for the next start
        return False


def _saved() -> str | None:
    try:
        key = keychain_key()
    except Exception:   # a keychain that cannot be read is treated as holding no key; the environment still counts
        key = None
    if key is None and _sealed_dir is not None:
        try:
            return read_sealed(_sealed_dir)
        except Exception:
            return None
    return key


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


# ---------------------------------------------------------------- the sealed copy, while Windows keeps Nines running
# Windows' own data protection (DPAPI) with the machine's key: anything running on this computer that can read the
# file can unseal it, nothing elsewhere can (DECISIONS, "Kept running by Windows"). The file is JSON:
# {"sealed": "<base64>"} for a key, {"sealed": null} for a key removed while Credential Manager could not be changed.
SEALED_FILE = "api-key.sealed"
_ENTROPY = b"closet/api-key/v1"

_sealed_dir: Path | None = None   # the data folder whose sealed file `get` falls back to; None: no fallback


class Sealer(Protocol):
    def seal(self, data: bytes) -> bytes: ...
    def unseal(self, data: bytes) -> bytes: ...


class Dpapi:
    """CryptProtectData with CRYPTPROTECT_LOCAL_MACHINE: unsealed by any account on this computer, by no other."""
    UI_FORBIDDEN, LOCAL_MACHINE = 0x1, 0x4

    def _call(self, data: bytes, protect: bool) -> bytes:
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        def blob(raw: bytes):
            buf = ctypes.create_string_buffer(raw, len(raw))
            return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        source, _keep1 = blob(data)
        entropy, _keep2 = blob(_ENTROPY)
        out = Blob()
        if protect:
            ok = crypt32.CryptProtectData(ctypes.byref(source), "Nines", ctypes.byref(entropy), None, None,
                                          self.UI_FORBIDDEN | self.LOCAL_MACHINE, ctypes.byref(out))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                                            self.UI_FORBIDDEN, ctypes.byref(out))
        if not ok:
            raise KeychainError("Windows could not seal or unseal the API key.")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))

    def seal(self, data: bytes) -> bytes:
        return self._call(data, True)

    def unseal(self, data: bytes) -> bytes:
        return self._call(data, False)


_sealer: Sealer | None = None


def sealer() -> Sealer:
    global _sealer
    if _sealer is None:
        if sys.platform != "win32":
            raise KeychainError("Only Windows seals the API key to this computer.")
        _sealer = Dpapi()
    return _sealer


def use_sealer(s: Sealer | None) -> None:
    """Seal with `s` instead of Windows (tests); None goes back to Windows."""
    global _sealer
    _sealer = s


def keep_sealed(data_dir: Path | None) -> None:
    """Fall back to the sealed file in `data_dir` when Credential Manager gives no key; None stops falling back."""
    global _sealed_dir
    _sealed_dir = data_dir


def sealed_path(data_dir: Path) -> Path:
    return Path(data_dir) / SEALED_FILE


def write_sealed(data_dir: Path, key: str | None) -> None:
    """Keep `key` sealed in the data folder; None notes that there is no key (it was removed)."""
    if key is not None and not KEY_RE.fullmatch(key):
        raise ValueError(NOT_A_KEY)
    sealed = base64.b64encode(sealer().seal(key.encode("utf-8"))).decode("ascii") if key is not None else None
    path = sealed_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps({"sealed": sealed}), encoding="utf-8")
    os.replace(part, path)


def read_sealed(data_dir: Path) -> str | None:
    """The key in the sealed file, or None when there is no file or it says the key was removed."""
    path = sealed_path(data_dir)
    if not path.exists():
        return None
    sealed = json.loads(path.read_text(encoding="utf-8")).get("sealed")
    if not sealed:
        return None
    return sealer().unseal(base64.b64decode(sealed)).decode("utf-8") or None


def has_sealed(data_dir: Path) -> bool:
    return sealed_path(data_dir).exists()


def remove_sealed(data_dir: Path) -> None:
    sealed_path(data_dir).unlink(missing_ok=True)
    sealed_path(data_dir).with_name(SEALED_FILE + ".part").unlink(missing_ok=True)


def save(key: str, data_dir: Path | None) -> None:
    """Save `key`: in the keychain, and, with `data_dir` (Windows keeps Nines running), sealed there too. A keychain that
    cannot be written then is only a problem when the sealed file cannot be written either (a copy started before
    sign-in, which most likely cannot reach Credential Manager)."""
    if data_dir is None:
        store().set(key)
        return
    try:
        store().set(key)
    except KeychainError:
        pass
    write_sealed(data_dir, key)


def remove(data_dir: Path | None) -> None:
    """Remove the key: from the keychain (under Nines and under Closet, so an old entry does not bring it back), and,
    with `data_dir`, from the sealed file too (which then says it is gone)."""
    if data_dir is None:
        store().delete()
        old_store().delete()
        return
    for s in (store(), old_store()):
        try:
            s.delete()
        except KeychainError:
            pass
    write_sealed(data_dir, None)


def unseal_back(data_dir: Path) -> None:
    """When Windows stops keeping Nines running: what the sealed file says goes back into the keychain (run in the
    owner's own session, where Credential Manager can be written), then the file is removed."""
    path = sealed_path(data_dir)
    if path.exists():
        try:
            sealed = json.loads(path.read_text(encoding="utf-8")).get("sealed")
            if sealed:
                store().set(sealer().unseal(base64.b64decode(sealed)).decode("utf-8"))
            else:
                store().delete()
                old_store().delete()
        except (KeychainError, ValueError, OSError):
            pass   # the keychain keeps what it had; the owner can save the key again in Settings
    remove_sealed(data_dir)
