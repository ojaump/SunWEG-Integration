"""Base entities for SunWEG."""

from __future__ import annotations

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Inverter, Plant
from .const import DOMAIN, MANUFACTURER
from .coordinator import SunWegCoordinator


class SunWegPlantEntity(CoordinatorEntity[SunWegCoordinator]):
    """An entity attached to a plant."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunWegCoordinator,
        plant_id: int,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self.entity_description = description
        self._attr_unique_id = f"{plant_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(plant_id))},
            name=coordinator.data[plant_id].name,
            manufacturer=MANUFACTURER,
            model="Plant",
            configuration_url=f"https://sun.weg.net/power-plant-page/{plant_id}",
        )

    @property
    def plant(self) -> Plant | None:
        """The plant this entity belongs to, if it is still being reported."""
        return self.coordinator.data.get(self._plant_id)

    @property
    def available(self) -> bool:
        """Whether the plant was present in the last successful poll."""
        return super().available and self.plant is not None


class SunWegInverterEntity(CoordinatorEntity[SunWegCoordinator]):
    """An entity attached to an inverter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunWegCoordinator,
        plant_id: int,
        inverter_id: int,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._inverter_id = inverter_id
        self.entity_description = description
        self._attr_unique_id = f"{inverter_id}_{description.key}"

        inverter = self.inverter
        assert inverter is not None  # entities are only created for live inverters
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(inverter_id))},
            name=inverter.name,
            manufacturer=MANUFACTURER,
            model=inverter.model,
            serial_number=inverter.serial,
            via_device=(DOMAIN, str(plant_id)),
        )

    @property
    def inverter(self) -> Inverter | None:
        """The inverter this entity belongs to, if it is still being reported."""
        plant = self.coordinator.data.get(self._plant_id)
        if plant is None:
            return None
        return next(
            (
                inverter
                for inverter in plant.inverters
                if inverter.id == self._inverter_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Whether the inverter reported a reading in the last poll.

        Retired inverters stay listed by the API with a null reading, so
        presence in the response is not enough on its own.
        """
        if not super().available:
            return False
        inverter = self.inverter
        return inverter is not None and inverter.has_reading
