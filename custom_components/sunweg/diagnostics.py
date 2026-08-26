"""Diagnostics, dispatched to the provider this entry was created for."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import is_huawei
from .huawei import diagnostics as huawei_diagnostics
from .weg import diagnostics as weg_diagnostics


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    provider = huawei_diagnostics if is_huawei(entry) else weg_diagnostics
    return await provider.async_get_config_entry_diagnostics(hass, entry)
