"""Polling coordinator for SunWEG."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Plant, SunWegAuthError, SunWegClient, SunWegError
from ..const import CONF_PLANTS, CONF_SCAN_INTERVAL, DOMAIN
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type SunWegConfigEntry = ConfigEntry[SunWegCoordinator]


class SunWegCoordinator(DataUpdateCoordinator[dict[int, Plant]]):
    """Polls every configured plant on one interval."""

    config_entry: SunWegConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SunWegConfigEntry, client: SunWegClient
    ) -> None:
        """Initialise the coordinator."""
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.plant_ids: list[int] = [
            int(plant_id) for plant_id in entry.options.get(CONF_PLANTS, [])
        ]

    async def _async_update_data(self) -> dict[int, Plant]:
        """Fetch every selected plant, in parallel."""
        try:
            results = await asyncio.gather(
                *(self.client.async_get_plant(plant_id) for plant_id in self.plant_ids)
            )
        except SunWegAuthError as err:
            # Triggers the reauth flow rather than just marking the entry failed.
            raise ConfigEntryAuthFailed(str(err)) from err
        except SunWegError as err:
            raise UpdateFailed(str(err)) from err

        return {plant.id: plant for plant in results}
