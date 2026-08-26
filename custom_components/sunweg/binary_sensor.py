"""Binary sensor platform, dispatched to the provider this entry was created for."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import is_huawei
from .huawei import binary_sensor as huawei_binary_sensor
from .weg import binary_sensor as weg_binary_sensor

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    provider = huawei_binary_sensor if is_huawei(entry) else weg_binary_sensor
    await provider.async_setup_entry(hass, entry, async_add_entities)
