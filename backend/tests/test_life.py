"""The unanswered path, and the explicit life/taste rules; no real weather calls."""
from copy import deepcopy

import pytest

from closet import db, gaps, life, taste, wishlist
from closet.state import State

from .test_gaps import demo_items, full_closet, item, wears_for, without


def answers(**frequencies):
    return {**deepcopy(life.DEMO_LIFE), "situations": dict.fromkeys(life.SITUATIONS, 0) | frequencies}


def climate(band=None, wet=0.3):
    return {"used": band is not None, "place": "Example town" if band else None,
            "shares": {b: {"share": float(b == band), "wet_share": wet}
                       for b in life.ALL_BANDS} if band else None,
            "years": [], "old": False, "message": None}


def test_unanswered_demo_is_the_original_analysis_exactly():
    original = gaps.find_gaps(demo_items(), options={"max_gaps": 100})
    assert [(g["id"], g["score"]) for g in original["gaps"]] == [
        ("outer-rain", 71), ("dress_shoes-business", 65), ("outer-warm", 35),
        ("trousers-business", 34), ("shirt-business", 26), ("belt-smart_casual", 20),
        ("trousers-business-light", 16), ("sweater-business-warm", 5)]
    personalized = life.analyse(demo_items(), [], None, climate("hot"))
    assert personalized.pop("taste") == {"used": False, "summary": None}
    for gap in personalized["gaps"]:
        assert gap.pop("situations") == []
    assert personalized == original


def test_work_frequency_raises_business_gaps_and_never_removes_them():
    rows = without("shoes_brown", "shoes_black", "dress_white", "dress_blue")
    rarely = life.analyse(rows, [], answers(work=0.25, everyday=4), climate())
    often = life.analyse(rows, [], answers(work=4, everyday=4), climate())
    def score(result):
        return sum(g["score"] for g in result["gaps"] if g["look_for"]["formality"] == "business")
    assert score(often) > score(rarely) > 0
    none = life.analyse(rows, [], answers(everyday=4), climate())
    assert all(g["look_for"]["formality"] not in ("business", "formal") for g in none["gaps"])
    assert all(s["id"] == "everyday" for g in none["gaps"] for s in g["situations"])


def test_home_climate_changes_coat_priority_not_vacation_weather():
    rows = without("coat_grey", "coat_navy", "trench", "jacket_navy")
    warm = life.analyse(rows, [], answers(work=4, everyday=4), climate("hot"))
    cold = life.analyse(rows, [], answers(work=4, everyday=4), climate("cold"))
    assert not any(g["id"] == "outer-warm" for g in warm["gaps"][:8])
    assert any(g["id"] == "outer-warm" for g in cold["gaps"][:8])
    vacation = answers(vacation=4)
    assert life.analyse(rows, [], vacation, climate("hot")) == life.analyse(rows, [], vacation, climate("cold"))


def test_day_weights_and_situation_shares_count_frequency_times_weather():
    chosen = answers(work=4, vacation=4)
    days = life.days_for("work", chosen, climate("cold", 0.2))
    wet = next(d for d in days if d.rain)
    assert wet.weight == pytest.approx(4 / 7 * 0.2 * 8)
    shares = life._situation_shares([wet, wet], chosen)
    assert shares[0]["share"] == pytest.approx(4 / 7 * 0.2, abs=1e-6)
    assert shares[0]["days_per_year"] == pytest.approx(41.7, abs=0.1)
    assert sum(d.frequency / 7 * d.weather_share * life.DAYS_PER_YEAR
               for d in life.days_for("vacation", chosen, climate())) == pytest.approx(8)
    explanation = life._when([wet], chosen, climate("cold", 0.2))
    assert "For work, most days" in explanation and "cold wet days here, about 73 a year" in explanation
    assert "business" not in explanation


