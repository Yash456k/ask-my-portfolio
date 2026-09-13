from __future__ import annotations

import json

import httpx
import pytest

from app.groq_client import GroqStreamError
from test_groq_client import _client, _Response, _success_lines


@pytest.fixture
def pipeline(pipeline):
    # Exercise fallback deliberately, independent of the production default
    # (whose fallback may itself be the first model in the catalog).
    return pipeline.model_copy(update={"fallback_order": [pipeline.llms[1].id]})


@pytest.mark.parametrize(
    ("status", "reason", "fallback"),
    [
        (400, "provider_request_rejected", False),
        (401, "provider_authentication_failed", False),
        (403, "provider_access_denied", True),
        (404, "provider_model_unavailable", True),
        (408, "provider_timeout", True),
        (409, "provider_conflict", True),
        (429, "provider_rate_limited", True),
        (503, "provider_unavailable", True),
    ],
)
async def test_http_diagnostics_are_stable_and_error_body_is_never_read(
    pipeline, status, reason, fallback
) -> None:
    class UnreadError(_Response):
        async def aread(self):
            pytest.fail("must not buffer or publish arbitrary upstream error bodies")

    selected = pipeline.llms[0].id
    client, transport = _client(
        pipeline,
        [UnreadError(status), _Response(200, lines=_success_lines("answer"))],
    )
    if fallback:
        events = [event async for event in client.stream(
            selected_model=selected, system_prompt="system", user_prompt="user"
        )]
        attempts = events[0]["attempts"]
        assert events[0]["fallbackUsed"] is True
    else:
        with pytest.raises(GroqStreamError) as caught:
            _ = [event async for event in client.stream(
                selected_model=selected, system_prompt="system", user_prompt="user"
            )]
        attempts = caught.value.attempts
    assert attempts == [{"model": selected, "status": status, "reason": reason}]
    assert len(transport.calls) == (2 if fallback else 1)


@pytest.mark.parametrize("error", [{"message": "secret request diagnostic"}, "secret upstream URL"])
async def test_stream_diagnostics_are_redacted_before_fallback(pipeline, error) -> None:
    client, _ = _client(pipeline, [
        _Response(200, lines=[f"data: {json.dumps({'error': error})}"]),
        _Response(200, lines=_success_lines("answer")),
    ])
    events = [event async for event in client.stream(
        selected_model=pipeline.llms[0].id, system_prompt="system", user_prompt="user"
    )]
    assert events[0]["attempts"][0]["reason"] == "stream_error"
    assert "secret" not in json.dumps(events)


@pytest.mark.parametrize(
    ("error", "reason"),
    [(httpx.ReadTimeout("secret endpoint"), "provider_timeout"),
     (httpx.ConnectError("secret endpoint"), "network_error")],
)
async def test_transport_errors_use_stable_codes(pipeline, error, reason) -> None:
    client, _ = _client(pipeline, [error, _Response(200, lines=_success_lines("answer"))])
    events = [event async for event in client.stream(
        selected_model=pipeline.llms[0].id, system_prompt="system", user_prompt="user"
    )]
    assert events[0]["attempts"][0]["reason"] == reason
    assert "secret" not in json.dumps(events)


async def test_stream_error_after_content_does_not_fallback(pipeline) -> None:
    lines = _success_lines("partial")[:1] + ['data: {"error":{"message":"secret upstream detail"}}']
    client, transport = _client(pipeline, [_Response(200, lines=lines)])
    with pytest.raises(GroqStreamError) as caught:
        _ = [event async for event in client.stream(
            selected_model=pipeline.llms[0].id, system_prompt="system", user_prompt="user"
        )]
    assert caught.value.attempts[0]["reason"] == "stream_error"
    assert len(transport.calls) == 1
    assert "secret" not in str(caught.value.attempts)
