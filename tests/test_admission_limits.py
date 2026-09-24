from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import ClientDisconnect
from test_admission import _app, _body, _settings

from app.admission import MAX_BODY_BYTES, AdmissionLimiter, AdmissionMiddleware


@pytest.mark.parametrize("declared", [False, True])
async def test_exact_body_limit_preserves_sse_and_aliases(pipeline, declared) -> None:
    application = _app(pipeline)
    encoded = json.dumps(_body(pipeline)).encode()
    padded = encoded + b" " * (MAX_BODY_BYTES - len(encoded))

    async def chunks():
        yield padded[:16000]
        yield padded[16000:]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/chat", content=padded if declared else chunks(),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data:")
    ]
    assert events[0]["type"] == "meta"
    assert events[0]["requestReceived"]["historyAware"] is False
    assert events[-1]["type"] == "done"
    assert application.state.admission.active == 0


async def test_spoofed_headers_cannot_bypass_prebody_burst_or_cors(pipeline) -> None:
    application = _app(pipeline, admission_per_ip_burst=1)
    origin = "https://portfolio.example.test"

    async def unread_body():
        pytest.fail("burst rejection must happen before reading the body")
        yield b""  # pragma: no cover

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("203.0.113.10", 123)),
        base_url="http://testserver",
    ) as client:
        first = await client.post("/v1/chat", json={}, headers={"X-Real-IP": "198.51.100.1"})
        second = await client.post(
            "/v1/chat", content=unread_body(),
            headers={
                "X-Real-IP": "198.51.100.2", "X-Forwarded-For": "198.51.100.3",
                "X-Verify-Evaluation": _settings().verify_fallback_token, "Origin": origin,
            },
        )
    assert first.status_code == 422
    assert second.status_code == 429
    assert second.json()["detail"] == "ip_burst_limit_exceeded"
    assert int(second.headers["retry-after"]) >= 1
    assert second.headers["access-control-allow-origin"] == origin
    assert "Retry-After" in second.headers["access-control-expose-headers"]
    assert len(application.state.admission.clients) == 1
    assert "203.0.113.10" not in application.state.admission.clients
    application.state.database.reserve_request_limits.assert_not_awaited()


async def test_trusted_proxy_uses_real_ip_not_forwarded_for(pipeline) -> None:
    application = _app(pipeline, admission_per_ip_burst=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("127.0.0.1", 123)),
        base_url="http://testserver",
    ) as client:
        codes = []
        for real_ip in ["198.51.100.1", "198.51.100.2", "198.51.100.1"]:
            response = await client.post(
                "/v1/chat", json={},
                headers={"X-Real-IP": real_ip, "X-Forwarded-For": "192.0.2.99"},
            )
            codes.append(response.status_code)
    assert codes == [422, 422, 429]


def test_tracking_expires_idle_but_not_active_clients(monkeypatch) -> None:
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("app.admission.time", SimpleNamespace(monotonic=lambda: clock.now))
    limiter = AdmissionLimiter(_settings(admission_max_clients=2, chat_max_concurrent=2))
    held, _, _ = limiter.acquire("held", True)
    idle, _, _ = limiter.acquire("idle", False)
    assert held is not None and idle is not None
    limiter.release(idle, False)
    for index in range(1000):
        assert limiter.acquire(str(index), False)[0] is None
    assert len(limiter.clients) == 2
    assert limiter.requests == limiter.settings.admission_global_burst
    clock.now += 10
    new, _, _ = limiter.acquire("new", False)
    assert new is not None
    assert set(limiter.clients) == {"held", "new"}
    assert limiter.active_chats == held.active_chats == 1
    limiter.release(held, True)
    limiter.release(new, False)
    assert limiter.active == limiter.active_chats == 0


@pytest.mark.parametrize(
    ("overrides", "first_ip", "second_ip", "is_chat", "reason"),
    [
        ({"admission_global_burst": 1}, "a", "b", False, "global_burst_limit_exceeded"),
        ({"chat_global_burst": 1}, "a", "b", True, "chat_global_burst_limit_exceeded"),
        ({"chat_per_ip_burst": 1}, "a", "a", True, "chat_ip_burst_limit_exceeded"),
        ({"admission_max_concurrent": 1}, "a", "b", False, "admission_concurrency_exceeded"),
        ({"chat_per_ip_concurrent": 1}, "a", "a", True, "chat_concurrency_exceeded"),
    ],
)
def test_independent_limits(overrides, first_ip, second_ip, is_chat, reason) -> None:
    limiter = AdmissionLimiter(_settings(**overrides))
    admitted, _, _ = limiter.acquire(first_ip, is_chat)
    assert admitted is not None
    rejected, actual_reason, retry = limiter.acquire(second_ip, is_chat)
    assert rejected is None
    assert actual_reason == reason
    assert retry >= 1
    limiter.release(admitted, is_chat)


