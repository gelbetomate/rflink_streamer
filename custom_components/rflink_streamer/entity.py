"""Entity base classes for RFLink Streamer."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, SIGNAL_AVAILABILITY, SIGNAL_HANDLE_EVENT

LOGGER = logging.getLogger(__name__)


class RFLinkStreamerEntity(RestoreEntity, ABC):
    """Base entity for RFLink Streamer entities."""

    _event_platform: str

    def __init__(self, config_entry_id: str, device_id: str, protocol: str) -> None:
        self._config_entry_id = config_entry_id
        self._device_id = device_id
        self._protocol = protocol
        self._attr_should_poll = False
        self._attr_available = False
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._device_id}"

    @property
    def name(self) -> str:
        return self._device_id.replace("_", " ").title()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name="RFLink Streamer Gateway",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._attr_available = self.hass.data[DOMAIN][self._config_entry_id]["client"].available
        self._unsubscribers.append(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_AVAILABILITY.format(self._config_entry_id),
                self._async_handle_availability,
            )
        )
        self._unsubscribers.append(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_HANDLE_EVENT.format(self._event_platform, self._device_id),
                self._async_dispatch_event,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        while self._unsubscribers:
            self._unsubscribers.pop()()
        await super().async_will_remove_from_hass()

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def protocol(self) -> str:
        return self._protocol

    def _async_handle_availability(self, available: bool) -> None:
        self._attr_available = available
        self.async_write_ha_state()

    def _async_dispatch_event(self, event_data: dict) -> None:
        self.async_handle_event(event_data)

    @abstractmethod
    def async_handle_event(self, event_data: dict) -> None:
        """Handle a parsed RFLink event."""
