"""Config flow for Water Utility Sensor."""
import logging
from typing import Optional, Dict, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .const import DOMAIN
from .providers import ProviderRegistry

_LOGGER = logging.getLogger(__name__)

CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
DEFAULT_UPDATE_INTERVAL_HOURS = 24

UPDATE_INTERVAL_OPTIONS = [
    (8,   "Every 8 hours"),
    (24,  "Once a day"),
    (168, "Once a week"),
]

# The frontend hands the selected radio value back as a string, so validating it
# straight against the integer keys fails with "value must be one of [8, 24, 168]"
# on any re-render of the form (e.g. after a failed login). Coerce before checking.
UPDATE_INTERVAL_SELECTOR = vol.All(
    vol.Coerce(int),
    vol.In({hours: label for hours, label in UPDATE_INTERVAL_OPTIONS}),
)


class WaterUtilityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for water utility sensors.

    Step 1 — provider selection (shown only when more than one provider exists).
    Step 2 — credentials for the chosen provider.
    """

    def __init__(self):
        self._provider_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Step 1 — choose provider
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Show provider selector if multiple providers are registered."""
        providers = await self.hass.async_add_executor_job(
            ProviderRegistry.list_providers
        )

        if len(providers) == 1:
            # Skip selection when there is only one provider
            self._provider_id = providers[0].id
            return await self.async_step_credentials()

        errors: Dict[str, str] = {}

        if user_input is not None:
            self._provider_id = user_input["provider"]
            return await self.async_step_credentials()

        provider_choices = {p.id: p.name for p in providers}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("provider"): vol.In(provider_choices),
            }),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 — credentials
    # ------------------------------------------------------------------

    async def async_step_credentials(
        self, user_input: Optional[Dict[str, Any]] = None
    ):
        """Collect and validate credentials for the chosen provider."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")
            update_interval_hours = user_input.get(
                CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
            )

            if username and password:
                provider_class = ProviderRegistry.get(self._provider_id)
                if provider_class:
                    try:
                        _LOGGER.info(
                            "Attempting login for provider=%s user=%s",
                            self._provider_id, username,
                        )
                        provider = provider_class(username, password)
                        login_ok = await self.hass.async_add_executor_job(
                            provider.login
                        )
                        _LOGGER.info("Login result: %s", login_ok)

                        if not login_ok:
                            errors["base"] = "verify_connection_failed"
                        else:
                            await self.async_set_unique_id(
                                f"water_{self._provider_id}_{username}"
                            )
                            self._abort_if_unique_id_configured()

                            # Derive a human-readable title from provider info
                            provider_info = provider_class("", "").info
                            title = f"{provider_info.name} ({username})"

                            return self.async_create_entry(
                                title=title,
                                data={
                                    CONF_USERNAME: username,
                                    CONF_PASSWORD: password,
                                    "provider": self._provider_id,
                                },
                                options={
                                    CONF_UPDATE_INTERVAL_HOURS: update_interval_hours,
                                },
                            )
                    except Exception as exc:
                        _LOGGER.exception(
                            "Error during config flow for provider=%s: %s",
                            self._provider_id, exc,
                        )
                        errors["base"] = "verify_connection_failed"
                else:
                    errors["base"] = "unknown_provider"

        # Fetch provider name for the form description
        provider_class = ProviderRegistry.get(self._provider_id)
        provider_name = (
            provider_class("", "").info.name if provider_class else self._provider_id
        )

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=DEFAULT_UPDATE_INTERVAL_HOURS,
                ): UPDATE_INTERVAL_SELECTOR,
            }),
            errors=errors,
            description_placeholders={"provider_name": provider_name},
        )

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------

    @staticmethod
    def async_get_options_flow(config_entry):
        return WaterUtilityOptionsFlow(config_entry)


class WaterUtilityOptionsFlow(OptionsFlow):
    """Options flow — update interval only."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=current_interval,
                ): UPDATE_INTERVAL_SELECTOR,
            }),
        )
