from ddo_tracker import catalog


def test_book_id_prefers_isbn():
    assert catalog.book_id("Judy Moody", "McDonald", "9780763606855") == "isbn:9780763606855"
    # non-ISBN falls back to a title+author slug (stable, case/space-insensitive)
    a = catalog.book_id("Judy Moody!", "McDonald, Megan", "")
    b = catalog.book_id("judy  moody", "mcdonald megan", "")
    assert a == b and a.startswith("ta:")


def test_upsert_dedupes_and_accumulates_cards():
    cat = {}
    bid1 = catalog.upsert(cat, title="Judy Moody", author="McDonald", isbn="9780763606855", card_name="BENJAMIN")
    bid2 = catalog.upsert(cat, title="Judy Moody", author="McDonald", isbn="9780763606855", card_name="NOAH")
    assert bid1 == bid2
    assert len(cat) == 1
    entry = cat[bid1]
    assert entry["seen_count"] == 2
    assert entry["cards"] == ["BENJAMIN", "NOAH"]


def test_upsert_backfills_isbn_from_later_record():
    cat = {}
    bid_noisbn = catalog.upsert(cat, title="Some Book", author="Anon")
    assert bid_noisbn.startswith("ta:")
    # A later record with an ISBN is a *different* id, but metadata backfill
    # applies within the same id.
    catalog.upsert(cat, title="Some Book", author="Anon", doc_type="Fiction")
    assert cat[bid_noisbn]["doc_type"] == "Fiction"


def test_ratings_and_assignment():
    cat = {}
    bid = catalog.upsert(cat, title="Dog Man", author="Pilkey", isbn="9781338741063")

    assert catalog.set_rating(cat, bid, "Noah", 5) is True
    assert cat[bid]["ratings"] == {"Noah": 5}
    # rating implies the person read it
    assert "Noah" in cat[bid]["assigned_to"]

    # clamp + a second person's independent rating
    catalog.set_rating(cat, bid, "Joshua", 9)
    assert cat[bid]["ratings"]["Joshua"] == 5
    assert catalog.average_rating(cat[bid]) == 5.0

    # clearing removes the rating but not necessarily the assignment
    catalog.set_rating(cat, bid, "Noah", 0)
    assert "Noah" not in cat[bid]["ratings"]

    assert catalog.people(cat) == ["Joshua", "Noah"]

    # unassign also drops that person's rating
    catalog.assign(cat, bid, "Joshua", assigned=False)
    assert "Joshua" not in cat[bid]["assigned_to"]
    assert "Joshua" not in cat[bid]["ratings"]


def test_set_rating_unknown_book_returns_false():
    assert catalog.set_rating({}, "isbn:0", "Noah", 5) is False


def test_to_list_newest_first():
    cat = {}
    a = catalog.upsert(cat, title="A", author="x")
    b = catalog.upsert(cat, title="B", author="y")
    cat[a]["last_seen"] = "2026-07-01"
    cat[b]["last_seen"] = "2026-07-20"
    ordered = [e["id"] for e in catalog.to_list(cat)]
    assert ordered[0] == b
