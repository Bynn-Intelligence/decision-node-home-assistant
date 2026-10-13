"""DecisionNode: ask the decision engine calibrated questions about your cameras."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import voluptuous as vol
from decisionnode import AuthenticationError, DecisionNodeError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import Asker, async_camera_image, async_create_client, async_path_image, decision_dict, url_image
from .const import CONF_MODEL, DEFAULT_MODEL, DOMAIN, EVENT_DECISION, SERVICE_DECIDE

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_CONFIG_ENTRY = "config_entry_id"
ATTR_CAMERA = "camera_entity_id"
ATTR_IMAGE_URL = "image_url"
ATTR_IMAGE_PATH = "image_path"
ATTR_QUESTIONS = "questions"
ATTR_STATE = "state"
ATTR_MODEL = "model"

DECIDE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
        vol.Optional(ATTR_CAMERA): cv.entity_id,
        vol.Optional(ATTR_IMAGE_URL): cv.string,
        vol.Optional(ATTR_IMAGE_PATH): cv.string,
        vol.Required(ATTR_QUESTIONS): vol.All(dict, vol.Length(min=1)),
        vol.Optional(ATTR_STATE): vol.Any(str, dict, list),
        vol.Optional(ATTR_MODEL): cv.string,
    }
)


@dataclass
class DecisionNodeData:
    """What one config entry holds while it is loaded."""

    asker: Asker
    unsubscribe: list[Callable[[], None]] = field(default_factory=list)


type DecisionNodeConfigEntry = ConfigEntry[DecisionNodeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the decide service, once for every entry."""

    async def decide(call: ServiceCall) -> ServiceResponse:
        entry = _entry_for(hass, call.data.get(ATTR_CONFIG_ENTRY))
        images = []
        if camera := call.data.get(ATTR_CAMERA):
            images.append(await async_camera_image(hass, camera))
        elif url := call.data.get(ATTR_IMAGE_URL):
            images.append(url_image(url))
        elif path := call.data.get(ATTR_IMAGE_PATH):
            images.append(await async_path_image(hass, path))
        try:
            decision = await entry.runtime_data.asker.decide(
                call.data[ATTR_QUESTIONS], images, call.data.get(ATTR_STATE), call.data.get(ATTR_MODEL)
            )
        except AuthenticationError as err:
            entry.async_start_reauth(hass)
            raise HomeAssistantError("DecisionNode refused the API key") from err
        except DecisionNodeError as err:
            raise HomeAssistantError(f"DecisionNode: {err.error_type or err.status}: {err.message}") from err
        result = decision_dict(decision)
        source = {"source": "service", "camera_entity_id": call.data.get(ATTR_CAMERA)}
        hass.bus.async_fire(EVENT_DECISION, {**source, **result})
        return result

    hass.services.async_register(
        DOMAIN, SERVICE_DECIDE, decide, schema=DECIDE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    return True


def _entry_for(hass: HomeAssistant, entry_id: str | None) -> DecisionNodeConfigEntry:
    entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError("No loaded DecisionNode entry")
    return entries[0]


async def async_setup_entry(hass: HomeAssistant, entry: DecisionNodeConfigEntry) -> bool:
    """Set up one DecisionNode account."""
    model = entry.data.get(CONF_MODEL) or DEFAULT_MODEL
    client = await async_create_client(hass, entry.data[CONF_API_KEY], model)
    entry.runtime_data = DecisionNodeData(asker=Asker(client, model))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from .frigate import async_setup_frigate  # noqa: PLC0415 - mqtt is optional

    if unsub := await async_setup_frigate(hass, entry):
        entry.runtime_data.unsubscribe.append(unsub)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: DecisionNodeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DecisionNodeConfigEntry) -> bool:
    """Unload one account and close its connections."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        for unsub in entry.runtime_data.unsubscribe:
            unsub()
        await entry.runtime_data.asker.client.close()
    return unloaded

