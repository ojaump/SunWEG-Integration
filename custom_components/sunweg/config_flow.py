"""Config flow for the SunWEG integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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

from .api import SunWegAuthError, SunWegClient, SunWegConnectionError
from .const import (
    CONF_PLANTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import SunWegConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


def _interval_selector() -> NumberSelector:
    """Build the poll-interval selector, in seconds."""
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=10,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


def _plants_selector(plants: dict[int, str]) -> SelectSelector:
    """Build the multi-select of plants on the account."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=str(plant_id), label=name)
                for plant_id, name in plants.items()
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


async def _async_authenticate(
    hass, username: str, password: str
) -> tuple[SunWegClient, dict[int, str]]:
    """Log in and list the plants, so both steps share one client."""
    client = SunWegClient(async_get_clientsession(hass), username, password)
    await client.login()
    return client, await client.async_list_plants()


class SunWegConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the SunWEG config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._username: str = ""
        self._password: str = ""
        self._plants: dict[int, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the sun.weg.net credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                client, self._plants = await _async_authenticate(
                    self.hass, self._username, self._password
                )
            except SunWegAuthError:
                errors["base"] = "invalid_auth"
            except SunWegConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during SunWEG login")
                errors["base"] = "unknown"
            else:
                if client.user_id is not None:
                    await self.async_set_unique_id(str(client.user_id))
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
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                },
                options={
                    CONF_PLANTS: user_input[CONF_PLANTS],
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLANTS, default=[str(pid) for pid in self._plants]
                ): _plants_selector(self._plants),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="plants", data_schema=schema)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a token/password failure at runtime."""
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
                await _async_authenticate(self.hass, self._username, password)
            except SunWegAuthError:
                errors["base"] = "invalid_auth"
            except SunWegConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during SunWEG reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_PASSWORD: password},
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
    def async_get_options_flow(entry: SunWegConfigEntry) -> SunWegOptionsFlow:
        """Get the options flow."""
        return SunWegOptionsFlow()


class SunWegOptionsFlow(OptionsFlow):
    """Change the poll interval and the selected plants after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_PLANTS: user_input[CONF_PLANTS],
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                }
            )

        entry = self.config_entry
        try:
            _, plants = await _async_authenticate(
                self.hass,
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
            )
        except (SunWegAuthError, SunWegConnectionError):
            # Offer the plants already configured rather than blocking the
            # user from changing the interval while the API is unreachable.
            plants = {int(pid): f"Plant {pid}" for pid in entry.options[CONF_PLANTS]}
            errors["base"] = "cannot_connect"

        current = entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLANTS, default=list(current.get(CONF_PLANTS, []))
                ): _plants_selector(plants),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
