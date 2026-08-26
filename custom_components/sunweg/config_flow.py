"""Config flow for the SunWEG / FusionSolar integration.

The two clouds share nothing but the shape of the flow: pick a provider, sign
in, then choose plants and intervals.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_PLANTS,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    PROVIDER_HUAWEI,
    PROVIDER_WEG,
)
from .huawei import const as huawei_const
from .huawei.api import (
    FusionSolarAuthError,
    FusionSolarClient,
    FusionSolarConnectionError,
)
from .weg import const as weg_const
from .weg.api import SunWegAuthError, SunWegClient, SunWegConnectionError

_LOGGER = logging.getLogger(__name__)

# One flow, two client libraries, so each failure mode comes in two flavours.
AUTH_ERRORS = (SunWegAuthError, FusionSolarAuthError)
CONNECTION_ERRORS = (SunWegConnectionError, FusionSolarConnectionError)

_PASSWORD = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)

WEG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): _PASSWORD,
    }
)

HUAWEI_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): _PASSWORD,
        vol.Required(
            huawei_const.CONF_HOST, default=huawei_const.DEFAULT_HOST
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
    }
)


def _interval_selector(minimum: int, maximum: int) -> NumberSelector:
    """Build a poll-interval selector, in seconds."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


def _plants_selector(plants: dict[str, str]) -> SelectSelector:
    """Build the multi-select of plants on the account."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=key, label=name) for key, name in plants.items()
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def _options_schema(
    provider: str, plants: dict[str, str], current: Mapping[str, Any]
) -> vol.Schema:
    """Build the plants-and-intervals form, shared by setup and options."""
    const = huawei_const if provider == PROVIDER_HUAWEI else weg_const
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_PLANTS, default=list(current.get(CONF_PLANTS, list(plants)))
        ): _plants_selector(plants),
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=current.get(CONF_SCAN_INTERVAL, const.DEFAULT_SCAN_INTERVAL),
        ): _interval_selector(const.MIN_SCAN_INTERVAL, const.MAX_SCAN_INTERVAL),
    }
    if provider == PROVIDER_HUAWEI:
        schema[
            vol.Required(
                huawei_const.CONF_FLOW_INTERVAL,
                default=current.get(
                    huawei_const.CONF_FLOW_INTERVAL, huawei_const.DEFAULT_FLOW_INTERVAL
                ),
            )
        ] = _interval_selector(
            huawei_const.MIN_FLOW_INTERVAL, huawei_const.MAX_FLOW_INTERVAL
        )
    return vol.Schema(schema)


def _options_from(provider: str, user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise the form values into entry options."""
    options = {
        CONF_PLANTS: user_input[CONF_PLANTS],
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
    }
    if provider == PROVIDER_HUAWEI:
        options[huawei_const.CONF_FLOW_INTERVAL] = int(
            user_input[huawei_const.CONF_FLOW_INTERVAL]
        )
    return options


async def _async_authenticate(
    hass: HomeAssistant, provider: str, data: Mapping[str, Any]
) -> tuple[str | None, dict[str, str]]:
    """Sign in and list the plants, as (unique id, {plant key: name}).

    The plant key is what ends up in the options and in every unique id, so it
    is kept as a string for both clouds even though WEG numbers its plants.
    """
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    if provider == PROVIDER_HUAWEI:
        host = data.get(huawei_const.CONF_HOST, huawei_const.DEFAULT_HOST)
        # Cookie-based, and not tied to a config entry yet, so this session has
        # to be kept apart from the shared one and detached by hand.
        session = async_create_clientsession(hass, auto_cleanup=False)
        try:
            client = FusionSolarClient(session, host, username, password)
            await client.login()
            return f"{host}:{username}", await client.async_list_plants()
        finally:
            session.detach()

    weg_client = SunWegClient(async_get_clientsession(hass), username, password)
    await weg_client.login()
    plants = await weg_client.async_list_plants()
    unique_id = None if weg_client.user_id is None else str(weg_client.user_id)
    return unique_id, {str(key): name for key, name in plants.items()}


class SunWegConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the SunWEG / FusionSolar config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._provider: str = PROVIDER_WEG
        self._credentials: dict[str, Any] = {}
        self._plants: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which cloud the inverters report to."""
        return self.async_show_menu(
            step_id="user", menu_options=[PROVIDER_WEG, PROVIDER_HUAWEI]
        )

    async def async_step_weg(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the sun.weg.net credentials."""
        return await self._async_step_credentials(PROVIDER_WEG, WEG_SCHEMA, user_input)

    async def async_step_huawei(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the FusionSolar credentials and server."""
        return await self._async_step_credentials(
            PROVIDER_HUAWEI, HUAWEI_SCHEMA, user_input
        )

    async def _async_step_credentials(
        self, provider: str, schema: vol.Schema, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Sign in, then move on to the plant selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._provider = provider
            self._credentials = dict(user_input)
            if host := self._credentials.get(huawei_const.CONF_HOST):
                self._credentials[huawei_const.CONF_HOST] = host.rstrip("/")
            try:
                unique_id, self._plants = await _async_authenticate(
                    self.hass, provider, self._credentials
                )
            except AUTH_ERRORS:
                errors["base"] = "invalid_auth"
            except CONNECTION_ERRORS:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                if unique_id is not None:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                if not self._plants:
                    return self.async_abort(reason="no_plants")
                return await self.async_step_plants()

        return self.async_show_form(step_id=provider, data_schema=schema, errors=errors)

    async def async_step_plants(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which plants to create entities for."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._credentials[CONF_USERNAME],
                data={CONF_PROVIDER: self._provider, **self._credentials},
                options=_options_from(self._provider, user_input),
            )

        return self.async_show_form(
            step_id="plants",
            data_schema=_options_schema(self._provider, self._plants, {}),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a credential or session failure at runtime."""
        self._provider = entry_data.get(CONF_PROVIDER, PROVIDER_WEG)
        self._credentials = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await _async_authenticate(
                    self.hass,
                    self._provider,
                    {**self._credentials, CONF_PASSWORD: password},
                )
            except AUTH_ERRORS:
                errors["base"] = "invalid_auth"
            except CONNECTION_ERRORS:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            description_placeholders={
                CONF_USERNAME: self._credentials.get(CONF_USERNAME, "")
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> SunWegOptionsFlow:
        """Get the options flow."""
        return SunWegOptionsFlow()


class SunWegOptionsFlow(OptionsFlow):
    """Change the poll intervals and the selected plants after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        provider = entry.data.get(CONF_PROVIDER, PROVIDER_WEG)

        if user_input is not None:
            return self.async_create_entry(data=_options_from(provider, user_input))

        errors: dict[str, str] = {}
        try:
            _, plants = await _async_authenticate(self.hass, provider, entry.data)
        except (*AUTH_ERRORS, *CONNECTION_ERRORS):
            # Offer the plants already configured rather than blocking a change
            # of interval while the cloud is unreachable.
            plants = {key: key for key in entry.options.get(CONF_PLANTS, [])}
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(provider, plants, entry.options),
            errors=errors,
        )
