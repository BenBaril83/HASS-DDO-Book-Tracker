"""Build and (optionally) email a digest of what's on loan.

``render_text`` / ``render_html`` turn the accounts into a readable summary
grouped by urgency. ``send_email`` delivers it over SMTP — the defaults target
Gmail, which works with an *app password* (not your normal password; create one
at https://myaccount.google.com/apppasswords with 2-Step Verification on).
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from html import escape
from typing import Optional

from .models import Account, Loan
from .report import all_loans


@dataclass
class EmailConfig:
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    recipients: list[str] = None  # type: ignore[assignment]
    use_tls: bool = True  # STARTTLS on 587; set False + port 465 for SMTPS

    def __post_init__(self) -> None:
        if self.recipients is None:
            self.recipients = []
        if not self.sender:
            self.sender = self.username


def _when_label(loan: Loan) -> str:
    d = loan.days_until_due
    if d is None:
        return "no due date"
    if d < 0:
        return f"OVERDUE by {-d} day(s)"
    if d == 0:
        return "due TODAY"
    if d == 1:
        return "due tomorrow"
    return f"due in {d} days"


def _buckets(accounts: list[Account]) -> tuple[list[Loan], list[Loan], list[Loan]]:
    overdue, soon, later = [], [], []
    for loan in all_loans(accounts):
        d = loan.days_until_due
        if d is not None and d < 0:
            overdue.append(loan)
        elif d is not None and d <= 3:
            soon.append(loan)
        else:
            later.append(loan)
    return overdue, soon, later


def subject_line(accounts: list[Account]) -> str:
    overdue, soon, _ = _buckets(accounts)
    if overdue:
        return f"\U0001F4DA Library: {len(overdue)} overdue, {len(soon)} due soon"
    if soon:
        return f"\U0001F4DA Library: {len(soon)} book(s) due soon"
    total = sum(a.item_count for a in accounts)
    return f"\U0001F4DA Library: {total} book(s) on loan"


def render_text(accounts: list[Account]) -> str:
    overdue, soon, later = _buckets(accounts)
    lines = [subject_line(accounts), ""]

    def section(title: str, loans: list[Loan]) -> None:
        if not loans:
            return
        lines.append(f"{title}:")
        for loan in loans:
            who = f" [{loan.account_name}]" if loan.account_name else ""
            due = loan.due_date.isoformat() if loan.due_date else "?"
            lines.append(f"  • {loan.title}{who} — {_when_label(loan)} ({due})")
        lines.append("")

    section("⚠️  Overdue", overdue)
    section("Due within 3 days", soon)
    section("Later", later)
    if not (overdue or soon or later):
        lines.append("Nothing on loan. 🎉")
    lines.append(f"Generated {date.today().isoformat()}")
    return "\n".join(lines)


def render_html(accounts: list[Account]) -> str:
    overdue, soon, later = _buckets(accounts)

    def rows(loans: list[Loan], color: str) -> str:
        out = []
        for loan in loans:
            who = escape(loan.account_name or "")
            due = loan.due_date.isoformat() if loan.due_date else "?"
            out.append(
                f'<tr>'
                f'<td style="padding:4px 10px;color:{color};font-weight:600">'
                f"{escape(_when_label(loan))}</td>"
                f'<td style="padding:4px 10px">{escape(loan.title)}</td>'
                f'<td style="padding:4px 10px;color:#555">{escape(loan.author)}</td>'
                f'<td style="padding:4px 10px;color:#555">{who}</td>'
                f'<td style="padding:4px 10px;color:#555">{due}</td>'
                f"</tr>"
            )
        return "".join(out)

    body = []
    if overdue:
        body.append(rows(overdue, "#c0392b"))
    if soon:
        body.append(rows(soon, "#d35400"))
    if later:
        body.append(rows(later, "#2c3e50"))
    table_rows = "".join(body) or (
        '<tr><td style="padding:10px">Nothing on loan 🎉</td></tr>'
    )

    return (
        '<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px">'
        f"<h2 style=\"margin:0 0 12px\">{escape(subject_line(accounts))}</h2>"
        '<table style="border-collapse:collapse;width:100%;font-size:14px">'
        '<thead><tr style="text-align:left;border-bottom:1px solid #ddd">'
        '<th style="padding:4px 10px">When</th>'
        '<th style="padding:4px 10px">Title</th>'
        '<th style="padding:4px 10px">Author</th>'
        '<th style="padding:4px 10px">Who</th>'
        '<th style="padding:4px 10px">Due</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table>"
        f'<p style="color:#888;font-size:12px;margin-top:14px">'
        f"Generated {date.today().isoformat()}</p></div>"
    )


def build_message(accounts: list[Account], config: EmailConfig) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject_line(accounts)
    msg["From"] = config.sender
    msg["To"] = ", ".join(config.recipients)
    msg.set_content(render_text(accounts))
    msg.add_alternative(render_html(accounts), subtype="html")
    return msg


def send_email(
    accounts: list[Account],
    config: EmailConfig,
    smtp: Optional[smtplib.SMTP] = None,
) -> None:
    """Send the digest. Pass ``smtp`` to inject a client (used by tests)."""
    if not config.recipients:
        raise ValueError("No recipients configured for the email digest.")
    msg = build_message(accounts, config)

    if smtp is not None:
        smtp.send_message(msg)
        return

    if config.use_tls:
        with smtplib.SMTP(config.host, config.port) as client:
            client.starttls(context=ssl.create_default_context())
            if config.username:
                client.login(config.username, config.password)
            client.send_message(msg)
    else:
        with smtplib.SMTP_SSL(
            config.host, config.port, context=ssl.create_default_context()
        ) as client:
            if config.username:
                client.login(config.username, config.password)
            client.send_message(msg)
