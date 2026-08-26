"""Sensors for SunWEG plants and inverters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfMass,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import Inverter, Plant
from .coordinator import SunWegConfigEntry
from .entity import SunWegInverterEntity, SunWegPlantEntity

PARALLEL_UPDATES = 0

# The reading exposes at most 12 MPPT channels (Upv1..Upv12 / Ipv1..Ipv12).
MAX_MPPT = 12


@dataclass(frozen=True, kw_only=True)
class SunWegPlantSensor(SensorEntityDescription):
    """Describes a plant-level sensor."""

    value_fn: Callable[[Plant], float | datetime | None]


@dataclass(frozen=True, kw_only=True)
class SunWegInverterSensor(SensorEntityDescription):
    """Describes an inverter-level sensor."""

    value_fn: Callable[[Inverter], float | datetime | int | None]


PLANT_SENSORS: tuple[SunWegPlantSensor, ...] = (
    SunWegPlantSensor(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.power_kw,
    ),
    SunWegPlantSensor(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_today_kwh,
    ),
    SunWegPlantSensor(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_total_kwh,
    ),
    SunWegPlantSensor(
        key="energy_month",
        translation_key="energy_month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_month_kwh,
    ),
    SunWegPlantSensor(
        key="energy_year",
        translation_key="energy_year",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_year_kwh,
    ),
    SunWegPlantSensor(
        key="co2_avoided",
        translation_key="co2_avoided",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda plant: plant.co2_avoided_kg,
    ),
    SunWegPlantSensor(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda plant: plant.last_update,
    ),
)

INVERTER_SENSORS: tuple[SunWegInverterSensor, ...] = (
    SunWegInverterSensor(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda inverter: inverter.power_kw,
    ),
    SunWegInverterSensor(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda inverter: inverter.energy_today_kwh,
    ),
    SunWegInverterSensor(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda inverter: inverter.energy_total_kwh,
    ),
    SunWegInverterSensor(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda inverter: inverter.value("Temp"),
    ),
    SunWegInverterSensor(
        key="frequency",
        translation_key="frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda inverter: inverter.value("Fac1") or inverter.value("fac"),
    ),
    SunWegInverterSensor(
        key="power_factor",
        translation_key="power_factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda inverter: inverter.value("cos"),
    ),
    SunWegInverterSensor(
        key="last_reading",
        translation_key="last_reading",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda inverter: inverter.last_reading,
    ),
)

# AC phases. The API numbers them 1-3; the labels follow the WEG portal.
PHASE_SENSORS: tuple[SunWegInverterSensor, ...] = tuple(
    sensor
    for phase, label in enumerate(("a", "b", "c"), start=1)
    for sensor in (
        SunWegInverterSensor(
            key=f"voltage_phase_{label}",
            translation_key=f"voltage_phase_{label}",
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda inverter, key=f"Uac{phase}": inverter.value(key),
        ),
        SunWegInverterSensor(
            key=f"current_phase_{label}",
            translation_key=f"current_phase_{label}",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda inverter, key=f"Iac{phase}": inverter.value(key),
        ),
    )
)


def _mppt_sensors(index: int) -> tuple[SunWegInverterSensor, ...]:
    """Build the voltage and current sensors for one MPPT channel."""
    return (
        SunWegInverterSensor(
            key=f"mppt_{index}_voltage",
            translation_key="mppt_voltage",
            translation_placeholders={"index": str(index)},
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            value_fn=lambda inverter, key=f"Upv{index}": inverter.value(key),
        ),
        SunWegInverterSensor(
            key=f"mppt_{index}_current",
            translation_key="mppt_current",
            translation_placeholders={"index": str(index)},
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda inverter, key=f"Ipv{index}": inverter.value(key),
        ),
    )


def _mppt_count(inverter: Inverter) -> int:
    """How many MPPT channels this inverter actually reports.

    Prefer the inverter's own `numMPPT` parameter; if it is missing, fall back
    to counting the Upv keys present in the reading.
    """
    if inverter.mppt_count:
        return min(inverter.mppt_count, MAX_MPPT)
    return sum(
        1 for i in range(1, MAX_MPPT + 1) if inverter.reading.get(f"Upv{i}") is not None
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunWegConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunWEG sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for plant in coordinator.data.values():
        entities.extend(
            SunWegPlantSensorEntity(coordinator, plant.id, description)
            for description in PLANT_SENSORS
        )

        for inverter in plant.inverters:
            # Retired inverters are still listed but have never reported; they
            # would only ever produce permanently unavailable entities.
            if not inverter.has_reading:
                continue

            descriptions = [*INVERTER_SENSORS, *PHASE_SENSORS]
            for index in range(1, _mppt_count(inverter) + 1):
                descriptions.extend(_mppt_sensors(index))

            entities.extend(
                SunWegInverterSensorEntity(
                    coordinator, plant.id, inverter.id, description
                )
                for description in descriptions
            )

    async_add_entities(entities)


class SunWegPlantSensorEntity(SunWegPlantEntity, SensorEntity):
    """A sensor reporting a value for a whole plant."""

    entity_description: SunWegPlantSensor

    @property
    def native_value(self) -> float | datetime | None:
        """Return the sensor value."""
        if (plant := self.plant) is None:
            return None
        return self.entity_description.value_fn(plant)


class SunWegInverterSensorEntity(SunWegInverterEntity, SensorEntity):
    """A sensor reporting a value for a single inverter."""

    entity_description: SunWegInverterSensor

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if (inverter := self.inverter) is None:
            return None
        return self.entity_description.value_fn(inverter)
