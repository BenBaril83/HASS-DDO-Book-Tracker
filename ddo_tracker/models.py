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
class Account:
    """A borrower account and the items it currently has on loan."""

    account_id: str
    name: str
    loans: list[Loan] = field(default_factory=list)
    is_primary: bool = False

    @property
    def item_count(self) -> int:
        return len(self.loans)

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
