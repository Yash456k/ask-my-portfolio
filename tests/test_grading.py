from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.grading import _answer_item, create_app

TAILNET = {"Tailscale-User-Login": "yash@example.test"}


class _Unused:
    def connection(self):  # pragma: no cover - requests below never reach the database
        raise AssertionError("database must not be touched")


def test_requests_without_tailnet_identity_are_refused() -> None:
    client = TestClient(create_app(_Unused()))
    assert client.get("/").status_code == 403
    assert client.get("/api/answers").status_code == 403
    assert client.get("/healthz").json() == {"ok": True}


def test_page_is_served_privately_to_tailnet_users() -> None:
    response = TestClient(create_app(_Unused())).get("/", headers=TAILNET)
    assert response.status_code == 200
    assert "Grade the" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_grades_and_choices_are_validated_before_the_database() -> None:
    client = TestClient(create_app(_Unused()))
    bad_grade = client.put("/api/answers/x/grade", json={"grade": "great"}, headers=TAILNET)
    bad_choice = client.put("/api/pairs/1", json={"choice": "c"}, headers=TAILNET)
    assert bad_grade.status_code == bad_choice.status_code == 422


def test_answer_items_number_sources_and_fall_back_to_archived_text() -> None:
    row = {
        "id": "abc",
        "created_at": datetime(2026, 9, 24, tzinfo=UTC),
        "question": "Who is Yash?",
        "history": [],
        "answer": "A developer [S1].",
        "requested_embedder": "jev",
        "actual_model": "deepseek/deepseek-v4.1-flash",
        "retrieved_chunks": [
            {"id": "88", "source": "a.md", "chunkIndex": 0, "score": 0.9},
            {"id": "999", "source": "b.md", "chunkIndex": 2, "score": 0.1},
        ],
        "latencies": {"totalMs": 2100},
        "signals": None,
        "retrieval": {},
        "country": "IN",
        "session": "1234abcd",
        "status": "completed",
        "grade": None,
        "note": None,
        "graded_at": None,
        "graded_by": None,
    }
    item = _answer_item(row, {"88": {"content": "Profile text", "chunk_index": 0}})
    assert [s["n"] for s in item["sources"]] == [1, 2]
    assert item["sources"][0]["content"] == "Profile text"
    assert item["sources"][1]["content"] == "(chunk text unavailable)"
    assert item["totalMs"] == 2100 and item["grade"] is None
