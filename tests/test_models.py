import json
from datetime import date
from pathlib import Path

from ddo_tracker.models import Account, Loan, parse_api_date

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_api_date_formats():
    assert parse_api_date("20260804") == date(2026, 8, 4)
    assert parse_api_date("20260714163640") == date(2026, 7, 14)
    assert parse_api_date("") is None
    assert parse_api_date("garbage") is None


def test_loan_from_api_real_payload():
    items = load("loans.json")["response"]["items"]
    loans = [Loan.from_api(i) for i in items]
    assert len(loans) == 4

    first = loans[0]
    assert first.title == "Judy Moody"
    assert first.author == "McDonald, Megan"
    assert first.due_date == date(2026, 8, 4)
    assert first.loan_date == date(2026, 7, 14)
    assert first.isbn == "9780763606855"
    assert first.doc_type == "Juvenile - Fiction"
    assert first.renewable is True


def test_author_cleanup_drops_role_and_dates():
    loan = Loan.from_api(
        {"title": "Take the plunge /", "author": "Green, John Patrick,1975- author,"}
    )
    assert loan.title == "Take the plunge"
    assert loan.author == "Green, John Patrick,1975"  # date kept, role/comma trimmed


def test_days_until_due_and_overdue(monkeypatch):
    loan = Loan(title="x", author="y", due_date=date(2026, 8, 4), loan_date=None)
    # Freeze "today" via a tiny shim on the model's date usage.
    import ddo_tracker.models as models

    class _Frozen(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 1)

    monkeypatch.setattr(models, "date", _Frozen)
    assert loan.days_until_due == 3
    assert loan.is_overdue is False

    overdue = Loan(title="x", author="y", due_date=date(2026, 7, 30), loan_date=None)
    assert overdue.days_until_due == -2
    assert overdue.is_overdue is True


def test_account_aggregates():
    items = load("loans.json")["response"]["items"]
    loans = [Loan.from_api(i) for i in items]
    account = Account(account_id="QMBDO.1", name="DOE JOHN", loans=loans, is_primary=True)
    assert account.item_count == 4
    assert account.next_due_date == date(2026, 7, 30)
    d = account.to_dict()
    assert d["item_count"] == 4
    assert len(d["loans"]) == 4
