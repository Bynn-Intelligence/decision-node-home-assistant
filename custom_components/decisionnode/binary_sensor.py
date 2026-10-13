"""Standing yes-or-no questions as binary sensors: on when the probability reaches the threshold."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_STANDING
from .entity import StandingCoordinator, StandingEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    entities = []
    for standing in entry.options.get(CONF_STANDING, []):
        if standing["question"]["type"] != "truth":
            continue
        coordinator = StandingCoordinator(hass, entry, standing)
        await coordinator.async_config_entry_first_refresh()
        entities.append(StandingBinarySensor(coordinator))
    async_add_entities(entities)


class StandingBinarySensor(StandingEntity, BinarySensorEntity):
    """A truth question: `truth` is the probability that the answer is yes."""

    @property
    def is_on(self) -> bool | None:
        answer = self.answer
        if answer is None or not isinstance(answer.get("truth"), (int, float)):
            return None
        return answer["truth"] >= self.coordinator.standing["threshold"]
