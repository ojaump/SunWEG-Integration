"""Client for the private API behind the FusionSolar web app."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import MOC_INVERTER, MOC_METER

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Returned by the cloud in place of a reading it does not have.
_NO_DATA = -9.9999999e7

# Session expired server-side; the body says so with HTTP 200.
_RELOGIN_CODE = 305

# How long to leave a plant alone after its subscription attempt failed, so a
# fast flow interval does not retry a broken endpoint every few seconds.
_SUBSCRIBE_RETRY = 300


class FusionSolarError(Exception):
    """Base error for the FusionSolar API."""


class FusionSolarAuthError(FusionSolarError):
    """Credentials or session were rejected."""


class FusionSolarConnectionError(FusionSolarError):
    """The API could not be reached or returned garbage."""


def _as_float(value: Any) -> float | None:
    """Coerce an API value to float, treating junk and no-data markers as missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # "--" comes back as a string and is caught above; this is the numeric one.
    return None if number <= _NO_DATA else number


def _epoch(value: Any, *, milliseconds: bool = False) -> datetime | None:
    """Turn a unix timestamp into an aware datetime."""
    if (number := _as_float(value)) is None or number <= 0:
        return None
    return datetime.fromtimestamp(
        number / 1000 if milliseconds else number, tz=timezone.utc
    )


def _quantity_kw(text: Any) -> float | None:
    """Parse a flow label such as `8.963 kW` into kW.

    The graph carries its values pre-formatted for display, unit included, so
    the unit has to be honoured rather than assumed.
    """
    parts = str(text or "").split()
    if len(parts) != 2:
        return None
    number, unit = parts
    # Some locales format with a decimal comma and no thousands separator.
    if "," in number and "." not in number:
        number = number.replace(",", ".")
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    scale = {"W": 0.001, "kW": 1.0, "MW": 1000.0}.get(unit)
    return None if scale is None else value * scale


@dataclass(slots=True)
class Device:
    """One inverter or meter, with its latest signal values."""

    dn: str
    name: str
    moc_id: int
    model: str | None
    status: int | None
    last_reading: datetime | None
    signals: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def is_online(self) -> bool:
        """Whether the cloud considers the device connected."""
        return self.status == 1

    def value(self, signal_id: int) -> float | None:
        """Read a numeric signal."""
        return _as_float(self.signals.get(signal_id, {}).get("realValue"))

    def text(self, signal_id: int) -> str | None:
        """Read a signal's display value, which for enums is the label."""
        value = self.signals.get(signal_id, {}).get("value")
        return None if value in (None, "") else str(value)


@dataclass(slots=True)
class Plant:
    """A plant, its KPIs, and the devices beneath it."""

    dn: str
    name: str
    status: str | None
    capacity_kw: float | None
    power_kw: float | None
    energy_today_kwh: float | None
    energy_month_kwh: float | None
    energy_year_kwh: float | None
    energy_total_kwh: float | None
    energy_used_today_kwh: float | None
    energy_self_used_today_kwh: float | None
    income_today: float | None
    co2_avoided_kg: float | None
    trees_planted: float | None
    last_update: datetime | None
    devices: list[Device] = field(default_factory=list)

    @property
    def is_online(self) -> bool:
        """Whether the plant is reported as connected."""
        return self.status == "connected"


@dataclass(slots=True)
class EnergyFlow:
    """The live energy-flow graph, flattened to the values worth reading."""

    values: dict[str, float] = field(default_factory=dict)

    def get(self, key: str) -> float | None:
        """Read one flow value in kW."""
        return self.values.get(key)

    @property
    def grid_power_kw(self) -> float | None:
        """Net grid power, positive when importing.

        The graph reports import and export as two separate one-way links and
        never both at once, so the missing one is zero rather than unknown.
        """
        imported = self.values.get("grid_import_power")
        exported = self.values.get("grid_export_power")
        if imported is None and exported is None:
            return None
        return round((imported or 0.0) - (exported or 0.0), 3)


# Graph nodes that carry a power value of their own, by managed-object class.
_FLOW_NODES: dict[int, str] = {20812: "pv_power", 90002: "load_power"}

