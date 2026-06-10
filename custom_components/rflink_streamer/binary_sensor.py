"""Binary sensor platform for RFLink Streamer."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVER_DEVICE
from .entity import RFLinkStreamerEntity

LOGGER = logging.getLogger(__name__)


class RFLinkStreamerBinarySensor(RFLinkStreamerEntity, BinarySensorEntity):
    """Representation of an RFLink Streamer binary sensor."""

    _event_platform = "binary_sensor"

    def __init__(self, config_entry_id: str, event_data: dict) -> None:
        super().__init__(config_entry_id, event_data["device_id"], event_data["protocol"])
        self._attr_is_on = False
        self._attr_device_class = _infer_device_class(event_data["protocol"])
        self._apply_event(event_data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

    def async_handle_event(self, event_data: dict) -> None:
        self._apply_event(event_data)
        self.async_write_ha_state()

    def _apply_event(self, event_data: dict) -> None:
        state = event_data.get("state")
        if isinstance(state, bool):
            self._attr_is_on = state


def _infer_device_class(protocol: str) -> BinarySensorDeviceClass | None:
    protocol_name = protocol.lower()
    if "doorbell" in protocol_name:
        return BinarySensorDeviceClass.OCCUPANCY
    if "pir" in protocol_name:
        return BinarySensorDeviceClass.MOTION
    if "alarm" in protocol_name:
        return BinarySensorDeviceClass.SAFETY
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RFLink Streamer binary sensors for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = runtime_data["known_devices"]["binary_sensor"]

    @callback
    def async_discover_device(event_data: dict) -> None:
        device_id = event_data["device_id"]
        if device_id in known_devices:
            return

        known_devices.add(device_id)
        async_add_entities([RFLinkStreamerBinarySensor(entry.entry_id, event_data)])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_DISCOVER_DEVICE.format("binary_sensor"),
            async_discover_device,
        )
    )
