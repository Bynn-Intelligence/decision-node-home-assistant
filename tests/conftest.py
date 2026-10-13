"""Fixtures: a mocked DecisionNode API behind the real SDK."""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from decisionnode import AsyncDecisionNode

GOOD_KEY = "dn_test_good"
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDgKKKK+eP2E//Z"
)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Load custom_components/ in every test."""


class MockAPI:
    """Answers /v1/models and /v1/decide, and keeps every request it was sent."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.truth = 0.9

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {GOOD_KEY}":
            return httpx.Response(401, json={"detail": {"error_type": "authentication_error", "message": "Invalid key"}})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"models": [{"name": "decisionnode-moe", "description": "", "release_date": "2026-10-01"}]})
        if request.url.path == "/v1/decide":
            body = json.loads(request.content)
            answers = {}
            for qid, q in body["questions"].items():
                if q["type"] == "truth":
                    answers[qid] = {"type": "truth", "truth": self.truth}
                elif q["type"] == "choice":
                    first = next(iter(q["criteria"]))
                    answers[qid] = {"type": "choice", "choice": first, "confidence": 0.8, "probabilities": {first: 0.8}}
                else:
                    answers[qid] = {"type": "number", "number": 3, "expected": 3.1, "confidence": 0.7, "probabilities": {"3": 0.7}}
            return httpx.Response(
                200,
                json={"model": "decisionnode-moe-0.9.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 0}},
                headers={"x-request-id": "req_test"},
            )
        return httpx.Response(404, json={"detail": "Not found"})

    def decides(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.url.path == "/v1/decide"]


@pytest.fixture
def mock_api() -> Any:
    api = MockAPI()

    def make(api_key: str, model: str) -> AsyncDecisionNode:
        return AsyncDecisionNode(
            api_key=api_key, model=model, max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(api.handler))
        )

    with patch("custom_components.decisionnode.api._make_client", side_effect=make), patch(
        "custom_components.decisionnode.api.MIN_SPACING", 0
    ):
        yield api
