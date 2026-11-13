import copy
import json
import random

import pytest

from closet import gaps, outfits, vocab
from closet.config import bundle_dir


def item(id, category, **kw):
    return {"id": id, "name": f"Test {id}", "category": category, "color": "navy",
            "pattern": "solid", "season": "all", "formality": "business", **kw}


def closet():
    return [
        item("shirt-a", "shirt"), item("shirt-b", "shirt"),
        item("trousers-a", "trousers"), item("trousers-b", "trousers"),
        item("shoes", "dress_shoes", material="leather"),
        item("coat", "coat", material="wool", weight_class="super_heavy"),
    ]


def report(items=None, wears=None):
    return gaps.analyze(closet() if items is None else items, wears or [])


def by_method(result, method):
    return [g for g in result["gaps"] if method in g["methods"]]


def test_missing_rain_layer_records_real_days_and_items():
    result = report()
    rain = [g for g in result["gaps"] if g["look_for"].get("material") == "waterproof"]
    assert rain
    assert any(d["rain"] and d["occasion"] == "business" for g in rain for d in g["evidence"]["days"])
    assert any("umbrella" in why for g in rain for why in g["why"])
    assert all(g["evidence"]["items"] for g in rain)


def test_existing_raincoat_removes_business_rain_gap():
    clothes = closet()
    clothes[-1].update(material="waterproof", weight_class="midweight")
    result = report(clothes)
    assert not [g for g in result["gaps"] if g["look_for"].get("material") == "waterproof"
                and any(d["occasion"] == "business" for d in g["evidence"]["days"])]


def test_heavy_raincoat_does_not_cover_every_mild_rainy_day():
    clothes = closet()
    clothes[-1].update(material="waterproof", weight_class="super_heavy")
    rain = next(g for g in report(clothes)["gaps"] if g["look_for"].get("material") == "waterproof")
    assert rain["look_for"]["weight_class"] == "lightweight"
    assert any(d["temperature"] == "mild" for d in rain["evidence"]["days"])


def test_lower_ranked_owned_raincoat_is_not_a_gap():
    clothes = closet()
    clothes[-1].update(weight_class="lightweight", rating="love")
    clothes.append(item("raincoat", "coat", material="waterproof", weight_class="lightweight",
                        formality="smart_casual", rating="meh"))
    answer = outfits.suggest(clothes, outfits.Context(12, 12, rain=True, occasion="business"))
    assert any("umbrella" in w for w in answer["outfits"][0]["warnings"])
    assert not [g for g in report(clothes)["gaps"] if g["look_for"].get("material") == "waterproof"]


def test_suede_coat_replacement_fits_over_heavy_shirts():
    clothes = [item(f"shirt-{n}", "shirt", weight_class="heavyweight") for n in range(3)]
    clothes += [item("coat", "coat", material="suede", weight_class="heavyweight"),
                item("trousers", "trousers"), item("shoes", "dress_shoes")]
    rain = [g for g in report(clothes)["gaps"] if g["look_for"].get("material") == "waterproof"]
    assert len(rain) == 1
    replacement = gaps._candidate(rain[0]["look_for"])
    assert all(outfits._layers_ok(outfits._piece(i), None, replacement)
               for i in clothes if i["category"] == "shirt")
    assert any("test coat" in why and "rain" in why for why in rain[0]["why"])


def test_already_warmest_coat_is_not_sold_as_a_warmer_one():
    clothes = closet()
    clothes[-1]["formality"] = "smart_casual"
    assert not [g for g in by_method(report(clothes), "days")
                if g["look_for"]["category"] == "coat" and g["look_for"].get("weight_class") == "super_heavy"]


def test_one_pair_of_smart_shoes_is_a_thin_place():
    thin = by_method(report(), "thin")
    shoe = next(g for g in thin if g["look_for"]["category"] == "dress_shoes")
    assert "shoes" in {i["id"] for i in shoe["evidence"]["items"]}
    assert any("test shoes" in why and "relies" in why for why in shoe["why"])
    assert any(d["occasion"] == "business" for d in shoe["evidence"]["days"])


def test_unused_alternative_is_not_a_thin_place():
    clothes = closet() + [item("other-shoes", "dress_shoes", rating="meh")]
    assert not [g for g in by_method(report(clothes), "thin") if g["look_for"]["category"] == "dress_shoes"]


