"""Polling coordinators for FusionSolar."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EnergyFlow,
    FusionSolarAuthError,
    FusionSolarClient,
    FusionSolarError,
    Plant,
)
from .const import (
    CONF_FLOW_INTERVAL,
    CONF_PLANTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_FLOW_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type FusionSolarConfigEntry = ConfigEntry[FusionSolarData]


@dataclass(slots=True)
class FusionSolarData:
    """What the platforms need to build their entities."""

    client: FusionSolarClient
    plants: FusionSolarPlantCoordinator
    flow: FusionSolarFlowCoordinator


class _BaseCoordinator[T](DataUpdateCoordinator[dict[str, T]]):
    """Fans one request out over every configured plant."""

    config_entry: FusionSolarConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FusionSolarConfigEntry,
        client: FusionSolarClient,
        name: str,
        interval: int,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.plant_dns: list[str] = [
            str(dn) for dn in entry.options.get(CONF_PLANTS, [])
        ]

    async def _async_fetch(self, station_dn: str) -> T:
        """Fetch this coordinator's data for one plant."""
        raise NotImplementedError

    async def _async_update_data(self) -> dict[str, T]:
        """Fetch every selected plant, in parallel."""
        try:
            results = await asyncio.gather(
                *(self._async_fetch(dn) for dn in self.plant_dns)
            )
        except FusionSolarAuthError as err:
            # Triggers the reauth flow rather than just marking the entry failed.
            raise ConfigEntryAuthFailed(str(err)) from err
        except FusionSolarError as err:
            raise UpdateFailed(str(err)) from err

        return dict(zip(self.plant_dns, results, strict=True))


class FusionSolarPlantCoordinator(_BaseCoordinator[Plant]):
    """Plant KPIs plus every inverter and meter reading, on the slow interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FusionSolarConfigEntry,
        client: FusionSolarClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            entry,
            client,
            "plants",
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

    async def _async_fetch(self, station_dn: str) -> Plant:
        """Fetch one plant and its devices."""
        return await self.client.async_get_plant(station_dn)


class FusionSolarFlowCoordinator(_BaseCoordinator[EnergyFlow]):
    """The live energy flow, on the fast interval the subscription enables."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FusionSolarConfigEntry,
        client: FusionSolarClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            entry,
            client,
            "energy flow",
            entry.options.get(CONF_FLOW_INTERVAL, DEFAULT_FLOW_INTERVAL),
        )

    async def _async_fetch(self, station_dn: str) -> EnergyFlow:
        """Fetch one plant's energy flow."""
        return await self.client.async_get_energy_flow(station_dn)
