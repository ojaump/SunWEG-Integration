"""The FusionSolar integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import FusionSolarClient
from .const import CONF_HOST, DEFAULT_HOST
from .coordinator import (
    FusionSolarConfigEntry,
    FusionSolarData,
    FusionSolarFlowCoordinator,
    FusionSolarPlantCoordinator,
)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FusionSolarConfigEntry) -> bool:
    """Set up FusionSolar from a config entry."""
    # FusionSolar authenticates with cookies, so this entry needs a jar of its
    # own rather than the one shared by every integration. Created here, the
    # session is detached for us when the entry unloads.
    session = async_create_clientsession(hass)

    client = FusionSolarClient(
        session,
        entry.data.get(CONF_HOST, DEFAULT_HOST),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    plants = FusionSolarPlantCoordinator(hass, entry, client)
    flow = FusionSolarFlowCoordinator(hass, entry, client)
    await plants.async_config_entry_first_refresh()
    await flow.async_config_entry_first_refresh()

    entry.runtime_data = FusionSolarData(client, plants, flow)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FusionSolarConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant, entry: FusionSolarConfigEntry
) -> None:
    """Reload when the poll intervals or the plant selection change."""
    await hass.config_entries.async_reload(entry.entry_id)
