"""The DDO Library Book Tracker integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import DDOCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Plain alias (not a PEP 695 `type` statement) so the module also parses on
# Python 3.11 CI runners; the runtime target is HA's 3.12+.
DDOConfigEntry = ConfigEntry

SERVICE_RATE_BOOK = "rate_book"
SERVICE_ASSIGN_BOOK = "assign_book"

RATE_SCHEMA = vol.Schema(
    {
        vol.Required("book_id"): cv.string,
        vol.Required("person"): cv.string,
        vol.Optional("rating"): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
    }
)
ASSIGN_SCHEMA = vol.Schema(
    {
        vol.Required("book_id"): cv.string,
        vol.Required("person"): cv.string,
        vol.Optional("assigned", default=True): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> bool:
    """Set up DDO Library Book Tracker from a config entry."""
    coordinator = DDOCoordinator(hass, entry)
    await coordinator.store.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not hass.config_entries.async_loaded_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_RATE_BOOK)
        hass.services.async_remove(DOMAIN, SERVICE_ASSIGN_BOOK)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> None:
    """Reload when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the rate/assign services once (shared across config entries)."""
    if hass.services.has_service(DOMAIN, SERVICE_RATE_BOOK):
        return

    def _stores():
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None:
                yield coordinator

    async def _apply(book_id: str, fn) -> None:
        """Apply a mutation to every catalog that has the book, refresh sensors."""
        found = False
        for coordinator in _stores():
            if coordinator.store.has(book_id):
                await fn(coordinator.store)
                coordinator.async_update_listeners()
                found = True
        if not found:
            raise ServiceValidationError(
                f"No book with id '{book_id}' is in the catalog yet."
            )

    async def _rate(call: ServiceCall) -> None:
        await _apply(
            call.data["book_id"],
            lambda store: store.async_rate(
                call.data["book_id"], call.data["person"], call.data.get("rating")
            ),
        )

    async def _assign(call: ServiceCall) -> None:
        await _apply(
            call.data["book_id"],
            lambda store: store.async_assign(
                call.data["book_id"], call.data["person"], call.data["assigned"]
            ),
        )

    hass.services.async_register(DOMAIN, SERVICE_RATE_BOOK, _rate, schema=RATE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_ASSIGN_BOOK, _assign, schema=ASSIGN_SCHEMA
    )