def test_loud_shirt_orphan_gets_plain_trousers_that_really_work():
    clothes = [
        item("loud-shirt", "shirt", pattern="floral", color="red"),
        item("plain-shirt", "shirt"),
        item("loud-trousers-a", "trousers", pattern="plaid"),
        item("loud-trousers-b", "trousers", pattern="camo"),
        item("shoes-a", "dress_shoes"), item("shoes-b", "dress_shoes"),
    ]
    orphan = next(g for g in by_method(report(clothes), "orphan")
                  if g["look_for"]["category"] == "trousers")
    assert "loud-shirt" in {i["id"] for i in orphan["evidence"]["items"]}
    purchase = {**orphan["look_for"], "id": "purchase", "color": orphan["look_for"]["colors"][0]}
    answer = outfits.suggest(clothes + [purchase], outfits.Context(20, 20, occasion="business", build_around="loud-shirt"))
    assert any(o["pieces"]["bottom"] == "purchase" for o in answer["outfits"])
    assert all(not any("bold patterns" in w for w in o["warnings"]) for o in answer["outfits"])


def test_day_with_no_layerable_outfit_gets_a_single_piece_repair():
    clothes = [item(f"shirt-{n}", "shirt", weight_class="super_heavy") for n in range(3)]
    clothes += [item("jacket", "jacket", weight_class="lightweight"),
                item("trousers", "trousers"), item("shoes", "dress_shoes")]
    ctx = outfits.Context(2, 2, occasion="business")
    assert outfits.suggest(clothes, ctx)["outfits"] == []
    repair = next(g for g in by_method(report(clothes), "days")
                  if any("No outfit fits together" in why for why in g["why"]))
    purchase = {**repair["look_for"], "id": "purchase", "color": repair["look_for"]["colors"][0]}
    assert outfits.suggest(clothes + [purchase], ctx)["outfits"]


def test_popularity_alone_does_not_make_an_orphan():
    clothes = closet() + [item(f"shirt-{n}", "shirt", rating="love") for n in range(10)]
    assert not by_method(report(clothes), "orphan")


def test_bounded_orphan_search_does_not_claim_absence(monkeypatch):
    monkeypatch.setattr(gaps, "WITNESS_LIMIT", 0)
    assert not by_method(report(), "orphan")


def test_wear_imbalance_and_never_worn_are_different():
    clothes = closet() + [item("shirt-c", "shirt")]
    wears = [{"item_id": "shirt-a", "worn_on": f"2026-10-{day:02d}"} for day in range(1, 13)]
    wears += [{"item_id": "shirt-b", "worn_on": "2026-10-01"}]
    result = report(clothes, wears)
    worn = by_method(result, "wear")
    assert len(worn) == 1
    assert worn[0]["evidence"]["wear_counts"] == {"shirt-a": 12, "shirt-b": 1, "shirt-c": 0}
    assert any("test shirt-a" in why for why in worn[0]["why"])
    never = next(note for note in result["notes"] if note["kind"] == "never_worn")
    assert "shirt-c" in never["item_ids"]
    assert not any("test shirt-c has" in why for g in result["gaps"] for why in g["why"])
    assert report(clothes, wears + wears) == result


def test_few_wears_do_not_suggest_a_duplicate():
    clothes = closet() + [item("shirt-c", "shirt")]
    assert not by_method(report(clothes, [{"item_id": "shirt-a", "worn_on": "2026-10-01"}]), "wear")


def test_missing_basic():
    clothes = [i for i in closet() if i["category"] != "dress_shoes"] + [item("shirt-c", "shirt")]
    basic = next(g for g in by_method(report(clothes), "basic") if g["look_for"]["category"] == "dress_shoes")
    assert basic["look_for"]["formality"] == "business"
    assert any("basics list" in why for why in basic["why"])
    assert not [g for g in by_method(report(clothes + [item("shoes", "dress_shoes")]), "basic")
                if g["look_for"]["category"] == "dress_shoes"]


def test_merging_combines_methods_days_and_wear_evidence():
    clothes = closet() + [item("shoes-2", "dress_shoes", formality="casual"),
                          item("shoes-3", "dress_shoes", formality="smart_casual")]
    wears = [{"item_id": "shoes", "worn_on": f"2026-10-{d:02d}"} for d in range(1, 13)]
    # Two business peers would remove the thin place, but the variety and wear rules can still agree.
    clothes[-2]["formality"] = "smart_casual"
    result = report(clothes, wears)
    worn = next(g for g in by_method(result, "wear") if g["look_for"]["category"] == "dress_shoes")
    assert "thin" in worn["methods"]  # formal days can only use the business pair
    assert worn["evidence"]["days"] and worn["evidence"]["wear_counts"]
    assert len({g["id"] for g in result["gaps"]}) == len(result["gaps"])


