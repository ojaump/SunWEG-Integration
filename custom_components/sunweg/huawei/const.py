"""Constants for the FusionSolar (Huawei) provider."""

from __future__ import annotations

from typing import Final

CONF_HOST: Final = "host"
CONF_FLOW_INTERVAL: Final = "flow_interval"

# FusionSolar is sharded by region; the account only exists on one of them.
DEFAULT_HOST: Final = "https://intl.fusionsolar.huawei.com"

# Plant KPIs and device signals are recomputed cloud-side every few minutes.
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 60
MAX_SCAN_INTERVAL: Final = 3600

# The energy flow is the one view the cloud will refresh on demand, once a
# live-data subscription is held for the plant. The subscription drives the
# devices at a 2 s period, so polling faster than that gains nothing.
DEFAULT_FLOW_INTERVAL: Final = 10
MIN_FLOW_INTERVAL: Final = 5
MAX_FLOW_INTERVAL: Final = 600

# Managed-object class ids, as used by every /rest/neteco and /rest/pvms call.
MOC_INVERTER: Final = 20822
MOC_METER: Final = 20816

MANUFACTURER: Final = "Huawei"
