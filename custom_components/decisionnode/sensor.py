"""Standing choice, score and number questions as sensors, and the last Frigate decision."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_FRIGATE, CONF_STANDING, DOMAIN
from .entity import StandingCoordinator, StandingEntity

VALUE_FIELD = {"choice": "choice", "score": "score", "number": "number"}
FRIGATE_SIGNAL = f"{DOMAIN}_frigate_{{}}"


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entities: list[SensorEntity] = []
    for standing in entry.options.get(CONF_STANDING, []):
        if standing["question"]["type"] not in VALUE_FIELD:
            continue
        coordinator = StandingCoordinator(hass, entry, standing)
        await coordinator.async_config_entry_first_refresh()
        entities.append(StandingSensor(coordinator))
    if entry.options.get(CONF_FRIGATE, {}).get("enabled"):
        entities.append(FrigateDecisionSensor(entry.entry_id))
    async_add_entities(entities)


class StandingSensor(StandingEntity, SensorEntity):
    """The answer's value: the choice, the score or the number."""

    @property
    def native_value(self) -> Any:
        answer = self.answer
        if answer is None:
            return None
        return answer.get(VALUE_FIELD[self.coordinator.standing["question"]["type"]])


class FrigateDecisionSensor(SensorEntity):
    """The last decision a Frigate event asked for: the event id, the answers in its attributes."""

    _attr_has_entity_name = True
    _attr_name = "Last Frigate decision"
    _attr_should_poll = False

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_frigate_last"
        self._attr_native_value = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, FRIGATE_SIGNAL.format(self._entry_id), self._update)
        )

    @callback
    def _update(self, data: dict[str, Any]) -> None:
        self._attr_native_value = data.get("event_id")
        self._attr_extra_state_attributes = {
            k: data.get(k) for k in ("camera", "label", "model", "answers", "request_id")
        }
        self.async_write_ha_state()
