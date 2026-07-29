"""A persistent, deduplicated catalog of books the family has borrowed.

This is pure, JSON-serialisable logic (no Home Assistant, no I/O) so it can be
unit-tested and persisted by whatever store the caller uses (the HA integration
saves it with Home Assistant's ``Store`` helper).

The catalog is keyed by a stable *book* id — not by loan instance — because a
book can be borrowed on any card for any person. Ratings are stored per person
(each family member can rate the same book differently), and ``assigned_to``
records who actually read it, independent of whose card borrowed it.

Shape::

    {
      "<book_id>": {
        "id": "...", "title": "...", "author": "...", "isbn": "...",
        "doc_type": "...", "first_seen": "2026-07-28", "last_seen": "...",
        "seen_count": 3, "cards": ["BARIL BENJAMIN"], "sources": ["loan"],
        "library_rating": 4 | None,
        "assigned_to": ["Noah"], "ratings": {"Noah": 5}
      },
      ...
    }
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

Catalog = dict[str, dict[str, Any]]


def book_id(title: str, author: str, isbn: str = "") -> str:
    """Stable id for a book: ISBN when we have one, else a title+author slug."""
    digits = "".join(ch for ch in (isbn or "") if ch.isdigit())
    if len(digits) in (10, 13):
        return f"isbn:{digits}"
    slug = _slug(title) + "|" + _slug(author)
    return f"ta:{slug}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _today() -> str:
    return date.today().isoformat()


def upsert(
    catalog: Catalog,
    *,
    title: str,
    author: str,
    isbn: str = "",
    doc_type: str = "",
    source: str = "loan",
    card_name: str = "",
    library_rating: Optional[int] = None,
) -> str:
    """Add or update a book from a loan/history record. Returns its id.

    Preserves user data (ratings, assignments) already attached to the book.
    """
    bid = book_id(title, author, isbn)
    entry = catalog.get(bid)
    if entry is None:
        entry = {
            "id": bid,
            "title": title,
            "author": author,
            "isbn": "".join(ch for ch in (isbn or "") if ch.isdigit()),
            "doc_type": doc_type,
            "first_seen": _today(),
            "last_seen": _today(),
            "seen_count": 0,
            "cards": [],
            "sources": [],
            "library_rating": library_rating,
            "assigned_to": [],
            "ratings": {},
        }
        catalog[bid] = entry

    entry["last_seen"] = _today()
    entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
    # Backfill better metadata if we learn it later.
    if not entry.get("isbn") and isbn:
        entry["isbn"] = "".join(ch for ch in isbn if ch.isdigit())
    if not entry.get("doc_type") and doc_type:
        entry["doc_type"] = doc_type
    if library_rating is not None:
        entry["library_rating"] = library_rating
    if card_name and card_name not in entry["cards"]:
        entry["cards"].append(card_name)
    if source and source not in entry["sources"]:
        entry["sources"].append(source)
    return bid


def set_rating(catalog: Catalog, bid: str, person: str, stars: Optional[int]) -> bool:
    """Set (1–5) or clear (None/0) a person's rating for a book.

    Returns False if the book id is unknown. Assigning a rating also marks the
    person as a reader of the book.
    """
    entry = catalog.get(bid)
    if entry is None:
        return False
    person = person.strip()
    if not stars:
        entry["ratings"].pop(person, None)
        return True
    stars = max(1, min(5, int(stars)))
    entry["ratings"][person] = stars
    if person and person not in entry["assigned_to"]:
        entry["assigned_to"].append(person)
    return True


def assign(catalog: Catalog, bid: str, person: str, assigned: bool = True) -> bool:
    """Mark (or unmark) a person as having read a book."""
    entry = catalog.get(bid)
    if entry is None:
        return False
    person = person.strip()
    if assigned:
        if person and person not in entry["assigned_to"]:
            entry["assigned_to"].append(person)
    else:
        if person in entry["assigned_to"]:
            entry["assigned_to"].remove(person)
        entry["ratings"].pop(person, None)
    return True


def people(catalog: Catalog) -> list[str]:
    """Every person seen in assignments or ratings, sorted."""
    names: set[str] = set()
    for entry in catalog.values():
        names.update(entry.get("assigned_to", []))
        names.update(entry.get("ratings", {}).keys())
    return sorted(names)


def to_list(catalog: Catalog) -> list[dict[str, Any]]:
    """Catalog entries as a list, most-recently-seen first."""
    return sorted(
        catalog.values(),
        key=lambda e: (e.get("last_seen", ""), e.get("title", "")),
        reverse=True,
    )


def average_rating(entry: dict[str, Any]) -> Optional[float]:
    ratings = entry.get("ratings", {})
    return round(sum(ratings.values()) / len(ratings), 1) if ratings else None
