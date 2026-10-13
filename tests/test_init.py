"""The decide service, the standing questions and the Frigate trigger."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from decisionnode import Image
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.decisionnode.const import DOMAIN, EVENT_DECISION
from custom_components.decisionnode.frigate import FrigateTrigger

from .conftest import GOOD_KEY, JPEG

QUESTIONS = {"package": {"type": "truth", "instructions": "Is a package on the doorstep?"}}


async def _setup(hass: HomeAssistant, options: dict[str, Any] | None = None, key: str = GOOD_KEY) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: key, "model": "decisionnode-moe"}, options=options or {})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_decide_returns_answers_and_fires_event(hass: HomeAssistant, mock_api: Any) -> None:
    await _setup(hass)
    events = async_capture_events(hass, EVENT_DECISION)
    with patch("custom_components.decisionnode.async_camera_image", return_value=Image("image", data=JPEG)):
        result = await hass.services.async_call(
            DOMAIN, "decide", {"camera_entity_id": "camera.front", "questions": QUESTIONS}, blocking=True, return_response=True
        )
    assert result["answers"] == {"package": {"type": "truth", "truth": 0.9}}
    assert result["model"] == "decisionnode-moe-0.9.0"
    assert result["request_id"] == "req_test"
    sent = mock_api.decides()[0]
    assert sent["questions"] == QUESTIONS
    assert base64.b64decode(sent["images"][0]["data"]) == JPEG
    await hass.async_block_till_done()
    assert events[0].data["source"] == "service"
    assert events[0].data["answers"] == result["answers"]


async def test_decide_with_image_url_and_state(hass: HomeAssistant, mock_api: Any) -> None:
    await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        "decide",
        {"image_url": "https://files.example.com/door.jpg", "state": "Front door", "questions": QUESTIONS},
        blocking=True,
        return_response=True,
    )
    sent = mock_api.decides()[0]
    assert sent["images"] == [{"id": "image", "url": "https://files.example.com/door.jpg"}]
    assert sent["state"] == "Front door"


async def test_decide_refused_key_starts_reauth(hass: HomeAssistant, mock_api: Any) -> None:
    entry = await _setup(hass, key="dn_revoked")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "decide", {"questions": QUESTIONS}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert any(flow["context"]["source"] == "reauth" for flow in entry.async_get_active_flows(hass, {"reauth"}))


async def test_standing_question_sensors(hass: HomeAssistant, mock_api: Any) -> None:
    options = {
        "standing_questions": [
            {"name": "Package", "question": {"type": "truth", "instructions": "A package?"}, "interval": 60, "threshold": 0.8},
            {
                "name": "Weather",
                "question": {"type": "choice", "instructions": "Weather?", "criteria": {"sunny": None, "rain": None}},
                "interval": 60,
                "threshold": 0.5,
            },
        ],
        "frigate": {},
    }
    await _setup(hass, options)
    package = hass.states.get("binary_sensor.decisionnode_package")
    assert package.state == "on"
    assert package.attributes["truth"] == 0.9
    weather = hass.states.get("sensor.decisionnode_weather")
    assert weather.state == "sunny"


async def test_frigate_event_asks_on_the_snapshot(hass: HomeAssistant, mock_api: Any, aioclient_mock: Any) -> None:
    frigate = {
        "enabled": True,
        "topic": "frigate/events",
        "frigate_url": "http://frigate.local:5000",
        "labels": ["person"],
        "cameras": [],
        "event_type": "new",
        "cooldown": 30,
        "questions": {"courier": {"type": "truth", "instructions": "Is this a courier?"}},
    }
    entry = await _setup(hass, {"standing_questions": [], "frigate": frigate})
    aioclient_mock.get("http://frigate.local:5000/api/events/e1/snapshot.jpg", content=JPEG)
    events = async_capture_events(hass, EVENT_DECISION)
    trigger = FrigateTrigger(hass, entry, frigate)
    message = {"type": "new", "after": {"id": "e1", "camera": "front", "label": "person"}}
    await trigger.on_message(SimpleNamespace(payload=json.dumps(message)))
    await hass.async_block_till_done()
    assert events[0].data["source"] == "frigate"
    assert events[0].data["event_id"] == "e1"
    assert events[0].data["answers"]["courier"]["truth"] == 0.9
    assert base64.b64decode(mock_api.decides()[0]["images"][0]["data"]) == JPEG
    # The same camera within the cooldown, and another label, ask nothing more.
    await trigger.on_message(SimpleNamespace(payload=json.dumps(message)))
    await trigger.on_message(SimpleNamespace(payload=json.dumps({"type": "new", "after": {"id": "e2", "camera": "back", "label": "car"}})))
    assert len(mock_api.decides()) == 1


async def test_unload_closes_the_client(hass: HomeAssistant, mock_api: Any) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