# Graph links, keyed by the i18n key the cloud puts on the label.
_FLOW_LINKS: dict[str, str] = {
    "neteco.pvms.energy.flow.buy.power": "grid_import_power",
    "neteco.pvms.energy.flow.sell.power": "grid_export_power",
    "neteco.pvms.energy.flow.input.power": "inverter_power",
    "neteco.pvms.basicUnifSignal.optimizer.outputPower": "inverter_power",
    # ponytail: battery keys are the documented pair but unverified against a
    # storage plant; drop them if a real one names them differently.
    "neteco.pvms.energy.flow.charge.power": "battery_charge_power",
    "neteco.pvms.energy.flow.discharge.power": "battery_discharge_power",
}


def parse_energy_flow(data: dict[str, Any]) -> tuple[EnergyFlow, dict[int, list[str]]]:
    """Flatten an `energyflow-live` graph into values and the devices it names."""
    flow = (data.get("data") or {}).get("flow") or {}
    values: dict[str, float] = {}
    devices: dict[int, list[str]] = {}

    for node in flow.get("nodes") or []:
        moc_id = node.get("mocId")
        if dev_ids := node.get("devIds"):
            devices.setdefault(int(moc_id), []).extend(str(dn) for dn in dev_ids)
        if (key := _FLOW_NODES.get(moc_id)) is None:
            continue
        value = _as_float(node.get("value"))
        if value is None:
            value = _quantity_kw((node.get("description") or {}).get("value"))
        if value is not None:
            values[key] = value

    for link in flow.get("links") or []:
        description = link.get("description") or {}
        if (key := _FLOW_LINKS.get(description.get("label"))) is None:
            continue
        if (value := _quantity_kw(description.get("value"))) is not None:
            values[key] = value

    return EnergyFlow(values), devices


def parse_plant(data: dict[str, Any], dn: str) -> Plant:
    """Turn a `station-detail` response into a Plant, without its devices."""
    detail = data.get("data") or {}
    return Plant(
        dn=str(detail.get("dn") or dn),
        name=str(detail.get("name") or dn),
        status=detail.get("plantStatus"),
        # `inverterPower` is the installed inverter capacity, in kW.
        capacity_kw=_as_float(detail.get("inverterPower")),
        power_kw=_as_float(detail.get("currentPower")),
        energy_today_kwh=_as_float(detail.get("dailyEnergy")),
        energy_month_kwh=_as_float(detail.get("monthEnergy")),
        energy_year_kwh=_as_float(detail.get("yearEnergy")),
        energy_total_kwh=_as_float(detail.get("cumulativeEnergy")),
        energy_used_today_kwh=_as_float(detail.get("dailyUseEnergy")),
        energy_self_used_today_kwh=_as_float(detail.get("dailySelfUseEnergy")),
        income_today=_as_float(detail.get("dailyIncome")),
        co2_avoided_kg=_as_float(detail.get("co2")),
        trees_planted=_as_float(detail.get("tree")),
        last_update=_epoch(detail.get("cacheFreSigUpdateTimestamp"), milliseconds=True),
    )


def parse_device(data: dict[str, Any], info: dict[str, Any], dn: str) -> Device:
    """Combine `device-realtime-data` with the cached `device-status-query` info."""
    signals: dict[int, dict[str, Any]] = {}
    status: int | None = None
    for block in data.get("data") or []:
        if "status" in block:
            status = int(_as_float(block["status"]) or 0)
        for signal in block.get("signals") or []:
            if (signal_id := signal.get("id")) is not None:
                signals[int(signal_id)] = signal

    latest = [t for s in signals.values() if (t := _epoch(s.get("latestTime")))]
    return Device(
        dn=dn,
        name=str(info.get("name") or dn),
        moc_id=int(_as_float(info.get("mocId")) or 0),
        # `meType` looks like "{STRI}String_Inverter_Huawei_SUN2000_HWMODBUS".
        model=(str(info["meType"]).rsplit("}", 1)[-1] or None)
        if info.get("meType")
        else None,
        status=status,
        last_reading=max(latest) if latest else None,
        signals=signals,
    )


