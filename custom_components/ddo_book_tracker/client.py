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

import logging
import re
import time
from typing import Any, Optional

import requests

from .models import Account, Loan

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://webopac.ddo.qc.ca/iguana/"
MAIN_PAGE = BASE_URL + "www.main.cls?sUrl=UserActivities"
JS_SETTINGS = BASE_URL + "www.jsSettings.cls"
REST_SERVER = BASE_URL + "Rest.Server.cls"

# The site stamps this version into its asset/settings URLs.
JS_VERSION = "6.5.01.3"

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
        service_profile: str = "Iguana",
        session: Optional[requests.Session] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.barcode = barcode
        self.pin = pin
        self.institution = institution
        self.service_profile = service_profile
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
        self._sidtkn: Optional[str] = None  # session token from the landing page
        self._url_token: Optional[str] = None  # query-string sessionId
        self._body_token: Optional[str] = None  # response sessionId
        self._logged_in = False

    # ------------------------------------------------------------------ #
    # Session bootstrap + login
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """Establish the session and grab the URL session token.

        The landing page sets the CSPSESSIONID cookie and embeds the session
        token (``Vfocus.Settings.sessionID``) in its inline script. The REST
        token we need for API calls is only rendered by ``jsSettings`` when it
        is called with that SIDTKN (and the version/timestamp the site uses) —
        called bare it returns an empty body.
        """
        resp = self.session.get(MAIN_PAGE, timeout=self.timeout)
        self._sidtkn = self._extract_sidtkn(resp.text)
        if not self._sidtkn:
            raise DDOLibraryError(
                "Could not find the session token on the library landing page; "
                "the site may be unreachable or its layout changed."
            )
        params = {
            "t": int(time.time() * 1000),
            "version": JS_VERSION,
            "SIDTKN": self._sidtkn,
        }
        # jsSettings embeds Vfocus.Settings.uaUrl with the REST sessionId.
        resp = self.session.get(
            JS_SETTINGS,
            params=params,
            headers={"Referer": MAIN_PAGE},
            timeout=self.timeout,
        )
        self._url_token = self._extract_url_token(resp.text)
        if not self._url_token:
            raise DDOLibraryError(
                "Could not locate the REST session token in jsSettings; "
                "the site layout may have changed."
            )

    @staticmethod
    def _extract_sidtkn(html: str) -> Optional[str]:
        """Pull SIDTKN from the ``Vfocus.Settings.sessionID`` inline script."""
        match = re.search(r"Vfocus\.Settings\.sessionID\s*=\s*'([^']+)'", html)
        return match.group(1) if match else None

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
                    "serviceProfile": self.service_profile,
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
        linked account and read those too.

        Two robustness rules the web UI also follows:

        * **Always switch back to the owner between linked accounts.** The site
          only ever switches *from* the owner (it reloads to the owner view
          after each switch); switching straight from one linked view to
          another is what the server rejects with ``invalidUserId``.
        * **Never let one unreadable linked account fail the whole fetch.** A
          card you don't have permission to view is skipped with a warning, so
          the primary account (and any readable linked accounts) still load.
        """
        self._require_login()
        linked = self.get_linked_accounts()
        own_id = linked.get("ownId", "")
        primary_name = self._primary_name(own_id)

        accounts: list[Account] = []

        primary = Account(account_id=own_id, name=primary_name, is_primary=True)
        primary.loans = self._read_current_loans(own_id, primary_name)
        accounts.append(primary)

        if include_linked:
            for entry in linked.get("linkedAccounts", []) or []:
                acct_id = entry.get("id", "")
                name = entry.get("name") or entry.get("alias") or acct_id
                account = self._read_linked_account(acct_id, name, own_id)
                if account is not None:
                    accounts.append(account)

        return accounts

    def _read_linked_account(
        self, account_id: str, name: str, own_id: str
    ) -> Optional[Account]:
        """Switch into a linked account and read its loans; ``None`` on failure.

        Always switches back to the owner afterwards so the next switch starts
        from a clean owner context.
        """
        try:
            self.switch_user(account_id)
            account = Account(account_id=account_id, name=name)
            account.loans = self._read_current_loans(account_id, name)
            return account
        except DDOLibraryError as err:
            _LOGGER.warning(
                "Skipping linked account %s (%s): %s", name, account_id, err
            )
            return None
        finally:
            if own_id:
                try:
                    self.switch_user(own_id)
                except DDOLibraryError as err:  # pragma: no cover - best effort
                    _LOGGER.warning("Could not switch back to owner: %s", err)

    def _read_current_loans(self, account_id: str, name: str) -> list[Loan]:
        """Read loans for the active account and stamp ownership on them."""
        loans = self.get_loans()
        for loan in loans:
            loan.account_id = account_id
            loan.account_name = name
        return loans

    def _primary_name(self, own_id: str) -> str:
        try:
            summary = self.get_summary()
        except DDOLibraryError:
            return own_id
        return summary.get("alias") or own_id
