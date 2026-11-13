"""Regression checks for category-specific taste and seasonal opportunity."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from closet import gaps, taste

from .test_gaps import item, wears_for


def suggestion(category, colors=None, evidence=()):
    return {"look_for": {"category": category, "formality": "business",
                         "colors": colors or ["brown", "black"], "pattern": None, "fit": None},
            "evidence": {"items": list(evidence)}, "why": []}


@pytest.mark.parametrize("category", ["belt", "dress_shoes", "coat"])
@pytest.mark.parametrize("source", ["wears", "ratings"])
def test_clothing_preferences_do_not_recolour_unrelated_kinds(category, source):
    rows = [item(f"tee{i}", "tee", color, "casual", rating="love",
                 silhouette={"fit": "regular"})
            for i, color in enumerate(["navy", "navy", "white", "white", "grey"])]
    wears = wears_for({row["id"]: 3 for row in rows}) if source == "wears" else []
    if source == "wears":
        for row in rows:
            row["rating"] = None
    gap = suggestion(category)
    original = deepcopy(gap)
    taste.apply([gap], taste.learn(rows, wears), gaps._closet(rows, wears))
    assert gap == original


def test_preferences_and_avoidances_are_specific_to_the_same_category():
    rows = [item(f"tee{i}", "tee", "navy", "casual", rating="love",
                 silhouette={"fit": "regular"}) for i in range(2)]
    rows += [item(f"shirt{i}", "shirt", "red", "business", pattern="plaid",
                  rating="dislike", silhouette={"fit": "slim"}) for i in range(3)]
    found = [suggestion(category) for category in ("tee", "shirt", "trousers")]
    original_trousers = deepcopy(found[2])
    taste.apply(found, taste.learn(rows, []), gaps._closet(rows, []))
    assert found[0]["look_for"]["colors"][0] == "navy"
    assert found[0]["look_for"]["fit"] == "regular"
    assert found[0]["look_for"]["avoid_fits"] == []
    assert found[0]["look_for"]["avoid_patterns"] == []
    assert found[1]["look_for"]["avoid_fits"] == ["slim"]
    assert found[1]["look_for"]["avoid_patterns"] == ["plaid"]
    assert found[2] == original_trousers


def test_one_favoured_item_in_each_kind_is_not_two_items_of_either_kind():
    rows = [item("tee", "tee", rating="love"), item("shirt", "shirt", rating="love")]
    rows += [item(f"neutral{i}", "trousers", rating="meh") for i in range(3)]
    assert not taste.learn(rows, [])["used"]


def test_same_kind_colour_preference_still_needs_two_items_and_four_points():
    rows = [item(f"tee{i}", "tee", "white", rating="like") for i in range(2)]
    rows += [item(f"neutral{i}", "trousers", rating="meh") for i in range(3)]
    gap = suggestion("tee")
    taste.apply([gap], taste.learn(rows, []), gaps._closet(rows, []))
    assert gap["look_for"]["colors"][0] == "white"
    assert "you rate white highly" in gap["why"][0]
    rows[1]["rating"] = "meh"
    assert not taste.learn(rows, [])["used"]


def test_compatibility_still_precedes_same_kind_colour_preference():
    rows = [item(f"tee{i}", "tee", "red", "casual", rating="love") for i in range(2)]
    rows += [item(f"neutral{i}", "trousers", "green", "casual", rating="meh") for i in range(3)]
    gap = suggestion("tee", ["white", "navy"], ["neutral0"])
    taste.apply([gap], taste.learn(rows, []), gaps._closet(rows, []))
    assert gap["look_for"]["colors"][0] != "red"


def seasonal_history(category, season, start="2026-05-01", end="2026-08-01",
                     owned="2025-01-01", worn_items=3, wear_count=12):
    rows = [item(f"unworn{i}", category, "red", "business", season=season,
                 pattern="plaid", silhouette={"fit": "slim"}, created_at=owned)
            for i in range(2)]
    rows += [item(f"worn{i}", "tee") for i in range(worn_items)]
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    wears = [{"item_id": f"worn{i % worn_items}",
              "worn_on": (first + (last - first) * i // (wear_count - 1)).isoformat()}
             for i in range(wear_count)]
    return rows, wears


@pytest.mark.parametrize("category,season,avoided", [
    ("coat", "cool", []),
    ("shorts", "warm", ["plaid"]),
    ("shirt", "all", ["plaid"]),
])
def test_never_worn_in_may_to_august_requires_the_items_actual_season(category, season, avoided):
    rows, wears = seasonal_history(category, season)
    learned = taste.learn(rows, wears)
    assert learned["by_category"][category]["avoided"]["pattern"] == avoided


@pytest.mark.parametrize("end,avoided", [
    ("2026-06-28", []),  # 89 warm-season days since April began.
    ("2026-06-29", ["plaid"]),  # 90 warm-season days.
])
def test_season_must_overlap_the_log_for_ninety_days(end, avoided):
    rows, wears = seasonal_history("shorts", "warm", start="2026-02-01", end=end)
    assert taste.learn(rows, wears)["by_category"]["shorts"]["avoided"]["pattern"] == avoided


@pytest.mark.parametrize("age,log_days,avoided", [
    (179, 90, []),
    (180, 89, []),
    (180, 90, ["plaid"]),
])
def test_never_worn_keeps_original_ownership_and_log_thresholds(age, log_days, avoided):
    end = date(2026, 8, 1)
    rows, wears = seasonal_history("shirt", "all", end=end.isoformat(),
                                  start=(end - timedelta(days=log_days)).isoformat(),
                                  owned=(end - timedelta(days=age)).isoformat())
    assert taste.learn(rows, wears)["by_category"]["shirt"]["avoided"]["pattern"] == avoided


def test_season_before_ownership_is_not_an_opportunity_to_wear():
    rows, wears = seasonal_history("coat", "cool", start="2026-01-01",
                                  end="2026-11-01", owned="2026-05-01")
    assert taste.learn(rows, wears)["by_category"]["coat"]["avoided"]["pattern"] == []


@pytest.mark.parametrize("worn_items,wear_count", [(3, 9), (2, 12)])
def test_long_ownership_and_applicable_season_cannot_replace_enough_wear_evidence(worn_items, wear_count):
    rows, wears = seasonal_history("shirt", "all", worn_items=worn_items, wear_count=wear_count)
    assert not taste.learn(rows, wears)["used"]
