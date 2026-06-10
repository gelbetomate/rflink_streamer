"""Sensor platform for RFLink Streamer."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVER_DEVICE
from .entity import RFLinkStreamerEntity

LOGGER = logging.getLogger(__name__)

_SENSOR_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "temp": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "hum": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "native_unit_of_measurement": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "baro": {
        "device_class": SensorDeviceClass.PRESSURE,
        "native_unit_of_measurement": UnitOfPressure.HPA,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "rain": {
        "device_class": SensorDeviceClass.PRECIPITATION,
        "native_unit_of_measurement": "mm",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "winsp": {
        "device_class": SensorDeviceClass.WIND_SPEED,
        "native_unit_of_measurement": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "uv": {
        "device_class": None,
        "native_unit_of_measurement": "UV index",
        "state_class": SensorStateClass.MEASUREMENT,
    },
}


class RFLinkStreamerSensor(RFLinkStreamerEntity, SensorEntity):
    """Representation of an RFLink Streamer sensor measurement."""

    _event_platform = "sensor"

    def __init__(self, config_entry_id: str, base_device_id: str, protocol: str, measurement: str, initial_value: Any) -> None:
        super().__init__(config_entry_id, f"{base_device_id}_{measurement}", protocol)
        self._measurement = measurement
        description = _SENSOR_DESCRIPTIONS[measurement]
        self._attr_device_class = description["device_class"]
        self._attr_native_unit_of_measurement = description["native_unit_of_measurement"]
        self._attr_state_class = description["state_class"]
        self._attr_native_value = initial_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
            return
        self._attr_native_value = _restore_native_value(last_state.state, self._measurement)

    def async_handle_event(self, event_data: dict[str, Any]) -> None:
        if self._measurement not in event_data["measurements"]:
            return
        self._attr_native_value = event_data["measurements"][self._measurement]
        self.async_write_ha_state()


def _restore_native_value(state: str, measurement: str) -> int | float | str:
    try:
        if measurement in {"temp", "rain", "winsp"}:
            return float(state)
        return int(state)
    except ValueError:
        return state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RFLink Streamer sensors for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    known_devices: set[str] = runtime_data["known_devices"]["sensor"]

    @callback
    def async_discover_device(event_data: dict[str, Any]) -> None:
        new_entities: list[RFLinkStreamerSensor] = []
        for measurement, value in event_data["measurements"].items():
            entity_device_id = f"{event_data['device_id']}_{measurement}"
            if entity_device_id in known_devices:
                continue
            known_devices.add(entity_device_id)
            new_entities.append(
                RFLinkStreamerSensor(
                    entry.entry_id,
                    event_data["device_id"],
                    event_data["protocol"],
                    measurement,
                    value,
                )
            )

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_DISCOVER_DEVICE.format("sensor"),
            async_discover_device,
        )
    )
