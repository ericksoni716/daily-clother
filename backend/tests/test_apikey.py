"""The API key box in Settings: the key is checked with Anthropic, kept in the computer's keychain, and never
shown, logged or handed to Claude Code."""
import json
import logging
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest
from PIL import Image

from closet import apikey
from closet.tagger import claude_cli
from closet.tagger import routes as tagger_routes
from closet.tagger.tagging import PlanSignIn, RouteUnavailable

KEY = "sk-ant-api03-" + "k" * 80
OTHER = "sk-ant-api03-" + "e" * 80


@pytest.fixture
def accepted(monkeypatch):
    checked = []
    monkeypatch.setattr(apikey, "check", lambda key: checked.append(key) or None)
    return checked


def test_only_something_shaped_like_a_key_is_taken():
    assert apikey.clean(f"  {KEY}\n") == KEY
    for wrong in ("", "hello", "sk-ant-", "sk-proj-" + "a" * 40, KEY + " extra", KEY + '"; rm -rf ~', KEY[:-60] + "\n" + KEY[-60:]):
        with pytest.raises(ValueError):
            apikey.clean(wrong)


@pytest.mark.parametrize("body", [
    {"key": [KEY]},
    {"key": {"nested": KEY}},
    {"wrong_field": KEY},
    {"key": KEY, KEY: OTHER},
    [KEY],
])
def test_invalid_key_requests_do_not_echo_inputs(client, keychain, body, caplog):
    response = client.put("/api/settings/api-key", json=body)
    assert response.status_code == 422
    assert KEY not in response.text + caplog.text
    assert OTHER not in response.text + caplog.text
    assert isinstance(response.json()["detail"], str)
    assert keychain.key is None


