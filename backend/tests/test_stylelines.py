"""Your style as remembered lines (closet/styleprofile.py, migration 0037): each line with where it came from, removed,
put back, changed or added on its own, and the text the stylist reads built from them. An older closet is carried
over without loss: the same text for the stylist, its history kept, and each line's source read from the history."""
from contextlib import closing

import pytest

from closet import db, styleprofile, styling

LINES = 37   # the migration that keeps the lines
STARTING = [ln for ln in styling.DEFAULT_PROFILE.splitlines() if ln.strip()]


def old_closet(cfg, versions: list[tuple[str, str, str]]):
    """A closet as it was before the lines (migration 36), with these versions of the profile: (text, source, at)."""
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(path)) as conn:
        for v, file in db.migration_files():
            if v < LINES:
                conn.executescript(f"BEGIN;\n{file.read_text(encoding='utf-8')}\nPRAGMA user_version = {v};\nCOMMIT;")
        for text, source, at in versions:
            conn.execute("INSERT INTO style_profile (text, source, created_at) VALUES (?, ?, ?)", (text, source, at))
    return path


def migrated(cfg, versions):
    path = old_closet(cfg, versions)
    with closing(db.connect(path)) as conn:
        before = styleprofile.text_for_stylist(conn)
        history = [tuple(r) for r in conn.execute("SELECT text, source, created_at FROM style_profile ORDER BY id")]
    assert LINES in db.migrate(path, cfg.local_backups_dir)["applied"]
    conn = db.connect(path)
    assert styleprofile.text_for_stylist(conn) == before   # the stylist reads exactly what it read before
    assert [tuple(r) for r in conn.execute("SELECT text, source, created_at FROM style_profile ORDER BY id")] == history
    return conn


def shape(conn):
    return [(ln["text"], ln["source"], ln["created_at"]) for ln in styleprofile.lines(conn)]


# ------------------------------------------------------------------ the migration
def test_an_older_closet_keeps_its_text_and_each_line_says_where_it_came_from(cfg):
    kept = styling.DEFAULT_KEPT
    with closing(migrated(cfg, [
        ("I dress plainly.", "owner", "2026-11-01T09:00:00Z"),
        ("I dress plainly.\n\n  - No ties.", "owner", "2026-11-03T09:00:00Z"),
        (f"{kept}\nI dress plainly.\n\n  - No ties.\n- I prefer boots.", "claude", "2026-11-05T09:00:00Z"),
        (f"{kept}\nI dress plainly.\n\n  - No ties.\n- I prefer boots.\nNavy with brown.", "owner",
         "2026-11-12T09:00:00Z"),
    ])) as conn:
        assert shape(conn) == [(kept, "start", "2026-11-05T09:00:00Z"),
                               ("I dress plainly.", "owner", "2026-11-01T09:00:00Z"),
                               ("  - No ties.", "owner", "2026-11-03T09:00:00Z"),
                               ("- I prefer boots.", "talk", "2026-11-05T09:00:00Z"),
                               ("Navy with brown.", "owner", "2026-11-12T09:00:00Z")]
        # built back from the lines, the text is the same, its empty line included
        assert styleprofile._built(styleprofile._rows(conn)) == styleprofile.text_for_stylist(conn)


def test_a_line_that_went_away_and_came_back_is_dated_from_its_return(cfg):
    with closing(migrated(cfg, [("Navy.", "owner", "2026-11-01T09:00:00Z"), ("", "owner", "2026-11-02T09:00:00Z"),
                                ("Navy.", "owner", "2026-11-04T09:00:00Z")])) as conn:
        assert shape(conn) == [("Navy.", "owner", "2026-11-04T09:00:00Z")]


@pytest.mark.parametrize("versions", [[], [("Mine.", "owner", "2026-11-01T09:00:00Z"), ("", "owner", "2026-11-02T09:00:00Z")]])
def test_an_older_closet_with_the_starting_profile_has_no_rows_and_shows_the_starting_lines(cfg, versions):
    with closing(migrated(cfg, versions)) as conn:
        assert conn.execute("SELECT count(*) FROM style_lines").fetchone()[0] == 0
        assert shape(conn) == [(ln, "start", None) for ln in STARTING]
        assert styleprofile.current(conn)["is_default"] is True


