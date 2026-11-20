"""How the owner dresses, kept for Claude choosing the outfits: the note on a piece about how they wear it
(`wear_notes`) and the style profile in Settings (closet/styleprofile.py, migration 0031)."""
from contextlib import closing

import pytest

from closet import db, outfits, styleprofile, styling
from closet.today import closet_rows

from .conftest import upload

STYLE = 31   # the migration that keeps them


def columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


# ------------------------------------------------------------------ the migration
def test_a_new_closet_has_the_note_on_a_piece_and_the_style_profile(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert "wear_notes" in columns(conn, "items")
        assert columns(conn, "style_profile") == {"id", "text", "source", "created_at"}
        with pytest.raises(Exception, match="CHECK"):
            conn.execute("INSERT INTO style_profile (text, source, created_at) VALUES ('x', 'someone', ?)", (db.now(),))


def test_an_older_closet_is_upgraded_and_keeps_its_items(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(path)) as conn:
        for v, file in db.migration_files():
            if v < STYLE:
                conn.executescript(f"BEGIN;\n{file.read_text(encoding='utf-8')}\nPRAGMA user_version = {v};\nCOMMIT;")
        conn.execute("INSERT INTO items (id, name, fit_notes, created_at, updated_at) VALUES ('old', 'Old tee', 'roomy', ?, ?)",
                     (db.now(), db.now()))
        assert "wear_notes" not in columns(conn, "items")
    assert STYLE in db.migrate(path, cfg.local_backups_dir)["applied"]
    with closing(db.connect(path)) as conn:
        row = conn.execute("SELECT name, fit_notes, wear_notes FROM items WHERE id = 'old'").fetchone()
        assert tuple(row) == ("Old tee", "roomy", None)
        assert styleprofile.current(conn)["is_default"] is True


# ------------------------------------------------------------------ how I wear it
def test_how_i_wear_it_is_set_read_back_and_cleared_like_fit_notes(client):
    item = upload(client).json()
    assert item["wear_notes"] is None
    url = f"/api/items/{item['id']}"
    r = client.patch(url, json={"wear_notes": "  only with the navy suit; runs warm  "})
    assert r.status_code == 200 and r.json()["wear_notes"] == "only with the navy suit; runs warm"
    assert client.get(url).json()["wear_notes"] == "only with the navy suit; runs warm"
    for empty in ("", "   ", None):
        client.patch(url, json={"wear_notes": "for dinners out"})
        assert client.patch(url, json={"wear_notes": empty}).json()["wear_notes"] is None
        assert client.get(url).json()["wear_notes"] is None


def test_how_i_wear_it_must_be_text(client):
    item = upload(client).json()
    r = client.patch(f"/api/items/{item['id']}", json={"wear_notes": 12})
    assert r.status_code == 422 and "text" in r.json()["detail"]


def test_how_i_wear_it_is_in_the_line_claude_reads_for_the_piece(client, cfg):
    client.post("/api/profile", json={"profile": "demo"})
    ctx = outfits.parse_request({"low_c": 8, "high_c": 14})[0]
    with closing(db.connect(cfg.db_path("demo"))) as conn:
        first = styling.listed(closet_rows(conn), ctx).ids[0]
    assert client.patch(f"/api/items/{first}", json={"wear_notes": "only with the navy suit"}).status_code == 200
    with closing(db.connect(cfg.db_path("demo"))) as conn:
        rows = closet_rows(conn)
        assert next(r for r in rows if r["id"] == first)["wear_notes"] == "only with the navy suit"
        listing = styling.listed(rows, ctx)
    assert "how I wear it: “only with the navy suit”" in listing.lines[listing.number(first) - 1]


# ------------------------------------------------------------------ the style profile
def test_the_starting_profile_is_in_force_until_the_owner_writes_one(client, services):
    body = client.get("/api/style/profile").json()
    starting = [ln for ln in styling.DEFAULT_PROFILE.splitlines() if ln.strip()]
    assert body == {"text": styling.DEFAULT_PROFILE, "is_default": True, "updated_at": None,
                    "default_text": styling.DEFAULT_PROFILE, "max_length": styleprofile.MAX_TEXT,
                    "lines": [{"id": -1 - i, "text": ln, "source": "start", "created_at": None}
                              for i, ln in enumerate(starting)]}


def test_a_saved_profile_is_read_back_with_its_line_breaks(client, cfg):
    text = "I run warm, so one layer fewer than most people.\r\n\r\nNo ties unless it is a wedding.\rNavy with brown."
    r = client.put("/api/style/profile", json={"text": f"  {text}\n\n"})
    assert r.status_code == 200
    kept = "I run warm, so one layer fewer than most people.\n\nNo ties unless it is a wedding.\nNavy with brown."
    assert r.json()["text"] == kept and r.json()["is_default"] is False and r.json()["updated_at"]
    assert client.get("/api/style/profile").json()["text"] == kept
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert styleprofile.text_for_stylist(conn) == kept
        assert conn.execute("SELECT source FROM style_profile").fetchone()[0] == "owner"


def test_an_empty_text_goes_back_to_the_starting_profile_and_keeps_the_history(client, cfg):
    client.put("/api/style/profile", json={"text": "No ties unless it is a wedding."})
    body = client.put("/api/style/profile", json={"text": "  \n "}).json()
    assert body["text"] == styling.DEFAULT_PROFILE and body["is_default"] is True and body["updated_at"]
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert styleprofile.text_for_stylist(conn) is None
        assert [r[0] for r in conn.execute("SELECT text FROM style_profile ORDER BY id")] == ["No ties unless it is a wedding.", ""]


def test_saving_the_text_already_in_force_adds_no_version(client, cfg):
    client.put("/api/style/profile", json={"text": "Navy with brown."})
    client.put("/api/style/profile", json={"text": "Navy with brown.\n"})
    client.put("/api/style/profile", json={"text": "Navy with grey."})
    client.put("/api/style/profile", json={"text": "Navy with grey."})
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert conn.execute("SELECT count(*) FROM style_profile").fetchone()[0] == 2


def test_saving_the_starting_text_or_nothing_while_it_is_in_force_adds_no_version(client, cfg):
    assert client.put("/api/style/profile", json={"text": ""}).json()["is_default"] is True
    assert client.put("/api/style/profile", json={"text": styling.DEFAULT_PROFILE}).json()["is_default"] is True
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert conn.execute("SELECT count(*) FROM style_profile").fetchone()[0] == 0


def test_a_profile_too_long_or_not_text_is_refused_with_a_sentence(client):
    longest = "x" * styleprofile.MAX_TEXT
    assert client.put("/api/style/profile", json={"text": longest}).status_code == 200
    r = client.put("/api/style/profile", json={"text": longest + "y"})
    assert r.status_code == 422 and "4,000 characters" in r.json()["detail"]
    for bad in (12, None, ["a"], {"a": 1}):
        r = client.put("/api/style/profile", json={"text": bad})
        assert r.status_code == 422 and "text" in r.json()["detail"]
    assert client.put("/api/style/profile", json=["a"]).status_code == 422
    assert client.put("/api/style/profile", json={}).status_code == 422
    assert client.put("/api/style/profile", content=b"{", headers={"content-type": "application/json"}).status_code == 400
    assert client.get("/api/style/profile").json()["text"] == longest


def test_the_demo_closet_has_its_own_profile(client):
    client.put("/api/style/profile", json={"text": "Mine."})
    client.post("/api/profile", json={"profile": "demo"})
    assert client.get("/api/style/profile").json()["is_default"] is True
    assert client.put("/api/style/profile", json={"text": "The demo's."}).json()["text"] == "The demo's."
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/style/profile").json()["text"] == "Mine."


def test_the_style_profile_needs_login(anon):
    assert anon.get("/api/style/profile").status_code == 401
    assert anon.put("/api/style/profile", json={"text": "Mine."}).status_code == 401


def test_only_the_owner_or_claude_writes_a_profile(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        with pytest.raises(ValueError):
            styleprofile.save(conn, "Mine.", source="someone")
        assert styleprofile.save(conn, "Claude's.", source="claude")["text"] == "Claude's."
        assert conn.execute("SELECT source FROM style_profile").fetchone()[0] == "claude"
