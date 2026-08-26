"""Sensors for FusionSolar plants, inverters and meters."""

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

from .api import Device, EnergyFlow, Plant
from .const import MOC_INVERTER, MOC_METER
from .coordinator import FusionSolarConfigEntry
from .entity import (
    FusionSolarDeviceEntity,
    FusionSolarFlowEntity,
    FusionSolarPlantEntity,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FusionSolarPlantSensor(SensorEntityDescription):
    """Describes a plant-level sensor."""

    value_fn: Callable[[Plant], float | datetime | None]


@dataclass(frozen=True, kw_only=True)
class FusionSolarFlowSensor(SensorEntityDescription):
    """Describes a live energy-flow sensor."""

    value_fn: Callable[[EnergyFlow], float | None]


@dataclass(frozen=True, kw_only=True)
class FusionSolarSignalSensor(SensorEntityDescription):
    """Describes a device signal, addressed by its numeric id.

    Signal ids are only unique within a device class: on an inverter 10025 is
    the run state, on a meter it is the apparent power.
    """

    signal_id: int
    is_text: bool = False


def _power(
    key: str, signal_id: int, unit: str, **kwargs: Any
) -> FusionSolarSignalSensor:
    """Build an active-power signal sensor."""
    return FusionSolarSignalSensor(
        key=key,
        translation_key=key,
        signal_id=signal_id,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3 if unit == UnitOfPower.KILO_WATT else 0,
        **kwargs,
    )


def _energy(key: str, signal_id: int, **kwargs: Any) -> FusionSolarSignalSensor:
    """Build a cumulative-energy signal sensor."""
    return FusionSolarSignalSensor(
        key=key,
        translation_key=key,
        signal_id=signal_id,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        **kwargs,
    )


def _voltage(key: str, signal_id: int) -> FusionSolarSignalSensor:
    """Build a voltage signal sensor."""
    return FusionSolarSignalSensor(
        key=key,
        translation_key=key,
        signal_id=signal_id,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    )


def _current(key: str, signal_id: int) -> FusionSolarSignalSensor:
    """Build a current signal sensor."""
    return FusionSolarSignalSensor(
        key=key,
        translation_key=key,
        signal_id=signal_id,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    )


def _diagnostic(key: str, signal_id: int, unit: str | None = None, **kwargs: Any):
    """Build a diagnostic signal sensor, off by default."""
    return FusionSolarSignalSensor(
        key=key,
        translation_key=key,
        signal_id=signal_id,
        native_unit_of_measurement=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        **kwargs,
    )


PLANT_SENSORS: tuple[FusionSolarPlantSensor, ...] = (
    FusionSolarPlantSensor(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda plant: plant.power_kw,
    ),
    FusionSolarPlantSensor(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_today_kwh,
    ),
    FusionSolarPlantSensor(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_total_kwh,
    ),
    FusionSolarPlantSensor(
        key="energy_month",
        translation_key="energy_month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_month_kwh,
    ),
    FusionSolarPlantSensor(
        key="energy_year",
        translation_key="energy_year",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_year_kwh,
    ),
    FusionSolarPlantSensor(
        key="energy_used_today",
        translation_key="energy_used_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_used_today_kwh,
    ),
    FusionSolarPlantSensor(
        key="energy_self_used_today",
        translation_key="energy_self_used_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda plant: plant.energy_self_used_today_kwh,
    ),
    FusionSolarPlantSensor(
        key="capacity",
        translation_key="capacity",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda plant: plant.capacity_kw,
    ),
    FusionSolarPlantSensor(
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
    FusionSolarPlantSensor(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda plant: plant.last_update,
    ),
)


def _flow_sensor(key: str, **kwargs: Any) -> FusionSolarFlowSensor:
    """Build one live energy-flow sensor, in kW."""
    return FusionSolarFlowSensor(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda flow, k=key: flow.get(k),
        **kwargs,
    )


# Keyed by the flow value each one needs, so a plant only gets the sensors its
# own graph actually carries -- no meter means no grid sensors.
FLOW_SENSORS: dict[str, FusionSolarFlowSensor] = {
    key: _flow_sensor(key)
    for key in (
        "pv_power",
        "inverter_power",
        "load_power",
        "grid_import_power",
        "grid_export_power",
        "battery_charge_power",
        "battery_discharge_power",
    )
}

# Signed net grid power, derived rather than reported: positive is importing.
GRID_POWER = FusionSolarFlowSensor(
    key="grid_power",
    translation_key="grid_power",
    device_class=SensorDeviceClass.POWER,
    native_unit_of_measurement=UnitOfPower.KILO_WATT,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=3,
    value_fn=lambda flow: flow.grid_power_kw,
)


INVERTER_SENSORS: tuple[FusionSolarSignalSensor, ...] = (
    _power("active_power", 10018, UnitOfPower.KILO_WATT),
    _energy("energy_today", 10032),
    _energy("energy_total", 10029),
    FusionSolarSignalSensor(
        key="grid_frequency",
        translation_key="grid_frequency",
        signal_id=10021,
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    FusionSolarSignalSensor(
        key="temperature",
        translation_key="temperature",
        signal_id=10023,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    FusionSolarSignalSensor(
        key="power_factor",
        translation_key="power_factor",
        signal_id=10020,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    FusionSolarSignalSensor(
        key="reactive_power",
        translation_key="reactive_power",
        signal_id=10019,
        native_unit_of_measurement="kvar",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    _voltage("voltage_phase_a", 10011),
    _voltage("voltage_phase_b", 10012),
    _voltage("voltage_phase_c", 10013),
    _voltage("voltage_line_ab", 10008),
    _voltage("voltage_line_bc", 10009),
    _voltage("voltage_line_ca", 10010),
    _current("current_phase_a", 10014),
    _current("current_phase_b", 10015),
    _current("current_phase_c", 10016),
    FusionSolarSignalSensor(
        key="inverter_state",
        translation_key="inverter_state",
        signal_id=10025,
        is_text=True,
    ),
    _diagnostic("insulation_resistance", 10024, "MΩ", suggested_display_precision=3),
    _diagnostic("rated_power", 10006, UnitOfPower.KILO_WATT),
    _diagnostic("startup_time", 10027, is_text=True),
    _diagnostic("shutdown_time", 10028, is_text=True),
)

METER_SENSORS: tuple[FusionSolarSignalSensor, ...] = (
    _power("active_power", 10004, UnitOfPower.WATT),
    _energy("energy_import", 10008),
    _energy("energy_export", 10009),
    FusionSolarSignalSensor(
        key="power_factor",
        translation_key="power_factor",
        signal_id=10006,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    FusionSolarSignalSensor(
        key="reactive_power",
        translation_key="reactive_power",
        signal_id=10005,
        native_unit_of_measurement="var",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    FusionSolarSignalSensor(
        key="apparent_power",
        translation_key="apparent_power",
        signal_id=10025,
        native_unit_of_measurement="kVA",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    _voltage("voltage_phase_a", 10002),
    _voltage("voltage_phase_b", 10010),
    _voltage("voltage_phase_c", 10011),
    _voltage("voltage_line_ab", 10016),
    _voltage("voltage_line_bc", 10017),
    _voltage("voltage_line_ca", 10018),
    _current("current_phase_a", 10003),
    _current("current_phase_b", 10012),
    _current("current_phase_c", 10013),
    _power("active_power_phase_a", 10019, UnitOfPower.WATT),
    _power("active_power_phase_b", 10020, UnitOfPower.WATT),
    _power("active_power_phase_c", 10021, UnitOfPower.WATT),
    _diagnostic(
        "reactive_energy_import",
        10023,
        "kvarh",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    _diagnostic(
        "reactive_energy_export",
        10024,
        "kvarh",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    FusionSolarSignalSensor(
        key="meter_state",
        translation_key="meter_state",
        signal_id=10001,
        is_text=True,
    ),
)

DEVICE_SENSORS: dict[int, tuple[FusionSolarSignalSensor, ...]] = {
    MOC_INVERTER: INVERTER_SENSORS,
    MOC_METER: METER_SENSORS,
}

LAST_READING = SensorEntityDescription(
    key="last_reading",
    translation_key="last_reading",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the FusionSolar sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = []

    for plant_dn, plant in data.plants.data.items():
        entities.extend(
            FusionSolarPlantSensorEntity(data.plants, plant, description)
            for description in PLANT_SENSORS
        )

        flow = data.flow.data.get(plant_dn)
        if flow is not None:
            entities.extend(
                FusionSolarFlowSensorEntity(data.flow, plant, description)
                for key, description in FLOW_SENSORS.items()
                if key in flow.values
            )
            if flow.grid_power_kw is not None:
                entities.append(
                    FusionSolarFlowSensorEntity(data.flow, plant, GRID_POWER)
                )

        for device in plant.devices:
            # A device class the signal map does not cover would otherwise get
            # entities reading the wrong signals off the shared ids.
            descriptions = DEVICE_SENSORS.get(device.moc_id)
            if not descriptions:
                continue
            entities.extend(
                FusionSolarSignalSensorEntity(data.plants, plant, device, description)
                for description in descriptions
                if description.signal_id in device.signals
            )
            entities.append(
                FusionSolarLastReading(data.plants, plant, device, LAST_READING)
            )

    async_add_entities(entities)


class FusionSolarPlantSensorEntity(FusionSolarPlantEntity, SensorEntity):
    """A sensor reporting a KPI for a whole plant."""

    entity_description: FusionSolarPlantSensor

    @property
    def native_value(self) -> float | datetime | None:
        """Return the sensor value."""
        if (plant := self.plant) is None:
            return None
        return self.entity_description.value_fn(plant)


class FusionSolarFlowSensorEntity(FusionSolarFlowEntity, SensorEntity):
    """A sensor reading one value out of the live energy flow."""

    entity_description: FusionSolarFlowSensor

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if (flow := self.flow) is None:
            return None
        return self.entity_description.value_fn(flow)


class FusionSolarSignalSensorEntity(FusionSolarDeviceEntity, SensorEntity):
    """A sensor reporting one signal of an inverter or meter."""

    entity_description: FusionSolarSignalSensor

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if (device := self.device) is None:
            return None
        signal_id = self.entity_description.signal_id
        if self.entity_description.is_text:
            return device.text(signal_id)
        return device.value(signal_id)


class FusionSolarLastReading(FusionSolarDeviceEntity, SensorEntity):
    """When the device last pushed a reading to the cloud."""

    @property
    def native_value(self) -> datetime | None:
        """Return the newest timestamp across the device's signals."""
        device: Device | None = self.device
        return None if device is None else device.last_reading