def test_malformed_key_json_does_not_echo_inputs(client, keychain, caplog):
    response = client.put("/api/settings/api-key", content=json.dumps({"key": KEY})[:-1],
                          headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert KEY not in response.text + caplog.text
    assert keychain.key is None


def test_a_key_is_checked_kept_in_the_keychain_and_never_sent_back(client, keychain, accepted, caplog, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    before = client.get("/api/settings").json()["api_key"]
    assert before == {"set": False, "source": None, "can_save": True, "where": "this Mac's keychain"}
    with caplog.at_level(logging.DEBUG):
        r = client.put("/api/settings/api-key", json={"key": f" {KEY} "})
    assert r.status_code == 200, r.text
    assert r.json()["api_key"] == {"set": True, "source": "keychain", "can_save": True, "where": "this Mac's keychain",
                                   "checked": True}
    assert keychain.key == KEY and accepted == [KEY]
    for text in (r.text, client.get("/api/settings").text, client.get("/api/tagging").text, caplog.text):
        assert KEY not in text and KEY[-20:] not in text
    assert {x["id"]: x["available"] for x in client.get("/api/tagging").json()["routes"]}["api"] is True


def test_a_key_anthropic_refuses_is_not_saved(client, keychain, monkeypatch):
    monkeypatch.setattr(apikey, "check", lambda key: "refused")
    r = client.put("/api/settings/api-key", json={"key": KEY})
    assert r.status_code == 422 and "did not accept" in r.json()["detail"]
    assert keychain.key is None
    r = client.put("/api/settings/api-key", json={"key": "not a key"})
    assert r.status_code == 422 and "sk-ant-" in r.json()["detail"]


def test_when_anthropic_cannot_be_reached_the_key_is_kept_and_it_says_so(client, keychain, monkeypatch):
    monkeypatch.setattr(apikey, "check", lambda key: "unknown")
    r = client.put("/api/settings/api-key", json={"key": KEY})
    assert r.status_code == 200 and r.json()["api_key"]["checked"] is False and keychain.key == KEY


def test_a_computer_without_a_keychain_says_so(client, accepted, monkeypatch):
    apikey.use_store(apikey.NoKeychain())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/api/settings").json()["api_key"] == {"set": False, "source": None, "can_save": False, "where": None}
    r = client.put("/api/settings/api-key", json={"key": KEY})
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_a_new_key_clears_the_note_about_a_refused_one_but_not_about_credit(client, services, accepted):
    services.state.update(tagging_api_off={"at": "2026-11-01T00:00:00Z", "reason": "key"})
    assert client.put("/api/settings/api-key", json={"key": KEY}).json()["tagging_api_off"] is None
    services.state.update(tagging_api_off={"at": "2026-11-01T00:00:00Z", "reason": "credit"})
    assert client.put("/api/settings/api-key", json={"key": OTHER}).json()["tagging_api_off"]["reason"] == "credit"


def test_removing_the_key_leaves_one_from_the_environment(client, keychain, accepted, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", OTHER)
    client.put("/api/settings/api-key", json={"key": KEY})
    assert apikey.get() == KEY   # the saved key wins
    r = client.delete("/api/settings/api-key")
    assert r.status_code == 200 and keychain.key is None
    assert r.json()["api_key"]["source"] == "environment" and apikey.get() == OTHER
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.delete("/api/settings/api-key").json()["api_key"]["set"] is False   # nothing to remove: fine


def test_a_keychain_that_cannot_be_read_falls_back_to_the_environment(monkeypatch):
    class Broken(apikey.NoKeychain):
        def get(self):
            raise apikey.KeychainError("locked")
    apikey.use_store(Broken())
    monkeypatch.setenv("ANTHROPIC_API_KEY", OTHER)
    assert apikey.get() == OTHER and apikey.info()["source"] == "environment"


def test_the_api_route_uses_the_saved_key(keychain, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    made = []
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: made.append(kw) or SimpleNamespace())
    with pytest.raises(RouteUnavailable):
        tagger_routes.Router("api")._api_client()   # no key yet
    keychain.key = KEY
    tagger_routes.Router("api")._api_client()
    assert made[-1]["api_key"] == KEY
    assert tagger_routes.api_status() == (True, "")


def test_claude_code_never_sees_the_saved_key(keychain, monkeypatch):
    keychain.key = KEY
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seen = []

    def run(cmd, **kw):
        seen.append(kw["env"])
        return SimpleNamespace(returncode=1, stdout=json.dumps({"is_error": True, "result": "Not logged in"}), stderr="")
    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    with pytest.raises(PlanSignIn):
        claude_cli.tag_item_cli("claude-haiku-5-5", [Image.new("RGBA", (10, 10))], exe="claude")
    assert seen and all(KEY not in v for v in seen[0].values())


def _api_error(cls, status, message):
    resp = httpx.Response(status, request=httpx.Request("GET", "https://api.anthropic.com/v1/models"))
    return cls(message, response=resp, body=None)


@pytest.mark.parametrize("raised,verdict", [
    (None, None),
    (_api_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "refused"),
    (_api_error(anthropic.BadRequestError, 400, "Not a valid API key for this workspace"), "refused"),
    (anthropic.APIConnectionError(request=httpx.Request("GET", "https://api.anthropic.com/v1/models")), "unknown"),
])
def test_checking_a_key_lists_one_model_and_costs_nothing(monkeypatch, raised, verdict):
    asked = []

    class Models:
        def list(self, **kw):
            asked.append(kw)
            if raised:
                raise raised
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(models=Models(), kw=kw))
    assert apikey.check(KEY) == verdict and asked == [{"limit": 1}]


# ---- the Mac keychain, through Apple's `security` tool (faked: these tests run on any computer)

def test_on_a_mac_the_key_goes_to_the_keychain_on_standard_input_only(monkeypatch):
    calls, saved = [], {}

    def run(args, input=None, **kw):
        calls.append((args, input))
        if args[1] == "-i":
            saved["key"] = input.split('-w "')[1].split('"')[0]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[1] == "find-generic-password":
            return SimpleNamespace(returncode=0, stdout=saved["key"] + "\n", stderr="") if saved else \
                SimpleNamespace(returncode=44, stdout="", stderr="not found")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(apikey.subprocess, "run", run)
    mac = apikey.MacKeychain()
    assert mac.get() is None
    mac.set(KEY)
    assert mac.get() == KEY
    assert all(KEY not in " ".join(args) for args, _ in calls)   # never on a command line
    assert any(stdin and "add-generic-password -U -s Nines -a anthropic-api-key" in stdin for _, stdin in calls)
    with pytest.raises(ValueError):
        mac.set('sk-ant-x" ; delete-keychain')
    mac.delete()
    assert calls[-1][0][1:] == ["delete-generic-password", "-s", "Nines", "-a", "anthropic-api-key"]


def test_on_a_mac_a_save_that_did_not_take_is_reported(monkeypatch):
    monkeypatch.setattr(apikey.subprocess, "run",
                        lambda args, **kw: SimpleNamespace(returncode=44 if args[1] != "-i" else 0, stdout="", stderr=""))
    with pytest.raises(apikey.KeychainError):
        apikey.MacKeychain().set(KEY)


# ---- the entry's name: Nines from now on; a key kept under Closet (0.13.0 and before) is carried over at start

class Entry:
    """One keychain entry, standing in for the computer's; `fail` names the calls that fail as a locked keychain's do."""
    where = "this Mac's keychain"

    def __init__(self, key=None, fail=(), reads_back=None):
        self.key, self.fail, self.reads_back = key, set(fail), reads_back

    def _check(self, call):
        if call in self.fail:
            raise apikey.KeychainError("locked")

    def get(self):
        self._check("get")
        return self.key

    def set(self, key):
        self._check("set")
        self.key = self.reads_back or key

    def delete(self):
        self._check("delete")
        self.key = None


def test_a_key_kept_under_closet_is_saved_under_nines_and_the_old_entry_removed(monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    new, old = Entry(), Entry(KEY)
    apikey.use_store(new, old=old)
    assert apikey.get() == KEY and apikey.info()["source"] == "keychain"   # read from the old entry until it has moved
    with caplog.at_level(logging.DEBUG):
        assert apikey.carry_over() is True
        assert apikey.carry_over() is False   # once
    assert new.key == KEY and old.key is None and apikey.get() == KEY
    assert KEY not in caplog.text and KEY[-20:] not in caplog.text


@pytest.mark.parametrize("failure", ["set", "read back wrong", "new unreadable", "old unreadable"])
def test_when_the_key_cannot_be_carried_over_the_old_entry_is_kept_and_used(monkeypatch, failure):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    new = {"set": Entry(fail={"set"}), "read back wrong": Entry(reads_back=OTHER),
           "new unreadable": Entry(fail={"get", "set"}), "old unreadable": Entry()}[failure]
    old = Entry(KEY, fail={"get", "delete"} if failure == "old unreadable" else ())
    apikey.use_store(new, old=old)
    assert apikey.carry_over() is False   # never raises
    assert old.key == KEY and new.key is None   # nothing lost, nothing half written
    if failure in ("set", "read back wrong"):
        assert apikey.get() == KEY   # the old entry is still read
    old.fail.clear()
    new.fail.clear()
    new.reads_back = None
    assert apikey.carry_over() is True and new.key == KEY and old.key is None   # the next start moves it


def test_when_both_entries_hold_a_key_the_one_under_nines_wins_and_the_old_one_goes():
    new, old = Entry(OTHER), Entry(KEY)
    apikey.use_store(new, old=old)
    assert apikey.get() == OTHER
    assert apikey.carry_over() is False
    assert new.key == OTHER and old.key is None


def test_removing_the_key_removes_it_from_the_old_entry_too(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    new, old = Entry(), Entry(KEY)
    apikey.use_store(new, old=old)
    apikey.remove(None)
    assert old.key is None and apikey.get() is None   # an entry left under Closet does not bring it back


def test_a_copy_that_cannot_reach_the_keychain_still_uses_the_sealed_key(monkeypatch, tmp_path):
    """Windows' background copy started before sign-in: neither entry can be read, so nothing is carried over, and the
    sealed file in the data folder (whose own names did not change) is what it uses."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class Reversed:
        def seal(self, data):
            return data[::-1]

        def unseal(self, data):
            return data[::-1]
    apikey.use_sealer(Reversed())
    try:
        apikey.write_sealed(tmp_path, KEY)
        apikey.keep_sealed(tmp_path)
        locked = {"get", "set", "delete"}
        new, old = Entry(fail=locked), Entry(OTHER, fail=locked)
        apikey.use_store(new, old=old)
        assert apikey.carry_over() is False and old.key == OTHER
        assert apikey.get() == KEY
        assert apikey.SEALED_FILE == "api-key.sealed" and apikey._ENTROPY == b"closet/api-key/v1"   # unsealable as before
    finally:
        apikey.keep_sealed(None)
        apikey.use_sealer(None)


def test_the_entries_are_named_nines_and_closet_on_windows():
    assert apikey.WindowsCredentials().TARGET == "Nines/anthropic-api-key"
    assert apikey.WindowsCredentials(apikey.OLD_SERVICE).TARGET == "Closet/anthropic-api-key"


def test_on_a_mac_a_key_under_closet_is_moved_to_nines(monkeypatch):
    items = {"Closet": KEY}

    def run(args, input=None, **kw):
        if args[1] == "-i":
            service = input.split(" -s ")[1].split(" ")[0]
            items[service] = input.split('-w "')[1].split('"')[0]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        service = args[args.index("-s") + 1]
        if service not in items:
            return SimpleNamespace(returncode=44, stdout="", stderr="not found")
        if args[1] == "delete-generic-password":
            del items[service]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout=items[service] + "\n", stderr="")
    monkeypatch.setattr(apikey.subprocess, "run", run)
    apikey.use_store(apikey.MacKeychain(), old=apikey.MacKeychain(apikey.OLD_SERVICE))
    assert apikey.carry_over() is True
    assert items == {"Nines": KEY}


def test_a_start_moves_the_key_and_says_so_without_the_key(monkeypatch, caplog):
    from closet import cli
    new, old = Entry(), Entry(KEY)
    apikey.use_store(new, old=old)
    with caplog.at_level(logging.INFO):
        cli._carry_over_api_key()
    assert new.key == KEY and "moved from the entry named Closet" in caplog.text and KEY not in caplog.text
