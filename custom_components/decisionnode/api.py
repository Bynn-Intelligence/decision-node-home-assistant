"""The calls to DecisionNode: the client, the images and the rate limit."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from decisionnode import AsyncDecisionNode, Decision, Image

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import MAX_CONCURRENT, MIN_SPACING


async def async_create_client(hass: HomeAssistant, api_key: str, model: str) -> AsyncDecisionNode:
    """A client with its own connection pool.

    The SDK takes only a plain ``httpx.AsyncClient`` (it refuses any client that might
    follow redirects), and Home Assistant's shared clients are not one, so the client
    keeps its own pool. It is made in the executor because opening the TLS context reads
    certificate files, which must not run in the event loop.
    """
    return await hass.async_add_executor_job(_make_client, api_key, model)


def _make_client(api_key: str, model: str) -> AsyncDecisionNode:
    return AsyncDecisionNode(api_key=api_key, model=model)


@dataclass
class Asker:
    """Asks DecisionNode for one config entry, at most MAX_CONCURRENT at a time and
    MIN_SPACING seconds apart."""

    client: AsyncDecisionNode
    model: str
    _gate: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT))
    _spacing: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last: float = 0.0

    async def decide(
        self,
        questions: Mapping[str, Any],
        images: list[Image] | None = None,
        state: Any = None,
        model: str | None = None,
    ) -> Decision:
        async with self._gate:
            async with self._spacing:
                wait = self._last + MIN_SPACING - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            kwargs: dict[str, Any] = {"questions": dict(questions), "images": images or None, "model": model}
            if state is not None:
                kwargs["state"] = state
            return await self.client.decide(**kwargs)


async def async_camera_image(hass: HomeAssistant, entity_id: str) -> Image:
    """The current picture of a camera entity."""
    from homeassistant.components import camera  # noqa: PLC0415 - camera is an after-dependency

    picture = await camera.async_get_image(hass, entity_id)
    return Image("image", data=picture.content)


async def async_path_image(hass: HomeAssistant, path: str) -> Image:
    """A picture read from a file Home Assistant may read (allowlist_external_dirs)."""
    if not hass.config.is_allowed_path(path):
        raise HomeAssistantError(f"{path} is not in allowlist_external_dirs")
    data = await hass.async_add_executor_job(Path(path).read_bytes)
    return Image("image", data=data)


def url_image(url: str) -> Image:
    """A picture the DecisionNode API fetches itself (https only)."""
    return Image("image", url=url)


def decision_dict(decision: Decision) -> dict[str, Any]:
    """The decision as plain data: the answers exactly as the API sent them."""
    raw = decision.raw if isinstance(decision.raw, dict) else {}
    answers = raw.get("answers") if isinstance(raw.get("answers"), dict) else {}
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    return {
        "model": decision.model,
        "request_id": decision.request_id,
        "answers": answers,
        "usage": usage,
    }
