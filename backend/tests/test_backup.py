import json
import time

from closet import autostart, backup, cli, config, demo, instance, phone

from .conftest import upload


def test_backup_then_restore_brings_everything_back(client, services, cfg, tmp_path):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    item = upload(client, name="Keeper").json()
    services.worker.drain()
    assert client.put("/api/settings", json={"backup_folder": str(folder)}).json()["backup_folder"] == str(folder)
    result = client.post("/api/backup").json()
    assert result["ok"] and result["images_copied"] == 4
    assert client.get("/api/settings").json()["last_good_backup"] == result["at"]
    root = folder / backup.SUBFOLDER
    assert json.loads((root / "manifest.json").read_text())["last_backup"] == result["at"]
    assert "passphrase" not in "".join(p.name for p in root.rglob("*")) and not list(root.rglob("settings.json"))

    client.delete(f"/api/items/{item['id']}")
    upload(client, key="later", name="Added after the backup")
    services.stop()
    restored = backup.restore(cfg, folder)
    assert restored["items"] == 1 and restored["previous_moved_to"]
    names = [i["name"] for i in client.get("/api/items").json()["items"]]
    assert names == ["Keeper"]
    body = client.get(f"/api/items/{item['id']}").json()
    assert client.get(body["photos"][0]["cutout_url"]).status_code == 200


def test_a_missing_backup_folder_is_reported_and_the_last_good_date_is_kept(client, services, cfg, tmp_path):
    folder = tmp_path / "Synced"
    folder.mkdir()
    upload(client)
    client.put("/api/settings", json={"backup_folder": str(folder)})
    good = client.post("/api/backup").json()
    folder.rename(tmp_path / "Unplugged")
    bad = client.post("/api/backup")
    assert bad.status_code == 409 and "not available" in bad.json()["error"]
    s = client.get("/api/settings").json()
    assert s["last_backup"]["ok"] is False and s["last_good_backup"] == good["at"]
    assert client.put("/api/settings", json={"backup_folder": str(tmp_path / "nope")}).status_code == 422


def test_nightly_backup_catches_up_after_the_program_was_off(services, cfg, tmp_path, client):
    folder = tmp_path / "Synced"
    folder.mkdir()
    upload(client)
    assert services.scheduler.tick() is None  # no folder chosen: nothing to do
    services.state.update(backup_folder=str(folder))
    first = services.scheduler.tick()
    assert first["ok"] and first["kind"] == "nightly"
    assert services.scheduler.tick() is None  # done within the last day
    assert backup.is_due(services.state, now=time.time() + backup.DUE_AFTER_SECONDS + 5)


