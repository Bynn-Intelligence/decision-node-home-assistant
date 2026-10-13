"""The Frigate trigger: a detection asks the configured questions about its snapshot."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from decisionnode import DecisionNodeError, Image

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import decision_dict
from .const import CONF_FRIGATE, EVENT_DECISION
from .sensor import FRIGATE_SIGNAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_frigate(hass: HomeAssistant, entry: Any) -> Callable[[], None] | None:
    """Subscribe to Frigate's events when the trigger is on and MQTT is set up."""
    frigate = entry.options.get(CONF_FRIGATE) or {}
    if not frigate.get("enabled"):
        return None
    if "mqtt" not in hass.config.components:
        _LOGGER.warning("The DecisionNode Frigate trigger needs the MQTT integration, which is not set up")
        return None
    from homeassistant.components import mqtt  # noqa: PLC0415 - mqtt is an after-dependency

    trigger = FrigateTrigger(hass, entry, frigate)
    return await mqtt.async_subscribe(hass, frigate["topic"], trigger.on_message)


class FrigateTrigger:
    """Turns a Frigate event message into a decision about the event's snapshot."""

    def __init__(self, hass: HomeAssistant, entry: Any, frigate: dict[str, Any]) -> None:
        self.hass = hass
        self.entry = entry
        self.frigate = frigate
        self._last: dict[str, float] = {}

    async def on_message(self, msg: Any) -> None:
        try:
            event = json.loads(msg.payload)
        except (TypeError, ValueError):
            return
        after = event.get("after") if isinstance(event, dict) else None
        if not isinstance(after, dict) or event.get("type") != self.frigate["event_type"]:
            return
        camera, label, event_id = after.get("camera"), after.get("label"), after.get("id")
        if label not in self.frigate["labels"] or not event_id:
            return
        if self.frigate["cameras"] and camera not in self.frigate["cameras"]:
            return
        now = time.monotonic()
        if now - self._last.get(camera, -1e9) < self.frigate["cooldown"]:
            return
        self._last[camera] = now
        await self.decide(event_id, camera, label)

    async def decide(self, event_id: str, camera: str, label: str) -> None:
        url = f"{self.frigate['frigate_url'].rstrip('/')}/api/events/{event_id}/snapshot.jpg"
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, params={"bbox": "0"}) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Frigate answered %s for the snapshot of event %s", resp.status, event_id)
                    return
                picture = await resp.read()
        except Exception as err:  # noqa: BLE001 - any network fault skips this event
            _LOGGER.warning("Could not read the snapshot of Frigate event %s: %s", event_id, err)
            return
        try:
            decision = await self.entry.runtime_data.asker.decide(
                self.frigate["questions"], [Image("snapshot", data=picture)], self.frigate.get("state")
            )
        except DecisionNodeError as err:
            _LOGGER.warning("DecisionNode could not decide Frigate event %s: %s", event_id, err.error_type or err.status)
            return
        data = {"source": "frigate", "event_id": event_id, "camera": camera, "label": label, **decision_dict(decision)}
        self.hass.bus.async_fire(EVENT_DECISION, data)
        async_dispatcher_send(self.hass, FRIGATE_SIGNAL.format(self.entry.entry_id), data)
