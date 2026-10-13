"""Standing questions: one question asked again and again, as a sensor."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from decisionnode import AuthenticationError, DecisionNodeError

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

from .api import async_camera_image, decision_dict, url_image
from .const import DOMAIN, EVENT_DECISION

_LOGGER = logging.getLogger(__name__)

QUESTION_ID = "q"


class StandingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Asks one standing question every `interval` seconds."""

    def __init__(self, hass: HomeAssistant, entry: Any, standing: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {standing['name']}",
            update_interval=timedelta(seconds=standing["interval"]),
        )
        self.standing = standing

    async def _async_update_data(self) -> dict[str, Any]:
        standing = self.standing
        images = []
        try:
            if camera := standing.get("camera"):
                images.append(await async_camera_image(self.hass, camera))
            elif url := standing.get("image_url"):
                images.append(url_image(url))
            decision = await self.config_entry.runtime_data.asker.decide(
                {QUESTION_ID: standing["question"]}, images, standing.get("state")
            )
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("DecisionNode refused the API key") from err
        except DecisionNodeError as err:
            raise UpdateFailed(f"{err.error_type or err.status}: {err.message}") from err
        result = decision_dict(decision)
        self.hass.bus.async_fire(
            EVENT_DECISION, {"source": "standing", "name": standing["name"], **result}
        )
        return result


class StandingEntity(CoordinatorEntity[StandingCoordinator]):
    """The common part of a standing question's entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: StandingCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        name = coordinator.standing["name"]
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="DecisionNode",
            manufacturer="Bynn Intelligence, Inc.",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def answer(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        answer = data.get("answers", {}).get(QUESTION_ID)
        return answer if isinstance(answer, dict) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"question": self.coordinator.standing["question"].get("instructions")}
        if self.answer is not None:
            attrs.update({k: v for k, v in self.answer.items() if k != "type"})
        if self.coordinator.data:
            attrs["model"] = self.coordinator.data.get("model")
        return attrs
