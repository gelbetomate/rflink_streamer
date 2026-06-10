"""Onboarding panel and websocket API for RFLink Streamer."""

from __future__ import annotations

import contextlib
import inspect
from collections import deque
from copy import deepcopy
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_SHOW_ONBOARDING_SIDEBAR,
    DEFAULT_SHOW_ONBOARDING_SIDEBAR,
    DOMAIN,
    ONBOARDING_PANEL_PATH,
    PLATFORMS,
)

LOGGER = logging.getLogger(__name__)

PANEL_TITLE = "RFLink Onboarding"
PANEL_NAME = "rflink-streamer-onboarding"
PANEL_ICON = "mdi:radio-tower"

WS_TYPE_LIST = "rflink_streamer/onboarding/list"
WS_TYPE_ADD = "rflink_streamer/onboarding/add"
WS_TYPE_IGNORE = "rflink_streamer/onboarding/ignore"
WS_TYPE_DELETE = "rflink_streamer/onboarding/delete"
WS_TYPE_TEST = "rflink_streamer/onboarding/test"
WS_TYPE_SET_SIDEBAR = "rflink_streamer/onboarding/set_sidebar"


def _get_runtime_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    return hass.data[DOMAIN][entry_id]


async def async_setup_onboarding(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register panel and websocket commands for onboarding UI."""
    frontend_dir = Path(__file__).parent / "frontend"
    if not hass.data[DOMAIN].get("onboarding_static_registered"):
        static_url = f"/{DOMAIN}/frontend"
        register_many = getattr(hass.http, "async_register_static_paths", None)
        if register_many is not None:
            await register_many([StaticPathConfig(static_url, str(frontend_dir), False)])
            LOGGER.info("RFLink onboarding static path registered via async_register_static_paths")
        else:
            register_one = getattr(hass.http, "async_register_static_path", None)
            if register_one is not None:
                await register_one(static_url, str(frontend_dir), cache_headers=False)
                LOGGER.info("RFLink onboarding static path registered via async_register_static_path")
            else:
                register_legacy = getattr(hass.http, "register_static_path", None)
                if register_legacy is not None:
                    register_legacy(static_url, str(frontend_dir), cache_headers=False)
                    LOGGER.info("RFLink onboarding static path registered via register_static_path")
                else:
                    raise RuntimeError("No supported static path registration API found")
        hass.data[DOMAIN]["onboarding_static_registered"] = True

    await async_set_sidebar_entry_enabled(
        hass,
        entry,
        entry.options.get(CONF_SHOW_ONBOARDING_SIDEBAR, DEFAULT_SHOW_ONBOARDING_SIDEBAR),
    )

    if hass.data[DOMAIN].get("ws_onboarding_registered"):
        return

    websocket_api.async_register_command(hass, _ws_list)
    websocket_api.async_register_command(hass, _ws_add)
    websocket_api.async_register_command(hass, _ws_ignore)
    websocket_api.async_register_command(hass, _ws_delete)
    websocket_api.async_register_command(hass, _ws_test)
    websocket_api.async_register_command(hass, _ws_set_sidebar)
    hass.data[DOMAIN]["ws_onboarding_registered"] = True


async def async_set_sidebar_entry_enabled(hass: HomeAssistant, entry: ConfigEntry, enabled: bool) -> None:
    """Show or hide the onboarding sidebar panel."""
    if enabled:
        await _maybe_await(
            panel_custom.async_register_panel(
                hass,
                webcomponent_name="rflink-streamer-onboarding",
                frontend_url_path=ONBOARDING_PANEL_PATH,
                module_url=f"/{DOMAIN}/frontend/rflink-streamer-onboarding.js",
                sidebar_title=PANEL_TITLE,
                sidebar_icon=PANEL_ICON,
                require_admin=False,
                config={"entry_id": entry.entry_id},
            )
        )
        LOGGER.info("RFLink onboarding panel registered in sidebar at /%s", ONBOARDING_PANEL_PATH)
        return

    with contextlib.suppress(ValueError):
        await _maybe_await(frontend.async_remove_panel(hass, ONBOARDING_PANEL_PATH))
        LOGGER.info("RFLink onboarding panel removed from sidebar")


async def async_remove_onboarding_panel(hass: HomeAssistant) -> None:
    """Remove onboarding panel on integration unload."""
    with contextlib.suppress(ValueError):
        await _maybe_await(frontend.async_remove_panel(hass, ONBOARDING_PANEL_PATH))


async def _maybe_await(result: Any) -> None:
    """Await coroutine results while supporting sync HA APIs."""
    if inspect.isawaitable(result):
        await result


def cache_event(runtime_data: dict[str, Any], event_data: dict[str, Any]) -> None:
    """Cache latest event per discovered raw device."""
    raw_id = event_data.get("raw_device_id")
    if not raw_id:
        return

    event_cache: dict[str, dict[str, Any]] = runtime_data["event_cache"]
    event_cache[raw_id] = deepcopy(event_data)
    order: deque[str] = runtime_data["event_order"]
    if raw_id in order:
        order.remove(raw_id)
    order.append(raw_id)
    while len(order) > runtime_data["event_cache_size"]:
        oldest = order.popleft()
        event_cache.pop(oldest, None)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_LIST,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def _ws_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    registry = runtime_data["device_registry"]
    devices = await registry.async_get_devices()
    event_cache: dict[str, dict[str, Any]] = runtime_data["event_cache"]

    pending: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []

    for raw_id, record in sorted(devices.items()):
        item = {
            "raw_device_id": raw_id,
            "canonical_id": record.get("canonical_id") or raw_id,
            "enabled": bool(record.get("enabled", False)),
            "ignored": bool(record.get("ignored", False)),
            "platform": record.get("platform") or "unknown",
            "preferred_platform": record.get("preferred_platform"),
            "protocol": record.get("protocol") or "unknown",
            "last_seen": record.get("last_seen"),
            "has_event": raw_id in event_cache,
            "measurements": list((event_cache.get(raw_id) or {}).get("measurements", {}).keys()),
        }
        if item["enabled"]:
            added.append(item)
        elif not item["ignored"]:
            pending.append(item)

    connection.send_result(
        msg["id"],
        {
            "pending": pending,
            "added": added,
            "sidebar_enabled": bool(
                runtime_data["entry"].options.get(
                    CONF_SHOW_ONBOARDING_SIDEBAR,
                    DEFAULT_SHOW_ONBOARDING_SIDEBAR,
                )
            ),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_ADD,
        vol.Required("entry_id"): str,
        vol.Required("raw_device_id"): str,
        vol.Optional("canonical_id"): str,
        vol.Optional("platform"): vol.In(PLATFORMS),
    }
)
@websocket_api.async_response
async def _ws_add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    registry = runtime_data["device_registry"]

    await registry.async_set_device_preferences(
        msg["raw_device_id"],
        enabled=True,
        ignored=False,
        canonical_id=msg.get("canonical_id"),
        preferred_platform=msg.get("platform"),
    )

    event_cache: dict[str, dict[str, Any]] = runtime_data["event_cache"]
    event_data = event_cache.get(msg["raw_device_id"])
    if event_data:
        mapped_event = registry.process_event(event_data, runtime_data["auto_add_new_devices"])
        if mapped_event is not None:
            runtime_data["dispatch_event"](mapped_event)

    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_IGNORE,
        vol.Required("entry_id"): str,
        vol.Required("raw_device_id"): str,
    }
)
@websocket_api.async_response
async def _ws_ignore(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    registry = runtime_data["device_registry"]
    raw_device_id = msg["raw_device_id"]
    devices_before = await registry.async_get_devices()
    record = devices_before.get(raw_device_id)

    await registry.async_set_device_preferences(
        raw_device_id,
        enabled=False,
        ignored=True,
    )

    if record is not None:
        canonical_id = record.get("canonical_id") or raw_device_id
        _remove_from_known_devices(runtime_data, canonical_id)
        if not _is_enabled_canonical_in_use(devices_before, raw_device_id, canonical_id):
            _remove_entities_for_canonical(hass, runtime_data["entry"].entry_id, canonical_id)

    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_DELETE,
        vol.Required("entry_id"): str,
        vol.Required("raw_device_id"): str,
    }
)
@websocket_api.async_response
async def _ws_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    registry = runtime_data["device_registry"]
    raw_device_id = msg["raw_device_id"]

    devices_before = await registry.async_get_devices()
    removed = await registry.async_delete_device(raw_device_id)
    if removed is None:
        connection.send_result(msg["id"], {"ok": True, "deleted": False})
        return

    canonical_id = removed.get("canonical_id") or raw_device_id

    runtime_data["event_cache"].pop(raw_device_id, None)
    order: deque[str] = runtime_data["event_order"]
    if raw_device_id in order:
        order.remove(raw_device_id)

    _remove_from_known_devices(runtime_data, canonical_id)

    still_in_use = _is_enabled_canonical_in_use(devices_before, raw_device_id, canonical_id)
    if not still_in_use:
        _remove_entities_for_canonical(hass, runtime_data["entry"].entry_id, canonical_id)

    connection.send_result(msg["id"], {"ok": True, "deleted": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_TEST,
        vol.Required("entry_id"): str,
        vol.Required("raw_device_id"): str,
    }
)
@websocket_api.async_response
async def _ws_test(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    event_data = runtime_data["event_cache"].get(msg["raw_device_id"])
    if event_data is None:
        connection.send_error(msg["id"], "not_found", "No recent event for this device")
        return

    connection.send_result(
        msg["id"],
        {
            "platform": event_data.get("platform"),
            "protocol": event_data.get("protocol"),
            "state": event_data.get("state"),
            "measurements": event_data.get("measurements", {}),
            "attributes": event_data.get("attributes", {}),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_SET_SIDEBAR,
        vol.Required("entry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def _ws_set_sidebar(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime_data = _get_runtime_data(hass, msg["entry_id"])
    entry: ConfigEntry = runtime_data["entry"]
    enabled = msg["enabled"]

    options = dict(entry.options)
    options[CONF_SHOW_ONBOARDING_SIDEBAR] = enabled
    hass.config_entries.async_update_entry(entry, options=options)
    await async_set_sidebar_entry_enabled(hass, entry, enabled)

    connection.send_result(msg["id"], {"ok": True, "sidebar_enabled": enabled})


def _is_enabled_canonical_in_use(
    devices_before: dict[str, dict[str, Any]],
    deleted_raw_id: str,
    canonical_id: str,
) -> bool:
    for raw_id, record in devices_before.items():
        if raw_id == deleted_raw_id:
            continue
        if not record.get("enabled", False):
            continue
        if record.get("ignored", False):
            continue
        if (record.get("canonical_id") or raw_id) == canonical_id:
            return True
    return False


def _remove_from_known_devices(runtime_data: dict[str, Any], canonical_id: str) -> None:
    for platform, known_ids in runtime_data["known_devices"].items():
        if platform == "sensor":
            for known_id in list(known_ids):
                if known_id == canonical_id or known_id.startswith(f"{canonical_id}_"):
                    known_ids.discard(known_id)
            continue
        known_ids.discard(canonical_id)


def _remove_entities_for_canonical(hass: HomeAssistant, entry_id: str, canonical_id: str) -> None:
    registry = er.async_get(hass)
    unique_id_prefix = f"{DOMAIN}_{canonical_id}"
    for entity_id, entity_entry in list(registry.entities.items()):
        if entity_entry.config_entry_id != entry_id:
            continue
        if not entity_entry.unique_id.startswith(unique_id_prefix):
            continue
        registry.async_remove(entity_id)
