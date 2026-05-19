"""Config flow for LK Марьино.net integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import MarynoNetApiClient
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("scan_interval", default=SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=60, max=3600)
        ),
        vol.Optional("verify_ssl", default=True): bool,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required("scan_interval"): vol.All(
            vol.Coerce(int), vol.Range(min=60, max=3600)
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LK Марьино.net."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            api_client = MarynoNetApiClient(
                username=user_input["username"],
                password=user_input["password"],
                verify_ssl=user_input.get("verify_ssl", True),
            )
            try:
                await api_client.authenticate()
                await api_client.get_account_info()
            except Exception as ex:
                _LOGGER.error("Authentication failed: %s", ex)
                errors["base"] = "invalid_auth"
            finally:
                await api_client.close()

            if not errors:
                return self.async_create_entry(
                    title=f"LK Марьино.net ({user_input['username']})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for LK Марьино.net."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            result = self.async_create_entry(title="", data=user_input)
            # Update config_entry data and reload
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return result

        current = self.config_entry.data.get("scan_interval", SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, {"scan_interval": current}
            ),
        )


@staticmethod
@callback
def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> OptionsFlowHandler:
    """Get the options flow for this handler."""
    return OptionsFlowHandler()
