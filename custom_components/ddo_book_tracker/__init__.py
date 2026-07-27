"""The DDO Library Book Tracker integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import DDOCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Plain alias (not a PEP 695 `type` statement) so the module also parses on
# Python 3.11 CI runners; the runtime target is HA's 3.12+.
DDOConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> bool:
    """Set up DDO Library Book Tracker from a config entry."""
    coordinator = DDOCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: DDOConfigEntry) -> None:
    """Reload when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
