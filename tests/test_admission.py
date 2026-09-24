from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.main import create_app
from app.settings import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, trusted_proxy_cidrs=["127.0.0.1/32"], **overrides)


def _app(pipeline, **overrides):
    application = create_app(_settings(**overrides), pipeline)
    application.state.database = SimpleNamespace(
        reserve_request_limits=AsyncMock(return_value=(True, 10, None)),
        start_query_log=AsyncMock(),
        finish_query_log=AsyncMock(),
        retrieve=AsyncMock(return_value=[]),
        health=AsyncMock(return_value={"ok": True}),
    )
    application.state.embeddings = SimpleNamespace(
        loaded_ids=[item.id for item in pipeline.embedders],
        encode_query=AsyncMock(return_value=[0.0]),
    )
    return application


def _body(pipeline) -> dict:
    return {
        "question": "What did Yash build?",
        "embedder": pipeline.embedders[0].id,
        "model": pipeline.llms[0].id,
        "topK": 3,
        "useHistory": False,
    }


@pytest.mark.asyncio
async def test_declared_oversize_rejected_before_body_or_database(pipeline) -> None:
    application = _app(pipeline)
    reads = 0

    async def body():
        nonlocal reads
        reads += 1
        yield b"{}"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/chat", content=body(), headers={"Content-Length": "32769"}
        )

    assert response.status_code == 413
    assert reads == 0
    application.state.database.reserve_request_limits.assert_not_awaited()


@pytest.mark.asyncio
async def test_chunked_oversize_rejected_before_database(pipeline) -> None:
    application = _app(pipeline)

    async def body():
        yield b" " * 16384
        yield b" " * 16385
        pytest.fail("oversized body must not be drained")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post("/v1/chat", content=body())

    assert response.status_code == 413
    application.state.database.reserve_request_limits.assert_not_awaited()


@pytest.mark.asyncio
async def test_health_cache_coalesces_parallel_requests(pipeline) -> None:
    application = _app(pipeline)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        responses = await asyncio.gather(*(client.get("/v1/health") for _ in range(8)))
    assert all(response.status_code == 200 for response in responses)
    assert application.state.database.health.await_count == 1


@pytest.mark.asyncio
async def test_unknown_chat_fields_rejected_before_database(pipeline) -> None:
    application = _app(pipeline)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post("/v1/chat", json={**_body(pipeline), "unexpected": "x"})
    assert response.status_code == 422
    application.state.database.reserve_request_limits.assert_not_awaited()


async def test_unknown_history_fields_rejected_before_database(pipeline) -> None:
    application = _app(pipeline)
    body = {**_body(pipeline), "history": [{"role": "user", "content": "ok", "extra": "no"}]}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post("/v1/chat", json=body)
    assert response.status_code == 422
    application.state.database.reserve_request_limits.assert_not_awaited()


@pytest.mark.parametrize("bootstrap", [False, True])
async def test_lifespan_passes_database_bootstrap_setting(pipeline, monkeypatch, bootstrap) -> None:
    captured = []
    database = SimpleNamespace(open=AsyncMock(), close=AsyncMock(), cleanup_retention=AsyncMock())
    embeddings = SimpleNamespace(load_all=AsyncMock())
    provider = SimpleNamespace(close=AsyncMock())

    def factory(_url, _embedders, *, bootstrap_schema):
        captured.append(bootstrap_schema)
        return database

    monkeypatch.setattr("app.main.Database", factory)
    monkeypatch.setattr("app.main.EmbeddingRegistry", lambda *_: embeddings)
    monkeypatch.setattr("app.main.GroqClient", lambda *_: provider)
    application = create_app(_settings(database_bootstrap_schema=bootstrap), pipeline)
    async with application.router.lifespan_context(application):
        assert application.state.database is database
    assert captured == [bootstrap]
    database.close.assert_awaited_once()
    provider.close.assert_awaited_once()
