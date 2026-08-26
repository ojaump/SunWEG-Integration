"""Base entities for FusionSolar."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Device, Plant
from ..const import DOMAIN
from .const import MANUFACTURER
from .coordinator import FusionSolarFlowCoordinator, FusionSolarPlantCoordinator


def _plant_device_info(plant: Plant) -> DeviceInfo:
    """The HA device standing for the plant itself."""
    return DeviceInfo(
        identifiers={(DOMAIN, plant.dn)},
        name=plant.name,
        manufacturer=MANUFACTURER,
        model="Plant",
    )


class FusionSolarPlantEntity(CoordinatorEntity[FusionSolarPlantCoordinator]):
    """An entity reporting a plant KPI, on the slow coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FusionSolarPlantCoordinator,
        plant: Plant,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._plant_dn = plant.dn
        self.entity_description = description
        self._attr_unique_id = f"{plant.dn}_{description.key}"
        self._attr_device_info = _plant_device_info(plant)

    @property
    def plant(self) -> Plant | None:
        """The plant this entity belongs to, if it is still being reported."""
        return self.coordinator.data.get(self._plant_dn)

    @property
    def available(self) -> bool:
        """Whether the plant was present in the last successful poll."""
        return super().available and self.plant is not None


class FusionSolarFlowEntity(CoordinatorEntity[FusionSolarFlowCoordinator]):
    """An entity reading the live energy flow, on the fast coordinator.

    It hangs off the same HA device as the plant KPIs; only the coordinator
    behind it differs.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FusionSolarFlowCoordinator,
        plant: Plant,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._plant_dn = plant.dn
        self.entity_description = description
        self._attr_unique_id = f"{plant.dn}_{description.key}"
        self._attr_device_info = _plant_device_info(plant)

    @property
    def flow(self):
        """The plant's last energy-flow reading."""
        return self.coordinator.data.get(self._plant_dn)

    @property
    def available(self) -> bool:
        """Whether the flow graph was returned in the last successful poll."""
        return super().available and self.flow is not None


class FusionSolarDeviceEntity(CoordinatorEntity[FusionSolarPlantCoordinator]):
    """An entity attached to one inverter or meter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FusionSolarPlantCoordinator,
        plant: Plant,
        device: Device,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._plant_dn = plant.dn
        self._device_dn = device.dn
        self.entity_description = description
        self._attr_unique_id = f"{device.dn}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.dn)},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=device.model,
            via_device=(DOMAIN, plant.dn),
        )

    @property
    def device(self) -> Device | None:
        """The device this entity belongs to, if it is still being reported."""
        if (plant := self.coordinator.data.get(self._plant_dn)) is None:
            return None
        return next((d for d in plant.devices if d.dn == self._device_dn), None)

    @property
    def available(self) -> bool:
        """Whether the device reported signals in the last poll."""
        device = self.device
        return super().available and device is not None and bool(device.signals)
