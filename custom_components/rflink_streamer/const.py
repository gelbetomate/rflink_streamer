"""Constants for the RFLink Streamer integration."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)

DOMAIN = "rflink_streamer"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_RECONNECT_INTERVAL = "reconnect_interval"
CONF_AUTO_ADD_NEW_DEVICES = "auto_add_new_devices"
CONF_ENABLED_DEVICE_IDS = "enabled_device_ids"
CONF_DEVICE_ALIASES = "device_aliases"
DEFAULT_PORT = 6638
DEFAULT_RECONNECT_INTERVAL = 10
DEFAULT_AUTO_ADD_NEW_DEVICES = False

RFLINK_RECV_PREFIX = "20;"

PLATFORMS = ["light", "switch", "sensor", "binary_sensor"]

SIGNAL_AVAILABILITY = "rflink_streamer_availability_{}"
SIGNAL_DISCOVER_DEVICE = "rflink_streamer_discover_{}"
SIGNAL_HANDLE_EVENT = "rflink_streamer_event_{}_{}"

SENSOR_PROTOCOLS = [
    "oregon",
    "alecto",
    "auriol",
    "mebus",
    "prologue",
    "fineoffset",
    "temperature",
    "humidity",
    "rain",
    "wind",
    "uv",
    "baro",
    "f007",
    "acurite",
    "globaltron",
    "infactory",
]
BINARY_SENSOR_PROTOCOLS = ["doorbell", "pir", "alarm"]
SWITCH_PROTOCOLS = ["rts", "rte", "bofumotor", "warema", "mertik", "trc02rgb"]
