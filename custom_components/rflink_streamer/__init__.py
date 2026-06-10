"""The RFLink Streamer integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_AUTO_ADD_NEW_DEVICES,
    CONF_HOST,
    CONF_PORT,
    CONF_RECONNECT_INTERVAL,
    DEFAULT_AUTO_ADD_NEW_DEVICES,
    DEFAULT_RECONNECT_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SIGNAL_AVAILABILITY,
    SIGNAL_DISCOVER_DEVICE,
    SIGNAL_HANDLE_EVENT,
)
from .device_registry import (
    RFLinkDeviceRegistry,
    build_legacy_registry_storage_key,
    build_registry_storage_key,
)
from .protocol import parse_rflink_line

LOGGER = logging.getLogger(__name__)


class RFLinkStreamerClient:
    """Manage the TCP connection to the RFLink stream."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        reconnect_interval: int,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.host = host
        self.port = port
        self.reconnect_interval = reconnect_interval
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._connected = False

    def async_start(self) -> None:
        if self._task is None:
            self._task = self.hass.async_create_task(self._run())

    @property
    def available(self) -> bool:
        return self._connected

    async def async_stop(self) -> None:
        self._stopped = True
        await self._async_close_writer()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._set_availability(False)

    async def async_send(self, command: str) -> None:
        if self._writer is None:
            raise HomeAssistantError("RFLink Streamer is not connected")
        self._writer.write(f"{command.rstrip('\r\n')}\n".encode())
        await self._writer.drain()

    async def _run(self) -> None:
        while not self._stopped:
            try:
                await self._async_connect_and_read()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                LOGGER.warning("RFLink Streamer connection error: %s", err)

            if not self._stopped:
                await asyncio.sleep(self.reconnect_interval)

    async def _async_connect_and_read(self) -> None:
        LOGGER.info("Connecting to RFLink stream at %s:%s", self.host, self.port)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=10,
        )
        self._set_availability(True)
        LOGGER.info("Connected to RFLink stream at %s:%s", self.host, self.port)

        try:
            while not self._stopped:
                raw_line = await self._reader.readline()
                if not raw_line:
                    raise ConnectionError("RFLink stream closed the connection")

                message = raw_line.decode(errors="ignore").strip()
                parsed = parse_rflink_line(message)
                if parsed is None:
                    continue

                runtime_data = self.hass.data[DOMAIN][self.entry_id]
                parsed = runtime_data["device_registry"].process_event(
                    parsed,
                    runtime_data["auto_add_new_devices"],
                )
                if parsed is None:
                    continue

                async_dispatcher_send(
                    self.hass,
                    SIGNAL_DISCOVER_DEVICE.format(parsed["platform"]),
                    parsed,
                )
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_HANDLE_EVENT.format(parsed["platform"], parsed["device_id"]),
                    parsed,
                )
        finally:
            await self._async_close_writer()
            self._set_availability(False)

    async def _async_close_writer(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return

        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    def _set_availability(self, available: bool) -> None:
        if self._connected == available:
            return
        self._connected = available
        async_dispatcher_send(
            self.hass,
            SIGNAL_AVAILABILITY.format(self.entry_id),
            available,
        )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the RFLink Streamer integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RFLink Streamer from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    storage_key = build_registry_storage_key(entry.data[CONF_HOST], entry.data[CONF_PORT])
    legacy_storage_key = build_legacy_registry_storage_key(entry.entry_id)
    device_registry = RFLinkDeviceRegistry(hass, storage_key, legacy_storage_key)
    await device_registry.async_load()

    runtime_data = hass.data[DOMAIN][entry.entry_id] = {
        "client": RFLinkStreamerClient(
            hass,
            entry.entry_id,
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.options.get(
                CONF_RECONNECT_INTERVAL,
                entry.data.get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
            ),
        ),
        "device_registry": device_registry,
        "auto_add_new_devices": entry.options.get(CONF_AUTO_ADD_NEW_DEVICES, DEFAULT_AUTO_ADD_NEW_DEVICES),
        "known_devices": {platform: set() for platform in PLATFORMS},
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime_data["client"].async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an RFLink Streamer config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    await runtime_data["client"].async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
