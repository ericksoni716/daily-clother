"""Who is asking through Tailscale (closet/tailnet.py): its headers, and on Windows, believing them only from the
Tailscale service. The Windows questions are tested from byte fixtures, as Windows answers them; one test asks a real
Windows computer and runs only there."""
import os
import socket
import struct

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import cli, tailnet

from .conftest import PASSPHRASE

TAILSCALE, OTHER = 4321, 9999
PORT = 8765
PHONE = "closet-pc.example-tailnet.ts.net"
ME = {"Tailscale-User-Login": "owner@example.com", "Tailscale-User-Name": "Sam Owner"}


def row(local: str, local_port: int, remote_port: int, pid: int, remote: str = "127.0.0.1") -> bytes:
    def addr(a: str) -> bytes:
        return bytes(int(p) for p in a.split("."))
    return tailnet.ROW.pack(5, addr(local), local_port.to_bytes(2, "big"), addr(remote), remote_port.to_bytes(2, "big"),
                            pid)


def table(*rows: bytes) -> bytes:
    return struct.pack("<I", len(rows)) + b"".join(rows)


CONNECTIONS = table(
    row("127.0.0.1", 50001, PORT, TAILSCALE),          # Tailscale Serve, passing a phone's request on
    row("127.0.0.1", 50002, PORT, OTHER),              # some other program
    row("127.0.0.1", 50003, 443, TAILSCALE),           # Tailscale, but to somewhere else
)


def test_finds_who_owns_the_other_end():
    assert tailnet.owner(CONNECTIONS, ("127.0.0.1", 50001), PORT) == TAILSCALE
    assert tailnet.owner(CONNECTIONS, ("127.0.0.1", 50002), PORT) == OTHER
    assert tailnet.owner(CONNECTIONS, ("127.0.0.1", 50003), PORT) is None
    assert tailnet.owner(CONNECTIONS, ("127.0.0.1", 50009), PORT) is None
    assert tailnet.owner(CONNECTIONS, ("::1", 50001), PORT) is None
    assert tailnet.owner(CONNECTIONS, ("testclient", 50001), PORT) is None
    assert tailnet.owner(table(), ("127.0.0.1", 50001), PORT) is None
    assert tailnet.owner(CONNECTIONS[:30], ("127.0.0.1", 50002), PORT) is None   # a table cut short


def test_believes_only_the_tailscale_service():
    check = tailnet.WindowsCheck(table=lambda: CONNECTIONS, tailscale_pids=lambda: {TAILSCALE})
    assert check("127.0.0.1", 50001, PORT)
    assert not check("127.0.0.1", 50002, PORT)
    assert not check("127.0.0.1", 50009, PORT)


def test_believes_no_one_when_tailscale_is_not_running_or_windows_will_not_say():
    assert not tailnet.WindowsCheck(table=lambda: CONNECTIONS, tailscale_pids=set)("127.0.0.1", 50001, PORT)

    def broken() -> bytes:
        raise OSError("no")
    assert not tailnet.WindowsCheck(table=broken, tailscale_pids=lambda: {TAILSCALE})("127.0.0.1", 50001, PORT)


def test_the_service_and_the_engine_it_started_count_and_nothing_else():
    processes = [(TAILSCALE, 600, "tailscaled.exe"), (5555, TAILSCALE, "tailscaled.exe"),
                 (5556, TAILSCALE, "notepad.exe"), (5557, 1234, "TAILSCALED.EXE")]
    assert tailnet.family(TAILSCALE, processes) == {TAILSCALE, 5555}
    assert tailnet.family(None, processes) == set()


def test_a_restarted_service_is_noticed():
    now, pids, asked = [0.0], [{TAILSCALE}], []

    def tailscale_pids():
        asked.append(1)
        return pids[0]
    check = tailnet.WindowsCheck(table=lambda: table(row("127.0.0.1", 50001, PORT, 5555)),
                                 tailscale_pids=tailscale_pids, clock=lambda: now[0])
    assert not check("127.0.0.1", 50001, PORT)
    pids[0] = {5555}   # Tailscale started again under a new process id
    assert check("127.0.0.1", 50001, PORT)
    count = len(asked)
    assert check("127.0.0.1", 50001, PORT) and len(asked) == count   # kept, not asked every time
    now[0] += tailnet.PIDS_SECONDS
    assert check("127.0.0.1", 50001, PORT) and len(asked) == count + 1


