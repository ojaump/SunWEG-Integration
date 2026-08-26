# SunWEG / FusionSolar for Home Assistant

One Home Assistant integration for two solar clouds: [SunWEG](https://sun.weg.net) (WEG inverters) and [FusionSolar](https://intl.fusionsolar.huawei.com) (Huawei inverters and meters). You pick the brand when you add it.

Historical data is intentionally left to Home Assistant: the integration only reads the current state, and long-term statistics come from the recorder.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ojaump/SunWEG-Integration`, category **Integration**.
2. Install **SunWEG / FusionSolar**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → SunWEG / FusionSolar**.

### Manual

Copy `custom_components/sunweg` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

The first step asks which cloud your inverters report to:

| | |
| --- | --- |
| **WEG** | Sign in with the email and password you use on sun.weg.net. |
| **Huawei** | Sign in with your FusionSolar portal username and password, and give the **server** your account lives on. FusionSolar is sharded by region, and an account only exists on one shard — use the host your browser shows once you are signed in, e.g. `https://intl.fusionsolar.huawei.com` or `https://eu5.fusionsolar.huawei.com`. |

Then pick the plants to monitor and the update interval. Everything is changeable later under the integration's **Configure** button.

| Interval | WEG | Huawei |
| --- | --- | --- |
| Update interval | 120 s (30 s – 60 min) | 300 s (60 s – 60 min) |
| Energy flow interval | — | 10 s (5 s – 10 min) |

> WEG inverters push a new reading to the cloud roughly every **6 minutes**, and FusionSolar recomputes its plant KPIs and device signals every few minutes, so polling faster than that returns the same values and just adds load. The **Last reading** sensor shows the timestamp of the data itself, as opposed to when Home Assistant last fetched it.

FusionSolar's **energy flow** is the exception, and gets its own much faster interval. The integration holds a **live-data subscription** for each plant (`livedata/v1/subscribe`), which makes the cloud poll the devices every 2 seconds instead of serving its minutes-old cache. The subscription lapses after a minute, so it is renewed on the way into every flow poll.

Both clouds can be configured at once — add the integration twice and pick a different brand each time.

---

## Entities: WEG

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

---

## Entities: Huawei

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

---

## Energy dashboard

Add the plant's **Total energy** sensor under **Solar production**. On a FusionSolar plant with a meter, add the meter's **Imported energy** and **Exported energy** under grid consumption and return.

## Notes and limitations

Both providers use the private API behind the vendor's own web app. Neither is an official or documented interface, and either may change without notice.

**WEG**

- Inverters that have been retired stay listed by the API with no reading attached. They are skipped rather than turned into permanently unavailable entities.
- An inverter's lifetime total of `0` is treated as "no data" rather than a real value, so a glitching inverter cannot look like a meter reset and fabricate a spike in your energy statistics.

**Huawei**

- This is not the official Northbound/OpenAPI interface.
- Signal ids are only unique per device class — `10025` is the inverter run state and the meter's apparent power — so signals are mapped per device type. A device that is neither an inverter nor a meter (optimiser, battery, logger) gets no entities.
- A plant's inverters and meters are discovered from the energy-flow graph. A device added later shows up after the integration is reloaded.
- Run-state and status values come back in the account's portal language, not Home Assistant's.
- Battery flow sensors are wired to the documented charge/discharge labels but were not verified against a real storage plant.

Credentials are stored by Home Assistant in the config entry; the integration signs in again automatically when the token or session expires.

## Layout

```
custom_components/sunweg/
├── __init__.py, sensor.py, binary_sensor.py, diagnostics.py   # dispatch on the entry's provider
├── config_flow.py, const.py                                   # brand picker, shared keys
├── weg/                                                       # sun.weg.net
└── huawei/                                                    # FusionSolar
```

A config entry records its provider in `data["provider"]`. Entries created before FusionSolar support existed have no such key and are treated as WEG, so they keep working untouched.

## Disclaimer

Not affiliated with or endorsed by WEG or Huawei.
