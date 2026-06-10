"""Switch platform for RFLink Streamer."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVER_DEVICE
from .entity import RFLinkStreamerEntity
from .protocol import format_rflink_command

LOGGER = logging.getLogger(__name__)


class RFLinkStreamerSwitch(RFLinkStreamerEntity, SwitchEntity):
    """Representation of an RFLink Streamer switch."""

    _event_platform = "switch"

    def __init__(self, config_entry_id: str, event_data: dict[str, Any]) -> None:
        super().__init__(config_entry_id, event_data["device_id"], event_data["protocol"])
        self._source_attributes = event_data["attributes"]
        self._attr_is_on = False
        self._apply_event(event_data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

    def async_handle_event(self, event_data: dict[str, Any]) -> None:
        self._apply_event(event_data)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        client = self.hass.data[DOMAIN][self._config_entry_id]["client"]
        await client.async_send(format_rflink_command(self.protocol, self._source_attributes, "ON"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        client = self.hass.data[DOMAIN][self._config_entry_id]["client"]
        await client.async_send(format_rflink_command(self.protocol, self._source_attributes, "OFF"))

    def _apply_event(self, event_data: dict[str, Any]) -> None:
        state = event_data.get("state")
        if isinstance(state, bool):
            self._attr_is_on = state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RFLink Streamer switches for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = runtime_data["known_devices"]["switch"]

    @callback
    def async_discover_device(event_data: dict[str, Any]) -> None:
        device_id = event_data["device_id"]
        if device_id in known_devices:
            return

        known_devices.add(device_id)
        async_add_entities([RFLinkStreamerSwitch(entry.entry_id, event_data)])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_DISCOVER_DEVICE.format("switch"),
            async_discover_device,
        )
    )
