"""Tests for the SunWEG config flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunweg.api import SunWegAuthError, SunWegConnectionError
from custom_components.sunweg.const import CONF_PLANTS, CONF_SCAN_INTERVAL, DOMAIN

from .conftest import PLANT_ID

PLANTS = {33264: "Terminação", 36146: "Granja 02", PLANT_ID: "Granja 03 - 100KW"}
CREDS = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}


def _patch_client(**kwargs):
    """Patch out the login + plant listing the flow performs."""
    return patch(
        "custom_components.sunweg.config_flow._async_authenticate",
        new=AsyncMock(return_value=(SimpleNamespace(user_id=15510), PLANTS), **kwargs),
    )


async def test_full_flow(hass: HomeAssistant) -> None:
    """Credentials, then plant selection, produce an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with _patch_client():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "plants"

    with patch(
        "custom_components.sunweg.async_setup_entry", return_value=True
    ) as setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PLANTS: [str(PLANT_ID)], CONF_SCAN_INTERVAL: 300},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == CREDS
    assert result["options"] == {
        CONF_PLANTS: [str(PLANT_ID)],
        CONF_SCAN_INTERVAL: 300,
    }
    assert len(setup.mock_calls) == 1


async def test_invalid_auth_recovers(hass: HomeAssistant) -> None:
    """A bad password shows an error, and the flow can then be completed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

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
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "plants"


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable API is reported as such."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_client(side_effect=SunWegConnectionError("boom")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDS
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_changes_interval(hass: HomeAssistant, mock_api) -> None:
    """The poll interval is configurable after setup."""
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
