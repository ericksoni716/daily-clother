"""Show drawings instead of photos (Settings, 22 November): one choice for the whole program, kept with the other
settings on the computer, so every device shows the same kind of picture. Off until the owner turns it on."""
from closet.state import State


def test_it_is_off_until_turned_on_and_kept(client, cfg):
    assert client.get("/api/settings").json()["show_drawings"] is False
    r = client.put("/api/settings", json={"show_drawings": True})
    assert r.status_code == 200 and r.json()["show_drawings"] is True
    assert client.get("/api/settings").json()["show_drawings"] is True
    assert State(cfg.state_path).get("show_drawings") is True   # kept on the computer, not by the page
    assert client.put("/api/settings", json={"show_drawings": False}).json()["show_drawings"] is False


def test_only_yes_or_no_is_taken(client):
    assert client.put("/api/settings", json={"show_drawings": "sometimes"}).status_code == 422
    r = client.put("/api/settings", json={"show_drawings": None})
    assert r.status_code == 200 and r.json()["show_drawings"] is False   # nothing said: nothing changes


def test_every_screen_reads_it_on_its_own_without_the_whole_of_settings(client):
    # the open closet reads only this when it opens; Settings' own read stays Settings' own
    assert client.get("/api/settings/pictures").json() == {"show_drawings": False}
    client.put("/api/settings", json={"show_drawings": True})
    assert client.get("/api/settings/pictures").json() == {"show_drawings": True}
