"""Generate an iCalendar (.ics) feed of book due dates.

This is the credential-free path into Google Calendar (and Apple/Outlook):
write the .ics somewhere your calendar app can reach it, then *subscribe* to
it. Each book becomes an all-day event on its due date with a reminder the day
before. Events use a stable UID (account + item barcode), so regenerating the
feed updates existing events instead of creating duplicates — returned books
simply drop out on the next refresh.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .models import Account
from .report import all_loans

# RFC 5545 wants CRLF line endings.
_CRLF = "\r\n"


def _escape(text: str) -> str:
    """Escape a value for an iCalendar text field (RFC 5545 §3.3.11)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets, per RFC 5545 §3.1."""
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    rest = line[75:]
    while rest:
        chunks.append(" " + rest[:74])
        rest = rest[74:]
    return _CRLF.join(chunks)


def _uid(account_id: str, barcode: str, due: date) -> str:
    key = barcode or f"{due.isoformat()}"
    return f"ddo-{account_id or 'x'}-{key}@ddo-book-tracker"


def build_ics(
    accounts: list[Account],
    reminder_days_before: int = 1,
    calendar_name: str = "DDO Library due dates",
) -> str:
    """Return an iCalendar document covering every dated loan."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ddo-book-tracker//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]

    for loan in all_loans(accounts):
        if loan.due_date is None:
            continue
        start = loan.due_date
        end = start + timedelta(days=1)  # all-day event: DTEND is exclusive
        who = f" ({loan.account_name})" if loan.account_name else ""
        summary = f"\U0001F4DA Due: {loan.title}{who}"
        desc_parts = [p for p in (loan.author, f"Barcode {loan.barcode}") if p]
        description = " — ".join(desc_parts)

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{_uid(loan.account_id, loan.barcode, start)}")
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}")
        lines.append(f"SUMMARY:{_escape(summary)}")
        if description:
            lines.append(f"DESCRIPTION:{_escape(description)}")
        lines.append("TRANSP:TRANSPARENT")
        if reminder_days_before is not None and reminder_days_before >= 0:
            lines.append("BEGIN:VALARM")
            lines.append("ACTION:DISPLAY")
            lines.append(f"DESCRIPTION:{_escape(summary)}")
            # Fire at 09:00 the configured number of days before the due date.
            hours = reminder_days_before * 24 - 9
            lines.append(f"TRIGGER:-PT{hours}H")
            lines.append("END:VALARM")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return _CRLF.join(_fold(line) for line in lines) + _CRLF