def test_shared_occasion_needs_merge_into_one_purchase():
    collector = gaps._Collector([outfits._piece(i) for i in closet()])
    for occasion in ("athletic", "casual"):
        ctx = outfits.Context(20, 20, occasion=occasion)
        collector.add(gaps._for_day("base", ctx), "days", gaps.DAY_SCORE, "A plain top is missing.",
                      day=gaps._day_record("mild", ctx, ["A plain top is missing."]))
    merged = collector.finish(gaps.MAX_GAPS)
    assert len(merged) == 1
    assert {d["occasion"] for d in merged[0]["evidence"]["days"]} == {"athletic", "casual"}


def test_ranking_limits_determinism_and_no_mutation():
    clothes = closet()
    original = copy.deepcopy(clothes)
    expected = report(clothes)
    assert expected["days_checked"] == len(gaps.DAY_TEMPERATURES) * 2 * len(vocab.FORMALITY)
    assert len(expected["gaps"]) <= gaps.MAX_GAPS
    assert [g["score"] for g in expected["gaps"]] == sorted((g["score"] for g in expected["gaps"]), reverse=True)
    assert all(0 <= g["score"] <= 100 for g in expected["gaps"])
    random.Random(7).shuffle(clothes)
    assert report(clothes) == expected
    assert sorted(clothes, key=lambda i: i["id"]) == sorted(original, key=lambda i: i["id"])
    assert gaps.find_gaps(clothes, [], gaps.Options(limit=2)) == expected["gaps"][:2]


@pytest.mark.parametrize("clothes", [[], closet()[:2]])
def test_tiny_closet_is_not_a_shopping_list(clothes):
    result = report(clothes)
    assert result["gaps"] == [] and result["days_checked"] == 0
    assert "too few" in result["notes"][0]["message"]


def test_laundry_ignored_and_unusable_items_excluded():
    clothes = closet()
    expected = report(clothes)
    assert report([{**i, "laundry": "laundry"} for i in clothes]) == expected
    assert report([{**i, "location": "laundry"} for i in clothes]) == expected
    assert report(clothes + [item("archived", "shirt", status="archived"),
                             item("disliked", "coat", rating="dislike"),
                             item("unlabelled", None)]) == expected


def test_demo_nonempty_and_every_gap_names_real_items():
    clothes = json.loads((bundle_dir() / "demo_data" / "items.json").read_text())["items"]
    result = report(clothes)
    real = {i["id"] for i in clothes}
    assert result["gaps"]
    for gap in result["gaps"]:
        evidence = gap["evidence"]["items"]
        assert evidence and {i["id"] for i in evidence} <= real
        assert any(i["name"] in " ".join(gap["why"]) for i in evidence)
        assert set(gap["evidence"]["works_with"]) <= real
        assert gap["look_for"]["category"] in vocab.CATEGORY
        assert set(gap["look_for"]["colors"]) <= set(vocab.COLOR)


def test_api_login_required(anon):
    assert anon.get("/api/gaps").status_code == 401


def test_api_shape_demo_main_separation_and_laundry(client):
    main = client.get("/api/gaps").json()
    assert main["gaps"] == [] and main["item_count"] == 0
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    response = client.get("/api/gaps")
    assert response.status_code == 200
    demo = response.json()
    assert set(demo) == {"gaps", "notes", "item_count", "days_checked"}
    assert demo["gaps"] and demo["item_count"] == 30
    rows = client.get("/api/items").json()["items"]
    for row in rows:
        assert client.post(f"/api/items/{row['id']}/laundry", json={"state": "laundry"}).status_code == 200
    assert client.get("/api/gaps").json() == demo
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.get("/api/gaps").json() == main


def test_api_work_runs_off_event_loop(client, monkeypatch):
    import asyncio

    def analyze(items, wears):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return {"gaps": [], "notes": [], "item_count": len(items), "days_checked": 0}

    monkeypatch.setattr(gaps, "analyze", analyze)
    assert client.get("/api/gaps").status_code == 200


def test_api_keeps_profile_captured_before_worker(client, services, monkeypatch):
    from closet import app as app_module

    client.post("/api/profile", json={"profile": "demo"})
    observed = {}

    async def delayed(work):
        services.state.update(profile="main")
        return work()

    def analyze(items, wears):
        observed.update(items=items, wears=wears)
        return {"gaps": [], "notes": [], "item_count": len(items), "days_checked": 0}

    monkeypatch.setattr(app_module, "run_in_threadpool", delayed)
    monkeypatch.setattr(gaps, "analyze", analyze)
    assert client.get("/api/gaps").json()["item_count"] == 30
    assert observed["wears"]
    assert {w["item_id"] for w in observed["wears"]} <= {i["id"] for i in observed["items"]}
