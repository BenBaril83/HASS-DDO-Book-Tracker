"""Data update coordinator for the DDO Library Book Tracker."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import DDOAuthError, DDOLibraryClient, DDOLibraryError
from .const import (
    CONF_BARCODE,
    CONF_INCLUDE_LINKED,
    CONF_INSTITUTION,
    CONF_PIN,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_INCLUDE_LINKED,
    DEFAULT_INSTITUTION,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from .models import Account
from .store import CatalogStore

_LOGGER = logging.getLogger(__name__)


class DDOCoordinator(DataUpdateCoordinator[list[Account]]):
    """Fetch loans for the configured account and its linked accounts."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        options = {**entry.data, **entry.options}
        hours = options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
        self._include_linked = options.get(
            CONF_INCLUDE_LINKED, DEFAULT_INCLUDE_LINKED
        )
        self._barcode = entry.data[CONF_BARCODE]
        self._pin = entry.data[CONF_PIN]
        self._institution = entry.data.get(CONF_INSTITUTION, DEFAULT_INSTITUTION)
        self.store = CatalogStore(hass, entry.entry_id)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=max(1, int(hours))),
        )

    def _fetch(self) -> list[Account]:
        """Blocking fetch — runs in the executor."""
        client = DDOLibraryClient(
            barcode=self._barcode,
            pin=self._pin,
            institution=self._institution,
        )
        client.login()
        return client.fetch_all_accounts(include_linked=self._include_linked)

    async def _async_update_data(self) -> list[Account]:
        try:
            accounts = await self.hass.async_add_executor_job(self._fetch)
        except DDOAuthError as err:
            # Surfaces as a reauth-worthy error / repair in HA.
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except DDOLibraryError as err:
            raise UpdateFailed(f"Error talking to the library: {err}") from err

        # Fold everything we saw into the persistent catalog (history + ratings
        # survive here even after a book is returned and drops off the API).
        await self.store.async_ingest(accounts)
        return accounts
