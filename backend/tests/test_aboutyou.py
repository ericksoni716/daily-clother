"""What "Find some" tells Claude about the owner beside the wish (closet/aboutyou.py): their style lines, what they
love and wear in that kind of piece, the brands they wear and their size, bounded and in a stable order. Plain rows,
no app and no demo closet; the last test reads a tiny closet's database."""
from contextlib import closing

from closet import aboutyou, db, sizes, styleprofile
from closet.tagger import shopping

NO_SIZES = {k: {"size": None, "brands": []} for k in sizes.KIND_KEYS}


def item(id, category, color="navy", rating=None, brand=None, fit=None, material=None, kind=None, status="active",
         pattern="solid", name="My secret name", notes="a private note"):
    return {"id": id, "status": status, "category": category, "color": color, "pattern": pattern, "rating": rating,
            "brand": brand, "silhouette": {"fit": fit} if fit else {}, "material": material, "kind": kind,
            "name": name, "notes": notes, "created_at": "2026-01-01T00:00:00Z", "season": "all"}


def worn(item_id, n, start=1):
    return [{"item_id": item_id, "worn_on": f"2026-03-{d:02d}"} for d in range(start, start + n)]


# a closet with enough ratings to say something: three coats (two navy ones loved), two tees rated meh
COATS = [item("c1", "coat", "navy", "love", "Example Brand", "regular", "wool", kind="overcoat"),
         item("c2", "coat", "navy", "love", "Example Brand", "slim", "cotton gabardine", kind="trench_coat"),
         item("c3", "coat", "tan", "like", "Other Label"),
         item("t1", "tee", "white", "meh", "Third Make"), item("t2", "tee", "grey", "meh")]


def test_nothing_known_says_nothing_and_the_prompt_is_as_before():
    assert aboutyou.about([], [], [], NO_SIZES, "coat") == ""
    wish = {"name": "A coat", "note": "", "look_for": {"category": "coat"}}
    assert shopping.find_prompt({**wish, "about": ""}) == shopping.find_prompt(wish)
    assert "About the person" not in shopping.find_prompt(wish) and "what is said about the person" not in shopping.find_prompt(wish)


def test_the_block_says_style_taste_pieces_brands_and_size_for_the_wishs_kind():
    saved = {**NO_SIZES, "jackets": {"size": "40R", "brands": [{"brand": "Example Brand", "size": "42R"}]},
             "tops": {"size": "M", "brands": []}}
    text = aboutyou.about(COATS, worn("c1", 4), ["Quiet colours, nothing shiny.", "  I like   a long coat. "], saved, "coat")
    assert text.startswith("About the person this is for\nThese are leanings to rank the products by, not requirements")
    assert "Their style, in their own words:\n- Quiet colours, nothing shiny.\n- I like a long coat." in text
    assert "What they love and wear in coats:\n- Colours they favour: navy." in text
    # loved first, then the most worn; in the closet's words, never the name or the note
    assert ("Pieces they love or wear most:\n- overcoat: navy, regular fit, wool (loved, worn on 4 days)\n"
            "- trench coat: navy, slim fit, cotton gabardine (loved)") in text
    assert "My secret name" not in text and "private note" not in text and "tan" not in text
    assert "Brands they already wear (a hint, not a filter): Example Brand, Other Label, Third Make." in text
    # only the wish's kind's size, with its brand's own; tops are not said for a coat
    assert "Their size:\n- Jackets and coats: 40R; in Example Brand: 42R.\nWhen a shop lists sizes" in text
    assert "- Tops" not in text


def test_too_little_evidence_makes_no_claim_about_colours():
    rows = COATS[:2]   # two ratings: under taste's threshold
    text = aboutyou.about(rows, [], [], NO_SIZES, "coat")
    assert "favour" not in text
    assert "- overcoat: navy, regular fit, wool (loved)" in text   # a loved piece is still a piece they love


def test_a_wish_with_no_kind_looks_across_the_closet_and_says_every_saved_size():
    saved = {**NO_SIZES, "tops": {"size": "M", "brands": []}, "shoes": {"size": "10.5 US", "brands": []}}
    text = aboutyou.about(COATS + [item("b1", "belt", rating="love")], [], [], saved, None)
    assert "What they love and wear across their clothes:" in text
    assert "belt" not in text   # accessories are left out of an overall look
    assert "Their sizes:\n- Tops: M.\n- Shoes: 10.5 US." in text


