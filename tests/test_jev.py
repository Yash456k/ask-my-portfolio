from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from test_admission import _app, _body

from app.jev import (
    PICK_QUESTION,
    JevRanking,
    JevUnavailable,
    build_request,
    rank,
)

CHUNKS = [
    {
        "id": "11",
        "source": "a.md",
        "title": "A",
        "chunkIndex": 0,
        "content": "Yash lives in Ahmedabad.",
    },
    {
        "id": "12",
        "source": "a.md",
        "title": "A",
        "chunkIndex": 1,
        "content": "He built NSK bookings.",
    },
    {
        "id": "13",
        "source": "b.md",
        "title": "B",
        "chunkIndex": 0,
        "content": "The RAG uses pgvector.",
    },
]
VISITOR = "123e4567-e89b-42d3-a456-426614174000"
SESSION = "123e4567-e89b-42d3-a456-426614174001"


def _result(pick: str, none: float, relevance: list[float]) -> dict:
    options = {f"c{i:02d}": 0.0 for i in range(1, 4)} | {"none": none}
    if pick != "none":
        options[pick] = 1.0 - none
    answers = {PICK_QUESTION: {"choice": pick, "confidence": 0.9, "probabilities": options}}
    answers |= {f"c{i:02d}": {"noul": value} for i, value in enumerate(relevance, start=1)}
    return {"answers": answers, "usage": {"input_tokens": 900}}


def test_request_uses_neutral_keys_and_both_question_types() -> None:
    body = build_request("where is yash", CHUNKS)
    questions = body["questions"]
    assert set(questions[PICK_QUESTION]["criteria"]) == {"c01", "c02", "c03", "none"}
    assert [questions[f"c0{i}"]["type"] for i in range(1, 4)] == ["noul"] * 3
    assert "Ahmedabad" in questions["c01"]["instructions"]["passage"]
    assert body["state"] == {"user_question": "where is yash"}


def test_choice_pick_leads_then_noul_orders_the_rest() -> None:
    ranking = rank(_result("c03", 0.02, [0.4, 0.9, 0.7]), CHUNKS)
    assert [chunk["id"] for chunk in ranking.ordered] == ["13", "12", "11"]
    assert ranking.ordered[0]["score"] == 0.98  # pick probability, higher than its 0.7
    assert ranking.pick == "13"
    assert ranking.none_probability == 0.02


def test_none_pick_keeps_noul_order_and_reports_refusal_signal() -> None:
    ranking = rank(_result("none", 0.93, [0.1, 0.3, 0.2]), CHUNKS)
    assert ranking.pick is None
    assert [chunk["id"] for chunk in ranking.ordered] == ["12", "13", "11"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["answers"][PICK_QUESTION]["probabilities"].pop("c02"),
        lambda r: r["answers"]["c01"].update(noul=1.7),
        lambda r: r["answers"].pop("c03"),
    ],
)
def test_malformed_answers_are_rejected(mutate) -> None:
    result = _result("c01", 0.0, [0.9, 0.1, 0.1])
    mutate(result)
    with pytest.raises((ValueError, KeyError)):
        rank(result, CHUNKS)


class _Provider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def stream(self, **kwargs):
        self.prompts.append(kwargs["user_prompt"])
        yield {"type": "model", "servedModel": "m", "fallbackUsed": False, "attempts": []}
        yield {"type": "token", "token": "Ahmedabad [S1]"}


def _jev_app(pipeline, jev_rank):
    application = _app(pipeline)
    application.state.jev = SimpleNamespace(rank=jev_rank)
    application.state.jev_chunks = CHUNKS
    application.state.provider = _Provider()
    fallback_rows = [{**CHUNKS[2], "score": 0.91}]
    application.state.database.retrieve = AsyncMock(return_value=fallback_rows)
    return application


async def _chat(application, **extra) -> list[dict]:
    body = {**_body(application.state.pipeline_for_test), "embedder": "jev", **extra}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("127.0.0.1", 9)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/v1/chat",
            json=body,
            headers={"CF-IPCountry": "in", "User-Agent": "UnitTest/1.0"},
        )
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data:")]


async def test_jev_route_answers_and_logs_everything(pipeline) -> None:
    ranking = rank(_result("c01", 0.01, [0.2, 0.1, 0.3]), CHUNKS)
    application = _jev_app(pipeline, AsyncMock(return_value=(ranking, {"input_tokens": 900})))
    application.state.pipeline_for_test = pipeline
    client = {
        "visitorId": VISITOR,
        "sessionId": SESSION,
        "timezone": "Asia/Kolkata",
        "language": "en-IN",
        "screen": "390x844",
    }
    events = await _chat(application, client=client)

    embedding = next(event for event in events if event["type"] == "embedding")
    assert embedding["kind"] == "jev" and embedding["chunksRead"] == 3
    sources = next(event for event in events if event["type"] == "sources")
    assert sources["chunks"][0]["id"] == "11"
    assert events[-1]["type"] == "done" and events[-1]["localRefusal"] is False
    application.state.database.retrieve.assert_not_awaited()

    database = application.state.database
    details = database.start_query_log.await_args.args[5]
    assert details["visitor_id"] == VISITOR and details["session_id"] == SESSION
    assert details["country"] == "IN" and details["user_agent"] == "UnitTest/1.0"
    assert len(details["device_hash"]) == 32 and details["client"]["screen"] == "390x844"
    finished = database.finish_query_log.await_args.kwargs
    assert finished["answer"] == "Ahmedabad [S1]"
    assert finished["retrieval"]["pickChunkId"] == "11"
    assert finished["retrieval"]["inputTokens"] == 900


async def test_jev_none_refuses_without_calling_the_llm(pipeline) -> None:
    ranking = rank(_result("none", 0.93, [0.1, 0.1, 0.1]), CHUNKS)
    application = _jev_app(pipeline, AsyncMock(return_value=(ranking, {})))
    application.state.pipeline_for_test = pipeline
    events = await _chat(application)
    assert events[-1]["localRefusal"] is True
    assert application.state.provider.prompts == []


async def test_jev_failure_falls_back_to_embedding_route(pipeline) -> None:
    application = _jev_app(pipeline, AsyncMock(side_effect=JevUnavailable("http_500")))
    application.state.pipeline_for_test = pipeline
    events = await _chat(application)
    embedding = next(event for event in events if event["type"] == "embedding")
    assert embedding["fallbackFrom"] == "jev" and embedding["embedder"] == "portfolio-e5-small"
    assert events[-1]["type"] == "done"
    retrieval = application.state.database.finish_query_log.await_args.kwargs["retrieval"]
    assert retrieval == {
        "retriever": "jev",
        "fallback": "portfolio-e5-small",
        "fallbackReason": "http_500",
    }


async def test_jev_is_rejected_when_not_configured(pipeline) -> None:
    application = _app(pipeline)
    application.state.jev = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.post("/v1/chat", json={**_body(pipeline), "embedder": "jev"})
        config = await client.get("/v1/config")
    assert response.status_code == 422
    assert all(item["id"] != "jev" for item in config.json()["embedders"])


def test_ranking_type_is_frozen() -> None:
    assert JevRanking.__dataclass_params__.frozen
