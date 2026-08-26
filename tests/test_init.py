"""Tests for setting up the SunWEG integration."""

from unittest.mock import patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunweg.weg.api import SunWegAuthError, Inverter, parse_plant
from custom_components.sunweg.const import CONF_PLANTS, CONF_SCAN_INTERVAL, DOMAIN

from .conftest import PLANT_FIXTURE, PLANT_ID


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
        options={CONF_PLANTS: [str(PLANT_ID)], CONF_SCAN_INTERVAL: 120},
        unique_id="15510",
    )


async def test_setup_creates_devices_and_entities(
    hass: HomeAssistant, mock_api
) -> None:
    """The entry loads, nesting the inverter under the plant."""
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.name == "LOADED"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 2
    assert any(device.via_device_id for device in devices), "inverter not nested"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_energy_sensors(hass: HomeAssistant, mock_api) -> None:
    """The Energy dashboard sensors carry the right units and state classes."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    total = hass.states.get("sensor.granja_03_100kw_total_energy")
    assert total.state == "477835.4"
    assert total.attributes["device_class"] == "energy"
    assert total.attributes["state_class"] == "total_increasing"
    assert total.attributes["unit_of_measurement"] == "kWh"

    today = hass.states.get("sensor.granja_03_100kw_energy_today")
    assert today.state == "504.2"

    # Pac is reported in kW, not W.
    power = hass.states.get("sensor.granja_03_100kw_power")
    assert power.attributes["unit_of_measurement"] == "kW"
    assert power.attributes["device_class"] == "power"


async def test_mppt_entities_match_inverter(hass: HomeAssistant, mock_api) -> None:
    """MPPT sensors follow the inverter's numMPPT rather than a fixed count."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    mppt = [e for e in entities if "mppt" in e.entity_id]
    assert len(mppt) == 18  # 9 trackers, voltage + current each
    assert hass.states.get("sensor.siw400_mppt_9_voltage") is not None
    assert hass.states.get("sensor.siw400_mppt_10_voltage") is None


async def test_bad_credentials_trigger_reauth(hass: HomeAssistant) -> None:
    """A rejected password starts the reauth flow instead of silently failing."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.sunweg.weg.api.SunWegClient._request",
        side_effect=SunWegAuthError("Login failed: invalido"),
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


def test_retired_inverter_is_parsed_but_has_no_reading() -> None:
    """An inverter the API lists with a null reading must not look live."""
    data = {
        **PLANT_FIXTURE,
        "inversores": [
            *PLANT_FIXTURE["inversores"],
            {"id": 55065, "nome": "a", "ulleitura": None, "parametros": {}},
        ],
    }
    plant = parse_plant(data, PLANT_ID)
    retired = next(inv for inv in plant.inverters if inv.id == 55065)
    assert retired.has_reading is False
    assert retired.is_online is False
    # It must not drag the plant totals down either.
    assert plant.energy_total_kwh == 477835.4


def test_zero_lifetime_total_is_treated_as_missing() -> None:
    """A zero lifetime total would look like a meter reset and fake a spike."""
    inverter = Inverter(
        id=1,
        name="i",
        serial=None,
        model=None,
        capacity_kw=None,
        status=1,
        mppt_count=2,
        last_reading=None,
        reading={"Etotal": 0.0, "Eday": 0.0},
    )
    assert inverter.energy_total_kwh is None
    assert inverter.energy_today_kwh == 0.0  # zero today is genuine
