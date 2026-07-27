import json
from pathlib import Path

import pytest

from ddo_tracker.client import DDOAuthError, DDOLibraryClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_text(name):
    return (FIXTURES / name).read_text()


class FakeResponse:
    def __init__(self, payload, text=None):
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        pass


JS_SETTINGS_TEXT = (
    "Vfocus.Settings.uaUrl = Vfocus.Settings.url + "
    "'Rest.Server.cls?sessionId=URLTOKEN123&method=user/';\n"
    "Vfocus.Settings.sessionID = 'SIDTKN';\n"
)


class FakeSession:
    """Mimics requests.Session for the endpoints the client uses."""

    def __init__(self):
        self.headers = {}
        self.switch_calls = []
        self.active_user = None
        self.login_ok = True

    def get(self, url, timeout=None):
        if "jsSettings" in url:
            return FakeResponse(None, text=JS_SETTINGS_TEXT)
        return FakeResponse(None, text="<html></html>")

    def post(self, url, json=None, timeout=None):
        req = (json or {}).get("request", {})
        if "user/credentials" in url:
            if not self.login_ok:
                return FakeResponse({"response": {"error": {"message": "bad"}}})
            return FakeResponse({"response": {"sessionId": "BODYTOKEN"}})
        if "user/summary" in url:
            return FakeResponse(json_load("summary.json"))
        if "user/linkedaccounts" in url:
            return FakeResponse(json_load("linkedaccounts.json"))
        if "user/switchuser" in url:
            self.switch_calls.append(req.get("userId"))
            self.active_user = req.get("userId")
            return FakeResponse({"response": {"result": 1}})
        if "user/loans" in url:
            return FakeResponse(json_load("loans.json"))
        raise AssertionError(f"unexpected url {url}")


def json_load(name):
    return json.loads(load_text(name))


def make_client(session=None):
    return DDOLibraryClient(barcode="0000", pin="1234", session=session or FakeSession())


def test_login_success_sets_token():
    session = FakeSession()
    client = make_client(session)
    client.login()
    assert client._url_token == "URLTOKEN123"
    assert client._body_token == "BODYTOKEN"


def test_login_failure_raises():
    session = FakeSession()
    session.login_ok = False
    client = make_client(session)
    with pytest.raises(DDOAuthError):
        client.login()


def test_get_loans_parses_items():
    client = make_client()
    client.login()
    loans = client.get_loans()
    assert len(loans) == 4
    assert loans[0].title == "Judy Moody"


def test_fetch_all_accounts_reads_primary_and_linked():
    session = FakeSession()
    client = make_client(session)
    accounts = client.fetch_all_accounts(include_linked=True)

    # 1 primary + 3 linked from the fixture.
    assert len(accounts) == 4
    assert accounts[0].is_primary is True

    linked_ids = {"QMBDO.00000000000002", "QMBDO.00000000000003", "QMBDO.00000000000004"}
    # switchuser called for each linked account, then back to owner.
    assert linked_ids.issubset(set(session.switch_calls))
    assert session.switch_calls[-1] == "QMBDO.00000000000001"  # back to owner

    # Loans get their owning account stamped on them.
    for account in accounts[1:]:
        for loan in account.loans:
            assert loan.account_id == account.account_id
            assert loan.account_name == account.name


def test_fetch_all_accounts_without_linked():
    session = FakeSession()
    client = make_client(session)
    accounts = client.fetch_all_accounts(include_linked=False)
    assert len(accounts) == 1
    assert session.switch_calls == []
