import random
from datetime import date, timedelta

from closet import insights

from .conftest import upload

TODAY = date(2026, 11, 13)
ADDED = "2026-01-05T12:00:00.000000Z"   # long enough ago not to count as added recently


def item(id, category="tee", name=None, price=None, season="all", created=ADDED, **kw):
    return {"id": id, "name": name if name is not None else f"{id} {category}", "category": category, "color": kw.pop("color", "navy"),
            "formality": kw.pop("formality", "casual"), "season": season, "price_cents": price, "status": kw.pop("status", "active"),
            "created_at": created, **kw}


def worn(item_id, *days_ago, today=TODAY):
    return [{"item_id": item_id, "worn_on": (today - timedelta(days=n)).isoformat()} for n in days_ago]


def busy_log(n=12, start=1):
    """An item worn on n days, so the log has enough history; returns (item, wears)."""
    return item("busy", "jeans", "Busy jeans"), worn("busy", *range(start, start + n))


def find(items, wears, today=TODAY):
    return insights.find_insights(items, wears, today)


# ---------------------------------------------------------------------------- money
def test_money_is_shown_as_typed_with_no_conversion():
    assert insights.money(4500) == "$45"
    assert insights.money(4550) == "$45.50"
    assert insights.money(104000) == "$1,040"
    assert insights.per_wear_money(240) == "$2.40"
    assert insights.per_wear_money(1200) == "$12.00"


# ---------------------------------------------------------------------------- cost per wear
def test_cost_per_wear_names_the_item_and_rounds_to_the_cent():
    items = [item("trousers", "trousers", "Grey wool trousers", price=6000),
             item("tee", "tee", "White tee", price=2500), item("cap", "hat", "Cap")]
    wears = worn("trousers", *range(1, 26)) + worn("tee", 1, 2, 3)
    cpw = find(items, wears)["cost_per_wear"]
    assert cpw["enough"] is True
    best = {e["id"]: e for e in cpw["best"] + cpw["worst"]}
    assert best["trousers"]["per_wear_cents"] == 240
    assert best["trousers"]["sentence"] == "Your grey wool trousers cost $2.40 a wear over 25 wears."
    assert best["tee"]["per_wear_cents"] == 833   # 2500 / 3, rounded
    assert [e["id"] for e in cpw["best"]][0] == "trousers" and [e["id"] for e in cpw["worst"]] == ["tee"]
    assert "cap" not in best   # no price, no cost per wear
    assert cpw["closet"] == {"pieces": 2, "spent_cents": 8500, "wears": 28, "per_wear_cents": 304}
    assert cpw["sentence"] == "You paid $85 for the 2 pieces with a price and have worn them 28 times: $3.04 a wear."


def test_a_priced_item_never_worn_has_no_cost_per_wear_but_its_price():
    items = [item("coat", "coat", "Black overcoat", price=35000), item("tee", "tee", "White tee", price=2500)]
    cpw = find(items, worn("tee", *range(1, 6)))["cost_per_wear"]
    assert [e["id"] for e in cpw["best"] + cpw["worst"]] == ["tee"]
    [coat] = cpw["not_worn"]
    assert coat == {"id": "coat", "price_cents": 35000, "wears": 0, "per_wear_cents": None,
                    "sentence": "Not worn yet: your black overcoat, $350."}
    # the closet's number counts what was paid for the coat too
    assert cpw["closet"]["spent_cents"] == 37500 and cpw["closet"]["wears"] == 5


def test_cost_per_wear_with_no_price_or_no_wears_says_so():
    no_price = find([item("a"), item("b")], worn("a", 1, 2, 3))["cost_per_wear"]
    assert no_price["enough"] is False and no_price["closet"] is None and "Add what you paid" in no_price["sentence"]
    unworn = find([item("a", price=1000), item("b", price=2000)], [])["cost_per_wear"]
    assert unworn["enough"] is False and unworn["best"] == [] and len(unworn["not_worn"]) == 2
    assert "None of the 2 pieces with a price has been worn yet" in unworn["sentence"]
    few = find([item("a", price=1000)], worn("a", 1, 2))["cost_per_wear"]
    assert few["enough"] is False and few["closet"] is None and few["best"][0]["per_wear_cents"] == 500
    assert f"once they have been worn {insights.CPW_MIN_CLOSET_WEARS} times" in few["sentence"]


