"""Config flow for RFLink Streamer."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_HOST, CONF_PORT, CONF_RECONNECT_INTERVAL, DEFAULT_PORT, DEFAULT_RECONNECT_INTERVAL, DOMAIN

LOGGER = logging.getLogger(__name__)


async def _async_validate_connection(host: str, port: int) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
    except (TimeoutError, OSError):
        return False

    del reader
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    return True


class RFLinkStreamerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RFLink Streamer."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                can_connect = await _async_validate_connection(user_input[CONF_HOST], user_input[CONF_PORT])
            except Exception:
                LOGGER.exception("Unexpected error while validating RFLink Streamer connection")
                errors["base"] = "unknown"
            else:
                if can_connect:
                    return self.async_create_entry(
                        title=unique_id,
                        data=user_input,
                    )
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                    vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): int,
                    vol.Required(
                        CONF_RECONNECT_INTERVAL,
                        default=(user_input or {}).get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
                    ): int,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return RFLinkStreamerOptionsFlow(config_entry)


class RFLinkStreamerOptionsFlow(config_entries.OptionsFlow):
    """Handle RFLink Streamer options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        reconnect_interval = self._config_entry.options.get(
            CONF_RECONNECT_INTERVAL,
            self._config_entry.data.get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RECONNECT_INTERVAL, default=reconnect_interval): int,
                }
            ),
        )
