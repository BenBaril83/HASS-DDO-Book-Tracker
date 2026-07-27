"""Config flow for the DDO Library Book Tracker integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

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

_LOGGER = logging.getLogger(__name__)


def _validate_login(barcode: str, pin: str, institution: str) -> dict[str, str]:
    """Blocking login check. Returns {'borrower_id', 'name'} on success."""
    client = DDOLibraryClient(barcode=barcode, pin=pin, institution=institution)
    client.login()
    summary = client.get_summary()
    return {
        "borrower_id": summary.get("borrowerId", barcode),
        "name": summary.get("alias") or barcode,
    }


class DDOConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await self.hass.async_add_executor_job(
                    _validate_login,
                    user_input[CONF_BARCODE].strip(),
                    user_input[CONF_PIN].strip(),
                    user_input.get(CONF_INSTITUTION, DEFAULT_INSTITUTION),
                )
            except DDOAuthError:
                errors["base"] = "invalid_auth"
            except DDOLibraryError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - defensive; log and show generic error
                _LOGGER.exception("Unexpected error validating DDO login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["borrower_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["name"],
                    data={
                        CONF_BARCODE: user_input[CONF_BARCODE].strip(),
                        CONF_PIN: user_input[CONF_PIN].strip(),
                        CONF_INSTITUTION: user_input.get(
                            CONF_INSTITUTION, DEFAULT_INSTITUTION
                        ),
                        CONF_INCLUDE_LINKED: user_input.get(
                            CONF_INCLUDE_LINKED, DEFAULT_INCLUDE_LINKED
                        ),
                        CONF_SCAN_INTERVAL_HOURS: user_input.get(
                            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BARCODE): str,
                vol.Required(CONF_PIN): str,
                vol.Optional(
                    CONF_INSTITUTION, default=DEFAULT_INSTITUTION
                ): str,
                vol.Optional(
                    CONF_INCLUDE_LINKED, default=DEFAULT_INCLUDE_LINKED
                ): bool,
                vol.Optional(
                    CONF_SCAN_INTERVAL_HOURS, default=DEFAULT_SCAN_INTERVAL_HOURS
                ): vol.All(int, vol.Range(min=1, max=24)),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DDOOptionsFlow()


class DDOOptionsFlow(OptionsFlow):
    """Allow changing the refresh interval and linked-account behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL_HOURS,
                    default=current.get(
                        CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
                    ),
                ): vol.All(int, vol.Range(min=1, max=24)),
                vol.Optional(
                    CONF_INCLUDE_LINKED,
                    default=current.get(
                        CONF_INCLUDE_LINKED, DEFAULT_INCLUDE_LINKED
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