# ---------------------------------------------------------------------------- never worn
def test_never_worn_leaves_out_items_added_recently():
    busy, wears = busy_log()
    wears += worn("busy", 60)   # the log began 60 days ago
    recent = (TODAY - timedelta(days=insights.RECENT_DAYS - 1)).isoformat() + "T09:00:00Z"
    older = (TODAY - timedelta(days=insights.RECENT_DAYS + 10)).isoformat() + "T09:00:00Z"
    items = [busy, item("old", "sweater", "Cream sweater"), item("new", "sweater", "New sweater", created=recent),
             item("later", "shirt", "Linen shirt", created=older)]
    never = find(items, wears)["never_worn"]
    assert never["enough"] is True
    by_id = {e["id"]: e for e in never["items"]}
    assert set(by_id) == {"old", "later"}
    first = (TODAY - timedelta(days=60)).isoformat()
    assert by_id["old"]["since"] == first and "began recording" in by_id["old"]["sentence"]
    assert by_id["later"]["since"] == older[:10] and "since you added it on" in by_id["later"]["sentence"]
    assert never["sentence"].startswith("2 pieces have not been worn since you began recording")


def test_never_worn_needs_enough_history():
    assert find([item("a"), item("b")], [])["never_worn"]["sentence"] == insights.NO_LOG
    short = find([item("a"), item("b")], worn("a", 1, 2, 3))["never_worn"]
    assert short["enough"] is False and short["items"] == []
    assert f"once {insights.NEVER_MIN_LOG_WEARS} wears are recorded (3 so far)" in short["sentence"]


def test_never_worn_takes_the_season_into_account():
    # the log began in June: a winter coat not worn all summer is not listed; a summer shirt not worn is
    today = date(2026, 8, 20)
    busy = item("busy", "jeans", "Busy jeans")
    wears = [{"item_id": "busy", "worn_on": (date(2026, 6, 10) + timedelta(days=5 * n)).isoformat()} for n in range(12)]
    items = [busy, item("coat", "coat", "Winter coat", season="cool"), item("shirt", "shirt", "Linen shirt", season="warm")]
    never = find(items, wears, today)["never_worn"]
    assert [e["id"] for e in never["items"]] == ["shirt"]
    # once its season has come round, the coat is listed too
    assert {e["id"] for e in find(items, wears, date(2026, 11, 20))["never_worn"]["items"]} == {"shirt", "coat"}


# ---------------------------------------------------------------------------- not worn for a long time
def test_a_winter_coat_not_worn_since_march_is_not_neglected_in_august():
    march = date(2026, 3, 10)
    busy = item("busy", "jeans", "Busy jeans")
    wears = [{"item_id": "coat", "worn_on": march.isoformat()},
             {"item_id": "tee", "worn_on": march.isoformat()},
             {"item_id": "busy", "worn_on": "2026-01-02"}]
    items = [busy, item("coat", "coat", "Winter coat", season="cool"), item("tee", "tee", "White tee", season="all")]
    august = find(items, wears, date(2026, 8, 20))["not_worn_lately"]
    assert august["enough"] is True
    assert [e["id"] for e in august["items"]] == ["busy", "tee"]   # the coat's season has hardly come round
    assert insights.season_days(march, date(2026, 8, 20), "cool") < insights.NEGLECT_DAYS
    december = find(items, wears, date(2026, 12, 20))["not_worn_lately"]
    coat = next(e for e in december["items"] if e["id"] == "coat")
    assert coat["last_worn"] == "2026-03-10" and coat["season_days"] >= insights.NEGLECT_DAYS
    assert coat["sentence"].startswith("Last worn on 10 March 2026;")


def test_season_days_counts_only_the_seasons_months():
    assert insights.season_days(date(2026, 1, 1), date(2026, 1, 31), "all") == 30
    assert insights.season_days(date(2026, 5, 31), date(2026, 9, 30), "cool") == 0
    assert insights.season_days(date(2026, 5, 31), date(2026, 9, 30), "warm") == 122
    assert insights.season_days(date(2026, 9, 30), date(2026, 10, 10), "cool") == 10   # October belongs to both
    assert insights.season_days(date(2026, 3, 1), date(2026, 3, 1), "warm") == 0


