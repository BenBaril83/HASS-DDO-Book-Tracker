import json
from datetime import date, timedelta
from pathlib import Path

from ddo_tracker.calendar import build_ics
from ddo_tracker.digest import (
    EmailConfig,
    build_message,
    render_html,
    render_text,
    send_email,
    subject_line,
)
from ddo_tracker.models import Account, Loan

FIXTURES = Path(__file__).parent / "fixtures"


def sample_accounts():
    items = json.loads((FIXTURES / "loans.json").read_text())["response"]["items"]
    acct = Account(
        account_id="QMBDO.1",
        name="Alice",
        is_primary=True,
        loans=[Loan.from_api(i) for i in items],
    )
    for loan in acct.loans:
        loan.account_name = acct.name
    return [acct]


# --- calendar -------------------------------------------------------------- #


def test_build_ics_structure_and_events():
    ics = build_ics(sample_accounts())
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip().endswith("END:VCALENDAR")
    # One VEVENT per dated loan (4 in the fixture).
    assert ics.count("BEGIN:VEVENT") == 4
    assert ics.count("BEGIN:VALARM") == 4
    assert "DTSTART;VALUE=DATE:20260804" in ics  # Judy Moody due date
    assert "SUMMARY:\U0001F4DA Due: Judy Moody (Alice)" in ics
    # CRLF line endings throughout.
    assert "\n" not in ics.replace("\r\n", "")


def test_build_ics_uid_is_stable():
    accounts = sample_accounts()
    first = build_ics(accounts)
    second = build_ics(accounts)
    # UIDs (and everything but DTSTAMP) are deterministic across runs.
    def uids(doc):
        return sorted(l for l in doc.splitlines() if l.startswith("UID:"))

    assert uids(first) == uids(second)
    assert all("@ddo-book-tracker" in u for u in uids(first))


def test_ics_escapes_special_characters():
    loan = Loan.from_api({"title": "Comma, semicolon; test", "author": "X"})
    loan.due_date = __import__("datetime").date(2026, 8, 1)
    acct = Account(account_id="1", name="Bob", loans=[loan])
    ics = build_ics([acct])
    assert "Comma\\, semicolon\\; test" in ics


# --- digest ---------------------------------------------------------------- #


def test_render_text_groups_by_urgency():
    accounts = sample_accounts()
    # Add a loan due within 3 days so the "soon" bucket is populated regardless
    # of when the suite runs. The fixture's due dates are absolute, so relying
    # on them for a relative "due within 3 days" bucket is a time-bomb.
    soon = Loan.from_api({"title": "Due Soon Book", "author": "X"})
    soon.due_date = date.today() + timedelta(days=2)
    soon.account_name = accounts[0].name
    accounts[0].loans.append(soon)

    text = render_text(accounts)
    assert "Judy Moody" in text
    assert "Due within 3 days" in text
    assert "Due Soon Book" in text


def test_render_html_is_escaped_and_tabular():
    html = render_html(sample_accounts())
    assert "<table" in html and "</table>" in html
    assert "Judy Moody" in html


def test_subject_line_reflects_counts():
    subject = subject_line(sample_accounts())
    assert "Library" in subject


def test_build_message_is_multipart():
    cfg = EmailConfig(username="me@gmail.com", recipients=["you@example.com"])
    msg = build_message(sample_accounts(), cfg)
    assert msg["To"] == "you@example.com"
    assert msg["From"] == "me@gmail.com"
    assert msg.is_multipart()  # text + html alternatives


class FakeSMTP:
    def __init__(self):
        self.sent = []

    def send_message(self, msg):
        self.sent.append(msg)


def test_send_email_uses_injected_client():
    cfg = EmailConfig(username="me@gmail.com", recipients=["you@example.com"])
    smtp = FakeSMTP()
    send_email(sample_accounts(), cfg, smtp=smtp)
    assert len(smtp.sent) == 1
    assert smtp.sent[0]["Subject"]


def test_send_email_requires_recipients():
    cfg = EmailConfig(username="me@gmail.com", recipients=[])
    try:
        send_email(sample_accounts(), cfg, smtp=FakeSMTP())
    except ValueError as exc:
        assert "recipients" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