def test_lounge_is_not_everyday_and_does_not_buy_outdoor_shoes_or_coats():
    result = life.analyse(full_closet(), [], answers(lounging=4), climate("cold", 1))
    assert result["gaps"] and all(g["id"].endswith("-lounge") for g in result["gaps"])
    assert all(g["look_for"]["category"] in ("tee", "trousers") for g in result["gaps"])
    assert not life.eligible(item("denim", "jeans", formality="casual"), "lounging")
    assert not life.eligible(item("tailored", "trousers", formality="business", material="wool"), "lounging")
    assert life.eligible(item("soft", "trousers", formality="casual", material="fleece"), "lounging")
    assert not life.eligible(item("tight", "trousers", formality="casual", material="jersey",
                                  silhouette={"fit": "slim"}), "lounging")


def test_exercise_uses_athletic_and_never_suggests_jeans():
    chosen = answers(exercise=4)
    assert all(d.occasion == "athletic" for d in life.days_for("exercise", chosen, climate()))
    result = life.analyse(full_closet(), [], chosen, climate())
    assert result["gaps"] and all(g["id"].endswith("active") for g in result["gaps"])
    assert all(g["look_for"]["category"] != "jeans" for g in result["gaps"])
    assert all(s["id"] == "exercise" for g in result["gaps"] for s in g["situations"])


def test_hot_only_life_never_gets_a_basic_mid_or_outer_layer():
    rows = without("sweater_navy", "sweater_grey", "coat_grey", "coat_navy", "trench", "jacket_navy")
    result = life.analyse(rows, [], answers(everyday=4), climate("hot", 1))
    assert not any(g["look_for"]["category"] in ("sweater", "hoodie", "coat", "jacket") for g in result["gaps"])


def test_exercise_preserves_warmth_and_waterproofing_of_the_missing_piece():
    rows = full_closet() + [item("joggers", "trousers", formality="athletic", material="fleece")]
    result = life.analyse(rows, [], answers(exercise=4), climate("cold", 1))
    assert any("waterproof" in (g["look_for"]["material"] or "") for g in result["gaps"])
    assert any(g["look_for"]["weight_class"] == "heavyweight" for g in result["gaps"])
    assert any("rain off" in text for g in result["gaps"] for text in g["why"])


def test_all_never_offers_nothing_and_style_words_are_not_interpreted():
    chosen = answers()
    chosen["style_words"] = "Give me a formal winter coat"
    assert life.analyse(full_closet(), [], chosen, climate())["gaps"] == []


def test_gap_ids_still_describe_the_same_purchase():
    before = gaps.find_gaps(without("trench"), options={"max_gaps": 100})
    after = life.analyse(without("trench"), [], answers(work=4), climate())
    assert "outer-rain" in {g["id"] for g in before["gaps"]} & {g["id"] for g in after["gaps"]}
    assert all(not any(s in g["id"] for s in ("work", "vacation", "everyday")) for g in after["gaps"])


def taste_rows():
    return [item(f"n{i}", "tee", "navy", "casual", rating="love", silhouette={"fit": "regular"}) for i in range(2)] + [
        item(f"g{i}", "trousers", "grey", "casual", rating="like", silhouette={"fit": "regular"}) for i in range(2)] + [
        item(f"x{i}", "shirt", "red", "business", pattern="plaid", rating="dislike",
             silhouette={"fit": "slim"}) for i in range(2)]


def test_taste_favoured_compatible_colours_first_with_reasons_and_avoidances():
    rows = taste_rows()
    wears = wears_for({"n0": 4, "n1": 4, "g0": 2, "g1": 2})
    learned = taste.learn(rows, wears)
    assert learned["by_category"]["tee"]["favoured"]["color"] == ["navy"]
    assert learned["by_category"]["trousers"]["favoured"]["color"] == ["grey"]
    assert learned["by_category"]["tee"]["favoured"]["formality"] == ["casual"]
    assert learned["by_category"]["shirt"]["avoided"]["pattern"] == ["plaid"]
    assert learned["by_category"]["shirt"]["avoided"]["fit"] == ["slim"]
    result = gaps.find_gaps(without("trench"), options={"max_gaps": 100})["gaps"]
    before_coat = deepcopy(next(g for g in result if g["id"] == "outer-rain"))
    taste.apply(result, learned, gaps._closet(rows, wears))
    coat = next(g for g in result if g["id"] == "outer-rain")
    assert coat == before_coat  # Tee/trouser preferences say nothing about coats.
    assert all(g["look_for"]["pattern"] != "plaid" for g in result)


