"""RFLink protocol helpers."""

from __future__ import annotations

import logging
import re
from typing import Any

from .const import BINARY_SENSOR_PROTOCOLS, RFLINK_RECV_PREFIX, SENSOR_PROTOCOLS, SWITCH_PROTOCOLS

LOGGER = logging.getLogger(__name__)

_LEVEL_RANGE = 15
_PROTOCOL_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SENSOR_ATTRIBUTE_KEYS = {"temp", "hum", "rain", "wind", "uv", "baro", "winsp"}


def parse_rflink_line(line: str) -> dict[str, Any] | None:
    """Parse a raw RFLink line into a normalized event."""
    message = line.strip()
    if not message or message.startswith("10;") or not message.startswith(RFLINK_RECV_PREFIX):
        return None

    parts = [part for part in message.split(";") if part]
    if len(parts) < 3 or parts[1] == "00":
        return None

    protocol = parts[2]
    attributes: dict[str, str] = {}
    for token in parts[3:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        attributes[key.lower()] = value

    device_key = attributes.get("id")
    if device_key is None:
        LOGGER.debug("Ignoring RFLink event without ID: %s", message)
        return None

    device_id = _build_device_id(protocol, device_key, attributes.get("switch"))
    measurements = _extract_measurements(attributes)

    return {
        "protocol": protocol,
        "device_id": device_id,
        "platform": infer_platform(protocol, attributes),
        "attributes": attributes,
        "state": _extract_state(attributes),
        "measurements": measurements,
    }


def infer_platform(protocol: str, attributes: dict[str, str]) -> str:
    """Infer the Home Assistant platform for an RFLink event."""
    protocol_name = protocol.lower()
    if _SENSOR_ATTRIBUTE_KEYS.intersection(attributes):
        return "sensor"
    if any(marker in protocol_name for marker in SENSOR_PROTOCOLS):
        return "sensor"
    if any(marker in protocol_name for marker in BINARY_SENSOR_PROTOCOLS):
        return "binary_sensor"
    if any(marker in protocol_name for marker in SWITCH_PROTOCOLS):
        return "switch"
    return "light"


def format_rflink_command(protocol: str, attributes: dict[str, str], command: str) -> str:
    """Format an outgoing RFLink command."""
    parts = ["10", protocol, attributes["id"]]
    switch = attributes.get("switch")
    if switch:
        parts.append(switch)
    parts.append(command)
    return ";".join(parts) + ";"


def brightness_to_rflink_level(brightness: int) -> str:
    """Convert a Home Assistant brightness value into an RFLink level."""
    scaled = round((max(0, min(255, brightness)) / 255) * _LEVEL_RANGE)
    return str(scaled)


def rflink_level_to_brightness(level: str) -> int:
    """Convert an RFLink dim level into a Home Assistant brightness."""
    value = int(level, 16) if any(character.isalpha() for character in level) else int(level)
    return round((value / _LEVEL_RANGE) * 255)


def _build_device_id(protocol: str, device_key: str, switch: str | None) -> str:
    protocol_slug = _PROTOCOL_SLUG_RE.sub("_", protocol.lower()).strip("_")
    if switch:
        return f"{protocol_slug}_{device_key.lower()}_{switch.lower()}"
    return f"{protocol_slug}_{device_key.lower()}"


def _extract_state(attributes: dict[str, str]) -> bool | int | None:
    command = attributes.get("cmd", "").upper()
    if command in {"ON", "ALLON"}:
        return True
    if command in {"OFF", "ALLOFF"}:
        return False
    if command.startswith("SET_LEVEL="):
        return rflink_level_to_brightness(command.split("=", 1)[1])
    return None


def _extract_measurements(attributes: dict[str, str]) -> dict[str, int | float]:
    measurements: dict[str, int | float] = {}

    if (value := attributes.get("temp")) is not None:
        raw = int(value, 16)
        if raw > 32767:
            raw -= 65536
        measurements["temp"] = round(raw * 0.1, 1)

    if (value := attributes.get("hum")) is not None:
        measurements["hum"] = int(value)

    if (value := attributes.get("baro")) is not None:
        measurements["baro"] = int(value, 16)

    if (value := attributes.get("rain")) is not None:
        measurements["rain"] = round(int(value, 16) / 10, 1)

    if (value := attributes.get("winsp")) is not None:
        measurements["winsp"] = round(int(value, 16) / 10, 1)

    if (value := attributes.get("uv")) is not None:
        measurements["uv"] = _parse_flexible_int(value)

    return measurements


def _parse_flexible_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return int(value, 16)