class FusionSolarClient:
    """Talks to FusionSolar, holding the session cookies and CSRF token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._roarand: str | None = None
        self._login_lock = asyncio.Lock()
        # Device metadata never changes; the subscription does, on a timer.
        self._device_info: dict[str, dict[str, Any]] = {}
        self._devices: dict[str, dict[int, list[str]]] = {}
        self._live_data: dict[str, bool] = {}
        self._subscribed_until: dict[str, float] = {}

    async def login(self) -> None:
        """Sign in and pick up the CSRF token the session is bound to."""
        redirect = f"{self._host}/rest/pvms/web/login/v1/redirecturl?isFirst=false"
        try:
            async with self._session.post(
                f"{self._host}/rest/dp/uidm/unisso/v1/validate-user",
                params={"service": "/rest/dp/uidm/auth/v1/on-sso-credential-ready"},
                json={
                    "username": self._username,
                    "password": self._password,
                    "verifycode": "",
                },
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise FusionSolarAuthError("Credentials rejected")
                response.raise_for_status()
                data = await response.json(content_type=None)

            # A wrong password comes back as HTTP 200, so only the body says so.
            payload = data.get("payload") or {}
            if data.get("code") != 0 or not payload.get("redirectURL"):
                raise FusionSolarAuthError(
                    f"Login failed: {payload.get('exceptionId') or data.get('message') or 'unknown error'}"
                )

            async with self._session.get(
                f"{self._host}{payload['redirectURL']}",
                params={"redirectionAddress": redirect},
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as response:
                response.raise_for_status()
                await response.read()

            async with self._session.get(
                f"{self._host}/rest/dpcloud/auth/v1/keep-alive",
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as response:
                response.raise_for_status()
                token = (await response.json(content_type=None)).get("payload")
        except FusionSolarError:
            raise
        except aiohttp.ClientError as err:
            raise FusionSolarConnectionError(
                f"Could not reach FusionSolar: {err}"
            ) from err
        except (TimeoutError, json.JSONDecodeError, ValueError) as err:
            raise FusionSolarConnectionError(
                f"Bad response from FusionSolar: {err}"
            ) from err

        if not token:
            raise FusionSolarAuthError("Logged in but no session token was issued")
        self._roarand = token
        # A new session invalidates whatever the old one had subscribed.
        self._subscribed_until.clear()

    def _headers(self) -> dict[str, str]:
        """Headers the web app sends on every call."""
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self._host,
            "Referer": f"{self._host}/uniportal/pvmswebsite/assets/build/cloud.html",
        }
        if self._roarand:
            headers["roarand"] = self._roarand
        return headers

    async def _async_relogin(self, used_token: str | None) -> None:
        """Log in again, unless a concurrent request already did.

        Plants and devices are fetched in parallel, so without this an expired
        session would kick off one login per outstanding request.
        """
        async with self._login_lock:
            if used_token is not None and self._roarand != used_token:
                return
            await self.login()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an authenticated call, logging in again if the session died.

        The JSON is returned as-is: most endpoints answer with an object, but
        some answer with a bare boolean or an array.
        """
        if self._roarand is None:
            await self._async_relogin(None)

        for attempt in (1, 2):
            token = self._roarand
            try:
                async with self._session.request(
                    method,
                    f"{self._host}{path}",
                    headers=self._headers(),
                    timeout=_TIMEOUT,
                    **kwargs,
                ) as response:
                    expired = response.status in (401, 403)
                    data: Any = {}
                    if not expired:
                        response.raise_for_status()
                        data = await response.json(content_type=None)
                        if isinstance(data, dict):
                            expired = _RELOGIN_CODE in (
                                data.get("code"),
                                data.get("failCode"),
                            )
                    if expired:
                        if attempt == 1:
                            _LOGGER.debug(
                                "Session rejected on %s, logging in again", path
                            )
                            await self._async_relogin(token)
                            continue
                        raise FusionSolarAuthError(f"Session rejected on {path}")
                    return data
            except FusionSolarError:
                raise
            except aiohttp.ClientError as err:
                raise FusionSolarConnectionError(
                    f"Request to {path} failed: {err}"
                ) from err
            except (TimeoutError, json.JSONDecodeError, ValueError) as err:
                raise FusionSolarConnectionError(
                    f"Bad response from {path}: {err}"
                ) from err

        raise FusionSolarConnectionError(f"Request to {path} failed")

    async def async_list_plants(self) -> dict[str, str]:
        """Return every plant on the account, as {dn: name}."""
        plants: dict[str, str] = {}
        page = 1
        while True:
            data = await self._request(
                "POST",
                "/rest/pvms/web/station/v1/station/station-list",
                json={
                    "curPage": page,
                    "pageSize": 100,
                    "gridConnectedTime": "",
                    # Only the names are read here, but the endpoint expects the
                    # day-scoping fields the web app always sends.
                    "queryTime": int(time.time() // 86400 * 86400 * 1000),
                    "timeZone": 0,
                    "sortId": "createTime",
                    "sortDir": "DESC",
                    "locale": "en_US",
                },
            )
            body = data.get("data") or {}
            for plant in body.get("list") or []:
                if dn := plant.get("dn"):
                    plants[str(dn)] = str(plant.get("name") or dn)
            if page >= int(_as_float(body.get("pageCount")) or 1):
                return plants
            page += 1

    async def async_get_energy_flow(self, station_dn: str) -> EnergyFlow:
        """Fetch the live energy flow, holding a live-data subscription for it.

        Without the subscription the cloud serves whatever its cache last held,
        which for most plants is minutes old.
        """
        await self._async_subscribe(station_dn)
        data = await self._request(
            "GET",
            "/rest/pvms/web/station/v1/overview/energyflow-live",
            params={"stationDn": station_dn},
        )
        flow, devices = parse_energy_flow(data)
        if devices:
            self._devices[station_dn] = devices
        return flow

    async def _async_supports_live_data(self, station_dn: str) -> bool:
        """Whether the plant can be subscribed to at all.

        Plenty of plants cannot -- the portal checks this before it subscribes,
        and subscribing anyway is rejected. It is a capability, so ask once.
        """
        if station_dn not in self._live_data:
            self._live_data[station_dn] = (
                await self._request(
                    "GET",
                    "/rest/dp/pvms/livedata/v1/support",
                    params={"domainDn": station_dn, "featureId": 1},
                )
                is True
            )
        return self._live_data[station_dn]

    async def _async_subscribe(self, station_dn: str) -> None:
        """Renew the plant's live-data subscription shortly before it lapses.

        Best effort throughout: the subscription only makes the cloud refresh
        the plant faster, so losing it costs freshness, not data, and must
        never take the whole entry down with it.
        """
        if time.monotonic() < self._subscribed_until.get(station_dn, 0.0):
            return

        try:
            if not await self._async_supports_live_data(station_dn):
                # Never expires, so this is asked once and then left alone.
                self._subscribed_until[station_dn] = float("inf")
                return
            data = await self._request(
                "POST",
                "/rest/dp/pvms/livedata/v1/subscribe",
                json={"domainDn": station_dn, "featureId": 1},
            )
        except FusionSolarConnectionError as err:
            _LOGGER.debug("Live data unavailable for %s: %s", station_dn, err)
            self._subscribed_until[station_dn] = time.monotonic() + _SUBSCRIBE_RETRY
            return

        remaining = _as_float((data.get("subscribeInfo") or {}).get("remainTime")) or 60
        # Renew early: a lapsed subscription silently falls back to stale data.
        self._subscribed_until[station_dn] = time.monotonic() + remaining * 0.5

    async def async_get_plant(self, station_dn: str) -> Plant:
        """Fetch one plant's KPIs together with every inverter and meter under it."""
        data, device_dns = await asyncio.gather(
            self._request(
                "GET",
                "/rest/pvms/web/station/v1/overview/station-detail",
                params={"stationDn": station_dn},
            ),
            self._async_device_dns(station_dn),
        )
        plant = parse_plant(data, station_dn)
        plant.devices = list(
            await asyncio.gather(*(self._async_get_device(dn) for dn in device_dns))
        )
        return plant

    async def _async_device_dns(self, station_dn: str) -> list[str]:
        """The inverters and meters of a plant, as named by the energy flow.

        The flow graph is the only view that lists them without walking the
        whole device tree, and the fast poll keeps this cache warm anyway.
        """
        if station_dn not in self._devices:
            try:
                await self.async_get_energy_flow(station_dn)
            except FusionSolarConnectionError as err:
                # The plant's own KPIs are still worth having, so report the
                # plant with no devices rather than failing it outright.
                _LOGGER.warning(
                    "Cannot list the devices of %s, its energy flow is unavailable: %s",
                    station_dn,
                    err,
                )
        devices = self._devices.get(station_dn, {})
        return [dn for moc in (MOC_INVERTER, MOC_METER) for dn in devices.get(moc, [])]

    async def _async_get_device(self, device_dn: str) -> Device:
        """Fetch one device's live signals, reusing its cached identity."""
        if (info := self._device_info.get(device_dn)) is None:
            response = await self._request(
                "POST",
                "/rest/neteco/web/config/device/v2/device-status-query",
                data={"dn": device_dn},
            )
            info = response.get("data") or {}
            self._device_info[device_dn] = info

        data = await self._request(
            "GET",
            "/rest/pvms/web/device/v1/device-realtime-data",
            params={"deviceDn": device_dn},
        )
        return parse_device(data, info, device_dn)
