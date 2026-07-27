"""Turn a set of accounts into human- and machine-readable reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from .models import Account, Loan


def all_loans(accounts: list[Account]) -> list[Loan]:
    """Every loan across every account, sorted by due date (soonest first)."""
    loans = [loan for account in accounts for loan in account.loans]
    loans.sort(key=lambda ln: (ln.due_date or date.max, ln.account_name, ln.title))
    return loans


def build_summary(accounts: list[Account]) -> dict[str, Any]:
    """Machine-readable summary suitable for Home Assistant / JSON output."""
    loans = all_loans(accounts)
    overdue = [ln for ln in loans if ln.is_overdue]
    due_soon = [
        ln
        for ln in loans
        if ln.days_until_due is not None and 0 <= ln.days_until_due <= 3
    ]
    next_due = next((ln.due_date for ln in loans if ln.due_date), None)
    return {
        "generated_at": date.today().isoformat(),
        "total_items": len(loans),
        "overdue_count": len(overdue),
        "due_soon_count": len(due_soon),
        "next_due_date": next_due.isoformat() if next_due else None,
        "accounts": [account.to_dict() for account in accounts],
        "items": [loan.to_dict() for loan in loans],
    }


def format_table(accounts: list[Account]) -> str:
    """Pretty, aligned text table of all books, sorted by due date."""
    loans = all_loans(accounts)
    if not loans:
        return "No books currently on loan across all accounts. 🎉"

    rows = []
    for loan in loans:
        due = loan.due_date.isoformat() if loan.due_date else "?"
        days = loan.days_until_due
        if days is None:
            when = ""
        elif days < 0:
            when = f"OVERDUE {-days}d"
        elif days == 0:
            when = "due TODAY"
        else:
            when = f"in {days}d"
        rows.append(
            (
                loan.account_name or "-",
                _truncate(loan.title, 45),
                _truncate(loan.author, 25),
                due,
                when,
            )
        )

    headers = ("Account", "Title", "Author", "Due", "When")
    widths = [
        max(len(headers[i]), max(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    def fmt(cols: tuple[str, ...]) -> str:
        return "  ".join(col.ljust(widths[i]) for i, col in enumerate(cols))

    lines = [fmt(headers), fmt(tuple("-" * w for w in widths))]
    lines.extend(fmt(row) for row in rows)

    summary = build_summary(accounts)
    footer = (
        f"\n{summary['total_items']} item(s) across {len(accounts)} account(s)"
        f" · {summary['overdue_count']} overdue"
        f" · {summary['due_soon_count']} due within 3 days"
    )
    return "\n".join(lines) + "\n" + footer


def _truncate(text: str, length: int) -> str:
    text = text or ""
    return text if len(text) <= length else text[: length - 1] + "…"
