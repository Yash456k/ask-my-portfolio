from __future__ import annotations

import json
from typing import Any

import pytest

from app.config import PipelineConfig
from app.groq_client import GroqClient, GroqStreamError


class _Response:
    def __init__(
        self,
        status_code: int,
        *,
        body: str = "",
        lines: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body.encode()
        self._lines = lines or []

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamContext:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args) -> None:
        return None


class _HttpClient:
    def __init__(self, responses: list[_Response | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def stream(self, method: str, endpoint: str, **kwargs) -> _StreamContext:
        self.calls.append({"method": method, "endpoint": endpoint, **kwargs})
        return _StreamContext(self.responses.pop(0))

    async def aclose(self) -> None:
        return None


def _client(pipeline: PipelineConfig, responses: list[_Response]) -> tuple[GroqClient, _HttpClient]:
    transport = _HttpClient(responses)
    client = object.__new__(GroqClient)
    client.api_key = "unit-test-key"
    client.api_keys = {"groq": "unit-test-key", "openrouter": "openrouter-test-key"}
    client.pipeline = pipeline
    client.client = transport
    return client, transport


def _success_lines(*tokens: str) -> list[str]:
    lines = [
        f"data: {json.dumps({'choices': [{'delta': {'content': token}}]})}" for token in tokens
    ]
    lines.append('data: {"choices":[],"usage":{"completion_tokens":2}}')
    lines.append("data: [DONE]")
    return lines


def test_candidates_preserve_selection_then_deduplicated_fallback_order(
    pipeline: PipelineConfig,
) -> None:
    client, _ = _client(pipeline, [])
    selected = "openai/gpt-oss-120b"

    assert client.candidates(selected, force_failure=False) == [
        selected,
        *pipeline.fallback_order,
    ]
    assert client.candidates(selected, force_failure=True) == [
        "verification/forced-provider-error",
        selected,
        *pipeline.fallback_order,
    ]


@pytest.mark.asyncio
async def test_forced_failure_attempt_is_visible_then_selected_model_streams(
    pipeline: PipelineConfig,
) -> None:
    selected = pipeline.llms[0].id
    error = _Response(
        404,
        body='{"error":{"message":"verification model intentionally missing"}}',
    )
    success = _Response(200, lines=_success_lines("Hello", " there"))
    client, transport = _client(pipeline, [error, success])

    events = [
        event
        async for event in client.stream(
            selected_model=selected,
            system_prompt="system",
            user_prompt="user",
            force_failure=True,
        )
    ]

    assert [call["json"]["model"] for call in transport.calls] == [
        "verification/forced-provider-error",
        selected,
    ]
    assert events[0] == {
        "type": "model",
        "requestedModel": selected,
        "servedModel": selected,
        "fallbackUsed": True,
        "attempts": [
            {
                "model": "verification/forced-provider-error",
                "status": 404,
                "reason": "provider_model_unavailable",
            }
        ],
    }
    assert [event["token"] for event in events if event["type"] == "token"] == [
        "Hello",
        " there",
    ]
    assert events[-1] == {
        "type": "usage",
        "usage": {"completion_tokens": 2},
    }


@pytest.mark.asyncio
async def test_retryable_provider_error_falls_back_in_configured_order(
    pipeline: PipelineConfig,
) -> None:
    selected = pipeline.llms[-1].id
    fallback = pipeline.fallback_order[0]
    client, transport = _client(
        pipeline,
        [
            _Response(429, body='{"error":{"message":"rate limited"}}'),
            _Response(200, lines=_success_lines("fallback answer")),
        ],
    )

    events = [
        event
        async for event in client.stream(
            selected_model=selected,
            system_prompt="system",
            user_prompt="user",
        )
    ]

    assert [call["json"]["model"] for call in transport.calls] == [selected, fallback]
    assert events[0]["servedModel"] == fallback
    assert events[0]["fallbackUsed"] is True
    assert events[0]["attempts"] == [
        {"model": selected, "status": 429, "reason": "provider_rate_limited"}
    ]


@pytest.mark.asyncio
async def test_non_retryable_rejection_does_not_spend_fallback_candidates(
    pipeline: PipelineConfig,
) -> None:
    selected = pipeline.llms[0].id
    client, transport = _client(
        pipeline,
        [_Response(400, body='{"error":{"message":"invalid request"}}')],
    )

    with pytest.raises(GroqStreamError) as captured:
        _ = [
            event
            async for event in client.stream(
                selected_model=selected,
                system_prompt="system",
                user_prompt="user",
            )
        ]

    assert len(transport.calls) == 1
    assert captured.value.attempts == [
        {"model": selected, "status": 400, "reason": "provider_request_rejected"}
    ]


@pytest.mark.asyncio
async def test_openrouter_free_uses_openrouter_endpoint_and_reports_resolved_model(
    pipeline: PipelineConfig,
) -> None:
    selected = "openrouter/free"
    lines = [
        'data: {"model":"openai/gpt-oss-20b:free","choices":[{"delta":{"content":"Hello"}}]}',
        "data: [DONE]",
    ]
    client, transport = _client(pipeline, [_Response(200, lines=lines)])

    events = [
        event
        async for event in client.stream(
            selected_model=selected,
            system_prompt="system",
            user_prompt="user",
        )
    ]

    call = transport.calls[0]
    assert call["endpoint"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["HTTP-Referer"] == "https://www.yash456k.com"
    assert call["json"]["model"] == "openrouter/free"
    assert call["json"]["max_tokens"] == pipeline.generation.max_tokens
    assert "max_completion_tokens" not in call["json"]
    assert events[0]["servedModel"] == "openai/gpt-oss-20b:free"


@pytest.mark.asyncio
async def test_missing_openrouter_key_falls_back_to_groq(
    pipeline: PipelineConfig,
) -> None:
    client, transport = _client(pipeline, [_Response(200, lines=_success_lines("fallback"))])
    client.api_keys["openrouter"] = None

    events = [
        event
        async for event in client.stream(
            selected_model="openrouter/free",
            system_prompt="system",
            user_prompt="user",
        )
    ]

    assert transport.calls[0]["json"]["model"] == pipeline.fallback_order[0]
    assert events[0]["fallbackUsed"] is True
    assert events[0]["attempts"] == [
        {"model": "openrouter/free", "status": None, "reason": "openrouter_not_configured"}
    ]