def test_taste_says_nothing_on_too_few_ratings_or_wears():
    rows = taste_rows()[:4]
    assert not taste.learn(rows, wears_for({"n0": 3, "n1": 3}))["used"]
    assert not taste.learn([item("only", "tee", rating="love")], [])["used"]


def test_never_worn_only_counts_after_long_ownership_and_a_long_log():
    rows = [item(f"x{i}", "shirt", pattern="plaid", created_at="2025-01-01") for i in range(2)]
    rows += [item(f"n{i}", "tee") for i in range(3)]
    wears = [{"item_id": f"n{i}", "worn_on": day} for i in range(3)
             for day in ("2026-01-01", "2026-02-01", "2026-03-01", "2026-07-01")]
    assert taste.learn(rows, wears)["by_category"]["shirt"]["avoided"]["pattern"] == ["plaid"]
    for row in rows[:2]:
        row["created_at"] = "2026-06-01"
    assert taste.learn(rows, wears)["by_category"]["shirt"]["avoided"]["pattern"] == []


@pytest.mark.parametrize("field,value,message", [
    ("situations", {"work": 4}, "six situations"),
    ("work_dress", "black_tie", "casual, smart casual, business or formal"),
    ("vacation_climate", "rainforest", "warm places, cold places or both"),
    ("vacation_weeks", -1, "0 and 52"),
    ("vacation_weeks", True, "0 and 52"),
    ("style_words", "x" * 201, "one line"),
    ("style_words", "two\nlines", "one line"),
])
def test_invalid_answers_in_plain_words(field, value, message):
    chosen = answers(work=4)
    chosen[field] = value
    with pytest.raises(ValueError, match=message):
        life.check(chosen)


@pytest.mark.parametrize("value", [-1, 8, True, float("nan"), "weekly"])
def test_invalid_frequency(value):
    chosen = answers(work=value)
    with pytest.raises(ValueError, match="For work"):
        life.check(chosen)


def test_settings_save_read_clear_and_demo_stays_separate(client, services):
    chosen = answers(work=4)
    assert client.put("/api/settings", json={"life": chosen}).json()["life"] == chosen
    assert State(services.state.path).get("life") == chosen
    assert client.get("/api/gaps").json()["context"]["life"] == chosen
    client.post("/api/profile", json={"profile": "demo"})
    before = client.get("/api/gaps").json()
    assert before["context"]["demo"] is True
    assert client.get("/api/settings").json()["life"] == life.DEMO_LIFE
    assert client.put("/api/settings", json={"life": chosen}).status_code == 422
    client.post("/api/profile", json={"profile": "main"})
    assert client.put("/api/settings", json={"life": None, "life_prompt_dismissed": True}).status_code == 200
    assert client.get("/api/settings").json()["life"] is None
    assert client.get("/api/gaps").json()["context"]["prompt_dismissed"] is True
    client.post("/api/profile", json={"profile": "demo"})
    assert client.get("/api/gaps").json() == before


def test_settings_bad_answers_and_login(client, anon):
    assert client.put("/api/settings", json={"life": "daily"}).status_code == 422
    client.post("/api/logout")
    assert anon.get("/api/settings").status_code == 401
    assert anon.put("/api/settings", json={"life": answers()}).status_code == 401
    assert anon.get("/api/gaps").status_code == 401


