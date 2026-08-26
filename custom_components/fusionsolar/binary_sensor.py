"""Connectivity binary sensors for FusionSolar."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MOC_INVERTER, MOC_METER
from .coordinator import FusionSolarConfigEntry
from .entity import FusionSolarDeviceEntity, FusionSolarPlantEntity

PARALLEL_UPDATES = 0

ONLINE = BinarySensorEntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the FusionSolar binary sensors."""
    coordinator = entry.runtime_data.plants
    entities: list[BinarySensorEntity] = []

    for plant in coordinator.data.values():
        entities.append(FusionSolarPlantOnline(coordinator, plant, ONLINE))
        entities.extend(
            FusionSolarDeviceOnline(coordinator, plant, device, ONLINE)
            for device in plant.devices
            if device.moc_id in (MOC_INVERTER, MOC_METER)
        )

    async_add_entities(entities)


class FusionSolarPlantOnline(FusionSolarPlantEntity, BinarySensorEntity):
    """Reports whether the cloud still sees the plant."""

    @property
    def is_on(self) -> bool | None:
        """Return true if the plant is connected."""
        if (plant := self.plant) is None:
            return None
        return plant.is_online


class FusionSolarDeviceOnline(FusionSolarDeviceEntity, BinarySensorEntity):
    """Reports whether the inverter or meter is connected."""

    @property
    def available(self) -> bool:
        """Stay available while the device is offline.

        This sensor exists to report the outage, so unlike the measurement
        entities it must not vanish along with the signals.
        """
        return self.coordinator.last_update_success and self.device is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is connected."""
        if (device := self.device) is None:
            return None
        return device.is_online
