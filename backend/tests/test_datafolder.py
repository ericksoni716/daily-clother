"""The data folder moves from Closet to Nines in the user folder, once, at start (DECISIONS, "The program file: Nines").

Every test uses its own stand-in user folder (tmp_path); none touches the real ~/Closet or ~/Nines.
"""
import json
import os
from types import SimpleNamespace

import pytest

from closet import cli, config, datafolder, instance


def _never_running(folder):
    return False


def _old_closet(home, settings=None):
    old = home / "Closet"
    (old / "images").mkdir(parents=True)
    (old / "closet.db").write_bytes(b"the closet")
    (old / "images" / "a.webp").write_bytes(b"a photo")
    if settings is not None:
        (old / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return old


def test_the_closet_folder_is_renamed_to_nines(tmp_path):
    old = _old_closet(tmp_path)
    assert config.load({}, home=tmp_path).data_dir == old   # before the move the old folder is used
    outcome = datafolder.settle({}, tmp_path, _never_running)
    assert outcome.kind == "moved"
    new = tmp_path / "Nines"
    assert not old.exists() and (new / "closet.db").read_bytes() == b"the closet"
    assert (new / "images" / "a.webp").read_bytes() == b"a photo"
    assert config.load({}, home=tmp_path).data_dir == new
    # the next start has nothing to do
    assert datafolder.settle({}, tmp_path, _never_running).kind == "none"
    assert not old.exists() and config.load({}, home=tmp_path).data_dir == new


def test_a_new_computer_starts_in_nines(tmp_path):
    assert datafolder.settle({}, tmp_path, _never_running).kind == "none"
    assert config.load({}, home=tmp_path).data_dir == tmp_path / "Nines"
    assert not (tmp_path / "Closet").exists()


def test_a_chosen_data_folder_is_used_as_it_is(tmp_path):
    old = _old_closet(tmp_path)
    chosen = tmp_path / "elsewhere"
    env = {"CLOSET_DATA_DIR": str(chosen)}
    assert datafolder.settle(env, tmp_path, _never_running).kind == "none"
    assert old.exists() and not (tmp_path / "Nines").exists()
    assert config.load(env, home=tmp_path).data_dir == chosen


def test_when_both_folders_exist_nines_is_used_and_closet_left_alone(tmp_path):
    old = _old_closet(tmp_path)
    new = tmp_path / "Nines"
    new.mkdir()
    (new / "closet.db").write_bytes(b"the newer closet")
    outcome = datafolder.settle({}, tmp_path, _never_running)
    assert outcome.kind == "both" and str(old) in outcome.message and str(new) in outcome.message
    assert (old / "closet.db").read_bytes() == b"the closet" and (old / "images" / "a.webp").exists()
    assert (new / "closet.db").read_bytes() == b"the newer closet" and not (new / "images").exists()
    assert config.load({}, home=tmp_path).data_dir == new


def test_a_rename_that_fails_changes_nothing_and_is_tried_again_next_start(tmp_path, monkeypatch):
    old = _old_closet(tmp_path, settings={"backup_folder": str(tmp_path / "Closet" / "copies")})
    real = os.rename

    def refused(src, dst):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")
    monkeypatch.setattr(datafolder.os, "rename", refused)
    outcome = datafolder.settle({}, tmp_path, _never_running)
    assert outcome.kind == "failed" and "being used by another process" in outcome.message
    assert (old / "closet.db").read_bytes() == b"the closet" and not (tmp_path / "Nines").exists()
    assert json.loads((old / "settings.json").read_text())["backup_folder"] == str(old / "copies")
    assert config.load({}, home=tmp_path).data_dir == old   # this run goes on in Closet
    monkeypatch.setattr(datafolder.os, "rename", real)
    assert datafolder.settle({}, tmp_path, _never_running).kind == "moved"
    assert config.load({}, home=tmp_path).data_dir == tmp_path / "Nines"


def test_a_copy_still_running_in_closet_keeps_the_folder_where_it_is(tmp_path):
    old = _old_closet(tmp_path)
    asked = []
    outcome = datafolder.settle({}, tmp_path, lambda folder: asked.append(folder) or True)
    assert outcome.kind == "running" and asked == [old]
    assert old.exists() and not (tmp_path / "Nines").exists()
    assert config.load({}, home=tmp_path).data_dir == old


def test_the_stored_paths_into_the_old_folder_follow_it(tmp_path):
    old = tmp_path / "Closet"
    outside = tmp_path / "USB" / "backups"
    settings = {
        "update_ready": {"version": "0.12.0", "path": str(old / "updates" / "0.12.0-Nines.exe"), "sha256": "ab", "at": 1},
        "backup_folder": str(old / "my copies"),
        "last_backup": {"at": 1, "ok": True, "error": None, "folder": str(old / "my copies"), "kind": "daily"},
        "place": {"name": "Somewhere"},
        "window_key": "k",
    }
    _old_closet(tmp_path, settings=settings)
    assert datafolder.settle({}, tmp_path, _never_running).kind == "moved"
    new = tmp_path / "Nines"
    stored = json.loads((new / "settings.json").read_text(encoding="utf-8"))
    assert stored["update_ready"] == {**settings["update_ready"], "path": str(new / "updates" / "0.12.0-Nines.exe")}
    assert stored["backup_folder"] == str(new / "my copies")
    assert stored["last_backup"] == {**settings["last_backup"], "folder": str(new / "my copies")}
    assert stored["place"] == {"name": "Somewhere"} and stored["window_key"] == "k"   # the rest as it was

    # a backup folder outside the data folder, or one whose name only starts the same, is not touched
    home2 = tmp_path / "other"
    _old_closet(home2, settings={"backup_folder": str(outside), "last_backup": {"folder": str(home2 / "Closet backups")}})
    assert datafolder.settle({}, home2, _never_running).kind == "moved"
    stored = json.loads((home2 / "Nines" / "settings.json").read_text(encoding="utf-8"))
    assert stored == {"backup_folder": str(outside), "last_backup": {"folder": str(home2 / "Closet backups")}}


def test_settings_that_cannot_be_read_are_moved_as_they_are(tmp_path):
    old = _old_closet(tmp_path)
    (old / "settings.json").write_text("{not json", encoding="utf-8")
    outcome = datafolder.settle({}, tmp_path, _never_running)
    assert outcome.kind == "moved" and "settings" in outcome.message
    assert (tmp_path / "Nines" / "settings.json").read_text(encoding="utf-8") == "{not json"


def test_a_copy_running_is_found_from_its_lock_file(tmp_path):
    folder = tmp_path / "Closet"
    folder.mkdir()
    assert cli._running_in(folder) is False   # no lock file
    instance.write_lock(config.Config(folder), 1)   # a lock left behind: nothing answers on that port
    assert cli._running_in(folder) is False


@pytest.fixture
def started(monkeypatch):
    seen = SimpleNamespace(settled=[], served=[])
    monkeypatch.setattr(datafolder, "settle",
                        lambda env, home, running: seen.settled.append((env, home, running))
                        or datafolder.Outcome("none"))
    monkeypatch.setattr(cli, "serve", lambda args, cfg: seen.served.append(len(seen.settled)) or 0)
    monkeypatch.setattr(cli, "cmd_reset", lambda args, cfg: seen.served.append(len(seen.settled)) or 0)
    monkeypatch.setenv("CLOSET_DATA_DIR", "/nowhere/real")
    return seen


def test_the_folder_is_settled_before_anything_opens_it(started):
    assert cli.main(["--no-browser"]) == 0
    assert started.served == [1] and started.settled[0][2] is cli._running_in
    assert cli.main(["reset-passphrase"]) == 0 and started.served == [1, 2]


def test_an_updates_hand_over_never_moves_the_folder(started):
    assert cli.main(["--no-browser", "--replace"]) == 0
    assert started.settled == [] and started.served == [0]
