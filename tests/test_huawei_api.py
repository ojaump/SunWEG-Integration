"""Parser tests for FusionSolar, against responses captured from the live API."""

import json
from pathlib import Path

from custom_components.sunweg.huawei.api import (
    _quantity_kw,
    parse_device,
    parse_energy_flow,
    parse_plant,
)
from custom_components.sunweg.huawei.const import MOC_INVERTER, MOC_METER

FIXTURES = Path(__file__).parent / "fixtures" / "huawei"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_quantity_kw() -> None:
    """Flow labels carry their unit, and it has to be honoured."""
    assert _quantity_kw("8.963 kW") == 8.963
    assert _quantity_kw("500 W") == 0.5
    assert _quantity_kw("1 MW") == 1000.0
    assert _quantity_kw("8,963 kW") == 8.963
    assert _quantity_kw("") is None
    assert _quantity_kw("8.963") is None
    assert _quantity_kw("8.963 kvar") is None


def test_parse_energy_flow() -> None:
    """The graph flattens to power values plus the devices it names."""
    flow, devices = parse_energy_flow(_load("energyflow_live"))

    assert flow.get("pv_power") == 45.796
    assert flow.get("load_power") == 88.108
    assert flow.get("inverter_power") == 45.796
    assert flow.get("grid_import_power") == 42.312
    assert flow.get("grid_export_power") is None
    # Import only, so the net is the import.
    assert flow.grid_power_kw == 42.312

    assert len(devices[MOC_INVERTER]) == 5
    assert devices[MOC_METER] == ["NE=55898110", "NE=55898136"]


def test_parse_plant() -> None:
    """station-detail carries every plant KPI the integration exposes."""
    plant = parse_plant(_load("station_detail"), "NE=34597654")

    assert plant.dn == "NE=34597654"
    assert plant.name == "Plant A"
    assert plant.is_online
    assert plant.capacity_kw == 211.0
    assert plant.power_kw == 32.007
    assert plant.energy_today_kwh == 251.40
    assert plant.energy_total_kwh == 496505.9
    assert plant.last_update is not None
    assert plant.devices == []


def test_parse_inverter() -> None:
    """Inverter signals are read by id, with the run state kept as its label."""
    device = parse_device(
        _load("device_realtime_inverter"),
        _load("device_status_inverter")["data"],
        "NE=34597658",
    )

    assert device.name == "Inverter 1"
    assert device.moc_id == MOC_INVERTER
    assert device.model == "String_Inverter_Huawei_SUN2000_HWMODBUS"
    assert device.is_online
    assert device.value(10018) == 11.304  # active power, kW
    assert device.value(10032) == 65.35  # energy today, kWh
    assert device.value(10029) == 156051.88  # total energy, kWh
    assert device.value(10023) == 37.7  # internal temperature
    assert device.text(10025) == "Ligação à rede"  # run state, localised
    assert device.last_reading is not None


def test_parse_meter() -> None:
    """The same ids mean different signals on a meter, and power can be negative."""
    device = parse_device(
        _load("device_realtime_meter"),
        {"name": "Meter 1", "mocId": MOC_METER, "meType": "{METER}Meter_HWMODBUS"},
        "NE=55898110",
    )

    assert device.moc_id == MOC_METER
    assert device.is_online
    assert device.value(10004) == -39594.0  # active power, W, signed
    assert device.value(10008) == 12325.00  # imported energy, kWh
    assert device.value(10009) == 55392.00  # exported energy, kWh
    assert device.value(10025) == 53.039  # apparent power, not a run state here
    assert device.text(10001) == "Normal"
