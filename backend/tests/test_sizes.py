"""Your sizes (closet/sizes.py, migration 0047): the usual size for each kind of piece and a brand's own, kept in the
closet; the size most common on the owner's items offered while none is saved; and the endpoints."""
from contextlib import closing

import pytest

from closet import db, sizes
from closet.items import ItemError


@pytest.fixture
def conn(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as c:
        yield c


def add_item(conn, id, category, size, status="active"):
    conn.execute("INSERT INTO items (id, status, category, size, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (id, status, category, size, db.now(), db.now()))


def kind(answer, key):
    return next(k for k in answer["kinds"] if k["kind"] == key)


def test_categories_belong_to_their_kind():
    assert [sizes.kind_of(c) for c in ("tee", "shirt", "sweater", "hoodie", "jeans", "shorts", "coat", "boots")] == \
        ["tops", "tops", "knitwear", "knitwear", "trousers", "trousers", "jackets", "shoes"]
    assert sizes.kind_of("belt") is None and sizes.kind_of(None) is None and sizes.kind_of("other") is None


def test_a_new_closet_has_no_sizes_and_every_kind_in_order(conn):
    answer = sizes.current(conn)
    assert [k["kind"] for k in answer["kinds"]] == ["tops", "knitwear", "trousers", "jackets", "shoes"]
    assert all(k["size"] is None and k["suggested"] is None and k["brands"] == [] for k in answer["kinds"])


def test_the_most_common_size_on_your_items_is_suggested_until_one_is_saved(conn):
    for n, (category, size) in enumerate([("tee", "M"), ("shirt", " m "), ("polo", "L"), ("tee", "M"),
                                          ("jeans", "32x32"), ("boots", "10.5"), ("hat", "M")]):
        add_item(conn, f"i{n}", category, size)
    add_item(conn, "old", "tee", "XL", status="archived")
    answer = sizes.current(conn)
    assert kind(answer, "tops")["suggested"] == "M" and kind(answer, "trousers")["suggested"] == "32x32"
    assert kind(answer, "shoes")["suggested"] == "10.5" and kind(answer, "knitwear")["suggested"] is None
    assert kind(answer, "tops")["size"] is None   # a suggestion is never used until it is saved
    assert sizes.saved(conn)["tops"]["size"] is None
    answer = sizes.set_size(conn, "tops", "  L ")
    assert kind(answer, "tops")["size"] == "L" and kind(answer, "tops")["suggested"] is None


def test_a_size_is_saved_changed_and_cleared(conn):
    sizes.set_size(conn, "trousers", "32x32")
    assert sizes.saved(conn)["trousers"]["size"] == "32x32"
    sizes.set_size(conn, "trousers", "33x32")
    assert sizes.saved(conn)["trousers"]["size"] == "33x32"
    for empty in ("", "   ", None):
        sizes.set_size(conn, "trousers", "33x32")
        assert sizes.set_size(conn, "trousers", empty) and sizes.saved(conn)["trousers"]["size"] is None


def test_a_brand_that_fits_differently(conn):
    sizes.set_size(conn, "tops", "M")
    sizes.set_brand(conn, "tops", "example brand", "L")
    answer = sizes.set_brand(conn, "tops", "Example Brand", "XL")   # the same brand, written again, takes the new spelling
    assert kind(answer, "tops")["brands"] == [{"brand": "Example Brand", "size": "XL"}]
    assert kind(answer, "tops")["size"] == "M"
    sizes.set_brand(conn, "tops", "Another Make", "S")
    assert [b["brand"] for b in sizes.saved(conn)["tops"]["brands"]] == ["Another Make", "Example Brand"]
    sizes.set_brand(conn, "tops", "EXAMPLE BRAND", "")
    assert [b["brand"] for b in sizes.saved(conn)["tops"]["brands"]] == ["Another Make"]
    assert sizes.saved(conn)["tops"]["size"] == "M"   # taking a brand off leaves the usual size


def test_what_is_refused(conn):
    with pytest.raises(ItemError, match="at most 20"):
        sizes.set_size(conn, "tops", "M" * 21)
    with pytest.raises(ItemError, match="as text"):
        sizes.set_size(conn, "tops", 12)
    with pytest.raises(ItemError, match="brand's name"):
        sizes.set_brand(conn, "tops", "  ", "L")
    with pytest.raises(ItemError) as e:
        sizes.set_size(conn, "hats", "M")
    assert e.value.status == 404
    for n in range(sizes.MAX_BRANDS):
        sizes.set_brand(conn, "shoes", f"Make {n}", "10")
    with pytest.raises(ItemError, match="at most 10 brands"):
        sizes.set_brand(conn, "shoes", "One More", "10")
    sizes.set_brand(conn, "shoes", "Make 3", "11")   # changing one already kept is fine


# ------------------------------------------------------------------ the endpoints
def test_the_sizes_endpoints(client):
    answer = client.get("/api/sizes").json()
    assert kind(answer, "tops")["size"] is None and answer["max_size"] == sizes.MAX_SIZE
    r = client.put("/api/sizes/tops", json={"size": "M"})
    assert r.status_code == 200 and kind(r.json(), "tops")["size"] == "M"
    r = client.put("/api/sizes/tops/brand", json={"brand": "Example Brand", "size": "L"})
    assert r.status_code == 200 and kind(r.json(), "tops")["brands"] == [{"brand": "Example Brand", "size": "L"}]
    assert kind(client.get("/api/settings").json()["sizes"], "tops")["size"] == "M"
    assert kind(client.put("/api/sizes/tops", json={"size": None}).json(), "tops")["size"] is None


def test_the_sizes_endpoints_refuse(client):
    r = client.put("/api/sizes/hats", json={"size": "M"})
    assert r.status_code == 404 and "tops, knitwear" in r.json()["detail"]
    r = client.put("/api/sizes/tops", json={"size": "M" * 21})
    assert r.status_code == 422 and "at most 20" in r.json()["detail"]
    assert client.put("/api/sizes/tops", json={"size": "M", "other": 1}).status_code == 422
    r = client.put("/api/sizes/tops/brand", json={"brand": "", "size": "L"})
    assert r.status_code == 422 and "brand's name" in r.json()["detail"]