def test_only_the_newest_snapshots_are_kept(services, cfg, tmp_path, client, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    upload(client)
    stamps = iter(f"202601{d:02d}-010101" for d in range(1, 30))
    monkeypatch.setattr(backup, "_stamp", lambda: next(stamps))
    for _ in range(backup.KEEP_SNAPSHOTS + 3):
        assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    snaps = sorted((folder / backup.SUBFOLDER / "db").glob("*.sqlite"))
    assert len(snaps) == backup.KEEP_SNAPSHOTS and snaps[0].name == "closet-20260104-010101.sqlite"


def test_restore_command_refuses_an_empty_folder(cfg, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLOSET_DATA_DIR", str(cfg.data_dir))
    (tmp_path / "empty").mkdir()
    assert cli.main(["restore", str(tmp_path / "empty")]) == 1
    assert "No backup was found" in capsys.readouterr().out


def test_demo_closet_has_about_forty_items_and_leaves_the_real_one_alone(client, cfg):
    upload(client, name="Mine")
    assert client.post("/api/profile", json={"profile": "demo"}).json() == {"profile": "demo"}
    listed = client.get("/api/items").json()["items"]
    assert len(listed) == 43 and all(i["name"] != "Mine" for i in listed)
    with_photo = [i for i in listed if i["has_photo"]]
    assert len(with_photo) == 7 and all(i["cutout_state"] == "ready" and i["thumb_url"] for i in with_photo)
    assert all(i["has_illustration"] for i in listed)
    one = client.get(f"/api/items/{with_photo[0]['id']}").json()
    assert one["illustration_svg"].startswith("<svg") and client.get(one["photos"][0]["cutout_url"]).status_code == 200
    drawn = client.get(listed[0]["illustration_url"])
    assert drawn.status_code == 200 and drawn.headers["content-type"].startswith("image/svg+xml") and drawn.text.startswith("<svg")
    assert demo.ensure(cfg) == 0  # seeding twice adds nothing
    assert client.get("/api/session").json()["profile"] == "demo"
    client.post("/api/profile", json={"profile": "main"})
    assert [i["name"] for i in client.get("/api/items").json()["items"]] == ["Mine"]
    assert client.post("/api/profile", json={"profile": "other"}).status_code == 422


HOST = "my-pc.example-tailnet.ts.net"
STATUS = json.dumps({"BackendState": "Running", "Self": {"DNSName": HOST + "."}})


def _serve(*shares):
    """A hand-written `tailscale serve status --json`: (https port, path, proxy target) per share."""
    tcp, web = {}, {}
    for port, path, target in shares:
        tcp[str(port)] = {"HTTPS": True}
        web.setdefault(f"{HOST}:{port}", {"Handlers": {}})["Handlers"][path] = {"Proxy": target}
    return json.dumps({"TCP": tcp, "Web": web}) if shares else "{}"


def _phone_info(serve_text, status_text=STATUS, code=0):
    import closet.phone as p

    def runner(args, **_):
        class R:
            returncode = code
            stdout = serve_text if args[1:3] == ["serve", "status"] else status_text
        return R()

    real = p.find_tailscale
    try:
        p.find_tailscale = lambda: "/usr/bin/tailscale"
        return phone.info(8765, runner=runner)
    finally:
        p.find_tailscale = real


def test_phone_address_is_only_one_that_reaches_closet():
    # no shares: the computer's bare name is not Closet's address
    got = _phone_info(_serve())
    assert got["running"] is True and got["address"] is None and got["stop_command"] is None
    assert got["command"] == "tailscale serve --bg 8765" and got["others_share"] is False

    # Closet on 443
    got = _phone_info(_serve((443, "/", "http://127.0.0.1:8765")))
    assert got["address"] == f"https://{HOST}" and got["stop_command"] == "tailscale serve --https=443 off"

    # another app on 443, Closet on 8443 (localhost counts too)
    got = _phone_info(_serve((443, "/", "http://127.0.0.1:3000"), (8443, "/", "http://localhost:8765")))
    assert got["address"] == f"https://{HOST}:8443" and got["stop_command"] == "tailscale serve --https=8443 off"
    assert got["others_share"] is True

    # another app only: no address, and a command that leaves 443 to it
    got = _phone_info(_serve((443, "/", "http://127.0.0.1:3000")))
    assert got["address"] is None and got["stop_command"] is None
    assert got["command"] == "tailscale serve --bg --https=8443 8765"


def test_phone_command_skips_ports_already_taken():
    taken = _serve((443, "/", "http://127.0.0.1:3000"), (8443, "/", "http://127.0.0.1:4000"))
    assert _phone_info(taken)["command"] == "tailscale serve --bg --https=8444 8765"
    assert phone.start_command(8765, [443, 8443, 8444]) == "tailscale serve --bg --https=10000 8765"
    assert phone.start_command(8765, [443, 8443, 8444, 10000]) == "tailscale serve --bg --https=10001 8765"
    # a share of another port of this computer, or of Closet at a path, is not Closet
    got = _phone_info(_serve((443, "/", "http://127.0.0.1:87650"), (8443, "/closet", "http://127.0.0.1:8765")))
    assert got["address"] is None
    # a foreground `tailscale serve` still running counts as well
    fg = json.dumps({"Foreground": {"abc": json.loads(_serve((443, "/", "http://127.0.0.1:8765")))}})
    assert _phone_info(fg)["address"] == f"https://{HOST}"
    for text in ("{}", ""):
        assert phone.parse_serve(text, 8765) == {"closet": None, "taken": []}


def test_phone_info_never_raises():
    for serve_text, status_text in (("not json", "not json"), ("[1]", "[1]"), ('{"Web": {"x:443": 5}}', "{}")):
        got = _phone_info(serve_text, status_text)
        assert got["tailscale_installed"] is True and got["address"] is None
    assert _phone_info(_serve((443, "/", "http://127.0.0.1:8765")), code=1)["address"] is None

    import closet.phone as p

    def broken(*a, **k):
        raise OSError("no tailscale")
    real = p.find_tailscale
    try:
        p.find_tailscale = lambda: "/usr/bin/tailscale"
        assert phone.info(8765, runner=broken)["address"] is None
        p.find_tailscale = lambda: None
        assert phone.info(8765)["tailscale_installed"] is False
    finally:
        p.find_tailscale = real


def test_start_at_login_writes_and_removes_its_entry(tmp_path):
    assert autostart.is_enabled("linux", tmp_path) is False
    autostart.set_enabled(True, exe="/opt/Closet/closet", platform="linux", home=tmp_path)
    entry = (tmp_path / ".config" / "autostart" / "closet.desktop").read_text()
    assert '"/opt/Closet/closet" --no-browser' in entry and autostart.is_enabled("linux", tmp_path)
    autostart.set_enabled(True, exe="/Applications/Closet.app/Contents/MacOS/Closet", platform="darwin", home=tmp_path)
    assert autostart.is_enabled("darwin", tmp_path)
    autostart.set_enabled(False, platform="linux", home=tmp_path)
    assert not autostart.is_enabled("linux", tmp_path)


def test_only_one_copy_runs_per_data_folder(cfg):
    assert instance.running_instance(cfg) is None
    instance.write_lock(cfg, 1)  # stale lock: nothing answers on that port
    assert instance.running_instance(cfg) is None
    port = instance.pick_port("127.0.0.1", 18765)
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
        assert instance.pick_port("127.0.0.1", port) == port + 1
    instance.clear_lock(cfg)
    assert not cfg.lock_path.exists()


def test_selfcheck_reports_each_library(cfg):
    result = cli.selfcheck(False, cfg)
    assert result["webp"]["ok"] and result["onnxruntime"]["ok"] and result["database"]["ok"]
    assert result["model_state"] == {"ok": True, "detail": "missing"}
    assert result["tagger"]["ok"]
    assert "43 items" in result["database"]["detail"]
    assert result["drawing"]["ok"] and "drew a shirt" in result["drawing"]["detail"]


def test_settings_follow_the_environment(tmp_path):
    c = config.load({"CLOSET_DATA_DIR": str(tmp_path / "d"), "CLOSET_HOST": "0.0.0.0", "CLOSET_PORT": "9000", "CLOSET_NO_AUTO_DOWNLOAD": "1"})
    assert (c.data_dir, c.host, c.port, c.auto_download_model) == (tmp_path / "d", "0.0.0.0", 9000, False)
    assert c.db_path("demo") == tmp_path / "d" / "demo" / "closet.db"
