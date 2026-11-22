"""Who is asking through Tailscale, and whether it really was Tailscale that said so.

Closet listens only on 127.0.0.1, and Tailscale Serve passes the phone's requests on to it from the Tailscale service,
adding headers that say which signed-in member of the tailnet is asking (`Tailscale-User-Login`, `Tailscale-User-Name`;
Serve removes any a browser sent, and adds none for Funnel, its public way in). Any other program on this computer,
under any account, could connect to the same port and send the same headers. So on Windows, before Closet believes
them, it asks Windows which process owns the other end of the connection, and which process is the Tailscale service.
Only when they are the same process are the headers Tailscale's own. The service may run Tailscale's engine as a child
process (it starts it again if it fails), so a `tailscaled.exe` the service started itself counts as the service too.

Both questions normally need no special rights: any account can list TCP connections with their owning process (as
`netstat -ano` does), list processes with their parents, and read a service's status. The check has three answers:
True (the Tailscale service), False (Windows shows something else: another program owns the connection, the
connection is not there, or the Tailscale service is not installed or not running) and None (Windows could not be
asked: a call failed, or refused to say). `gate.py` refuses on False and believes the headers on True or None, so a
lookup that fails never shuts the owner out, while a program Windows shows not to be Tailscale is always refused.

Elsewhere (a Mac, tests) there is no such question to ask, `checker()` returns None, and the headers are believed.
`gate.py` reads them, refuses a Tailscale request that names no one, and records who came in; see DECISIONS, "The doors
decide who comes in".
"""
from __future__ import annotations

import ipaddress
import logging
import struct
import sys
import threading
import time
from collections.abc import Callable
from email.header import decode_header, make_header

log = logging.getLogger("closet.tailnet")

FUNNEL_HEADER = "tailscale-funnel-request"
LOGIN_HEADER = "tailscale-user-login"
NAME_HEADER = "tailscale-user-name"

SERVICE = "Tailscale"           # the Windows service the Tailscale installer adds
ENGINE = "tailscaled.exe"       # the program the service runs, and runs again as its child
PIDS_SECONDS = 30               # how long the service's process ids are kept before asking again

ROW = struct.Struct("<I4s2s2x4s2s2xI")    # MIB_TCPROW_OWNER_PID: state, local addr/port, remote addr/port, pid

Check = Callable[[str, int, int], bool | None]   # True: Tailscale; False: positively not; None: could not tell


def owner(table: bytes, client: tuple[str, int], server_port: int) -> int | None:
    """The process that owns `client`'s end of a connection to `server_port` on this computer.

    `table` is what GetExtendedTcpTable returns for IPv4 with owning processes: a count, then a
    row per connection. Seen from the client's side, its local end is `client` and its remote
    end is Closet's port. Addresses and ports are in network byte order.
    """
    try:
        address = ipaddress.IPv4Address(client[0]).packed
    except ValueError:
        return None
    port = client[1].to_bytes(2, "big")
    closet = server_port.to_bytes(2, "big")
    (count,) = struct.unpack_from("<I", table, 0)
    for i in range(count):
        offset = 4 + i * ROW.size
        if offset + ROW.size > len(table):
            break
        _state, local, local_port, _remote, remote_port, pid = ROW.unpack_from(table, offset)
        if local == address and local_port == port and remote_port == closet:
            return pid
    return None


def family(service_pid: int | None, processes: list[tuple[int, int, str]]) -> set[int]:
    """The service's own process and the copies of Tailscale's engine it started.

    `processes` is (process id, parent's id, program name) for each process running.
    """
    if not service_pid:
        return set()
    return {service_pid} | {pid for pid, parent, name in processes if parent == service_pid and name.lower() == ENGINE}


def _processes() -> list[tuple[int, int, str]]:
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):   # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    TH32CS_SNAPPROCESS, INVALID = 0x2, ctypes.c_void_p(-1).value

    snapshot = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID:
        raise ctypes.WinError()
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        found = []
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            found.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return found
    finally:
        kernel.CloseHandle(snapshot)


def _tailscale_pids() -> set[int]:
    """The Tailscale service's processes; empty when it is not installed or not running (raises when Windows will not
    say)."""
    pid = _service_pid()
    return family(pid, _processes()) if pid else set()