def _scope() -> dict:
    return {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "POST", "scheme": "http", "path": "/v1/chat", "raw_path": b"/v1/chat",
        "root_path": "", "query_string": b"", "http_version": "1.1",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("203.0.113.10", 123), "server": ("testserver", 80),
    }


@pytest.mark.parametrize("finish", ["normal", "cancel", "send_failure"])
async def test_chat_slot_covers_last_stream_send_and_releases(pipeline, finish) -> None:
    application = _app(pipeline, chat_max_concurrent=1, chat_per_ip_burst=10)
    at_final_send = asyncio.Event()
    unblock_send = asyncio.Event()

    async def receive():
        return {"type": "http.request", "body": json.dumps(_body(pipeline)).encode()}

    async def send(message):
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            at_final_send.set()
            await unblock_send.wait()
            if finish == "send_failure":
                raise OSError("client disconnected during final send")

    task = asyncio.create_task(application(_scope(), receive, send))
    try:
        await asyncio.wait_for(at_final_send.wait(), 2)
        assert application.state.admission.active_chats == 1
        application.state.database.reserve_request_limits.assert_awaited_once()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application, client=("203.0.113.20", 123)),
            base_url="http://testserver",
        ) as client:
            response = await client.post("/v1/chat", json=_body(pipeline))
        assert response.status_code == 429
        assert response.json()["detail"] == "chat_concurrency_exceeded"
        application.state.database.reserve_request_limits.assert_awaited_once()
        if finish == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            unblock_send.set()
            if finish == "send_failure":
                with pytest.raises(ClientDisconnect):
                    await task
            else:
                await task
        assert application.state.admission.active == 0
        assert application.state.admission.active_chats == 0
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            response = await client.post("/v1/chat", json=_body(pipeline))
        assert response.status_code == 200
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.parametrize("failure", ["validation", "database", "quota", "embedding"])
async def test_slot_released_on_pipeline_failures(pipeline, failure) -> None:
    application = _app(pipeline, chat_max_concurrent=1)
    if failure == "database":
        application.state.database.start_query_log.side_effect = RuntimeError("db failure")
    elif failure == "quota":
        application.state.database.reserve_request_limits.return_value = (False, 0, "ip")
    elif failure == "embedding":
        application.state.embeddings.encode_query.side_effect = RuntimeError("embedding failure")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/v1/chat", json={} if failure == "validation" else _body(pipeline)
        )
    expected = {"validation": 422, "database": 500, "quota": 429, "embedding": 200}
    assert response.status_code == expected[failure]
    assert application.state.admission.active == application.state.admission.active_chats == 0


@pytest.mark.parametrize("disconnect", [False, True])
async def test_body_timeout_and_disconnect_release_without_dispatch(
    monkeypatch, disconnect
) -> None:
    monkeypatch.setattr("app.admission.BODY_READ_TIMEOUT_SECONDS", 0.01)
    settings = _settings()
    limiter = AdmissionLimiter(settings)
    downstream = AsyncMock()
    middleware = AdmissionMiddleware(downstream, settings, limiter)
    sent = []

    async def receive():
        if disconnect:
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        raise AssertionError("unreachable without cancellation")

    async def send(message):
        sent.append(message)

    await middleware(_scope(), receive, send)
    downstream.assert_not_awaited()
    assert limiter.active == limiter.active_chats == 0
    if disconnect:
        assert sent == []
    else:
        assert sent[0]["status"] == 408


@pytest.mark.parametrize("bad_length", ["-1", "nope", "1,2", ""])
async def test_invalid_content_length_does_not_dispatch(pipeline, bad_length) -> None:
    application = _app(pipeline)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/chat", content=b"{}", headers={"Content-Length": bad_length}
        )
    assert response.status_code == 400
    application.state.database.reserve_request_limits.assert_not_awaited()


async def test_health_cache_refreshes_and_caches_failures(pipeline, monkeypatch) -> None:
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("app.main.time", SimpleNamespace(monotonic=lambda: clock.now))
    application = _app(pipeline)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        assert (await client.get("/v1/health")).status_code == 200
        clock.now += 2.9
        assert (await client.get("/v1/health")).status_code == 200
        application.state.database.health.assert_awaited_once()
        clock.now += 0.1
        application.state.database.health.side_effect = RuntimeError("private db diagnostic")
        first = await client.get("/v1/health")
        second = await client.get("/v1/health")
        assert first.status_code == second.status_code == 503
        assert first.json()["database"] == {"ok": False}
        assert "private" not in first.text
        assert application.state.database.health.await_count == 2