def test_not_worn_lately_waits_for_a_long_enough_log():
    busy, wears = busy_log()
    lately = find([busy], wears)["not_worn_lately"]
    assert lately["enough"] is False and "The wear log goes back 12 days" in lately["sentence"]


# ---------------------------------------------------------------------------- worn most and the spread
def test_worn_most_over_each_window():
    items = [item("jeans", "jeans", "Dark jeans"), item("chinos", "trousers", "Tan chinos"), item("tee", "tee", "White tee")]
    wears = (worn("jeans", 1, 2, 3, 4) + worn("chinos", 40, 41, 42, 43, 44, 45) + worn("tee", 100, 101, 102, 103, 104, 105, 106)
             + worn("chinos", 5))
    windows = {w["days"]: w for w in find(items, wears)["worn_most"]["windows"]}
    assert [w["days"] for w in find(items, wears)["worn_most"]["windows"]] == [30, 90, None]
    assert windows[30]["items"] == [{"id": "jeans", "wears": 4}, {"id": "chinos", "wears": 1}]
    assert windows[30]["sentence"] == "Worn most in the last 30 days: your dark jeans, 4 times."
    assert windows[90]["items"][0] == {"id": "chinos", "wears": 7}
    # a tie goes to the piece worn more recently
    assert windows[None]["items"][:2] == [{"id": "chinos", "wears": 7}, {"id": "tee", "wears": 7}]
    assert windows[None]["sentence"] == "Worn most since you began recording what you wear: your tan chinos and white tee, 7 times each."


def test_worn_most_says_when_a_window_has_too_few_wears():
    items = [item("jeans", "jeans", "Dark jeans")]
    windows = {w["days"]: w for w in find(items, worn("jeans", 1, 50, 51, 52, 53))["worn_most"]["windows"]}
    assert windows[30]["enough"] is False and windows[30]["items"] == []
    assert windows[30]["sentence"].startswith("Only 1 wear in the last 30 days.")
    assert windows[90]["enough"] is True


def test_the_spread_tells_a_few_pieces_doing_the_work_from_even_wear():
    items = [item("j1", "jeans", "Dark jeans"), item("j2", "jeans", "Black jeans"), item("j3", "jeans", "Light jeans"),
             item("t1", "tee", "White tee"), item("t2", "tee", "Grey tee")]
    wears = worn("j1", *range(1, 10)) + worn("j2", 3) + worn("t1", 1, 2, 3) + worn("t2", 4, 5, 6)
    spread = find(items, wears)["spread"]
    assert spread["enough"] is True
    cats = {c["category"]: c for c in spread["categories"]}
    assert cats["jeans"]["kind"] == "few" and cats["jeans"]["doing_most"] == 1 and cats["jeans"]["share"] == 90
    assert cats["jeans"]["sentence"] == "Jeans: 1 of 3 gets 90% of the wears (your dark jeans)."
    assert [i["wears"] for i in cats["jeans"]["items"]] == [9, 1, 0]
    assert cats["tee"]["kind"] == "even" and cats["tee"]["doing_most"] == 2
    assert spread["categories"][0]["category"] == "jeans"   # the few-doing-the-work first


def test_the_spread_needs_enough_wears():
    spread = find([item("j1", "jeans"), item("j2", "jeans")], worn("j1", 1, 2))["spread"]
    assert spread["enough"] is False and spread["categories"] == [] and "Not enough wears yet" in spread["sentence"]


