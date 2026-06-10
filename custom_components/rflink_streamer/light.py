"""Light platform for RFLink Streamer."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVER_DEVICE
from .entity import RFLinkStreamerEntity
from .protocol import brightness_to_rflink_level, format_rflink_command

LOGGER = logging.getLogger(__name__)


class RFLinkStreamerLight(RFLinkStreamerEntity, LightEntity):
    """Representation of an RFLink Streamer light."""

    _event_platform = "light"

    def __init__(self, config_entry_id: str, event_data: dict[str, Any]) -> None:
        super().__init__(config_entry_id, event_data["device_id"], event_data["protocol"])
        self._source_attributes = event_data["attributes"]
        self._supports_brightness = False
        self._attr_is_on = False
        self._attr_brightness = None
        self._apply_event(event_data)

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {ColorMode.BRIGHTNESS if self._supports_brightness else ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.BRIGHTNESS if self._supports_brightness else ColorMode.ONOFF

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        self._attr_is_on = last_state.state == STATE_ON
        brightness = last_state.attributes.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            self._supports_brightness = True
            self._attr_brightness = brightness

    def async_handle_event(self, event_data: dict[str, Any]) -> None:
        self._apply_event(event_data)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            self._supports_brightness = True
            command = f"SET_LEVEL={brightness_to_rflink_level(brightness)}"
            self._attr_brightness = brightness
            self._attr_is_on = brightness > 0
        else:
            command = "ON"
            self._attr_is_on = True

        client = self.hass.data[DOMAIN][self._config_entry_id]["client"]
        await client.async_send(format_rflink_command(self.protocol, self._source_attributes, command))

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        client = self.hass.data[DOMAIN][self._config_entry_id]["client"]
        await client.async_send(format_rflink_command(self.protocol, self._source_attributes, "OFF"))

    def _apply_event(self, event_data: dict[str, Any]) -> None:
        state = event_data.get("state")
        if isinstance(state, bool):
            self._attr_is_on = state
            if not state:
                self._attr_brightness = None
        elif isinstance(state, int):
            self._supports_brightness = True
            self._attr_brightness = state
            self._attr_is_on = state > 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RFLink Streamer lights for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = runtime_data["known_devices"]["light"]

    @callback
    def async_discover_device(event_data: dict[str, Any]) -> None:
        device_id = event_data["device_id"]
        if device_id in known_devices:
            return

        known_devices.add(device_id)
        async_add_entities([RFLinkStreamerLight(entry.entry_id, event_data)])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_DISCOVER_DEVICE.format("light"),
            async_discover_device,
        )
    )
