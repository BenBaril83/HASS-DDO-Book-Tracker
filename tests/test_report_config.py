import json
from datetime import date
from pathlib import Path

import pytest

from ddo_tracker.config import ConfigError, load_config
from ddo_tracker.models import Account, Loan
from ddo_tracker.report import all_loans, build_summary, format_table

FIXTURES = Path(__file__).parent / "fixtures"


def sample_accounts():
    items = json.loads((FIXTURES / "loans.json").read_text())["response"]["items"]
    a = Account(
        account_id="A",
        name="Alice",
        is_primary=True,
        loans=[Loan.from_api(i) for i in items[:2]],
    )
    b = Account(
        account_id="B",
        name="Bob",
        loans=[Loan.from_api(i) for i in items[2:]],
    )
    for acct in (a, b):
        for loan in acct.loans:
            loan.account_name = acct.name
    return [a, b]


def test_all_loans_sorted_by_due_date():
    loans = all_loans(sample_accounts())
    dues = [ln.due_date for ln in loans if ln.due_date]
    assert dues == sorted(dues)


def test_build_summary_shape():
    summary = build_summary(sample_accounts())
    assert summary["total_items"] == 4
    assert len(summary["accounts"]) == 2
    assert len(summary["items"]) == 4
    assert "next_due_date" in summary
    # Every item carries a due date from the fixture.
    assert summary["next_due_date"] == "2026-07-30"


def test_format_table_contains_titles_and_footer():
    text = format_table(sample_accounts())
    assert "Judy Moody" in text
    assert "Account" in text and "Due" in text
    assert "item(s) across 2 account(s)" in text


def test_format_table_empty():
    assert "No books" in format_table([])


def test_load_config_from_yaml(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "accounts:\n"
        "  - barcode: '111'\n"
        "    pin: '222'\n"
        "    include_linked: false\n"
    )
    config = load_config(str(cfg))
    assert len(config.accounts) == 1
    assert config.accounts[0].barcode == "111"
    assert config.accounts[0].include_linked is False


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray config.yaml
    monkeypatch.delenv("DDO_CONFIG", raising=False)
    monkeypatch.setenv("DDO_BARCODE", "abc")
    monkeypatch.setenv("DDO_PIN", "xyz")
    config = load_config()
    assert config.accounts[0].barcode == "abc"


def test_load_config_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DDO_CONFIG", raising=False)
    monkeypatch.delenv("DDO_BARCODE", raising=False)
    monkeypatch.delenv("DDO_PIN", raising=False)
    with pytest.raises(ConfigError):
        load_config()
