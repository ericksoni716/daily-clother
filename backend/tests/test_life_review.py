"""Regressions for the owner's numbered review, with synthetic closets only."""
from copy import deepcopy

import pytest

from closet import gaps, life, wishlist

from .test_gaps import full_closet, item, without
from .test_life import answers, climate


@pytest.mark.parametrize("name", ["Grey sweatpants", "Black joggers", "Tracksuit bottoms",
                                  "Lounge trousers", "Fleeces", "Jersey trousers"])
def test_soft_cloth_compounds_and_plurals_fill_home_bottoms(name):
    rows = full_closet() + [
        item("soft1", "trousers", formality="casual", name=name),
        item("soft2", "trousers", formality="casual", name=name)]
    result = life.analyse(rows, [], answers(lounging=4), climate())
    assert not any(g["id"] == "trousers-casual-lounge" for g in result["gaps"])


@pytest.mark.parametrize("frequency,words", [(0.25, "now and then"), (1, "about once a week"), (4, "most days")])
def test_reasons_keep_the_owners_piece_and_use_human_frequency(frequency, words):
    rows = without("shoes_black", "boots_brown", "boots_black", "sneakers_white", "sneakers_grey")
    result = life.analyse(rows, [], answers(work=frequency), climate())
    shoes = next(g for g in result["gaps"] if g["look_for"]["category"] == "dress_shoes")
    text = " ".join(shoes["why"])
    assert "your brown derbies" in text
    assert f"For work, {words}" in text
    assert "0.25" not in text and "1 days" not in text and "one shoes" not in text


def test_reason_adds_measured_weather_without_throwing_away_rain_evidence():
    rows = without("trench")
    result = life.analyse(rows, [], answers(work=4), climate("cold", 0.14))
    coat = next(g for g in result["gaps"] if g["id"] == "outer-rain")
    assert any("cold wet days here, about 51 a year" in text for text in coat["why"])
    assert any("Nothing you own keeps the rain off" in text for text in coat["why"])


def test_exercise_does_not_change_the_name_of_an_existing_rain_suggestion():
    rows = without("trench") + [item("joggers", "trousers", formality="athletic", material="fleece")]
    original = gaps.find_gaps(rows, options={"max_gaps": 100})
    result = life.analyse(rows, [], answers(work=4, exercise=4), climate("cold", 1))
    expected = next(g["name"] for g in original["gaps"] if g["id"] == "outer-rain")
    assert next(g["name"] for g in result["gaps"] if g["id"] == "outer-rain") == expected


def test_no_zero_score_suggestions_for_rare_days():
    result = life.analyse(without("trench"), [], answers(work=0.001), climate())
    assert all(g["score"] > 0 for g in result["gaps"])


def suggestion(gid, situations=None):
    return {"id": gid, "name": gid, "score": 40,
            "situations": situations or [{"id": "work", "share": 0.1}],
            "why": ["For work, most days: your own piece needs a partner."],
            "evidence": {"days": [{"situation": "work"}], "items": []}}


def analysis(*suggestions):
    return {"gaps": list(suggestions), "context": {
        "life": answers(work=4), "taste": {"used": False}, "suppressed": []}}


def hidden(gid):
    return [{"gap_id": gid, "name": gid, "reason": "never_wear", "hidden_at": "2026-11-01T10:00:00Z"}]


def consent(gid):
    return {gid: {"hidden_at": hidden(gid)[0]["hidden_at"], "situations": ["work"]}}


@pytest.mark.parametrize("gid", ["outer", "outer-warm", "outer-rain", "outer-rainwarm"])
def test_outerwear_never_suppresses_another_weather_requirement(gid):
    others = [suggestion(i) for i in ("outer", "outer-warm", "outer-rain", "outer-rainwarm") if i != gid]
    answer = analysis(suggestion(gid), *others)
    result = wishlist._hold_back(answer, hidden(gid), set(), consent(gid))
    assert {g["id"]: g for g in result["gaps"]} == {g["id"]: g for g in answer["gaps"]}


def test_pre_questionnaire_hide_cannot_silently_hide_more_after_answering():
    answer = analysis(suggestion("trousers-business"), suggestion("trousers-business-light"))
    result = wishlist._hold_back(answer, hidden("trousers-business"), set())
    assert result["gaps"] == answer["gaps"]
    assert result["context"]["suppressed"][0]["needs_confirmation"] is True


