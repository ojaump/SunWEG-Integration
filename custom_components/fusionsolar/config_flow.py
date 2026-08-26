"""Config flow for the FusionSolar integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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

from .api import FusionSolarAuthError, FusionSolarClient, FusionSolarConnectionError
from .const import (
    CONF_FLOW_INTERVAL,
    CONF_HOST,
    CONF_PLANTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_FLOW_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_FLOW_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_FLOW_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import FusionSolarConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
        vol.Required(CONF_HOST, default=DEFAULT_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
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
                SelectOptionDict(value=dn, label=name) for dn, name in plants.items()
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def _options_schema(plants: dict[str, str], current: Mapping[str, Any]) -> vol.Schema:
    """Build the plant-and-intervals form, shared by setup and options."""
    return vol.Schema(
        {
            vol.Required(
                CONF_PLANTS,
                default=list(current.get(CONF_PLANTS, list(plants))),
            ): _plants_selector(plants),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): _interval_selector(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL),
            vol.Required(
                CONF_FLOW_INTERVAL,
                default=current.get(CONF_FLOW_INTERVAL, DEFAULT_FLOW_INTERVAL),
            ): _interval_selector(MIN_FLOW_INTERVAL, MAX_FLOW_INTERVAL),
        }
    )


def _options_from(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise the form values into entry options."""
    return {
        CONF_PLANTS: user_input[CONF_PLANTS],
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
        CONF_FLOW_INTERVAL: int(user_input[CONF_FLOW_INTERVAL]),
    }


async def _async_authenticate(
    hass: HomeAssistant, host: str, username: str, password: str
) -> dict[str, str]:
    """Log in and list the plants, then drop the session again."""
    # Not tied to a config entry yet, so this one has to be detached by hand.
    session = async_create_clientsession(hass, auto_cleanup=False)
    try:
        client = FusionSolarClient(session, host, username, password)
        await client.login()
        return await client.async_list_plants()
    finally:
        session.detach()


class FusionSolarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the FusionSolar config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._host: str = DEFAULT_HOST
        self._username: str = ""
        self._password: str = ""
        self._plants: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the FusionSolar credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST].rstrip("/")
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                self._plants = await _async_authenticate(
                    self.hass, self._host, self._username, self._password
                )
            except FusionSolarAuthError:
                errors["base"] = "invalid_auth"
            except FusionSolarConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during FusionSolar login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{self._host}:{self._username}")
                self._abort_if_unique_id_configured()
                if not self._plants:
                    return self.async_abort(reason="no_plants")
                return await self.async_step_plants()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_plants(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which plants to create entities for."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._username,
                data={
                    CONF_HOST: self._host,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                },
                options=_options_from(user_input),
            )

        return self.async_show_form(
            step_id="plants", data_schema=_options_schema(self._plants, {})
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a session failure at runtime."""
        self._host = entry_data.get(CONF_HOST, DEFAULT_HOST)
        self._username = entry_data[CONF_USERNAME]
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
                    self.hass, self._host, self._username, password
                )
            except FusionSolarAuthError:
                errors["base"] = "invalid_auth"
            except FusionSolarConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during FusionSolar reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
            description_placeholders={CONF_USERNAME: self._username},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: FusionSolarConfigEntry) -> FusionSolarOptionsFlow:
        """Get the options flow."""
        return FusionSolarOptionsFlow()


class FusionSolarOptionsFlow(OptionsFlow):
    """Change the poll intervals and the selected plants after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=_options_from(user_input))

        errors: dict[str, str] = {}
        entry = self.config_entry
        try:
            plants = await _async_authenticate(
                self.hass,
                entry.data.get(CONF_HOST, DEFAULT_HOST),
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
            )
        except (FusionSolarAuthError, FusionSolarConnectionError):
            # Offer the plants already configured rather than blocking a change
            # of interval while the cloud is unreachable.
            plants = {dn: dn for dn in entry.options.get(CONF_PLANTS, [])}
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(plants, entry.options),
            errors=errors,
        )
