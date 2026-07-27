"""Client for the DDO (Dollard-des-Ormeaux) library OPAC.

The library runs Infor's *Iguana* web OPAC (``webopac.ddo.qc.ca``). There is
no public/documented API, so this client drives the same JSON REST endpoints
the website's JavaScript uses. The relevant calls, reverse-engineered from a
logged-in session, are:

    POST Rest.Server.cls?sessionId=<url-token>&method=user/credentials
        body: {"request": {"user", "password", "institution", ...}}
        -> authenticates the session, returns {"response": {"sessionId": ...}}

    POST ...&method=user/loans          body: {"request": {"sessionId": ...}}
    POST ...&method=user/summary        body: {"request": {"sessionId": ...}}
    POST ...&method=user/linkedaccounts body: {"request": {"sessionId": ...}}
    POST ...&method=user/switchuser     body: {"request": {"sessionId", "userId"}}

Two distinct session tokens are involved:
  * a *URL token* baked into ``Vfocus.Settings.uaUrl`` (query-string sessionId)
  * a *body token* returned as ``response.sessionId`` after login

Both are scraped from the initial page load / login response. Because this is
an undocumented surface it can change without notice; the parsing of loan data
(the part that matters) is covered by tests against real captured responses.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import requests

from .models import Account, Loan

BASE_URL = "https://webopac.ddo.qc.ca/iguana/"
MAIN_PAGE = BASE_URL + "www.main.cls?sUrl=UserActivities"
JS_SETTINGS = BASE_URL + "www.jsSettings.cls"
REST_SERVER = BASE_URL + "Rest.Server.cls"

DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class DDOLibraryError(Exception):
    """Raised when the library site returns an error or unexpected payload."""


class DDOAuthError(DDOLibraryError):
    """Raised specifically when login fails (bad barcode/PIN)."""


class DDOLibraryClient:
    """Log in to one DDO account and read its (and linked accounts') loans.

    Parameters
    ----------
    barcode:
        The library card barcode used as the login username.
    pin:
        The account PIN / password.
    institution:
        Iguana "meta institution" ident. DDO uses ``"QMBDO"``; the site also
        accepts an empty string, which is the default the web UI sends.
    """

    def __init__(
        self,
        barcode: str,
        pin: str,
        institution: str = "",
        session: Optional[requests.Session] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.barcode = barcode
        self.pin = pin
        self.institution = institution
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://webopac.ddo.qc.ca",
                "Referer": MAIN_PAGE,
            }
        )
        # Populated during bootstrap()/login().
        self._url_token: Optional[str] = None  # query-string sessionId
        self._body_token: Optional[str] = None  # response sessionId
        self._logged_in = False

    # ------------------------------------------------------------------ #
    # Session bootstrap + login
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """Establish the CSP session cookie and grab the URL session token."""
        # Loading the main page sets the CSPSESSIONID cookie.
        self.session.get(MAIN_PAGE, timeout=self.timeout)
        # jsSettings embeds Vfocus.Settings.uaUrl with the query sessionId.
        resp = self.session.get(JS_SETTINGS, timeout=self.timeout)
        self._url_token = self._extract_url_token(resp.text)
        if not self._url_token:
            raise DDOLibraryError(
                "Could not locate the REST session token in jsSettings; "
                "the site layout may have changed."
            )

    @staticmethod
    def _extract_url_token(js_text: str) -> Optional[str]:
        """Pull the sessionId query token out of the uaUrl JS assignment."""
        # Vfocus.Settings.uaUrl = <base> + 'Rest.Server.cls?sessionId=XXXX&method=user/';
        match = re.search(r"Rest\.Server\.cls\?sessionId=([^&'\"]+)&method=", js_text)
        return match.group(1) if match else None

    def _rest_url(self, method: str) -> str:
        if not self._url_token:
            raise DDOLibraryError("Client not bootstrapped; call login() first.")
        return f"{REST_SERVER}?sessionId={self._url_token}&method={method}"

    def _post(self, method: str, request_body: dict[str, Any]) -> dict[str, Any]:
        resp = self.session.post(
            self._rest_url(method),
            json={"request": request_body},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:  # pragma: no cover - network/format guard
            raise DDOLibraryError(
                f"Non-JSON response from {method}: {resp.text[:200]!r}"
            ) from exc
        response = payload.get("response", payload)
        if isinstance(response, dict) and response.get("error"):
            raise DDOLibraryError(f"{method} returned error: {response['error']}")
        return response

    def login(self) -> None:
        """Bootstrap the session then authenticate with barcode + PIN."""
        if self._url_token is None:
            self.bootstrap()
        try:
            response = self._post(
                "user/credentials",
                {
                    "language": "eng",
                    "serviceProfile": "",
                    "locationProfile": "",
                    "user": self.barcode,
                    "password": self.pin,
                    "institution": self.institution,
                },
            )
        except DDOLibraryError as exc:
            raise DDOAuthError(f"Login failed: {exc}") from exc
        token = response.get("sessionId")
        if not token:
            raise DDOAuthError(
                "Login did not return a session token; check the barcode/PIN."
            )
        self._body_token = token
        self._logged_in = True

    def _require_login(self) -> str:
        if not self._logged_in or not self._body_token:
            self.login()
        assert self._body_token is not None
        return self._body_token

    # ------------------------------------------------------------------ #
    # Data endpoints
    # ------------------------------------------------------------------ #
    def get_summary(self) -> dict[str, Any]:
        return self._post("user/summary", {"sessionId": self._require_login()})

    def get_linked_accounts(self) -> dict[str, Any]:
        return self._post(
            "user/linkedaccounts", {"sessionId": self._require_login()}
        )

    def get_loans(self) -> list[Loan]:
        """Return the loans for the *currently active* account."""
        response = self._post(
            "user/loans",
            {
                "sessionId": self._require_login(),
                "LocationProfile": "",
                "range": {"from": 1, "to": 200},
                "sort": {"sortBy": "!DueDate", "sortDirection": "DESC"},
            },
        )
        items = response.get("items", []) or []
        return [Loan.from_api(item) for item in items]

    def switch_user(self, user_id: str) -> None:
        """Switch the active borrower to a linked account by its id."""
        self._post(
            "user/switchuser",
            {"sessionId": self._require_login(), "userId": user_id},
        )

    # ------------------------------------------------------------------ #
    # High-level aggregation
    # ------------------------------------------------------------------ #
    def fetch_all_accounts(self, include_linked: bool = True) -> list[Account]:
        """Return the primary account plus every linked account with loans.

        Because DDO family cards are *linked*, one login can read all of them:
        we read the primary account's loans, then ``switchuser`` into each
        linked account and read those too, switching back to the owner at the
        end so the session is left in a known state.
        """
        self._require_login()
        linked = self.get_linked_accounts()
        own_id = linked.get("ownId", "")
        primary_name = self._primary_name(own_id)

        accounts: list[Account] = []

        primary = Account(account_id=own_id, name=primary_name, is_primary=True)
        primary.loans = self._loans_for(own_id, own_id)
        accounts.append(primary)

        if include_linked:
            for entry in linked.get("linkedAccounts", []) or []:
                acct_id = entry.get("id", "")
                name = entry.get("name") or entry.get("alias") or acct_id
                account = Account(account_id=acct_id, name=name)
                account.loans = self._loans_for(acct_id, own_id, name)
                accounts.append(account)
            # Leave the session pointing back at the owner.
            if own_id:
                self.switch_user(own_id)

        return accounts

    def _loans_for(
        self, account_id: str, own_id: str, name: str = ""
    ) -> list[Loan]:
        """Switch to ``account_id`` (unless it's the owner) and read loans."""
        if account_id and account_id != own_id:
            self.switch_user(account_id)
        loans = self.get_loans()
        for loan in loans:
            loan.account_id = account_id
            if name:
                loan.account_name = name
        return loans

    def _primary_name(self, own_id: str) -> str:
        try:
            summary = self.get_summary()
        except DDOLibraryError:
            return own_id
        return summary.get("alias") or own_id