def test_an_accessory_wish_gets_no_size():
    saved = {**NO_SIZES, "tops": {"size": "M", "brands": []}}
    assert "size" not in aboutyou.about([], [], [], saved, "belt").lower()


def test_brands_are_ordered_by_wears_and_ratings_spelt_as_most_items_and_capped():
    rows = [item(f"i{n}", "tee", rating=None, brand=f"Brand {n:02d}") for n in range(12)]
    rows += [item("x1", "tee", brand="example brand"), item("x2", "tee", brand="Example  Brand", rating="love"),
             item("x3", "tee", brand="Example Brand"), item("d1", "tee", brand="Hated Make", rating="dislike"),
             item("a1", "tee", brand="Gone Make", status="archived")]
    names = aboutyou.brand_names(rows, aboutyou._worn_days(worn("i5", 9)))
    assert names[:2] == ["Brand 05", "Example Brand"] and len(names) == aboutyou.BRANDS
    assert "Hated Make" not in names and "Gone Make" not in names


def test_the_block_is_bounded_and_stable_whatever_the_closets_size():
    rows = [item(f"i{n:03d}", "coat", rating="love", brand=f"Make {n}", material="m" * 200) for n in range(300)]
    wears = [w for n in range(300) for w in worn(f"i{n:03d}", 5)]
    saved = {k: {"size": "S" * 20, "brands": [{"brand": f"B{n}" * 10, "size": "L" * 20} for n in range(10)]}
             for k in sizes.KIND_KEYS}
    lines = ["a long line about how I dress " * 30] * 40
    text = aboutyou.about(rows, wears, lines, saved, None)
    assert len(text) < 4000
    assert text.count("\n- coat") == aboutyou.PIECES and text.count(" in B") == aboutyou.SIZE_BRANDS
    assert text == aboutyou.about(list(reversed(rows)), list(reversed(wears)), lines, saved, None)


def test_the_prompt_keeps_the_wish_first_and_the_block_apart():
    wish = {"name": "A rain-proof outer layer", "note": "", "price_max": 90.0, "price_currency": "GBP",
            "look_for": {"category": "coat"},
            "about": aboutyou.about(COATS, [], ["Quiet colours."], NO_SIZES, "coat")}
    text = shopping.find_prompt(wish)
    assert text.index("Wish: A rain-proof outer layer") < text.index("- price: at most 90 GBP") < text.index(aboutyou.HEADING)
    assert text.index(aboutyou.HEADING) < text.index("Search the web")
    assert "it never replaces the wish or its price range" in text


def test_for_search_reads_the_style_lines_and_the_saved_sizes_of_the_closet(cfg):
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        wish = {"name": "Boots", "look_for": {"category": "boots"}}
        assert aboutyou.for_search(conn, [], [], wish) == ""   # the starting profile says nothing about the owner
        styleprofile.add_line(conn, "Dark leather, never suede.")
        sizes.set_size(conn, "shoes", "10.5 US")
        text = aboutyou.for_search(conn, [], [], wish)
        assert "- Dark leather, never suede." in text and "- Shoes: 10.5 US." in text
        assert "umbrella" in text   # the starting line that stays once the owner writes one is theirs too


def test_a_search_is_not_told_of_clothes_for_home_swimming_or_a_sport_as_pieces_loved():
    # a search for trousers must not hear that tartan lounge pants are the trousers they love (gaps.everyday)
    rows = [item("l1", "trousers", "red", "love", pattern="plaid", kind="lounge_pants"),
            item("s1", "shorts", "orange", "love", kind="swim_trunks"),
            item("g1", "sneakers", "white", "love", kind="tennis_shoe"),
            item("c1", "trousers", "tan", "love", kind="chinos")]
    worn_ = worn("l1", 6) + worn("s1", 6) + worn("g1", 6)
    for category in ("trousers", "shorts", "sneakers", None):
        text = aboutyou.about(rows, worn_, [], NO_SIZES, category)
        assert "lounge" not in text and "swim" not in text and "tennis" not in text and "plaid" not in text
    assert "- chinos: tan (loved)" in aboutyou.about(rows, worn_, [], NO_SIZES, "trousers")
