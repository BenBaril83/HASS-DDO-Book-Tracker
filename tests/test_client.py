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
        self.credentials_body = None
        self.invalid_switch_ids = set()

    def get(self, url, timeout=None, params=None, headers=None):
        if "jsSettings" in url:
            # Real bootstrap requires the SIDTKN param; assert it's passed.
            assert params and params.get("SIDTKN") == "SID123"
            return FakeResponse(None, text=JS_SETTINGS_TEXT)
        # Landing page embeds the session token inline.
        return FakeResponse(
            None, text="<script>Vfocus.Settings.sessionID = 'SID123';</script>"
        )

    def post(self, url, json=None, timeout=None):
        req = (json or {}).get("request", {})
        if "user/credentials" in url:
            self.credentials_body = req
            if not self.login_ok:
                return FakeResponse({"response": {"error": {"message": "bad"}}})
            return FakeResponse({"response": {"sessionId": "BODYTOKEN"}})
        if "user/summary" in url:
            return FakeResponse(json_load("summary.json"))
        if "user/linkedaccounts" in url:
            return FakeResponse(json_load("linkedaccounts.json"))
        if "user/switchuser" in url:
            uid = req.get("userId")
            self.switch_calls.append(uid)
            if uid in self.invalid_switch_ids:
                return FakeResponse(
                    {"response": {"error": {"message": "invalidUserId"}}}
                )
            self.active_user = uid
            return FakeResponse({"response": {"result": 1}})
        if "user/loans" in url:
            return FakeResponse(json_load("loans.json"))
        if "user/reservations" in url:
            return FakeResponse(json_load("reservations.json"))
        if "user/loanhistory" in url:
            return FakeResponse(json_load("loanhistory.json"))
        raise AssertionError(f"unexpected url {url}")


def json_load(name):
    return json.loads(load_text(name))


def make_client(session=None):
    return DDOLibraryClient(barcode="0000", pin="1234", session=session or FakeSession())


def test_extract_sidtkn():
    from ddo_tracker.client import DDOLibraryClient as C

    assert C._extract_sidtkn("x Vfocus.Settings.sessionID = 'ABC123'; y") == "ABC123"
    assert C._extract_sidtkn("no token here") is None


def test_login_success_sets_token():
    session = FakeSession()
    client = make_client(session)
    client.login()
    assert client._sidtkn == "SID123"
    assert client._url_token == "URLTOKEN123"
    assert client._body_token == "BODYTOKEN"


def test_login_sends_verified_payload():
    # Field set + values confirmed against a captured login request.
    session = FakeSession()
    client = DDOLibraryClient(barcode="00006002413000", pin="secret", session=session)
    client.login()
    body = session.credentials_body
    assert body == {
        "language": "eng",
        "serviceProfile": "Iguana",
        "locationProfile": "",
        "user": "00006002413000",
        "password": "secret",
        "institution": "",
    }


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


def test_get_loan_history_parses_items():
    client = make_client()
    client.login()
    history = client.get_loan_history()
    assert len(history) == 2
    assert history[0].title == "Frog and Toad Are Friends"
    assert history[0].isbn == "9780064440202"
    assert history[0].library_rating == 4
    assert history[1].library_rating is None  # empty rating -> None


def test_get_reservations_parses_items():
    client = make_client()
    client.login()
    res = client.get_reservations()
    assert len(res) == 2

    ready = [r for r in res if r.is_ready]
    assert len(ready) == 1
    assert ready[0].title == "Dog Man"
    assert ready[0].isbn == "9781338741063"
    assert ready[0].pickup_location == "DOLLARD-DES-ORMEAUX"
    assert ready[0].available_until is not None

    queued = [r for r in res if not r.is_ready]
    assert queued[0].queue_position == 3
    # pickup_location falls back to the pickupLocations list entry
    assert queued[0].pickup_location == "DOLLARD-DES-ORMEAUX"


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

    # Loans and reservations get their owning account stamped on them.
    for account in accounts[1:]:
        for loan in account.loans:
            assert loan.account_id == account.account_id
            assert loan.account_name == account.name
        assert len(account.reservations) == 2
        for res in account.reservations:
            assert res.account_id == account.account_id
            assert res.account_name == account.name


def test_fetch_all_accounts_returns_to_owner_between_switches():
    session = FakeSession()
    client = make_client(session)
    client.fetch_all_accounts(include_linked=True)
    owner = "QMBDO.00000000000001"
    # Every linked switch is immediately followed by a switch back to owner.
    linked_switches = [uid for uid in session.switch_calls if uid != owner]
    assert len(linked_switches) == 3
    # owner switch-backs equal the number of linked accounts visited.
    assert session.switch_calls.count(owner) == 3
    # Pattern is linked, owner, linked, owner, ...
    assert session.switch_calls[1::2] == [owner, owner, owner]


def test_fetch_all_accounts_skips_unreadable_linked():
    session = FakeSession()
    # First linked account can't be switched into (invalidUserId).
    session.invalid_switch_ids = {"QMBDO.00000000000002"}
    client = make_client(session)
    accounts = client.fetch_all_accounts(include_linked=True)

    # Primary + the two readable linked accounts (the bad one is skipped).
    ids = [a.account_id for a in accounts]
    assert "QMBDO.00000000000002" not in ids
    assert len(accounts) == 3
    assert accounts[0].is_primary is True
    # We still returned to the owner after the failed switch.
    assert session.switch_calls[-1] == "QMBDO.00000000000001"


def test_fetch_all_accounts_without_linked():
    session = FakeSession()
    client = make_client(session)
    accounts = client.fetch_all_accounts(include_linked=False)
    assert len(accounts) == 1
    assert session.switch_calls == []
