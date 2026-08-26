"""The SunWEG / FusionSolar integration.

One integration, two clouds. Which one an entry talks to is fixed at setup
time and read back out of the entry, so every platform dispatches the same way.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import huawei, weg
from .const import is_huawei

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry against whichever cloud it was created for."""
    provider = huawei if is_huawei(entry) else weg
    await provider.async_setup_entry(hass, entry)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the poll interval or the plant selection changes."""
    await hass.config_entries.async_reload(entry.entry_id)
