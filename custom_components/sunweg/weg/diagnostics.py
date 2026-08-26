"""Diagnostics for the SunWEG integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SunWegConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "serial", "esn", "Inversor"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SunWegConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "plants": [
            async_redact_data(asdict(plant), TO_REDACT)
            for plant in coordinator.data.values()
        ],
    }
