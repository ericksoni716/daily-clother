import errno
import json

import pytest

from closet.state import State


@pytest.mark.parametrize("operation", ["update", "mutate", "mutate_if_changed"])
@pytest.mark.parametrize("failure", ["write", "replace"])
def test_failed_save_keeps_settings_in_memory_and_on_disk(tmp_path, monkeypatch, operation, failure):
    state = State(tmp_path / "settings.json")
    state.update(life={"situations": {"work": 1}})
    before = json.loads(state.path.read_text())

    def disk_full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    with monkeypatch.context() as m:
        if failure == "write":
            m.setattr(type(state.path), "write_text", disk_full)
        else:
            m.setattr("closet.state.os.replace", disk_full)
        with pytest.raises(OSError, match="No space"):
            if operation == "update":
                state.update(life={"situations": {"work": 5}})
            else:
                state.mutate(lambda data: data["life"]["situations"].update(work=5),
                             save_if_changed=operation == "mutate_if_changed")

    assert state.get("life") == before["life"]
    assert json.loads(state.path.read_text()) == before
    state.update(profile="demo")
    assert State(state.path).get("life") == before["life"]


def test_failed_mutation_does_not_leave_partial_settings(tmp_path):
    state = State(tmp_path / "settings.json")
    state.update(life={"situations": {"work": 1}})

    def broken(data):
        data["life"]["situations"]["work"] = 5
        raise ValueError("invalid change")

    with pytest.raises(ValueError, match="invalid change"):
        state.mutate(broken)
    assert state.get("life") == {"situations": {"work": 1}}
