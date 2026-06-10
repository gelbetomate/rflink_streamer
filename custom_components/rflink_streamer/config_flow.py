"""Config flow for RFLink Streamer."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AUTO_ADD_NEW_DEVICES,
    CONF_DEVICE_ALIASES,
    CONF_ENABLED_DEVICE_IDS,
    CONF_HOST,
    CONF_PORT,
    CONF_RECONNECT_INTERVAL,
    DEFAULT_AUTO_ADD_NEW_DEVICES,
    DEFAULT_PORT,
    DEFAULT_RECONNECT_INTERVAL,
    DOMAIN,
)
from .device_registry import RFLinkDeviceRegistry, normalize_logical_id

LOGGER = logging.getLogger(__name__)

CONF_DEVICE_FILTER = "device_filter"


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
        self._registry: RFLinkDeviceRegistry | None = None
        self._devices: dict[str, dict[str, Any]] = {}
        self._reconnect_interval = config_entry.options.get(
            CONF_RECONNECT_INTERVAL,
            config_entry.data.get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
        )
        self._auto_add_new_devices = config_entry.options.get(
            CONF_AUTO_ADD_NEW_DEVICES,
            DEFAULT_AUTO_ADD_NEW_DEVICES,
        )
        self._enabled_device_ids: set[str] = set()
        self._device_aliases = ""
        self._device_filter = ""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._reconnect_interval = user_input[CONF_RECONNECT_INTERVAL]
            self._auto_add_new_devices = user_input[CONF_AUTO_ADD_NEW_DEVICES]
            self._device_filter = user_input.get(CONF_DEVICE_FILTER, "").strip().lower()
            return await self.async_step_devices()

        if self._registry is None:
            self._registry = RFLinkDeviceRegistry(self.hass, self._config_entry.entry_id)
            await self._registry.async_load()
            self._devices = await self._registry.async_get_devices()
            self._enabled_device_ids = {
                raw_id
                for raw_id, values in self._devices.items()
                if values.get("enabled", False)
            }
            self._device_aliases = _format_aliases(self._devices)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RECONNECT_INTERVAL, default=self._reconnect_interval): int,
                    vol.Required(CONF_AUTO_ADD_NEW_DEVICES, default=self._auto_add_new_devices): bool,
                    vol.Optional(CONF_DEVICE_FILTER, default=self._device_filter): str,
                }
            ),
        )

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if self._registry is None:
            self._registry = RFLinkDeviceRegistry(self.hass, self._config_entry.entry_id)
            await self._registry.async_load()

        self._devices = await self._registry.async_get_devices()
        errors: dict[str, str] = {}
        visible_device_selection = _build_filtered_device_selection(self._devices, self._device_filter)
        visible_ids = set(visible_device_selection)

        if user_input is not None:
            try:
                aliases = _parse_aliases(user_input.get(CONF_DEVICE_ALIASES, ""))
            except ValueError:
                errors["base"] = "invalid_aliases"
            else:
                selected_visible_ids = set(user_input.get(CONF_ENABLED_DEVICE_IDS, []))
                self._enabled_device_ids = (self._enabled_device_ids - visible_ids) | selected_visible_ids
                self._device_aliases = user_input.get(CONF_DEVICE_ALIASES, "")
                new_filter = user_input.get(CONF_DEVICE_FILTER, "").strip().lower()

                # Re-render the form when filter text changed so the ID list updates.
                if new_filter != self._device_filter:
                    self._device_filter = new_filter
                    return await self.async_step_devices()

                await self._registry.async_apply_user_preferences(self._enabled_device_ids, aliases)
                return self.async_create_entry(
                    data={
                        CONF_RECONNECT_INTERVAL: self._reconnect_interval,
                        CONF_AUTO_ADD_NEW_DEVICES: self._auto_add_new_devices,
                    }
                )

        schema_dict: dict[vol.Marker, Any] = {
            vol.Optional(CONF_DEVICE_FILTER, default=self._device_filter): str,
            vol.Optional(CONF_DEVICE_ALIASES, default=self._device_aliases): str,
        }

        if visible_device_selection:
            visible_enabled_defaults = sorted(self._enabled_device_ids & visible_ids)
            schema_dict[vol.Optional(CONF_ENABLED_DEVICE_IDS, default=visible_enabled_defaults)] = cv.multi_select(
                visible_device_selection
            )

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )


def _format_device_option(raw_device_id: str, values: dict[str, Any]) -> str:
    canonical_id = values.get("canonical_id") or raw_device_id
    protocol = values.get("protocol") or "unknown"
    state = "enabled" if values.get("enabled") else "disabled"
    if canonical_id == raw_device_id:
        return f"{raw_device_id} ({protocol}, {state})"
    return f"{raw_device_id} -> {canonical_id} ({protocol}, {state})"


def _build_filtered_device_selection(
    devices: dict[str, dict[str, Any]],
    filter_text: str,
) -> dict[str, str]:
    normalized_filter = filter_text.strip().lower()
    selection: dict[str, str] = {}
    for raw_device_id, values in sorted(devices.items()):
        canonical_id = str(values.get("canonical_id") or "")
        protocol = str(values.get("protocol") or "")
        platform = str(values.get("platform") or "")
        haystack = f"{raw_device_id} {canonical_id} {protocol} {platform}".lower()
        if normalized_filter and normalized_filter not in haystack:
            continue
        selection[raw_device_id] = _format_device_option(raw_device_id, values)

    return selection


def _format_aliases(devices: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"{raw_device_id}={values['canonical_id']}"
        for raw_device_id, values in sorted(devices.items())
        if values.get("canonical_id") and values["canonical_id"] != raw_device_id
    ]
    return "\n".join(lines)


def _parse_aliases(raw_aliases: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for line in raw_aliases.splitlines():
        normalized_line = line.strip()
        if not normalized_line or normalized_line.startswith("#"):
            continue
        if "=" not in normalized_line:
            raise ValueError("Alias line must contain '='")
        raw_device_id, canonical_id = normalized_line.split("=", 1)
        raw_device_id = raw_device_id.strip()
        canonical_id = normalize_logical_id(canonical_id)
        if not raw_device_id or not canonical_id:
            raise ValueError("Alias line must contain valid IDs")
        aliases[raw_device_id] = canonical_id

    return aliases
