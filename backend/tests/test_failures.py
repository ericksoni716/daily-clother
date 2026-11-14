"""A failed item says why: the plain sentence, the stored reason cleaned of keys and outside paths, the log line,
and "Try again" queueing one job.

Nothing here reaches Claude or the model: the cutter and `FakeClaude` (conftest) stand in for them.
"""
import logging

from closet import db, failures, jobs, tagjobs
from closet.tagger.tagging import TaggingError

from .conftest import fake_cutter, upload

FAKE_KEY = "sk-ant-api03-" + "Ab1" * 12   # shaped like a key; not one
LOGGED = "closet.failures"


def cut(services):
    services.worker.is_ready = lambda: True
    return services.worker.drain()


def jobs_of(cfg, item_id, kind):
    conn = db.connect(cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE kind = ? AND item_id = ? ORDER BY id", (kind, item_id))]
    finally:
        conn.close()


def warnings(caplog):
    return [r for r in caplog.records if r.name == LOGGED and r.levelno == logging.WARNING]


def test_an_item_that_has_not_failed_has_no_failure(client, services):
    item = upload(client).json()
    assert item["failure"] is None
    cut(services)
    assert client.get(f"/api/items/{item['id']}").json()["failure"] is None


def test_an_unknown_cutout_failure_shows_its_reason_and_is_logged_once(client, services, caplog):
    def broken(img):
        raise RuntimeError("the model ran out of memory on layer 7")

    services.worker.cutter = broken
    item = upload(client).json()
    with caplog.at_level(logging.INFO):
        assert cut(services) == jobs.MAX_ATTEMPTS
    failure = client.get(f"/api/items/{item['id']}").json()["failure"]
    assert failure["stage"] == "cutout"
    assert failure["reason"].startswith("The background could not be removed")
    assert failure["details"] == "the model ran out of memory on layer 7"
    logged = warnings(caplog)
    assert len(logged) == 1   # once, when it is marked failed, not on every attempt
    assert item["id"] in logged[0].getMessage() and "out of memory on layer 7" in logged[0].getMessage()


def test_an_unknown_description_failure_shows_its_reason_and_is_logged_once(client, services, claude, caplog):
    claude.mode = "fails"
    item = upload(client).json()
    cut(services)
    with caplog.at_level(logging.INFO):
        assert services.tag_worker.drain() == tagjobs.MAX_ATTEMPTS
    failure = client.get(f"/api/items/{item['id']}").json()["failure"]
    assert failure == {"stage": "description", "reason": tagjobs.FAILED, "details": "the answer was outside the schema"}
    logged = warnings(caplog)
    assert len(logged) == 1 and item["id"] in logged[0].getMessage()
    assert "description" in logged[0].getMessage()


def test_a_key_shaped_string_and_outside_paths_are_stripped_from_the_page_and_the_log(client, services, cfg, caplog):
    inside = cfg.data_dir / "images" / "abc" / "photo.webp"

    def broken(img):
        raise RuntimeError(f"Authorization: Bearer {FAKE_KEY} refused, key {FAKE_KEY}; read /home/someone/.claude/creds.json "
                           f"and C:\\Users\\someone\\secret.txt; wrote {inside}; owner a.person@example.com")

    services.worker.cutter = broken
    item = upload(client).json()
    with caplog.at_level(logging.INFO):
        cut(services)
    details = client.get(f"/api/items/{item['id']}").json()["failure"]["details"]
    message = warnings(caplog)[0].getMessage()
    for text in (details, message):
        assert "sk-" not in text and FAKE_KEY not in text and "Ab1Ab1" not in text
        assert "someone" not in text and ".claude" not in text and "example.com" not in text
        assert str(cfg.data_dir) not in text
        assert "[Closet folder]/images/abc/photo.webp" in text.replace("\\", "/")   # inside Closet's folder: kept
        assert "refused" in text   # the rest of the reason is still there
    assert FAKE_KEY not in caplog.text


def test_the_reason_is_kept_in_the_database_already_cleaned(client, services, claude, cfg):
    """The closet's database is copied into backups: the reason a job keeps holds no key, token, e-mail address or
    path outside Closet's folder either, for a cutout and for a description."""
    def raise_it(*_):
        raise TaggingError(f"API Error: 401 x-api-key={FAKE_KEY} for a.person@example.com, read /home/someone/x.json")

    services.worker.cutter = raise_it
    first = upload(client, key="k1").json()
    cut(services)
    services.worker.cutter = fake_cutter
    second = upload(client, key="k2").json()
    cut(services)
    claude.mode, services.tag_worker.tagger = "answers", raise_it
    services.tag_worker.drain()
    stored = [j["error"] for j in jobs_of(cfg, first["id"], "cutout") + jobs_of(cfg, second["id"], "tag")]
    assert len(stored) == 2
    for text in stored:
        assert FAKE_KEY not in text and "example.com" not in text and "someone" not in text
        assert text.startswith("API Error: 401")   # the rest of the reason is still there


def test_the_cleaner_on_its_own(tmp_path):
    folder = tmp_path / "Closet"
    assert failures.clean(None) is None and failures.clean("") is None
    assert failures.clean(f"key {FAKE_KEY} was refused") == "key [hidden] was refused"
    assert failures.clean("api_key=abc123 token: 'xyz'") == "api_key=[hidden] token: '[hidden]'"
    assert failures.clean("a long token " + "aB3" * 12) == "a long token [hidden]"
    assert failures.clean("see https://api.anthropic.com/v1/messages (400)") == "see https://api.anthropic.com/v1/messages (400)"
    assert failures.clean(f"open {folder}/closet.db and ~/x/y", folder) == "open [Closet folder]/closet.db and [a path outside Closet]"
    assert len(failures.clean("x" * 2000)) == failures.MAX_DETAILS


def test_a_description_left_crashing_is_reported_with_its_last_reason(client, services, claude, cfg, caplog):
    item = upload(client).json()
    cut(services)
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE jobs SET state = 'running', attempts = 3, error = 'the worker crashed' WHERE kind = 'tag'")
    conn.execute("UPDATE items SET tag_state = 'working'")
    conn.close()
    with caplog.at_level(logging.INFO):
        services.tag_worker.drain()
    failure = client.get(f"/api/items/{item['id']}").json()["failure"]
    assert failure["stage"] == "description" and failure["details"] == "the worker crashed"
    assert len(warnings(caplog)) == 1


def test_try_again_on_a_failed_cutout_queues_one_job(client, services, cfg):
    services.worker.cutter = lambda img: (_ for _ in ()).throw(RuntimeError("no"))
    item = upload(client).json()
    cut(services)
    assert len(jobs_of(cfg, item["id"], "cutout")) == 1
    for _ in range(3):
        r = client.post(f"/api/items/{item['id']}/retry-cutout")
        assert r.status_code == 202 and r.json()["failure"] is None
    assert [j["state"] for j in jobs_of(cfg, item["id"], "cutout")] == ["failed", "queued"]
    # a queued job the item's state does not show yet is not doubled either
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE items SET cutout_state = 'failed' WHERE id = ?", (item["id"],))
    conn.close()
    client.post(f"/api/items/{item['id']}/retry-cutout")
    assert [j["state"] for j in jobs_of(cfg, item["id"], "cutout")] == ["failed", "queued"]
    services.worker.cutter = fake_cutter
    assert cut(services) == 1
    assert client.get(f"/api/items/{item['id']}").json()["cutout_state"] == "ready"


def test_try_again_on_a_failed_description_queues_one_job(client, services, claude, cfg):
    claude.mode = "fails"
    item = upload(client).json()
    cut(services)
    services.tag_worker.drain()
    assert client.get(f"/api/items/{item['id']}").json()["failure"]["stage"] == "description"
    for _ in range(3):
        r = client.post(f"/api/items/{item['id']}/retag")
        assert r.status_code == 202 and r.json()["failure"] is None
    assert [j["state"] for j in jobs_of(cfg, item["id"], "tag")] == ["failed", "queued"]
    claude.mode = "answers"
    assert services.tag_worker.drain() == 1
    assert client.get(f"/api/items/{item['id']}").json()["failure"] is None


def test_a_failure_without_a_stored_reason_still_says_what_went_wrong(client, services, cfg):
    item = upload(client).json()
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE jobs SET state = 'failed', error = NULL")
    conn.execute("UPDATE items SET cutout_state = 'failed', cutout_error = NULL")
    conn.close()
    failure = client.get(f"/api/items/{item['id']}").json()["failure"]
    assert failure == {"stage": "cutout", "reason": "The background could not be removed from this photo.", "details": None}


def test_tagging_error_text_from_the_tagger_is_cleaned(cfg):
    # the shape of a real tagger failure that quotes Claude Code's output
    e = TaggingError(f"claude-haiku through Claude Code gave no usable answer (exit 1): API Error: 401 x-api-key={FAKE_KEY}")
    assert FAKE_KEY not in failures.clean(str(e), cfg.data_dir)
