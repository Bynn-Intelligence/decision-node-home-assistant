"""Config, reauth and options flows of the DecisionNode integration."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from decisionnode import AuthenticationError, DecisionNodeError

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    ObjectSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import async_create_client
from .const import CONF_FRIGATE, CONF_MODEL, CONF_STANDING, DEFAULT_MODEL, DOMAIN
from .options import OptionsError, validate_frigate, validate_standing

KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(flow: ConfigFlow, api_key: str, model: str) -> str | None:
    """None when the key works, else the error key for the form."""
    client = await async_create_client(flow.hass, api_key, model)
    try:
        await client.models()
    except AuthenticationError:
        return "invalid_auth"
    except DecisionNodeError:
        return "cannot_connect"
    finally:
        await client.close()
    return None


def _unique_id(api_key: str) -> str:
    # A digest, so the entry's unique id never shows the key.
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


class DecisionNodeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a DecisionNode account."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            model = user_input.get(CONF_MODEL) or DEFAULT_MODEL
            error = await _validate(self, user_input[CONF_API_KEY], model)
            if error is None:
                await self.async_set_unique_id(_unique_id(user_input[CONF_API_KEY]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="DecisionNode", data={CONF_API_KEY: user_input[CONF_API_KEY], CONF_MODEL: model}
                )
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): KEY_SELECTOR,
                vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            model = entry.data.get(CONF_MODEL) or DEFAULT_MODEL
            error = await _validate(self, user_input[CONF_API_KEY], model)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DecisionNodeOptionsFlow()


class DecisionNodeOptionsFlow(OptionsFlow):
    """Standing questions and the Frigate trigger, edited as YAML."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.options
        if user_input is not None:
            try:
                standing = validate_standing(user_input.get(CONF_STANDING) or [])
                frigate = validate_frigate(user_input.get(CONF_FRIGATE) or {})
            except OptionsError as err:
                errors["base"] = err.key
            else:
                return self.async_create_entry(data={CONF_STANDING: standing, CONF_FRIGATE: frigate})
        schema = vol.Schema(
            {
                vol.Optional(CONF_STANDING, default=current.get(CONF_STANDING, [])): ObjectSelector(),
                vol.Optional(CONF_FRIGATE, default=current.get(CONF_FRIGATE, {})): ObjectSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
