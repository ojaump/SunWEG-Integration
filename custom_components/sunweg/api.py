"""Client for the SunWEG (sun.weg.net) private API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp

from .const import API_BASE, API_ORIGIN, STALE_READING_AFTER

_LOGGER = logging.getLogger(__name__)

# Refresh the token this long before it actually expires.
_TOKEN_LEEWAY = timedelta(minutes=15)
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class SunWegError(Exception):
    """Base error for the SunWEG API."""


class SunWegAuthError(SunWegError):
    """Credentials were rejected."""


class SunWegConnectionError(SunWegError):
    """The API could not be reached or returned garbage."""


def _as_float(value: Any) -> float | None:
    """Coerce an API value to float, treating junk as missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reading_timestamp(raw: str | None, tz_offset: int | None) -> datetime | None:
    """Parse `tsleitura` ("2026-07-13 21:53:03"), which is local to the plant."""
    if not raw:
        return None
    try:
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    tz = timezone(timedelta(hours=tz_offset if tz_offset is not None else 0))
    return naive.replace(tzinfo=tz)


def _http_timestamp(raw: str | None) -> datetime | None:
    """Parse an RFC 2822 date such as `cache_updated_at`."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class Inverter:
    """A single inverter and its most recent reading."""

    id: int
    name: str
    serial: str | None
    model: str | None
    capacity_kw: float | None
    status: int | None
    mppt_count: int
    last_reading: datetime | None
    reading: dict[str, Any] = field(default_factory=dict)

    @property
    def has_reading(self) -> bool:
        """Whether the inverter reported anything at all."""
        return bool(self.reading)

    @property
    def is_online(self) -> bool:
        """Whether the last reading is recent enough to be trusted as live."""
        if self.last_reading is None:
            return False
        age = datetime.now(timezone.utc) - self.last_reading
        return age.total_seconds() < STALE_READING_AFTER

    def value(self, key: str) -> float | None:
        """Read a numeric field out of the last reading."""
        return _as_float(self.reading.get(key))

    @property
    def power_kw(self) -> float | None:
        """Instantaneous AC power. The API reports `Pac` in kW."""
        return self.value("Pac")

    @property
    def energy_today_kwh(self) -> float | None:
        """Energy generated today, in kWh."""
        return self.value("Eday")

    @property
    def energy_total_kwh(self) -> float | None:
        """Lifetime energy, in kWh.

        A zero lifetime total means "no data", never a genuine reading, and
        feeding it to a total_increasing sensor would look like a meter reset
        and fabricate a spike on the next real value. Report it as missing.
        """
        total = self.value("Etotal") or self.value("ETotal")
        return total or None


@dataclass(slots=True)
class Plant:
    """A plant and the inverters beneath it."""

    id: int
    name: str
    capacity_kw: float | None
    energy_month_kwh: float | None
    energy_year_kwh: float | None
    co2_avoided_kg: float | None
    trees_planted: float | None
    last_update: datetime | None
    inverters: list[Inverter] = field(default_factory=list)

    def _sum(self, attr: str) -> float | None:
        """Total an attribute across inverters that actually reported."""
        values = [
            value
            for inverter in self.inverters
            if (value := getattr(inverter, attr)) is not None
        ]
        return round(sum(values), 2) if values else None

    @property
    def power_kw(self) -> float | None:
        """Combined AC power of every inverter, in kW."""
        return self._sum("power_kw")

    @property
    def energy_today_kwh(self) -> float | None:
        """Combined energy generated today, in kWh."""
        return self._sum("energy_today_kwh")

    @property
    def energy_total_kwh(self) -> float | None:
        """Combined lifetime energy, in kWh."""
        return self._sum("energy_total_kwh")

    @property
    def is_online(self) -> bool:
        """Whether any inverter is currently reporting."""
        return any(inverter.is_online for inverter in self.inverters)


class SunWegClient:
    """Talks to the SunWEG API, holding on to a token between calls."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._login_lock = asyncio.Lock()
        self.user_id: int | None = None

    @staticmethod
    def _token_expiry(token: str) -> datetime | None:
        """Read `exp` out of the JWT payload without verifying the signature.

        Only used to refresh early; the server remains the authority.
        """
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return datetime.fromtimestamp(float(claims["exp"]), tz=timezone.utc)
        except (IndexError, KeyError, ValueError, TypeError, binascii.Error):
            return None

    async def login(self) -> None:
        """Exchange the credentials for a token."""
        payload = {
            "usuario": self._username,
            "senha": self._password,
            "rememberMe": True,
            "aceito": False,
        }
        try:
            async with self._session.post(
                f"{API_BASE}/login/autenticacao",
                json=payload,
                headers={"Origin": API_ORIGIN, "Referer": f"{API_ORIGIN}/"},
                timeout=_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise SunWegAuthError("Credentials rejected")
                response.raise_for_status()
                data = await response.json(content_type=None)
        except SunWegError:
            raise
        except aiohttp.ClientError as err:
            raise SunWegConnectionError(f"Could not reach SunWEG: {err}") from err
        except (TimeoutError, json.JSONDecodeError, ValueError) as err:
            raise SunWegConnectionError(f"Bad response from SunWEG: {err}") from err

        # A wrong password comes back as HTTP 200 with success=false, so the
        # status code alone is not enough to tell auth failures apart.
        if not data.get("success") or not (token := data.get("token")):
            raise SunWegAuthError(f"Login failed: {data.get('erro', 'unknown error')}")

        self._token = token
        self._token_expires = self._token_expiry(token)
        self.user_id = (data.get("usuario") or {}).get("id")

    def _token_is_stale(self) -> bool:
        """Whether the token is missing or close enough to expiry to renew."""
        if self._token is None:
            return True
        if self._token_expires is None:
            return False
        return datetime.now(timezone.utc) >= self._token_expires - _TOKEN_LEEWAY

    async def _async_ensure_token(self, used_token: str | None = None) -> None:
        """Log in, unless another request already did it for us.

        Plants are fetched concurrently, so without this every one of them
        would kick off its own login the moment the token expires.
        """
        async with self._login_lock:
            if used_token is not None:
                # Refresh only if nobody replaced the token we just failed with.
                if self._token != used_token:
                    return
            elif not self._token_is_stale():
                return
            await self.login()

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Perform an authenticated GET, logging in again if the token died."""
        if self._token_is_stale():
            await self._async_ensure_token()

        for attempt in (1, 2):
            token = self._token or ""
            try:
                async with self._session.get(
                    f"{API_BASE}/{path}",
                    params=params,
                    headers={
                        "X-Auth-Token-Update": token,
                        "Origin": API_ORIGIN,
                        "Referer": f"{API_ORIGIN}/",
                    },
                    timeout=_TIMEOUT,
                ) as response:
                    if response.status in (401, 403):
                        # The token was revoked early. Renew it once, then give up.
                        if attempt == 1:
                            _LOGGER.debug("Token rejected, logging in again")
                            await self._async_ensure_token(used_token=token)
                            continue
                        raise SunWegAuthError("Token rejected after re-login")
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except SunWegError:
                raise
            except aiohttp.ClientError as err:
                raise SunWegConnectionError(f"Request to {path} failed: {err}") from err
            except (TimeoutError, json.JSONDecodeError, ValueError) as err:
                raise SunWegConnectionError(f"Bad response from {path}: {err}") from err

        raise SunWegConnectionError(f"Request to {path} failed")

    async def async_list_plants(self) -> dict[int, str]:
        """Return the plants on the account, as {id: name}."""
        data = await self._request(
            "getdadosresumo",
            {
                "usina": "",
                "id": "",
                "situacao": "null",
                "limite": 200,
                "quantidade": 0,
                "paginaAtual": 1,
                "agrupado": "false",
                "gettotalizadores": "false",
            },
        )
        return {
            int(plant["id"]): str(plant.get("nome") or f"Plant {plant['id']}")
            for plant in data.get("usinas") or []
            if plant.get("id") is not None
        }

    async def async_get_plant(self, plant_id: int) -> Plant:
        """Fetch one plant with the live reading of each of its inverters."""
        data = await self._request(
            "viewresumov2", {"id": plant_id, "agrupado": "false"}
        )
        return parse_plant(data, plant_id)


def parse_plant(data: dict[str, Any], plant_id: int) -> Plant:
    """Turn a `viewresumov2` response into a Plant."""
    tz_offset = data.get("plant_tz")

    inverters: list[Inverter] = []
    for raw in data.get("inversores") or []:
        if raw.get("id") is None:
            continue
        # Decommissioned inverters linger in the response with a null reading;
        # they are kept here and filtered out when entities are created.
        reading = raw.get("ulleitura") or {}
        params = raw.get("parametros") or {}
        inverters.append(
            Inverter(
                id=int(raw["id"]),
                name=str(raw.get("nome") or f"Inverter {raw['id']}"),
                serial=raw.get("esn"),
                model=raw.get("modelo"),
                capacity_kw=_as_float(params.get("potenciaInstalada")),
                status=raw.get("status"),
                mppt_count=int(_as_float(params.get("numMPPT")) or 0),
                last_reading=_reading_timestamp(reading.get("tsleitura"), tz_offset),
                reading=reading,
            )
        )

    return Plant(
        id=int(data.get("id", plant_id)),
        name=str(data.get("nome") or f"Plant {plant_id}"),
        capacity_kw=_as_float(data.get("capacidade")),
        energy_month_kwh=_as_float(data.get("emonth")),
        energy_year_kwh=_as_float(data.get("eyear")),
        co2_avoided_kg=_as_float(data.get("co2_evitado")),
        trees_planted=_as_float(data.get("arvores_plantadas")),
        last_update=_http_timestamp(data.get("cache_updated_at")),
        inverters=inverters,
    )