def test_a_new_closet_has_the_tables_and_refuses_an_unknown_source(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"style_lines", "style_talk", "style_questions"} <= names
        with pytest.raises(Exception, match="CHECK"):
            conn.execute("INSERT INTO style_lines (position, text, source, created_at) VALUES (0, 'x', 'someone', ?)",
                         (db.now(),))


# ------------------------------------------------------------------ changing the lines
@pytest.fixture
def conn(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as c:
        yield c


def texts(conn):
    return [ln["text"] for ln in styleprofile.lines(conn)]


def test_adding_a_line_to_the_starting_profile_keeps_the_starting_line_that_stays(conn):
    line = styleprofile.add_line(conn, "  No ties   unless it is a wedding. ", "owner")
    assert line["text"] == "- No ties unless it is a wedding." and line["source"] == "owner" and line["created_at"]
    assert [(ln["text"], ln["source"]) for ln in styleprofile.lines(conn)] == [
        (styling.DEFAULT_KEPT, "start"), ("- No ties unless it is a wedding.", "owner")]
    assert styleprofile.text_for_stylist(conn) == f"{styling.DEFAULT_KEPT}\n- No ties unless it is a wedding."


def test_each_change_to_the_lines_is_a_version_of_the_text_with_who_made_it(conn):
    styleprofile.add_line(conn, "Navy with brown.", "talk")
    styleprofile.add_line(conn, "I run warm.", "question")
    assert [tuple(r) for r in conn.execute("SELECT source FROM style_profile ORDER BY id")] == [("claude",), ("owner",)]


def test_a_changed_line_is_the_owners_from_now_and_keeps_its_place_and_its_dash(conn):
    styleprofile.add_line(conn, "Navy with brown.", "talk")
    styleprofile.add_line(conn, "Grey with black.", "owner")
    first = styleprofile.lines(conn)[1]
    profile = styleprofile.edit_line(conn, first["id"], "Navy with tan.")
    assert [(ln["text"], ln["source"]) for ln in profile["lines"]][1:] == [("- Navy with tan.", "owner"),
                                                                          ("- Grey with black.", "owner")]
    assert profile["lines"][1]["id"] == first["id"]


def test_a_line_without_a_dash_keeps_none(conn):
    styleprofile.save(conn, "I dress plainly.")
    [line] = styleprofile.lines(conn)
    assert styleprofile.edit_line(conn, line["id"], "I dress simply.")["text"] == "I dress simply."


def test_a_removed_line_is_put_back_where_it_was_with_where_it_came_from(conn):
    for t in ("One.", "Two.", "Three."):
        styleprofile.add_line(conn, t, "talk")
    two = styleprofile.lines(conn)[2]
    profile = styleprofile.remove_line(conn, two["id"])
    assert profile["removed"] == two["id"] and "- Two." not in texts(conn)
    profile = styleprofile.restore_line(conn, two["id"])
    assert texts(conn)[1:] == ["- One.", "- Two.", "- Three."]
    assert profile["lines"][2] == two
    with pytest.raises(LookupError):
        styleprofile.restore_line(conn, two["id"])


def test_removing_the_last_line_brings_back_the_starting_profile(conn):
    styleprofile.save(conn, "Mine.")
    [line] = styleprofile.lines(conn)
    assert styleprofile.remove_line(conn, line["id"])["is_default"] is True
    assert texts(conn) == STARTING and styleprofile.text_for_stylist(conn) is None


def test_a_starting_line_can_be_changed_or_removed_while_the_starting_profile_is_in_force(conn):
    first, second = styleprofile.lines(conn)
    assert (first["id"], second["id"]) == (-1, -2)
    profile = styleprofile.remove_line(conn, -2)
    assert [(ln["text"], ln["source"]) for ln in profile["lines"]] == [(STARTING[0], "start")]
    assert profile["is_default"] is False and profile["text"] == STARTING[0]


def test_changing_a_starting_line_makes_it_the_owners(conn):
    profile = styleprofile.edit_line(conn, -1, "I carry an umbrella.")
    assert [(ln["text"], ln["source"]) for ln in profile["lines"]] == [("- I carry an umbrella.", "owner"),
                                                                      (STARTING[1], "start")]


def test_taking_back_the_first_line_added_brings_back_the_starting_profile_exactly(conn):
    line = styleprofile.add_line(conn, "Navy.", "talk")
    styleprofile.take_back(conn, line["id"])
    assert styleprofile.current(conn)["is_default"] is True and texts(conn) == STARTING


@pytest.mark.parametrize("bad, words", [("", "Write something first."), ("   ", "Write something first."),
                                        (3, "must be written as text"), ("x" * 501, "at most 500 characters")])
def test_a_line_that_is_not_one_is_refused_with_a_sentence(conn, bad, words):
    with pytest.raises(ValueError, match=words):
        styleprofile.add_line(conn, bad)


def test_a_line_that_would_make_the_text_too_long_is_refused_and_nothing_changes(conn):
    styleprofile.save(conn, "x" * (styleprofile.MAX_TEXT - 5))
    with pytest.raises(ValueError, match="at most 4,000 characters"):
        styleprofile.add_line(conn, "Navy with brown.")
    assert len(styleprofile.lines(conn)) == 1


def test_an_unknown_line_is_refused(conn):
    for bad in (999, True, "1", -9):
        with pytest.raises(LookupError):
            styleprofile.edit_line(conn, bad, "x")
        with pytest.raises(LookupError):
            styleprofile.remove_line(conn, bad)


# ------------------------------------------------------------------ the whole text
def test_saving_the_whole_text_keeps_where_each_unchanged_line_came_from(conn):
    styleprofile.add_line(conn, "Navy with brown.", "talk")
    talk = styleprofile.lines(conn)[1]
    styleprofile.save(conn, f"{styling.DEFAULT_KEPT}\n\n- Navy with brown.\nNo ties.")
    got = styleprofile.lines(conn)
    assert [(ln["text"], ln["source"]) for ln in got] == [(styling.DEFAULT_KEPT, "start"),
                                                         ("- Navy with brown.", "talk"), ("No ties.", "owner")]
    assert got[1]["id"] == talk["id"] and got[1]["created_at"] == talk["created_at"]
    assert styleprofile.text_for_stylist(conn) == f"{styling.DEFAULT_KEPT}\n\n- Navy with brown.\nNo ties."
    assert styleprofile._built(styleprofile._rows(conn)) == styleprofile.text_for_stylist(conn)


def test_a_starting_line_left_in_the_whole_text_stays_a_starting_line(conn):
    styleprofile.save(conn, f"{STARTING[0]}\nMine.")
    assert [ln["source"] for ln in styleprofile.lines(conn)] == ["start", "owner"]


# ------------------------------------------------------------------ the endpoints
def test_lines_are_added_changed_removed_and_put_back_through_the_api(client):
    r = client.post("/api/style/lines", json={"text": "No ties unless it is a wedding."})
    assert r.status_code == 200, r.text
    added = r.json()["lines"][-1]
    assert added["text"] == "- No ties unless it is a wedding." and added["source"] == "owner"
    r = client.patch(f"/api/style/lines/{added['id']}", json={"text": "No ties."})
    assert r.status_code == 200 and r.json()["lines"][-1]["text"] == "- No ties."
    r = client.delete(f"/api/style/lines/{added['id']}")
    assert r.status_code == 200 and r.json()["removed"] == added["id"]
    assert all(ln["id"] != added["id"] for ln in r.json()["lines"])
    r = client.post(f"/api/style/lines/{added['id']}/restore")
    assert r.status_code == 200 and r.json()["lines"][-1]["text"] == "- No ties."
    assert client.get("/api/settings").json()["style_profile"]["lines"][-1]["text"] == "- No ties."


def test_the_line_endpoints_refuse_with_a_sentence(client):
    assert client.post("/api/style/lines", json={"text": "  "}).json()["detail"] == "Write something first."
    assert client.post("/api/style/lines", json={}).status_code == 422
    assert client.post("/api/style/lines", content=b"{", headers={"content-type": "application/json"}).status_code == 400
    r = client.patch("/api/style/lines/999", json={"text": "x"})
    assert r.status_code == 404 and r.json()["detail"] == "That line is no longer in your style."
    assert client.delete("/api/style/lines/999").status_code == 404
    assert client.post("/api/style/lines/999/restore").status_code == 404


def test_the_lines_need_login(anon):
    assert anon.post("/api/style/lines", json={"text": "x"}).status_code == 401
    assert anon.delete("/api/style/lines/1").status_code == 401


def test_changing_a_starting_line_to_what_it_says_keeps_the_starting_profile(conn):
    assert styleprofile.edit_line(conn, -1, styleprofile.plain(STARTING[0]))["is_default"] is True
    assert conn.execute("SELECT count(*) FROM style_lines").fetchone()[0] == 0