@pytest.mark.parametrize("headers, viewer", [
    (ME, {"login": "owner@example.com", "name": "Sam Owner", "via": "tailscale"}),
    ({"Tailscale-User-Login": "owner@example.com"}, {"login": "owner@example.com", "name": "owner@example.com",
                                                      "via": "tailscale"}),
    ({"Tailscale-User-Login": "owner@example.com", "Tailscale-User-Name": "=?utf-8?q?Zo=C3=AB_Owner?="},
     {"login": "owner@example.com", "name": "Zoë Owner", "via": "tailscale"}),   # RFC 2047, as Tailscale sends it
    ({"Tailscale-User-Name": "Sam Owner"}, None),
    ({**ME, "Tailscale-Funnel-Request": "?1"}, None),
    ({}, None),
])
def test_who_tailscale_says_is_asking(headers, viewer):
    assert tailnet.viewer({k.lower(): v for k, v in headers.items()}) == viewer


# ------------------------------------------------------------------ through the app


def phone_client(services, check=None) -> TestClient:
    client = TestClient(app_module.create_app(services, tailscale_check=check), base_url=f"https://{PHONE}")
    assert client.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    return client


def came_in(client, headers=None) -> dict:
    return client.get("/api/settings", headers=headers or {}).json()["came_in"]


def test_who_came_in_is_recorded_and_the_passphrase_is_still_asked(services):
    def believed(host, port, server_port):
        return True
    phone = phone_client(services, believed)
    assert came_in(phone, ME) == {"via": "tailscale", "login": "owner@example.com", "name": "Sam Owner"}
    # in this pull request a phone that names no one goes on to the passphrase as before
    assert came_in(phone) == {"via": "tailscale", "login": None, "name": None}
    phone.cookies.clear()
    assert phone.get("/api/settings", headers=ME).status_code == 401


def test_tailscale_headers_from_anyone_but_tailscale_are_not_believed(services):
    asked = []

    def check(host, port, server_port):
        asked.append((host, port, server_port))
        return False
    phone = phone_client(services, check)
    assert came_in(phone, ME) == {"via": "tailscale", "login": None, "name": None}
    assert asked and asked[-1][1:] == (50000, 443)
    asked.clear()
    assert came_in(phone) == {"via": "tailscale", "login": None, "name": None} and not asked   # nothing to ask about
    assert phone.get("/api/health", headers=ME).status_code == 200 and not asked             # nor for the health check


def test_tailscale_headers_under_a_local_name_are_ignored(client):
    assert came_in(client, ME) == {"via": "computer", "login": None, "name": None}


def test_funnel_is_never_a_way_in(services):
    phone = phone_client(services)
    for path in ("/api/health", "/api/session"):
        r = phone.get(path, headers={**ME, "Tailscale-Funnel-Request": "?1"})
        assert r.status_code == 403 and r.json() == {"detail": app_module.gate.FUNNEL}
    page = phone.get("/", headers={"Tailscale-Funnel-Request": "?1"})
    assert page.status_code == 403 and "<h1>Closet is not on the open internet</h1>" in page.text


def test_a_forwarded_for_header_cannot_choose_the_address_checked(services):
    """Served as the launcher serves it, X-Forwarded-For is ignored: the check is asked about the real connection."""
    asked = []
    app = app_module.create_app(services, tailscale_check=lambda host, port, server_port: asked.append((host, port)) or port == 40000)
    config = cli.server_config(app, "127.0.0.1", PORT)
    assert config.proxy_headers is False
    config.load()
    phone = TestClient(config.loaded_app, base_url=f"https://{PHONE}", client=("127.0.0.1", 50000))
    assert phone.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    r = phone.get("/api/settings", headers={**ME, "X-Forwarded-For": "127.0.0.1:40000"})
    assert r.json()["came_in"]["login"] is None and asked == [("127.0.0.1", 50000)]


@pytest.mark.windows
def test_windows_answers_the_questions():
    """On a real Windows computer: the calls find this process's own connection, its parent and a service."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    client = socket.create_connection(server.getsockname())
    try:
        here, port = client.getsockname()
        assert tailnet.owner(tailnet._tcp_table(), (here, port), server.getsockname()[1]) == os.getpid()
        assert (os.getpid(), os.getppid()) in {(pid, parent) for pid, parent, _ in tailnet._processes()}
        assert tailnet._service_pid("EventLog")             # always running on Windows
        assert tailnet._service_pid("NoSuchServiceHere") is None
        check = tailnet.WindowsCheck(tailscale_pids=lambda: {os.getpid()})
        assert check(here, port, server.getsockname()[1])
        assert not tailnet.WindowsCheck()(here, port, server.getsockname()[1])   # this process is not Tailscale
    finally:
        client.close()
        server.close()
