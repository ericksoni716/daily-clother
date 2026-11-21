import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import autostart, backup, cli, config, db, demo, instance, phone

from .conftest import PASSPHRASE, FakeClaude, fake_cutter, upload


def test_backup_then_restore_brings_everything_back(client, services, cfg, tmp_path):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    item = upload(client, name="Keeper").json()
    services.worker.drain()
    url = f"/api/items/{item['id']}"
    assert client.patch(url, json={"category": "polo", "price_cents": 1234, "notes": "Résumé 衣服"}).status_code == 200
    assert client.post(url + "/wears").status_code == 201
    assert client.put(url + "/details", json={"details": {"placket_buttons": 2}}).status_code == 200
    conn = db.connect(cfg.db_path("main"))
    try:
        saved_database = list(conn.iterdump())
    finally:
        conn.close()
    saved_images = {p.relative_to(cfg.images_dir("main")): p.read_bytes()
                    for p in cfg.images_dir("main").rglob("*") if p.is_file()}
    assert client.put("/api/settings", json={"backup_folder": str(folder)}).json()["backup_folder"] == str(folder)
    result = client.post("/api/backup").json()
    assert result["ok"] and result["images_copied"] == 4
    assert client.get("/api/settings").json()["last_good_backup"] == result["at"]
    root = folder / backup.SUBFOLDER
    assert json.loads((root / "manifest.json").read_text())["last_backup"] == result["at"]
    assert "passphrase" not in "".join(p.name for p in root.rglob("*")) and not list(root.rglob("settings.json"))
    saved_settings = cfg.state_path.read_bytes()

    client.delete(f"/api/items/{item['id']}")
    upload(client, key="later", name="Added after the backup")
    services.stop()
    restored = backup.restore(cfg, folder)
    assert restored["items"] == 1 and restored["previous_moved_to"]
    conn = db.connect(cfg.db_path("main"))
    try:
        assert list(conn.iterdump()) == saved_database
    finally:
        conn.close()
    assert {p.relative_to(cfg.images_dir("main")): p.read_bytes()
            for p in cfg.images_dir("main").rglob("*") if p.is_file()} == saved_images
    assert cfg.state_path.read_bytes() == saved_settings
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


@pytest.mark.parametrize("same_second", [False, True])
def test_failed_image_copy_does_not_publish_a_snapshot(client, services, cfg, tmp_path, monkeypatch, same_second):
    folder = tmp_path / "Synced"
    folder.mkdir()
    monkeypatch.setattr(backup, "_stamp", lambda: "20260101-010101")
    upload(client, name="Keeper")
    good = backup.run_backup(cfg, services.state, folder=folder)
    root = folder / backup.SUBFOLDER
    previous = (root / "db" / good["snapshot"]).read_bytes()
    manifest = (root / "manifest.json").read_bytes()
    upload(client, key="later")
    if not same_second:
        monkeypatch.setattr(backup, "_stamp", lambda: "20260102-010101")

    def interrupted_copy(src, dest, *args, **kwargs):
        Path(dest).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(backup.shutil, "copy2", interrupted_copy)
    failed = backup.run_backup(cfg, services.state, folder=folder)
    assert not failed["ok"]
    assert sorted(p.name for p in (root / "db").glob("closet-*.sqlite")) == [good["snapshot"]]
    assert (root / "db" / good["snapshot"]).read_bytes() == previous
    assert (root / "manifest.json").read_bytes() == manifest


