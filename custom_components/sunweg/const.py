"""Constants for the SunWEG integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sunweg"

CONF_PLANTS: Final = "plants"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 120
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

API_BASE: Final = "https://api.sunweg.net/v2"
API_ORIGIN: Final = "https://sun.weg.net"

# The upstream loggers push a new reading roughly every 6 minutes, so an
# inverter is considered offline once its reading is older than this.
STALE_READING_AFTER: Final = 1800

MANUFACTURER: Final = "WEG"
