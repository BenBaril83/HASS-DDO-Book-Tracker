"""Data models for the DDO library book tracker.

These dataclasses wrap the raw JSON returned by the DDO (Dollard-des-Ormeaux)
Iguana OPAC REST API and add the small amount of derived information the
tracker actually cares about: clean due dates and "how many days left".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


def parse_api_date(value: str) -> Optional[date]:
    """Parse the API's compact date formats into a ``date``.

    The API uses ``YYYYMMDD`` for due dates and ``YYYYMMDDHHMMSS`` for loan
    timestamps. Returns ``None`` for empty/unparseable values rather than
    raising, so one odd record can't break a whole account's report.
    """
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    for length, fmt in ((14, "%Y%m%d%H%M%S"), (8, "%Y%m%d")):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], fmt).date()
            except ValueError:
                continue
    return None


@dataclass
class Loan:
    """A single item currently checked out."""

    title: str
    author: str
    due_date: Optional[date]
    loan_date: Optional[date]
    barcode: str = ""
    doc_type: str = ""
    renewals_used: int = 0
    renewable: bool = True
    fine: float = 0.0
    isbn: str = ""
    # Owning account, filled in by the client when aggregating.
    account_id: str = ""
    account_name: str = ""

    @property
    def days_until_due(self) -> Optional[int]:
        """Whole days from today until the due date (negative = overdue)."""
        if self.due_date is None:
            return None
        return (self.due_date - date.today()).days

    @property
    def is_overdue(self) -> bool:
        d = self.days_until_due
        return d is not None and d < 0

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "Loan":
        return cls(
            title=_clean_title(item.get("title", "")),
            author=_clean_author(item.get("author", "")),
            due_date=parse_api_date(item.get("dueDate", "")),
            loan_date=parse_api_date(item.get("loanDate", "")),
            barcode=str(item.get("barcode", "")),
            doc_type=item.get("docType", ""),
            renewals_used=int(item.get("renewalCounter", 0) or 0),
            renewable=bool(item.get("renewal", 0)),
            fine=float(item.get("fine", 0) or 0),
            isbn=_extract_isbn(item.get("image", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation (used by the HA/json output)."""
        return {
            "title": self.title,
            "author": self.author,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "loan_date": self.loan_date.isoformat() if self.loan_date else None,
            "days_until_due": self.days_until_due,
            "is_overdue": self.is_overdue,
            "barcode": self.barcode,
            "doc_type": self.doc_type,
            "renewals_used": self.renewals_used,
            "renewable": self.renewable,
            "fine": self.fine,
            "isbn": self.isbn,
            "account_id": self.account_id,
            "account_name": self.account_name,
        }


@dataclass
class Reservation:
    """A hold/reservation the borrower has placed on an item."""

    title: str
    author: str
    queue_position: int = 0
    is_ready: bool = False  # waiting on the hold shelf for pickup
    available_until: Optional[date] = None  # pick up by this date
    pickup_location: str = ""
    reserved_since: Optional[date] = None
    expiry_date: Optional[date] = None
    barcode: str = ""
    doc_type: str = ""
    isbn: str = ""
    account_id: str = ""
    account_name: str = ""

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "Reservation":
        available_until = parse_api_date(item.get("availableUntil", ""))
        pickup = item.get("pickupLocation") or ""
        if not pickup:
            locations = item.get("pickupLocations") or []
            if isinstance(locations, list) and locations:
                first = locations[0]
                pickup = first.get("name", "") if isinstance(first, dict) else str(first)
        return cls(
            title=_clean_title(item.get("title", "")),
            author=_clean_author(item.get("author", "")),
            queue_position=int(item.get("queuePosition", 0) or 0),
            is_ready=available_until is not None,
            available_until=available_until,
            pickup_location=pickup,
            reserved_since=parse_api_date(item.get("reservedSince", "")),
            expiry_date=parse_api_date(item.get("expiryDate", "")),
            barcode=str(item.get("barcode", "")),
            doc_type=item.get("docType", ""),
            isbn=_extract_isbn(item.get("image", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "queue_position": self.queue_position,
            "is_ready": self.is_ready,
            "available_until": self.available_until.isoformat()
            if self.available_until
            else None,
            "pickup_location": self.pickup_location,
            "reserved_since": self.reserved_since.isoformat()
            if self.reserved_since
            else None,
            "isbn": self.isbn,
            "doc_type": self.doc_type,
            "account_id": self.account_id,
            "account_name": self.account_name,
        }


@dataclass
class HistoryItem:
    """A previously-borrowed item from the library's loan history.

    Only populated for accounts where the borrower enabled loan-history
    retention in the library; otherwise the library returns nothing.
    """

    title: str
    author: str
    loan_date: Optional[date] = None
    isbn: str = ""
    doc_type: str = ""
    library_rating: Optional[int] = None
    account_id: str = ""
    account_name: str = ""

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> "HistoryItem":
        rating_raw = str(item.get("rating", "") or "").strip()
        return cls(
            title=_clean_title(item.get("title", "")),
            author=_clean_author(item.get("author", "")),
            loan_date=parse_api_date(item.get("loanDate", "")),
            isbn=_extract_isbn(item.get("image", "")),
            doc_type=item.get("docType", ""),
            library_rating=int(rating_raw) if rating_raw.isdigit() else None,
        )


@dataclass
class Account:
    """A borrower account, its current loans, reservations and history."""

    account_id: str
    name: str
    loans: list[Loan] = field(default_factory=list)
    reservations: list[Reservation] = field(default_factory=list)
    history: list[HistoryItem] = field(default_factory=list)
    is_primary: bool = False

    @property
    def item_count(self) -> int:
        return len(self.loans)

    @property
    def reservations_ready(self) -> int:
        return sum(1 for r in self.reservations if r.is_ready)

    @property
    def next_due_date(self) -> Optional[date]:
        dates = [loan.due_date for loan in self.loans if loan.due_date]
        return min(dates) if dates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "name": self.name,
            "is_primary": self.is_primary,
            "item_count": self.item_count,
            "next_due_date": self.next_due_date.isoformat()
            if self.next_due_date
            else None,
            "loans": [loan.to_dict() for loan in self.loans],
            "reservation_count": len(self.reservations),
            "reservations_ready": self.reservations_ready,
            "reservations": [r.to_dict() for r in self.reservations],
        }


def _clean_title(title: str) -> str:
    """Trim the trailing sub-title/punctuation cruft the catalog adds."""
    return title.strip().rstrip("/:.").strip()


def _clean_author(author: str) -> str:
    """Reduce catalog author strings to just the name.

    Examples::

        "McDonald, Megan."                       -> "McDonald, Megan"
        "Green, John Patrick,1975- author,"      -> "Green, John Patrick,1975"
        "Warner, Gertrude Chandler,1890-1979, author." -> "Warner, Gertrude Chandler,1890-1979"
    """
    author = author.strip()
    # Cut the trailing "author"/"auteur" role marker (preceded by , - or space).
    author = re.split(r"[,\-\s]+(?:author|auteur)\b", author, maxsplit=1)[0]
    return author.strip().rstrip(",.-").strip()


def _extract_isbn(image_field: str) -> str:
    """Pull the ISBN/EAN out of the syndetics cover-image URL blob."""
    if not image_field:
        return ""
    for token in ("isbn=", "ean="):
        idx = image_field.find(token)
        if idx != -1:
            start = idx + len(token)
            end = start
            while end < len(image_field) and image_field[end].isalnum():
                end += 1
            candidate = image_field[start:end]
            if candidate:
                return candidate
    return ""
