"""Constants shared by both providers."""

from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry

DOMAIN: Final = "sunweg"

# Which cloud a config entry talks to. Entries created before FusionSolar
# support existed have no such key and are WEG by definition.
CONF_PROVIDER: Final = "provider"
PROVIDER_WEG: Final = "weg"
PROVIDER_HUAWEI: Final = "huawei"

CONF_PLANTS: Final = "plants"
CONF_SCAN_INTERVAL: Final = "scan_interval"


def is_huawei(entry: ConfigEntry) -> bool:
    """Whether this entry talks to FusionSolar rather than the WEG cloud."""
    return entry.data.get(CONF_PROVIDER) == PROVIDER_HUAWEI
