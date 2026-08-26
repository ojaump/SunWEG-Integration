"""End-to-end setup tests for the FusionSolar integration."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fusionsolar.api import FusionSolarAuthError
from custom_components.fusionsolar.const import (
    CONF_FLOW_INTERVAL,
    CONF_HOST,
    CONF_PLANTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_HOST,
    DOMAIN,
    MOC_INVERTER,
    MOC_METER,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fusionsolar"
PLANT_DN = "NE=34597654"
METER_DNS = ("NE=55898110", "NE=55898136")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="user",
        data={
            CONF_HOST: DEFAULT_HOST,
            CONF_USERNAME: "user",
            CONF_PASSWORD: "secret",
        },
        options={
            CONF_PLANTS: [PLANT_DN],
            CONF_SCAN_INTERVAL: 300,
            CONF_FLOW_INTERVAL: 10,
        },
        unique_id=f"{DEFAULT_HOST}:user",
    )


@pytest.fixture
def mock_api():
    """Replay recorded responses at the HTTP boundary, keyed by endpoint.

    Everything above _request -- the session handling, parsing, both
    coordinators and the entities -- runs for real.
    """

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        if "station-detail" in path:
            return _load("station_detail")
        if "energyflow-live" in path:
            return _load("energyflow_live")
        if "subscribe" in path:
            return {"success": True, "subscribeInfo": {"remainTime": 60}}
        if "device-status-query" in path:
            dn = kwargs["data"]["dn"]
            is_meter = dn in METER_DNS
            return {
                "data": {
                    "dn": dn,
                    "name": f"{'Meter' if is_meter else 'Inverter'} {dn[-3:]}",
                    "mocId": MOC_METER if is_meter else MOC_INVERTER,
                    "meType": "{METER}Meter" if is_meter else "{STRI}String_Inverter",
                }
            }
        if "device-realtime-data" in path:
            dn = kwargs["params"]["deviceDn"]
            name = "meter" if dn in METER_DNS else "inverter"
            return _load(f"device_realtime_{name}")
        raise AssertionError(f"unexpected request to {path}")

    with patch(
        "custom_components.fusionsolar.api.FusionSolarClient._request", _request
    ) as mocked:
        yield mocked


async def test_setup_creates_devices_and_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """The entry loads with the inverters and meters nested under the plant."""
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.name == "LOADED"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    # The plant, its five inverters and its two meters.
    assert len(devices) == 8
    assert sum(1 for device in devices if device.via_device_id) == 7

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_energy_flow_sensors_are_live(hass: HomeAssistant, mock_api) -> None:
    """The flow sensors come off the fast coordinator, in kW."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    pv = hass.states.get("sensor.plant_a_pv_power")
    assert pv.state == "45.796"
    assert pv.attributes["unit_of_measurement"] == "kW"
    assert pv.attributes["device_class"] == "power"

    assert hass.states.get("sensor.plant_a_load_power").state == "88.108"
    assert hass.states.get("sensor.plant_a_grid_import_power").state == "42.312"
    # Import only, so net grid power is the import.
    assert hass.states.get("sensor.plant_a_grid_power").state == "42.312"
    # Nothing exported and no battery, so those sensors are not created.
    assert hass.states.get("sensor.plant_a_grid_export_power") is None
    assert hass.states.get("sensor.plant_a_battery_charge_power") is None


async def test_meter_and_inverter_signals(hass: HomeAssistant, mock_api) -> None:
    """Shared signal ids resolve per device class, not globally."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # 10025 is the run state on an inverter...
    assert hass.states.get("sensor.inverter_658_state").state == "Ligação à rede"
    assert hass.states.get("sensor.inverter_658_active_power").state == "11.304"
    assert (
        hass.states.get("sensor.inverter_658_active_power").attributes[
            "unit_of_measurement"
        ]
        == "kW"
    )

    # ...and the apparent power on a meter.
    assert hass.states.get("sensor.meter_110_apparent_power").state == "53.039"
    meter_power = hass.states.get("sensor.meter_110_active_power")
    assert meter_power.state == "-39594.0"
    assert meter_power.attributes["unit_of_measurement"] == "W"


async def test_rejected_session_triggers_reauth(hass: HomeAssistant) -> None:
    """An expired session starts the reauth flow instead of failing silently."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.fusionsolar.api.FusionSolarClient._request",
        side_effect=FusionSolarAuthError("Session rejected"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state.name == "SETUP_ERROR"
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"]["source"] == "reauth"
    ]
    assert flows and flows[0]["step_id"] == "reauth_confirm"