# ---------------------------------------------------------------------------- what the closet is made of
def test_what_the_closet_is_made_of():
    busy, wears = busy_log()
    items = [busy, item("a", "tee", color="white"), item("b", "tee", color="white", season="warm"),
             item("c", "coat", color="black", formality="business", season="cool"), item("gone", "tee", status="archived")]
    makeup = find(items, wears + worn("a", 200))["makeup"]
    assert makeup["pieces"] == 4 and makeup["worn"] == 1 and makeup["enough"] is True
    assert makeup["by"]["category"][0] == {"value": "tee", "count": 2, "worn": 0}
    assert {"value": "jeans", "count": 1, "worn": 1} in makeup["by"]["category"]
    assert makeup["by"]["season"][0] == {"value": "all", "count": 2, "worn": 1}
    assert set(makeup["by"]) == {"category", "color", "formality", "season"}
    assert makeup["sentence"] == "You have 4 pieces; 1 of them (25%) was worn in the last 90 days."


def test_a_closet_with_too_little_history_says_so_for_every_finding():
    answer = find([item("a", price=500), item("b")], [])
    for key in ("cost_per_wear", "never_worn", "not_worn_lately", "worn_most", "spread", "makeup"):
        assert answer[key]["enough"] is False, key
        assert answer[key]["sentence"], key
    assert answer["log"] == {"wears": 0, "first": None, "days": 0}
    empty = find([], [])
    assert empty["makeup"]["sentence"] == "There is nothing in this closet yet."


# ---------------------------------------------------------------------------- determinism and odd data
def test_same_inputs_give_the_same_answer_in_any_order():
    items = [item(f"i{n}", ["tee", "jeans", "sneakers", "coat"][n % 4], f"Piece {n}", price=1000 + n * 100 if n % 2 else None,
                  season=["all", "warm", "cool"][n % 3]) for n in range(20)]
    wears = [w for n in range(0, 20, 3) for w in worn(f"i{n}", *range(n, n + 120, 7))]
    answer = find(items, wears)
    rng = random.Random(4)
    for _ in range(3):
        a, b = items[:], wears[:]
        rng.shuffle(a)
        rng.shuffle(b)
        assert find(a, b) == answer


def test_archived_items_future_wears_and_odd_data_are_left_out():
    busy, wears = busy_log()
    items = [busy, item("gone", "tee", price=100, status="archived"), {"id": None}, None, "nonsense", {"id": "x", "category": "cape"}]
    odd = wears + worn("gone", 1, 2) + [{"item_id": "busy", "worn_on": "2099-01-01"}, {"item_id": "busy", "worn_on": "soon"}, None]
    answer = find(items, odd)
    assert answer["cost_per_wear"]["enough"] is False and answer["cost_per_wear"]["best"] == []
    assert answer["makeup"]["pieces"] == 2
    assert all(i["id"] != "gone" for w in answer["worn_most"]["windows"] for i in w["items"])


# ---------------------------------------------------------------------------- API
def test_insights_needs_login(anon):
    assert anon.get("/api/insights").status_code == 401


def test_insights_answers_for_the_open_closet(client):
    main_item = upload(client).json()
    main = client.get("/api/insights")
    assert main.status_code == 200
    body = main.json()
    assert set(body) == {"today", "log", "cost_per_wear", "never_worn", "not_worn_lately", "worn_most", "spread", "makeup"}
    assert body["makeup"]["pieces"] == 1 and body["log"]["wears"] == 0

    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"]}
    demo = client.get("/api/insights").json()
    assert demo["makeup"]["pieces"] == len(demo_ids) and demo["log"]["wears"] > 0
    cpw = demo["cost_per_wear"]
    assert cpw["enough"] is True and cpw["best"] and cpw["not_worn"]
    assert " a wear over " in cpw["best"][0]["sentence"]
    assert demo["never_worn"]["enough"] is True and demo["never_worn"]["items"]
    listed = {e["id"] for e in cpw["best"] + cpw["worst"] + cpw["not_worn"] + demo["never_worn"]["items"]}
    assert listed <= demo_ids and main_item["id"] not in listed

    # archiving a never-worn piece takes it off the list
    gone = demo["never_worn"]["items"][0]["id"]
    assert client.patch(f"/api/items/{gone}", json={"status": "archived"}).status_code == 200
    again = client.get("/api/insights").json()
    assert gone not in {e["id"] for e in again["never_worn"]["items"]}
    assert again["makeup"]["pieces"] == len(demo_ids) - 1

    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.get("/api/insights").json()["makeup"]["pieces"] == 1
