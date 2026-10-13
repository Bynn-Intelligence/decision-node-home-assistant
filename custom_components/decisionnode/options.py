"""The options: standing questions and the Frigate trigger, checked before they are saved."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_FRIGATE_COOLDOWN,
    DEFAULT_FRIGATE_TOPIC,
    DEFAULT_INTERVAL,
    DEFAULT_THRESHOLD,
    MIN_INTERVAL,
)

STANDING_TYPES = ("truth", "choice", "score", "number")

QUESTION = vol.Schema(
    {vol.Required("type"): cv.string, vol.Required("instructions"): vol.Any(str, dict, list)},
    extra=vol.ALLOW_EXTRA,
)

STANDING = vol.Schema(
    {
        vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=64)),
        vol.Exclusive("camera", "picture"): cv.entity_domain("camera"),
        vol.Exclusive("image_url", "picture"): cv.url,
        vol.Optional("state"): vol.Any(str, dict, list),
        vol.Required("question"): QUESTION,
        vol.Optional("interval", default=DEFAULT_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=MIN_INTERVAL)),
        vol.Optional("threshold", default=DEFAULT_THRESHOLD): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
    }
)

FRIGATE = vol.Schema(
    {
        vol.Optional("enabled", default=False): cv.boolean,
        vol.Optional("topic", default=DEFAULT_FRIGATE_TOPIC): cv.string,
        vol.Optional("frigate_url"): cv.url,
        vol.Optional("labels", default=["person"]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("cameras", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("event_type", default="new"): vol.In(["new", "update", "end"]),
        vol.Optional("cooldown", default=DEFAULT_FRIGATE_COOLDOWN): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("state"): vol.Any(str, dict, list),
        vol.Optional("questions", default={}): {cv.string: QUESTION},
    }
)


class OptionsError(Exception):
    """An option that cannot be saved; key is the form's error key."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def validate_standing(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise OptionsError("standing_not_a_list")
    try:
        items = [STANDING(item) for item in value]
    except vol.Invalid as err:
        raise OptionsError("standing_invalid") from err
    names = [item["name"] for item in items]
    if len(set(names)) != len(names):
        raise OptionsError("standing_duplicate_name")
    if any(item["question"]["type"] not in STANDING_TYPES for item in items):
        raise OptionsError("standing_type")
    return items


def validate_frigate(value: Any) -> dict[str, Any]:
    try:
        frigate = FRIGATE(value)
    except vol.Invalid as err:
        raise OptionsError("frigate_invalid") from err
    if frigate["enabled"] and (not frigate.get("frigate_url") or not frigate["questions"]):
        raise OptionsError("frigate_incomplete")
    return frigate