def _tcp_table() -> bytes:
    import ctypes
    from ctypes import wintypes

    get = ctypes.windll.iphlpapi.GetExtendedTcpTable
    get.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG,
                    ctypes.c_int, wintypes.ULONG]
    get.restype = wintypes.DWORD
    AF_INET, TCP_TABLE_OWNER_PID_ALL, ERROR_INSUFFICIENT_BUFFER = 2, 5, 122
    size = wintypes.DWORD(0)
    for _ in range(5):   # connections can open between asking the size and reading the table
        buffer = ctypes.create_string_buffer(size.value or 1)
        result = get(buffer, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
        if result == 0:
            return buffer.raw
        if result != ERROR_INSUFFICIENT_BUFFER:
            raise OSError(result, "GetExtendedTcpTable failed")
        size = wintypes.DWORD(size.value + 4096)
    raise OSError("The list of connections kept growing")


def _service_pid(name: str = SERVICE) -> int | None:
    """The process id of the running service (Tailscale's, unless named), or None if it isn't installed or isn't
    running. Raises when Windows will not say (the service cannot be opened for any other reason, such as a copy of
    Nines started before sign-in that is not allowed to ask): that is not knowing, not a "no"."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.OpenSCManagerW.restype = ctypes.c_void_p
    advapi.OpenServiceW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD]
    advapi.OpenServiceW.restype = ctypes.c_void_p
    advapi.QueryServiceStatusEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.DWORD)]
    advapi.QueryServiceStatusEx.restype = wintypes.BOOL
    advapi.CloseServiceHandle.argtypes = [ctypes.c_void_p]
    SC_MANAGER_CONNECT, SERVICE_QUERY_STATUS, SC_STATUS_PROCESS_INFO, SERVICE_RUNNING = 0x1, 0x4, 0, 4
    ERROR_SERVICE_DOES_NOT_EXIST = 1060

    manager = advapi.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not manager:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        service = advapi.OpenServiceW(manager, name, SERVICE_QUERY_STATUS)
        if not service:
            error = ctypes.get_last_error()
            if error == ERROR_SERVICE_DOES_NOT_EXIST:
                return None   # not installed
            raise ctypes.WinError(error)
        try:
            status = (wintypes.DWORD * 9)()   # SERVICE_STATUS_PROCESS
            needed = wintypes.DWORD(0)
            if not advapi.QueryServiceStatusEx(service, SC_STATUS_PROCESS_INFO, status, ctypes.sizeof(status),
                                               ctypes.byref(needed)):
                raise ctypes.WinError(ctypes.get_last_error())
            state, pid = status[1], status[7]
            return pid if state == SERVICE_RUNNING and pid else None
        finally:
            advapi.CloseServiceHandle(service)
    finally:
        advapi.CloseServiceHandle(manager)


class WindowsCheck:
    """Asks Windows, for each request that says it came through Tailscale, whether it did: True, False, or None when
    Windows could not be asked (see the top)."""

    def __init__(self, table: Callable[[], bytes] = _tcp_table, tailscale_pids: Callable[[], set[int]] = _tailscale_pids,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._table = table
        self._tailscale_pids = tailscale_pids
        self._clock = clock
        self._lock = threading.Lock()
        self._pids: tuple[float, set[int]] | None = None
        self._warned = False

    def _tailscale(self, fresh: bool) -> set[int]:
        with self._lock:
            if fresh or not self._pids or self._clock() - self._pids[0] >= PIDS_SECONDS:
                self._pids = (self._clock(), self._tailscale_pids())
            return self._pids[1]

    def __call__(self, client_host: str, client_port: int, server_port: int) -> bool | None:
        try:
            pid = owner(self._table(), (client_host, client_port), server_port)
            # Not in the table: the connection is gone. Tailscale Serve keeps it open until it has the answer, so this
            # is only ever a program that sent its request and dropped the connection: a no, not an unknown.
            if pid is None:
                return False
            if pid in self._tailscale(fresh=False):
                return True
            # Tailscale may have restarted since its ids were kept; ask once more before saying no.
            return pid in self._tailscale(fresh=True)
        except Exception as exc:  # noqa: BLE001 - could not tell, and why said once
            if not self._warned:
                log.warning("Could not check that a request came through Tailscale: %s", exc)
                self._warned = True
            return None


def header_text(value: str) -> str:
    """Tailscale writes a name that is not plain ASCII the way email headers do (RFC 2047)."""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def funnel(headers) -> bool:
    """Whether Tailscale says this came in through Funnel, its way in from the public internet."""
    return bool(headers.get(FUNNEL_HEADER))


def viewer(headers) -> dict[str, str] | None:
    """Who Tailscale says is asking ({login, name, via}), or None when it says no one. Not yet believed: see
    `WindowsCheck`."""
    login = headers.get(LOGIN_HEADER)
    if not login or funnel(headers):
        return None
    login = header_text(login)
    return {"login": login, "name": header_text(headers.get(NAME_HEADER) or login), "via": "tailscale"}


def checker() -> Check | None:
    """The check for this computer, or None where there isn't one (anywhere but Windows)."""
    return WindowsCheck() if sys.platform == "win32" else None
