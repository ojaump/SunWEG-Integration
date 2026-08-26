"""The SunWEG (WEG) provider."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SunWegClient
from .coordinator import SunWegConfigEntry, SunWegCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: SunWegConfigEntry) -> None:
    """Set up the coordinator this entry's entities read from."""
    client = SunWegClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = SunWegCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
