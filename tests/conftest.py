"""Shared fixtures for the SunWEG tests."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

PLANT_ID = 57219

# A real viewresumov2 response captured from the live API, with the personal
# fields scrubbed. Keeping it verbatim is the point: it carries the quirks the
# integration has to survive (kW power, a null-reading inverter, 9 MPPTs).
PLANT_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plant.json").read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/sunweg."""
    return


@pytest.fixture
def mock_api():
    """Replay the recorded response at the HTTP boundary.

    Everything above _request -- token handling, parsing, the coordinator and
    the entities -- runs for real.
    """
    with patch(
        "custom_components.sunweg.weg.api.SunWegClient._request",
        return_value=PLANT_FIXTURE,
    ) as mocked:
        yield mocked
