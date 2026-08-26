"""Tests for the SunWEG / FusionSolar config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunweg.const import (
    CONF_PLANTS,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    PROVIDER_HUAWEI,
    PROVIDER_WEG,
)
from custom_components.sunweg.huawei.api import FusionSolarAuthError
from custom_components.sunweg.huawei.const import (
    CONF_FLOW_INTERVAL,
    CONF_HOST,
    DEFAULT_HOST,
)
from custom_components.sunweg.weg.api import SunWegAuthError, SunWegConnectionError

from .conftest import PLANT_ID

PLANTS = {"33264": "Terminação", "36146": "Granja 02", str(PLANT_ID): "Granja 03"}
CREDS = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}
HUAWEI_CREDS = {
    CONF_USERNAME: "user",
    CONF_PASSWORD: "secret",
    CONF_HOST: DEFAULT_HOST,
}


def _patch_client(unique_id="15510", **kwargs):
    """Patch out the login + plant listing the flow performs."""
    return patch(
        "custom_components.sunweg.config_flow._async_authenticate",
        new=AsyncMock(return_value=(unique_id, PLANTS), **kwargs),
    )


async def _pick(hass: HomeAssistant, provider: str) -> dict:
    """Start the flow and choose a provider from the menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [PROVIDER_WEG, PROVIDER_HUAWEI]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": provider}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == provider
    return result


async def test_weg_flow(hass: HomeAssistant) -> None:
    """Picking WEG asks for the sun.weg.net credentials and no server."""
    result = await _pick(hass, PROVIDER_WEG)
    assert CONF_HOST not in result["data_schema"].schema

    with _patch_client():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )
    assert result["step_id"] == "plants"
    # No energy flow on the WEG cloud, so no second interval to set.
    assert CONF_FLOW_INTERVAL not in result["data_schema"].schema

    with patch("custom_components.sunweg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PLANTS: [str(PLANT_ID)], CONF_SCAN_INTERVAL: 300},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {CONF_PROVIDER: PROVIDER_WEG, **CREDS}
    assert result["options"] == {
        CONF_PLANTS: [str(PLANT_ID)],
        CONF_SCAN_INTERVAL: 300,
    }


async def test_huawei_flow(hass: HomeAssistant) -> None:
    """Picking Huawei asks for a server too, and for the energy flow interval."""
    result = await _pick(hass, PROVIDER_HUAWEI)
    assert CONF_HOST in result["data_schema"].schema

    with _patch_client(unique_id=f"{DEFAULT_HOST}:user"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], HUAWEI_CREDS
        )
    assert result["step_id"] == "plants"
    assert CONF_FLOW_INTERVAL in result["data_schema"].schema

    with patch("custom_components.sunweg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PLANTS: [str(PLANT_ID)],
                CONF_SCAN_INTERVAL: 300,
                CONF_FLOW_INTERVAL: 10,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PROVIDER: PROVIDER_HUAWEI, **HUAWEI_CREDS}
    assert result["options"][CONF_FLOW_INTERVAL] == 10


async def test_invalid_auth_recovers(hass: HomeAssistant) -> None:
    """A bad password shows an error, and the flow can then be completed."""
    result = await _pick(hass, PROVIDER_WEG)

    with _patch_client(side_effect=SunWegAuthError("invalido")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    with _patch_client():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )
    assert result["step_id"] == "plants"


async def test_provider_errors_are_both_recognised(hass: HomeAssistant) -> None:
    """Each cloud raises its own exception type; the flow handles both."""
    result = await _pick(hass, PROVIDER_HUAWEI)
    with _patch_client(side_effect=FusionSolarAuthError("rejected")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], HUAWEI_CREDS
        )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await _pick(hass, PROVIDER_WEG)
    with _patch_client(side_effect=SunWegConnectionError("boom")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_changes_interval(hass: HomeAssistant, mock_api) -> None:
    """The poll interval is configurable after setup.

    The entry deliberately carries no provider key, the way entries created
    before FusionSolar support did; those are WEG.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=CREDS,
        options={CONF_PLANTS: [str(PLANT_ID)], CONF_SCAN_INTERVAL: 120},
        unique_id="15510",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with _patch_client():
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_PLANTS: [str(PLANT_ID)], CONF_SCAN_INTERVAL: 600},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 600
    # The entry reloads, so the coordinator picks the new interval up.
    assert entry.runtime_data.update_interval.total_seconds() == 600
