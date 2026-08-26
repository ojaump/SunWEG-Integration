"""The FusionSolar (Huawei) provider."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
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


async def async_setup_entry(hass: HomeAssistant, entry: FusionSolarConfigEntry) -> None:
    """Set up the two coordinators this entry's entities read from."""
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
