# SunWEG and FusionSolar for Home Assistant

Two Home Assistant integrations for solar plants: [SunWEG](https://sun.weg.net) (WEG inverters) and [FusionSolar](https://intl.fusionsolar.huawei.com) (Huawei inverters and meters). Both expose live plant and device telemetry as sensors.

Historical data is intentionally left to Home Assistant: both integrations only read the current state, and long-term statistics come from the recorder.

They are independent — install either or both.

- [SunWEG](#sunweg) — the sections immediately below.
- [FusionSolar](#fusionsolar) — at the end.

---

# SunWEG

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ojaump/SunWEG-Integration`, category **Integration**.
2. Install **SunWEG**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → SunWEG**.

> HACS installs one integration per repository, so it only picks up `sunweg`. Install FusionSolar manually.

### Manual

Copy `custom_components/sunweg` and/or `custom_components/fusionsolar` into your Home Assistant `config/custom_components/` directory and restart, then add the integration from **Settings → Devices & Services**.

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


---

# FusionSolar

Reads the private API behind the FusionSolar web portal: plant KPIs, every inverter and meter under the plant, and the live energy flow.

## Configuration

Sign in with the same username and password you use on the portal, and give the **server address** your account lives on — FusionSolar is sharded by region, and the account only exists on one shard. It is the host in your browser's address bar once you are signed in, e.g. `https://intl.fusionsolar.huawei.com` or `https://eu5.fusionsolar.huawei.com`.

Then pick the plants to monitor and the two intervals:

| Interval | Default | Range | Covers |
| --- | --- | --- | --- |
| Update interval | 300 s | 60 s – 60 min | Plant KPIs, inverter and meter signals |
| Energy flow interval | 10 s | 5 s – 10 min | The live energy flow only |

The energy flow gets its own, much faster interval because the integration holds a **live-data subscription** for each plant (`livedata/v1/subscribe`), which makes the cloud poll the devices every 2 seconds instead of serving its minutes-old cache. The subscription lapses after a minute, so it is renewed on the way into every flow poll. Everything else is recomputed cloud-side every few minutes, so polling it faster only adds load.

## Entities

Each plant is a device; its inverters and meters are child devices.

### Plant

| Entity | Unit | Notes |
| --- | --- | --- |
| Power | kW | As reported by the plant |
| Energy today / this month / this year | kWh | |
| Total energy | kWh | `total_increasing` — works in the Energy dashboard |
| Energy used today / Self-used energy today | kWh | Only meaningful on plants with a meter |
| Installed capacity | kW | Disabled by default |
| CO2 avoided | kg | Disabled by default |
| Last update | timestamp | When the cloud last refreshed the plant's cache |
| Online | connectivity | |

### Energy flow (fast)

Created only for the values a given plant's flow graph actually carries, so a plant with no meter gets no grid sensors.

| Entity | Unit |
| --- | --- |
| PV power / Inverter power / Load power | kW |
| Grid import power / Grid export power | kW |
| Grid power | kW — signed, positive when importing |
| Battery charge / discharge power | kW |

### Inverter

Active power, energy today, total energy, grid frequency, internal temperature, power factor, reactive power, phase A/B/C voltage and current, line voltage AB/BC/CA, and the run state. Insulation resistance, rated power and the startup/shutdown times are diagnostic and disabled by default.

### Meter

Active power (signed, in W), imported and exported energy, apparent and reactive power, power factor, per-phase active power, phase A/B/C voltage and current, line voltage AB/BC/CA, and the run state. Reactive energy is diagnostic and disabled by default.

## Energy dashboard

Add the plant's **Total energy** under Solar production. On a plant with a meter, add the meter's **Imported energy** and **Exported energy** under grid consumption and return.

## Notes and limitations

- This uses the private API behind the FusionSolar web app; it is not the official Northbound/OpenAPI interface and may change without notice.
- Signal ids are only unique per device class — `10025` is the inverter run state and the meter's apparent power — so signals are mapped per device type. A device that is neither an inverter nor a meter (optimiser, battery, logger) gets no entities.
- The plant's inverters and meters are discovered from the energy-flow graph. A device added later shows up after the integration is reloaded.
- Run-state and status values come back in the account's portal language, not Home Assistant's.
- Battery flow sensors are wired to the documented charge/discharge labels but were not verified against a real storage plant.
- Credentials are stored by Home Assistant in the config entry; the integration signs in again automatically when the session expires.

## Disclaimer

Not affiliated with or endorsed by Huawei or WEG.
