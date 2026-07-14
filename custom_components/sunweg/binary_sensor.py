"""Connectivity binary sensors for SunWEG."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SunWegConfigEntry
from .entity import SunWegInverterEntity, SunWegPlantEntity

PARALLEL_UPDATES = 0

PLANT_ONLINE = BinarySensorEntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)

INVERTER_ONLINE = BinarySensorEntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunWegConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunWEG binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    for plant in coordinator.data.values():
        entities.append(SunWegPlantOnline(coordinator, plant.id, PLANT_ONLINE))
        entities.extend(
            SunWegInverterOnline(coordinator, plant.id, inverter.id, INVERTER_ONLINE)
            for inverter in plant.inverters
            if inverter.has_reading
        )

    async_add_entities(entities)


class SunWegPlantOnline(SunWegPlantEntity, BinarySensorEntity):
    """Reports whether any inverter in the plant is still sending readings."""

    @property
    def is_on(self) -> bool | None:
        """Return true if the plant is reporting."""
        if (plant := self.plant) is None:
            return None
        return plant.is_online


class SunWegInverterOnline(SunWegInverterEntity, BinarySensorEntity):
    """Reports whether the inverter's last reading is recent."""

    @property
    def available(self) -> bool:
        """Stay available even when the inverter goes stale.

        This sensor exists precisely to report staleness, so unlike the
        measurement entities it must not disappear along with the data.
        """
        return self.coordinator.last_update_success and self.inverter is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the inverter reported recently."""
        if (inverter := self.inverter) is None:
            return None
        return inverter.is_online
