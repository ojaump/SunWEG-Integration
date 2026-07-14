# SunWEG for Home Assistant

Home Assistant integration for [SunWEG](https://sun.weg.net) (WEG solar inverters), exposing live plant and inverter telemetry as sensors.

Historical data is intentionally left to Home Assistant: the integration only reads the current state, and long-term statistics come from the recorder.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ojaump/SunWEG-Integration`, category **Integration**.
2. Install **SunWEG**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → SunWEG**.

### Manual

Copy `custom_components/sunweg` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

Sign in with the same email and password you use on sun.weg.net, then pick which plants to monitor and the update interval.

The update interval defaults to **2 minutes** and can be changed at any time under the integration's **Configure** button (30 s – 60 min).

> The inverters only push a new reading to the SunWEG cloud roughly every **6 minutes**, so polling faster than that returns the same values and just adds load. The **Last reading** sensor shows the timestamp of the data itself, as opposed to when Home Assistant last fetched it.

## Entities

Each plant becomes a device, with its inverters as child devices.

### Plant

| Entity | Unit | Notes |
| --- | --- | --- |
| Power | kW | Sum of the inverters |
| Energy today | kWh | `total_increasing` — works in the Energy dashboard |
| Total energy | kWh | `total_increasing` |
| Energy this month / this year | kWh | As reported by SunWEG |
| CO2 avoided | kg | Disabled by default |
| Last update | timestamp | When SunWEG refreshed its cache |
| Online | connectivity | Any inverter reporting recently |

### Inverter

| Entity | Unit |
| --- | --- |
| Power | kW |
| Energy today / Total energy | kWh |
| Temperature | °C |
| Grid frequency | Hz |
| Power factor | — (disabled by default) |
| Voltage / Current phase A, B, C | V / A |
| MPPT *n* voltage / current | V / A |
| Last reading | timestamp |
| Online | connectivity |

MPPT entities are created to match the number of trackers the inverter reports (`numMPPT`).

## Energy dashboard

Add the plant's **Total energy** sensor under **Solar production**.

## Notes and limitations

- This uses the private API behind the sun.weg.net web app; it is not an official or documented WEG interface and may change without notice.
- Inverters that have been retired stay listed by the API with no reading attached. They are skipped rather than turned into permanently unavailable entities.
- An inverter's lifetime total of `0` is treated as "no data" rather than a real value, so a glitching inverter cannot look like a meter reset and fabricate a spike in your energy statistics.
- Credentials are stored by Home Assistant in the config entry; the integration logs in again automatically when the token (valid ~7 days) expires.

## Disclaimer

Not affiliated with or endorsed by WEG.