def test_held_back_suggestion_stays_visible_with_its_cause():
    answer = analysis(suggestion("trousers-business"), suggestion("trousers-business-light"))
    original = deepcopy(answer)
    result = wishlist._hold_back(answer, hidden("trousers-business"), set(), consent("trousers-business"))
    held = next(g for g in result["gaps"] if g["id"] == "trousers-business-light")
    assert held["held_back_by"][0]["gap_id"] == "trousers-business"
    assert held["state"] == "held_back"
    assert answer == original


def test_partly_held_back_gap_is_kept_even_beyond_open_limit(cfg, services):
    from closet import db

    conn = db.connect(cfg.db_path("main"))
    try:
        original = suggestion("trousers-business")
        decision = wishlist.hide(conn, original, "never_wear")
        approved = {original["id"]: {"hidden_at": decision["hidden_at"], "situations": ["work"]}}
        similar = suggestion("trousers-business-light", [
            {"id": "work", "share": 0.1}, {"id": "vacation", "share": 0.1}])
        result = wishlist.mark(conn, analysis(original, similar), 0, approved)
        held = next(g for g in result["gaps"] if g["id"] == similar["id"])
        assert held["held_back_by"][0]["gap_id"] == original["id"]
    finally:
        conn.close()


def test_legacy_hide_needs_explicit_confirmation_and_undo_restores(client, services, cfg):
    from closet import db

    from .test_gaps import demo_items
    client.post("/api/profile", json={"profile": "demo"})
    # Create an old decision directly, as in a restored/pre-questionnaire database.
    conn = db.connect(cfg.db_path("demo"))
    try:
        original = {"id": "trousers-business", "name": "Smart trousers"}
        wishlist.hide(conn, original, "never_wear")
    finally:
        conn.close()
    before = client.get("/api/gaps").json()
    decision = next(p for p in before["context"]["suppressed"] if p["gap_id"] == original["id"])
    assert decision["needs_confirmation"]
    assert services.state.get("life_gap_hides").get("demo", {}) == {}
    assert client.post("/api/gaps/trousers-business/hide", json={"reason": "never_wear"}).status_code == 200
    after = client.get("/api/gaps").json()
    decision = next(p for p in after["context"]["suppressed"] if p["gap_id"] == original["id"])
    assert not decision["needs_confirmation"]
    assert client.delete("/api/gaps/trousers-business/hide").status_code == 204
    assert client.get("/api/gaps").json()["context"]["suppressed"] == []
    assert services.state.get("life_gap_hides").get("demo", {}) == {}
    # Consent never touches the unanswered analysis or leaks into the other profile.
    assert life.analyse(demo_items(), [], None, climate())["taste"]["used"] is False
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/gaps").json()["context"]["suppressed"] == []


def test_confirmed_legacy_hide_cannot_lend_consent_to_a_restored_older_decision(client, services, cfg):
    from closet import db

    client.post("/api/profile", json={"profile": "demo"})
    conn = db.connect(cfg.db_path("demo"))
    try:
        conn.execute("INSERT INTO hidden_gaps (gap_id, name, reason, hidden_at) VALUES (?, ?, ?, ?)",
                     ("trousers-business", "Smart trousers", "never_wear", "2025-01-01T10:00:00Z"))
        original = dict(conn.execute("SELECT * FROM hidden_gaps WHERE gap_id = 'trousers-business'").fetchone())
        response = client.post("/api/gaps/trousers-business/hide", json={"reason": "never_wear"})
        assert response.status_code == 200
        confirmed = response.json()
        assert confirmed["hidden_at"] != original["hidden_at"]
        assert services.state.get("life_gap_hides")["demo"]["trousers-business"]["hidden_at"] == confirmed["hidden_at"]
        before_restore = client.get("/api/gaps").json()
        assert not next(p for p in before_restore["context"]["suppressed"]
                        if p["gap_id"] == original["gap_id"])["needs_confirmation"]

        conn.execute("UPDATE hidden_gaps SET hidden_at = :hidden_at WHERE gap_id = :gap_id", original)
        restored = client.get("/api/gaps").json()
        assert next(p for p in restored["context"]["suppressed"]
                    if p["gap_id"] == original["gap_id"])["needs_confirmation"]
    finally:
        conn.close()