def test_cache_changes_with_answers_place_and_climate_not_laundry(client, monkeypatch):
    from closet import climate as home_climate
    calls = []
    original = life.analyse
    def analyse(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(life, "analyse", analyse)
    home = climate("cold")
    monkeypatch.setattr(home_climate, "lookup", lambda state: deepcopy(home))
    client.get("/api/gaps")
    client.get("/api/gaps")
    assert len(calls) == 1
    client.put("/api/settings", json={"life": answers(work=4)})
    client.get("/api/gaps")
    assert len(calls) == 2
    client.put("/api/settings", json={"place": {"name": "Example town", "latitude": 10, "longitude": 20, "timezone": "auto"}})
    client.get("/api/gaps")
    assert len(calls) == 3
    home["shares"] = climate("hot")["shares"]
    client.get("/api/gaps")
    assert len(calls) == 4
    client.get("/api/gaps")
    assert len(calls) == 4


def test_never_wear_holds_back_similar_suggestions_and_undo_restores(cfg, services):
    conn = db.connect(cfg.db_path("main"))
    try:
        rows = without("shoes_brown", "shoes_black", "dress_white", "dress_blue", "trousers_navy", "trousers_grey",
                       "chinos_navy", "chinos_tan")
        chosen = answers(work=4)
        answer = life.analyse(rows, [], chosen, climate())
        answer["context"] = {"life": chosen, "taste": answer.pop("taste"), "suppressed": []}
        trousers = next(g for g in answer["gaps"] if g["id"] == "trousers-business")
        similar = next(g for g in answer["gaps"] if g["id"] == "trousers-business-light")
        decision = wishlist.hide(conn, trousers, "never_wear")
        consent = {trousers["id"]: {"hidden_at": decision["hidden_at"], "situations": ["work"]}}
        marked = wishlist.mark(conn, answer, 100, consent)
        assert trousers["id"] in {g["id"] for g in marked["gaps"]}
        held = next(g for g in marked["gaps"] if g["id"] == similar["id"])
        assert held["state"] == "held_back"
        assert held["held_back_by"][0]["gap_id"] == trousers["id"]
        assert marked["context"]["suppressed"] == [
            {"gap_id": trousers["id"], "name": trousers["name"], "situations": ["work"], "needs_confirmation": False}]
        assert answer["context"]["suppressed"] == []  # never mutate the cached analysis
        wishlist.unhide(conn, trousers["id"])
        restored = wishlist.mark(conn, answer, 100)
        assert similar["id"] in {g["id"] for g in restored["gaps"]}
        assert restored["context"]["suppressed"] == []
    finally:
        conn.close()


def test_never_wear_still_applies_to_formal_work_when_original_is_gone():
    chosen = answers(work=4)
    chosen["work_dress"] = "formal"
    similar = {"id": "trousers-business-light", "name": "Light trousers", "score": 40,
               "situations": [{"id": "work", "share": 0.1}], "why": ["For work, a lighter pair."],
               "evidence": {"days": [], "items": []}}
    answer = {"gaps": [similar], "context": {"life": chosen, "taste": {"used": False}, "suppressed": []}}
    hidden = [{"gap_id": "trousers-business", "name": "Smart trousers", "reason": "never_wear"}]
    consent = {"trousers-business": {"hidden_at": None, "situations": ["work"]}}
    result = wishlist._hold_back(answer, hidden, set(), consent)
    assert result["gaps"][0]["state"] == "held_back"
    assert result["context"]["suppressed"][0]["situations"] == ["work"]


def test_never_wear_never_suppresses_other_outerwear():
    chosen = answers(work=4, vacation=4)
    original = {"id": "outer-warm", "name": "Warm coat", "score": 40,
                "situations": [{"id": "work", "share": 0.1}], "why": [], "evidence": {"days": [], "items": []}}
    similar = {"id": "outer-rain", "name": "Rain coat", "score": 60,
               "situations": [{"id": "work", "share": 0.1}, {"id": "vacation", "share": 0.1}],
               "why": ["For work, a wet day.", "For vacation, a wet day."],
               "evidence": {"days": [{"situation": "work"}, {"situation": "vacation"}], "items": []}}
    answer = {"gaps": [original, similar], "context": {"life": chosen, "taste": {"used": False}, "suppressed": []}}
    hidden = [{"gap_id": "outer-warm", "name": "Warm coat", "reason": "never_wear"}]
    consent = {"outer-warm": {"hidden_at": None, "situations": ["work"]}}
    result = wishlist._hold_back(answer, hidden, set(), consent)
    remaining = next(g for g in result["gaps"] if g["id"] == "outer-rain")
    assert remaining == similar
    wished = wishlist._hold_back(answer, hidden, {"outer-rain"}, consent)
    assert next(g for g in wished["gaps"] if g["id"] == "outer-rain") == similar