def test_interrupted_image_refresh_preserves_the_previous_backup(client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    item = upload(client).json()
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    rel = item["photos"][0]["url"].removeprefix("/media/")
    previous = (cfg.images_dir("main") / rel).read_bytes()
    digest = hashlib.sha256(previous).hexdigest()
    saved = folder / backup.SUBFOLDER / backup.CONTENT / digest[:2] / digest
    assert saved.read_bytes() == previous
    (cfg.images_dir("main") / rel).write_bytes(previous + b"changed")

    def interrupted_copy(src, dest, *args, **kwargs):
        Path(dest).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(backup.shutil, "copy2", interrupted_copy)
    assert not backup.run_backup(cfg, services.state, folder=folder)["ok"]
    assert saved.read_bytes() == previous


def test_item_deleted_during_backup_cannot_produce_a_successful_incomplete_snapshot(
        client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    item = upload(client).json()
    snapshot = db.snapshot

    def snapshot_then_delete(src, dest):
        snapshot(src, dest)
        assert client.delete(f"/api/items/{item['id']}").status_code == 204

    monkeypatch.setattr(db, "snapshot", snapshot_then_delete)
    result = backup.run_backup(cfg, services.state, folder=folder)
    assert not result["ok"]
    assert not list((folder / backup.SUBFOLDER / "db").glob("closet-*.sqlite"))


def test_restore_refuses_missing_images_without_changing_the_live_closet(client, services, cfg, tmp_path):
    folder = tmp_path / "Synced"
    folder.mkdir()
    item = upload(client).json()
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    rel = item["photos"][0]["url"].removeprefix("/media/")
    digest = hashlib.sha256((cfg.images_dir("main") / rel).read_bytes()).hexdigest()
    (folder / backup.SUBFOLDER / backup.CONTENT / digest[:2] / digest).unlink()
    upload(client, key="later", name="Not backed up")
    services.stop()
    with pytest.raises(backup.BackupError, match="image"):
        backup.restore(cfg, folder)
    assert len(client.get("/api/items").json()["items"]) == 2
    assert (cfg.images_dir("main") / rel).is_file()


@pytest.mark.parametrize("failure", ["database", "images", "migration", "install"])
def test_failed_restore_leaves_the_live_closet_in_place(client, services, cfg, tmp_path, monkeypatch, failure):
    folder = tmp_path / "Synced"
    folder.mkdir()
    upload(client, name="Backed up")
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    upload(client, key="later", name="Not backed up")
    services.stop()
    images_before = {p.relative_to(cfg.images_dir("main")): p.read_bytes()
                     for p in cfg.images_dir("main").rglob("*") if p.is_file()}
    settings_before = cfg.state_path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as m:
        if failure == "database":
            m.setattr(backup.shutil, "copy2", fail)
            m.setattr(db, "snapshot", fail)
        elif failure == "images":
            m.setattr(backup.shutil, "copytree", fail)   # a backup in the old layout
            m.setattr(backup.shutil, "copy2", fail)      # images kept by content, copied one by one
        elif failure == "migration":
            m.setattr(db, "migrate", fail)
        else:
            real_replace = Path.replace
            real_copytree = backup.shutil.copytree

            def fail_install(path, target):
                if Path(target) == cfg.images_dir("main") and path.parent.name.startswith(".restore-"):
                    raise OSError("disk full")
                return real_replace(path, target)

            def fail_copytree(src, dest, *args, **kwargs):
                if Path(dest) == cfg.images_dir("main"):
                    raise OSError("disk full")
                return real_copytree(src, dest, *args, **kwargs)

            m.setattr(Path, "replace", fail_install)
            # The old implementation installs with copytree, not a rename.
            m.setattr(backup.shutil, "copytree", fail_copytree)
        with pytest.raises(OSError, match="disk full"):
            backup.restore(cfg, folder)

    assert cfg.db_path("main").is_file()
    conn = db.connect(cfg.db_path("main"))
    try:
        assert {r[0] for r in conn.execute("SELECT name FROM items")} == {"Backed up", "Not backed up"}
    finally:
        conn.close()
    assert {p.relative_to(cfg.images_dir("main")): p.read_bytes()
            for p in cfg.images_dir("main").rglob("*") if p.is_file()} == images_before
    assert cfg.state_path.read_bytes() == settings_before


def test_restore_command_refuses_an_empty_folder(cfg, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLOSET_DATA_DIR", str(cfg.data_dir))
    (tmp_path / "empty").mkdir()
    assert cli.main(["restore", str(tmp_path / "empty")]) == 1
    assert "No backup was found" in capsys.readouterr().out


# ---------------------------------------------------------------- the images of each snapshot, and old backups

def _closet_now(cfg):
    """The real closet as it stands: its database, line by line, and every image."""
    conn = db.connect(cfg.db_path("main"))
    try:
        dump = list(conn.iterdump())
    finally:
        conn.close()
    images = {p.relative_to(cfg.images_dir("main")).as_posix(): p.read_bytes()
              for p in cfg.images_dir("main").rglob("*") if p.is_file()}
    return dump, images


def _cutout(client, item_id) -> str:
    return client.get(f"/api/items/{item_id}").json()["photos"][0]["cutout_url"].removeprefix("/media/")


def _old_layout_backup(cfg, folder, stamp):
    """A backup as the program wrote them before images were kept by content (#218): the database snapshot, and
    one images folder shared by every snapshot, a file copied again only when its size changed."""
    root = folder / backup.SUBFOLDER
    snap = root / "db" / f"closet-{stamp}.sqlite"
    db.snapshot(cfg.db_path("main"), snap)
    for f in cfg.images_dir("main").rglob("*"):
        if f.is_file():
            dest = root / "images" / f.relative_to(cfg.images_dir("main"))
            if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
    (root / "manifest.json").write_text(json.dumps(
        {"last_backup": "2026-01-01T01:01:01Z", "snapshot": snap.name, "snapshots": [snap.name],
         "data_version": db.latest_version()}, indent=1))
    return snap.name


def test_restoring_an_older_snapshot_gives_its_own_cutout(client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    item = upload(client).json()
    services.worker.drain()
    cut = cfg.images_dir("main") / _cutout(client, item["id"])
    monkeypatch.setattr(backup, "_stamp", lambda: "20260101-010101")
    first = backup.run_backup(cfg, services.state, folder=folder)
    assert first["ok"]
    backed_up = _closet_now(cfg)
    cut.write_bytes(cut.read_bytes() + b"a newer cutout")   # the cutout made again, under the same name
    monkeypatch.setattr(backup, "_stamp", lambda: "20260102-010101")
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    newer = _closet_now(cfg)
    services.stop()

    monkeypatch.setattr(backup, "_stamp", lambda: "20260103-010101")
    backup.restore(cfg, folder, first["snapshot"])
    assert _closet_now(cfg) == backed_up
    backup.restore(cfg, folder)   # the newest still has the newer one
    assert _closet_now(cfg) == newer


def test_an_unchanged_closet_adds_no_images_and_a_damaged_copy_is_made_again(client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    upload(client)
    services.worker.drain()
    monkeypatch.setattr(backup, "_stamp", lambda: "20260101-010101")
    assert backup.run_backup(cfg, services.state, folder=folder)["images_copied"] == 4
    root = folder / backup.SUBFOLDER
    stored = sorted(p.name for p in root.rglob("*") if p.is_file() and "db" not in p.parts)
    monkeypatch.setattr(backup, "_stamp", lambda: "20260102-010101")
    assert backup.run_backup(cfg, services.state, folder=folder)["images_copied"] == 0
    assert sorted(p.name for p in root.rglob("*") if p.is_file() and "db" not in p.parts) == stored
    blob = next(p for p in (root / backup.CONTENT).rglob("*") if p.is_file())
    blob.write_bytes(b"")   # a copy cut short, as an unplugged drive can leave it
    monkeypatch.setattr(backup, "_stamp", lambda: "20260103-010101")
    assert backup.run_backup(cfg, services.state, folder=folder)["images_copied"] == 1
    assert hashlib.sha256(blob.read_bytes()).hexdigest() == blob.name


def test_an_old_layout_backup_still_restores_its_own_images(client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    item = upload(client, name="Backed up").json()
    services.worker.drain()
    cut = cfg.images_dir("main") / _cutout(client, item["id"])
    old = _old_layout_backup(cfg, folder, "20260101-010101")
    backed_up = _closet_now(cfg)
    cut.write_bytes(cut.read_bytes() + b"a newer cutout")
    upload(client, key="later", name="Not in the old backup")
    services.worker.drain()
    monkeypatch.setattr(backup, "_stamp", lambda: "20260102-010101")
    new = backup.run_backup(cfg, services.state, folder=folder)   # into the same folder, with this program
    assert new["ok"]
    newer = _closet_now(cfg)
    services.stop()

    monkeypatch.setattr(backup, "_stamp", lambda: "20260103-010101")
    assert backup.restore(cfg, folder, old)["items"] == 1
    assert _closet_now(cfg) == backed_up
    assert backup.restore(cfg, folder, new["snapshot"])["items"] == 2
    assert _closet_now(cfg) == newer


def test_pruning_keeps_every_image_a_remaining_snapshot_needs(client, services, cfg, tmp_path, monkeypatch):
    folder = tmp_path / "Synced"
    folder.mkdir()
    services.worker.is_ready = lambda: True
    item = upload(client).json()
    services.worker.drain()
    cut = cfg.images_dir("main") / _cutout(client, item["id"])
    root = folder / backup.SUBFOLDER
    _old_layout_backup(cfg, folder, "20251231-010101")
    versions = {}
    for day in range(1, backup.KEEP_SNAPSHOTS + 4):
        cut.write_bytes(b"cutout %d" % day)
        monkeypatch.setattr(backup, "_stamp", lambda day=day: f"202601{day:02d}-010101")
        result = backup.run_backup(cfg, services.state, folder=folder)
        assert result["ok"]
        versions[result["snapshot"]] = cut.read_bytes()
        if day == 1:   # the old-layout snapshot is still kept, and so are its images
            assert (root / "images").is_dir()
    kept = sorted(p.name for p in (root / "db").glob("closet-*.sqlite"))
    assert kept == sorted(versions)[-backup.KEEP_SNAPSHOTS:]
    assert not (root / "images").exists()   # no snapshot left uses the old layout
    stored = {p.name for p in root.rglob("*") if p.is_file() and "db" not in p.parts and p.name != "manifest.json"}
    for snap in kept:
        assert hashlib.sha256(versions[snap]).hexdigest() in stored
    for gone in sorted(versions)[:-backup.KEEP_SNAPSHOTS]:
        assert hashlib.sha256(versions[gone]).hexdigest() not in stored
    services.stop()
    monkeypatch.setattr(backup, "_stamp", lambda: "20260301-010101")
    for snap in (kept[0], kept[-1]):
        backup.restore(cfg, folder, snap)
        assert cut.read_bytes() == versions[snap]


# ---------------------------------------------------------------- a restore cut short: the journal

# Runs a restore in a program of its own and ends that program at once, as a power cut or a forced quit would,
# just after one of the moves that put the backup in place: the first, the middle one or the last (argv[4] is how
# many there are). "none" ends it just before the first move.
KILL = """
import os, sys
from pathlib import Path
from closet import backup, config
cfg = config.Config(Path(sys.argv[1]), auto_download_model=False)
real, moves = Path.replace, []
def replace(src, dst):
    dst = Path(dst)
    if dst.parent != cfg.data_dir and not dst.parent.name.startswith("replaced-"):
        return real(src, dst)
    if sys.argv[3] == "none":
        os._exit(9)
    real(src, dst)
    moves.append(dst)
    steps = int(sys.argv[4])
    if len(moves) == {"first": 1, "middle": (steps + 1) // 2, "last": steps}[sys.argv[3]]:
        os._exit(9)
Path.replace = replace
backup.restore(cfg, Path(sys.argv[2]))
"""


def _kill_restore(cfg, folder, when):
    live = [cfg.db_path("main"), cfg.images_dir("main")] + [cfg.db_path("main").with_name(f"closet.db{e}")
                                                            for e in ("-wal", "-shm")]
    steps = sum(p.exists() for p in live) + 2   # each moved aside, then the database and images put in
    env = dict(os.environ, PYTHONPATH=str(Path(backup.__file__).parents[1]))
    done = subprocess.run([sys.executable, "-c", KILL, str(cfg.data_dir), str(folder), when, str(steps)], env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 9, done.stderr


def _start_again(cfg):
    claude = FakeClaude()
    return app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude,
                                     routes=lambda: claude.routes(), corrector=claude.correct)


def _backed_up_then_changed(client, services, cfg, folder):
    """A closet backed up, then changed. Returns the closet as backed up and as it is now."""
    folder.mkdir()
    services.worker.is_ready = lambda: True
    upload(client, name="Backed up")
    services.worker.drain()
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    backed_up = _closet_now(cfg)
    upload(client, key="later", name="Not backed up")
    services.worker.drain()
    services.stop()
    return backed_up, _closet_now(cfg)


@pytest.mark.parametrize("when", ["first", "middle", "last"])
def test_a_restore_cut_short_is_finished_at_the_next_start(client, services, cfg, tmp_path, when):
    backed_up, before = _backed_up_then_changed(client, services, cfg, tmp_path / "Synced")
    settings = cfg.state_path.read_bytes()
    _kill_restore(cfg, tmp_path / "Synced", when)
    again = _start_again(cfg)
    try:
        assert _closet_now(cfg) == backed_up   # all of the backup: every new file was there, whole
        assert cfg.state_path.read_bytes() == settings
        assert not (cfg.data_dir / backup.JOURNAL).exists()
        assert not list(cfg.data_dir.glob(".restore-*"))
        aside = [p for p in cfg.data_dir.glob("replaced-*") if (p / "closet.db").exists()]
        assert len(aside) == 1   # the closet from before is kept, as after any restore
        notice = backup.restore_notice(cfg)
        assert notice["outcome"] == "finished" and "interrupted" in notice["message"]
    finally:
        again.stop()


def test_a_restore_cut_short_without_all_its_new_files_is_undone(client, services, cfg, tmp_path):
    backed_up, before = _backed_up_then_changed(client, services, cfg, tmp_path / "Synced")
    settings = cfg.state_path.read_bytes()
    _kill_restore(cfg, tmp_path / "Synced", "middle")
    staged = [p for p in cfg.data_dir.glob(".restore-*/images/**/*") if p.is_file()]
    assert staged
    staged[0].write_bytes(b"cut")   # a new file damaged: the restore cannot be finished
    again = _start_again(cfg)
    try:
        assert _closet_now(cfg) == before
        assert cfg.state_path.read_bytes() == settings
        assert not (cfg.data_dir / backup.JOURNAL).exists()
        notice = backup.restore_notice(cfg)
        assert notice["outcome"] == "undone"
        assert notice["message"] == ("A restore was interrupted; your closet was put back as it was before the "
                                     "restore.")
        anon = TestClient(app_module.create_app(again))
        assert anon.post("/api/login", json={"passphrase": PASSPHRASE}).status_code == 204
        assert anon.get("/api/restore-notice").json()["notice"]["message"] == notice["message"]
        assert anon.delete("/api/restore-notice").status_code == 204
        assert anon.get("/api/restore-notice").json() == {"notice": None}   # shown once
        assert len(anon.get("/api/items").json()["items"]) == 2
    finally:
        again.stop()


def test_a_restore_cut_short_while_its_journal_was_written_leaves_the_closet_as_it_was(client, services, cfg, tmp_path):
    backed_up, before = _backed_up_then_changed(client, services, cfg, tmp_path / "Synced")
    (cfg.data_dir / (backup.JOURNAL + ".tmp")).write_text('{"version": 1, "steps": [{"kind": "as')
    again = _start_again(cfg)
    try:
        assert _closet_now(cfg) == before
        assert not (cfg.data_dir / (backup.JOURNAL + ".tmp")).exists()
        assert backup.restore_notice(cfg) is None   # nothing had happened yet
    finally:
        again.stop()


def test_a_damaged_journal_moves_nothing(client, services, cfg, tmp_path):
    backed_up, before = _backed_up_then_changed(client, services, cfg, tmp_path / "Synced")
    _kill_restore(cfg, tmp_path / "Synced", "none")   # the journal is written, nothing moved yet
    journal = cfg.data_dir / backup.JOURNAL
    assert journal.is_file()
    journal.write_bytes(journal.read_bytes()[:40])
    again = _start_again(cfg)
    try:
        assert _closet_now(cfg) == before
        assert not journal.exists() and list(cfg.data_dir.glob("restore-journal.unreadable-*.json"))
        assert backup.restore_notice(cfg)["outcome"] == "unreadable"
    finally:
        again.stop()


def test_demo_closet_has_about_forty_items_and_leaves_the_real_one_alone(client, cfg):
    upload(client, name="Mine")
    assert client.post("/api/profile", json={"profile": "demo"}).json() == {"profile": "demo"}
    listed = client.get("/api/items").json()["items"]
    assert len(listed) == 49 and all(i["name"] != "Mine" for i in listed)
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
    autostart.set_enabled(True, exe="/opt/Nines/nines", platform="linux", home=tmp_path)
    entry = (tmp_path / ".config" / "autostart" / "nines.desktop").read_text()
    assert '"/opt/Nines/nines" --no-browser' in entry and "Name=Nines" in entry and autostart.is_enabled("linux", tmp_path)
    autostart.set_enabled(True, exe="/Applications/Nines.app/Contents/MacOS/Nines", platform="darwin", home=tmp_path)
    assert autostart.is_enabled("darwin", tmp_path)
    autostart.set_enabled(False, platform="linux", home=tmp_path)
    assert not autostart.is_enabled("linux", tmp_path)


def test_mac_start_at_login_preserves_the_program_path(tmp_path):
    import plistlib

    exe = '/Applications/Nines & café <test>/Nines.app/Contents/MacOS/Nines'
    autostart.set_enabled(True, exe=exe, platform="darwin", home=tmp_path)
    entry = plistlib.loads((tmp_path / "Library" / "LaunchAgents" / "app.nines.plist").read_bytes())
    assert entry == {"Label": "app.nines", "ProgramArguments": [exe, "--no-browser"], "RunAtLoad": True}
    autostart.set_enabled(False, platform="darwin", home=tmp_path)
    assert not autostart.is_enabled("darwin", tmp_path)


def _old_entries(home):
    """What Closet.exe 0.11.0 wrote for start at login on a Mac and on Linux, byte for byte."""
    import plistlib

    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "app.closet.plist").write_bytes(plistlib.dumps({
        "Label": "app.closet", "ProgramArguments": ["/Applications/Closet.app/Contents/MacOS/Closet", "--no-browser"],
        "RunAtLoad": True}))
    desktop = home / ".config" / "autostart"
    desktop.mkdir(parents=True)
    (desktop / "closet.desktop").write_text('[Desktop Entry]\nType=Application\nName=Closet\nExec="/opt/closet" '
                                            '--no-browser\nX-GNOME-Autostart-enabled=true\n')
    return agents / "app.closet.plist", desktop / "closet.desktop"


def test_an_old_closet_entry_for_start_at_login_is_carried_over(tmp_path):
    import plistlib

    mac_old, linux_old = _old_entries(tmp_path)
    # the old entry is not this program's: start at login reads as off until it is carried over
    assert not autostart.is_enabled("darwin", tmp_path) and not autostart.is_enabled("linux", tmp_path)
    exe = "/Applications/Nines.app/Contents/MacOS/Nines"
    assert autostart.carry_over(exe=exe, platform="darwin", home=tmp_path) is True
    assert not mac_old.exists() and autostart.is_enabled("darwin", tmp_path)
    entry = plistlib.loads((tmp_path / "Library" / "LaunchAgents" / "app.nines.plist").read_bytes())
    assert entry["ProgramArguments"] == [exe, "--no-browser"] and entry["Label"] == "app.nines"
    assert autostart.carry_over(exe="/opt/nines", platform="linux", home=tmp_path) is True
    assert not linux_old.exists() and autostart.is_enabled("linux", tmp_path)
    assert '"/opt/nines" --no-browser' in (tmp_path / ".config" / "autostart" / "nines.desktop").read_text()
    # once carried over there is nothing left to do
    assert autostart.carry_over(exe=exe, platform="darwin", home=tmp_path) is False
    assert autostart.carry_over(exe="/opt/nines", platform="linux", home=tmp_path) is False


def test_nothing_is_carried_over_without_an_old_entry_or_from_source(tmp_path):
    assert autostart.carry_over(exe="/opt/nines", platform="linux", home=tmp_path) is False
    assert not autostart.is_enabled("linux", tmp_path)   # start at login stays off when it was off
    _old_entries(tmp_path)
    assert autostart.carry_over(exe=None, platform="linux", home=tmp_path) is False   # run from source: no program
    assert (tmp_path / ".config" / "autostart" / "closet.desktop").exists()


class _FakeRegistry:
    """Stands in for `winreg` with one Run key in memory, so the Windows side runs on any computer."""
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = object(), 2, 1

    def __init__(self):
        self.values: dict[str, str] = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, key):
        assert key == autostart.RUN_KEY
        return self._Key()

    def CreateKeyEx(self, root, key, reserved, access):
        assert key == autostart.RUN_KEY
        return self._Key()

    def QueryValueEx(self, k, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, k, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, k, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_an_old_closet_run_value_on_windows_is_carried_over(monkeypatch):
    reg = _FakeRegistry()
    monkeypatch.setitem(sys.modules, "winreg", reg)
    reg.values["Closet"] = r'"C:\Users\Owner\Apps\Closet\Closet.exe" --no-browser'
    assert not autostart.is_enabled("win32")
    exe = r"C:\Users\Owner\Apps\Closet\Nines.exe"
    assert autostart.carry_over(exe=exe, platform="win32") is True
    assert reg.values == {"Nines": f'"{exe}" --no-browser'}   # the old value is gone: it would open a deleted file
    assert autostart.is_enabled("win32")
    assert autostart.carry_over(exe=exe, platform="win32") is False
    autostart.set_enabled(False, platform="win32")
    assert reg.values == {}


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
    assert result["avif"]["ok"] and "decoded 32x24" in result["avif"]["detail"]
    assert result["model_state"] == {"ok": True, "detail": "missing"}
    assert result["tagger"]["ok"]
    assert "49 items" in result["database"]["detail"]
    assert result["drawing"]["ok"] and "drew a shirt" in result["drawing"]["detail"]


def test_settings_follow_the_environment(tmp_path):
    c = config.load({"CLOSET_DATA_DIR": str(tmp_path / "d"), "CLOSET_HOST": "0.0.0.0", "CLOSET_PORT": "9000", "CLOSET_NO_AUTO_DOWNLOAD": "1"})
    assert (c.data_dir, c.host, c.port, c.auto_download_model) == (tmp_path / "d", "0.0.0.0", 9000, False)
    assert c.db_path("demo") == tmp_path / "d" / "demo" / "closet.db"
