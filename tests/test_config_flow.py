"""The config flow, its reauth and the options."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.decisionnode.const import DOMAIN

from .conftest import GOOD_KEY


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_api: Any) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: GOOD_KEY, "model": "decisionnode-moe"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: GOOD_KEY, "model": "decisionnode-moe"}
    assert mock_api.requests[0].url.path == "/v1/models"


async def test_user_flow_invalid_key(hass: HomeAssistant, mock_api: Any) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "dn_bad", "model": "decisionnode-moe"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_updates_the_key(hass: HomeAssistant, mock_api: Any) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "dn_old", "model": "decisionnode-moe"}, unique_id="x")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "dn_bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: GOOD_KEY})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == GOOD_KEY


async def test_options_validate_standing_questions(hass: HomeAssistant, mock_api: Any) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: GOOD_KEY, "model": "decisionnode-moe"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"standing_questions": [{"name": "x", "question": {"type": "point", "instructions": "?"}}]}
    )
    assert result["errors"] == {"base": "standing_type"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"standing_questions": [{"name": "Package", "question": {"type": "truth", "instructions": "A package?"}, "interval": 5}]},
    )
    assert result["errors"] == {"base": "standing_invalid"}


async def test_options_knowledge_needs_a_collection(hass: HomeAssistant, mock_api: Any) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: GOOD_KEY, "model": "decisionnode-moe"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    question = {"name": "Dishwasher", "question": {"type": "truth", "instructions": "Call a technician?"}}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"standing_questions": [{**question, "knowledge": {"scope": "kitchen"}}]}
    )
    assert result["errors"] == {"base": "standing_invalid"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"standing_questions": [], "frigate": {"knowledge": {"top_k": 2}}}
    )
    assert result["errors"] == {"base": "frigate_invalid"}
    knowledge = {"collection": "col_3f6c1a9e0b2d4c7f8a1e5d9b2c4f6a80", "scope": "kitchen", "top_k": 2, "require": True}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"standing_questions": [{**question, "knowledge": knowledge}]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["standing_questions"][0]["knowledge"] == knowledge
