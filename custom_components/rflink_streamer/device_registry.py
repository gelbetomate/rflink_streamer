"""Persistent registry for discovered RFLink device IDs."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_STORAGE_VERSION = 1
_LOGICAL_ID_RE = re.compile(r"[^a-z0-9]+")
_STORAGE_KEY_RE = re.compile(r"[^a-z0-9]+")


def normalize_logical_id(value: str) -> str:
    """Normalize a user-defined logical device ID."""
    return _LOGICAL_ID_RE.sub("_", value.strip().lower()).strip("_")


def build_registry_storage_key(host: str, port: int) -> str:
    """Build a stable storage key for one RFLink gateway endpoint."""
    endpoint = _STORAGE_KEY_RE.sub("_", f"{host}_{port}".strip().lower()).strip("_")
    return f"{DOMAIN}_{endpoint}_devices"


def build_legacy_registry_storage_key(entry_id: str) -> str:
    """Build the legacy storage key used by earlier versions."""
    return f"{DOMAIN}_{entry_id}_devices"


class RFLinkDeviceRegistry:
    """Track discovered RFLink raw IDs and their exposure settings."""

    def __init__(self, hass: HomeAssistant, storage_key: str, legacy_storage_key: str | None = None) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, _STORAGE_VERSION, storage_key)
        self._legacy_store: Store[dict[str, Any]] | None = None
        if legacy_storage_key and legacy_storage_key != storage_key:
            self._legacy_store = Store(hass, _STORAGE_VERSION, legacy_storage_key)
        self._devices: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load device registry from storage."""
        data = await self._store.async_load()
        if not data and self._legacy_store is not None:
            data = await self._legacy_store.async_load()
            if data:
                # Persist migrated legacy data under the new endpoint-based key.
                self._store.async_delay_save(self._async_serialize, 0)
        if not data:
            return

        loaded_devices = data.get("devices")
        if isinstance(loaded_devices, dict):
            self._devices = loaded_devices

    def process_event(self, event_data: dict[str, Any], auto_add_new_devices: bool) -> dict[str, Any] | None:
        """Update registry from an event and return mapped event if enabled."""
        raw_device_id = event_data["device_id"]
        now = dt_util.utcnow().isoformat()
        record = self._devices.get(raw_device_id)
        changed = False

        if record is None:
            record = {
                "platform": event_data["platform"],
                "protocol": event_data["protocol"],
                "last_seen": now,
                "last_event": deepcopy(event_data),
                "last_raw_string": event_data.get("raw_message"),
                "enabled": auto_add_new_devices,
                "ignored": False,
                "canonical_id": raw_device_id,
                "preferred_platform": None,
            }
            self._devices[raw_device_id] = record
            changed = True
        else:
            if record.get("platform") != event_data["platform"]:
                record["platform"] = event_data["platform"]
                changed = True
            if record.get("protocol") != event_data["protocol"]:
                record["protocol"] = event_data["protocol"]
                changed = True
            if record.get("last_seen") != now:
                record["last_seen"] = now
                changed = True
            if record.get("last_event") != event_data:
                record["last_event"] = deepcopy(event_data)
                changed = True
            if record.get("last_raw_string") != event_data.get("raw_message"):
                record["last_raw_string"] = event_data.get("raw_message")
                changed = True
            if not isinstance(record.get("enabled"), bool):
                record["enabled"] = auto_add_new_devices
                changed = True
            if not isinstance(record.get("ignored"), bool):
                record["ignored"] = False
                changed = True
            canonical_id = normalize_logical_id(str(record.get("canonical_id", "")))
            if not canonical_id:
                canonical_id = raw_device_id
            if record.get("canonical_id") != canonical_id:
                record["canonical_id"] = canonical_id
                changed = True
            preferred_platform = record.get("preferred_platform")
            if preferred_platform is not None and not isinstance(preferred_platform, str):
                record["preferred_platform"] = None
                changed = True

        if changed:
            self._schedule_save()

        if record.get("ignored", False):
            return None

        if not record.get("enabled", False):
            return None

        mapped_event = dict(event_data)
        mapped_event["raw_device_id"] = raw_device_id
        mapped_event["device_id"] = record["canonical_id"]
        mapped_event["platform"] = record.get("preferred_platform") or event_data["platform"]
        return mapped_event

    async def async_get_devices(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the discovered devices table."""
        return deepcopy(self._devices)

    async def async_apply_user_preferences(
        self,
        enabled_raw_ids: set[str],
        alias_map: dict[str, str],
    ) -> None:
        """Update enabled flags and aliases from options UI input."""
        changed = False
        for raw_device_id in enabled_raw_ids | set(alias_map):
            if raw_device_id not in self._devices:
                self._devices[raw_device_id] = {
                    "platform": "unknown",
                    "protocol": "unknown",
                    "last_seen": None,
                    "last_event": None,
                    "last_raw_string": None,
                    "enabled": False,
                    "ignored": False,
                    "canonical_id": raw_device_id,
                    "preferred_platform": None,
                }
                changed = True

        for raw_device_id, record in self._devices.items():
            enabled = raw_device_id in enabled_raw_ids
            canonical_id = alias_map.get(raw_device_id, raw_device_id)
            if record.get("enabled") != enabled:
                record["enabled"] = enabled
                changed = True
            if record.get("canonical_id") != canonical_id:
                record["canonical_id"] = canonical_id
                changed = True
            if not isinstance(record.get("ignored"), bool):
                record["ignored"] = False
                changed = True
            if record.get("preferred_platform") is not None and not isinstance(record.get("preferred_platform"), str):
                record["preferred_platform"] = None
                changed = True

        if changed:
            self._schedule_save()

    async def async_delete_device(self, raw_device_id: str) -> dict[str, Any] | None:
        """Delete a discovered device record by raw ID."""
        removed = self._devices.pop(raw_device_id, None)
        if removed is not None:
            self._schedule_save()
            return deepcopy(removed)
        return None

    async def async_set_device_preferences(
        self,
        raw_device_id: str,
        *,
        enabled: bool | None = None,
        canonical_id: str | None = None,
        ignored: bool | None = None,
        preferred_platform: str | None = None,
    ) -> None:
        """Update one device record from onboarding UI actions."""
        changed = False
        record = self._devices.get(raw_device_id)
        if record is None:
            record = {
                "platform": preferred_platform or "unknown",
                "protocol": "unknown",
                "last_seen": None,
                "last_event": None,
                "last_raw_string": None,
                "enabled": False,
                "ignored": False,
                "canonical_id": raw_device_id,
                "preferred_platform": None,
            }
            self._devices[raw_device_id] = record
            changed = True

        if enabled is not None and record.get("enabled") != enabled:
            record["enabled"] = enabled
            changed = True

        if ignored is not None and record.get("ignored") != ignored:
            record["ignored"] = ignored
            changed = True

        if canonical_id is not None:
            normalized = normalize_logical_id(canonical_id)
            if not normalized:
                normalized = raw_device_id
            if record.get("canonical_id") != normalized:
                record["canonical_id"] = normalized
                changed = True

        if preferred_platform is not None:
            if record.get("preferred_platform") != preferred_platform:
                record["preferred_platform"] = preferred_platform
                changed = True

        if changed:
            self._schedule_save()

    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._async_serialize, 2)

    def _async_serialize(self) -> dict[str, Any]:
        return {"devices": self._devices}
