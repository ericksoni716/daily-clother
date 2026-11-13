import time
from collections import Counter

import pytest

from closet import trips


def closet(size=20):
    cats = ["shirt", "tee", "trousers", "sneakers", "sweater", "coat"]
    return [{"id": f"piece-{i:03}", "name": f"Plain {cats[i % 6]} {i}", "category": cats[i % 6],
             "color": "navy", "pattern": "solid", "season": "all", "formality": "casual",
             "laundry": "clean", "status": "active", "weight_class": "midweight"}
            for i in range(size)]


def days(n=10, low=16, high=22, rain=False):
    return [{"date": f"2027-06-{i + 1:02}", "low_c": low, "high_c": high, "rain": rain, "source": "forecast"}
            for i in range(n)]


def packed(plan):
    return {p["id"] for group in plan["packing"].values() for p in group}


def test_covered_only_by_packed_and_rewear_counts():
    rows = closet()
    answer = trips.plan(rows, days())
    assert not answer["uncovered"]
    assert len(packed(answer)) < 3 * 10
    uses = Counter()
    for day in answer["days"]:
        assert trips.ids(day["outfit"]) <= packed(answer)
        uses.update(trips.ids(day["outfit"]))
    for g in answer["packing"].values():
        for p in g:
            assert p["days_worn"] == uses[p["id"]]
    assert all(uses[r["id"]] <= trips.capacity(r, False) for r in rows)
    assert answer["basics"][0]["count"] == 11
    assert trips.plan(list(reversed(rows)), days()) == answer


def test_laundry_archive_swap_pin_and_washing():
    rows = closet(30)
    rows[0]["laundry"] = "laundry"
    rows[1]["status"] = "archived"
    answer = trips.plan(rows, days(), leave_out=["piece-006"], pins=["piece-012"])
    assert not {"piece-000", "piece-001", "piece-006"} & packed(answer)
    assert "piece-012" in packed(answer)
    washed = trips.plan(rows, days(), can_wash=True)
    assert washed["piece_count"] < answer["piece_count"]
    with pytest.raises(ValueError, match="unavailable"):
        trips.plan(rows, days(), pins=["piece-000"])


def test_uncovered_rain_unknown_and_occasion():
    rows = closet()
    assert trips.plan(rows, days(1, rain=True))["uncovered"]
    d = days(1)
    d[0]["low_c"] = None
    assert "unknown" in trips.plan(rows, d)["uncovered"][0]["reasons"][0]
    answer = trips.plan(rows, days(2), overrides=[{"date": "2027-06-02", "occasion": "formal"}])
    assert answer["days"][0]["outfit"] and not answer["days"][1]["outfit"]
    assert answer["days"][1]["occasion"] == "formal"


def test_already_worn_tops_need_washing():
    rows = closet(6)
    for row in rows:
        row["wears_since_wash"] = 5
    assert trips.plan(rows, days(1))["uncovered"]
    assert not trips.plan(rows, days(1), can_wash=True)["uncovered"]


def test_ten_days_300_items_stays_fast():
    start = time.perf_counter()
    answer = trips.plan(closet(300), days())
    elapsed = time.perf_counter() - start
    assert not answer["uncovered"]
    assert elapsed < 20, f"10 days, 300 items took {elapsed:.2f}s"
