"""Private grading service for logged answers and blind model comparisons.

Runs as its own container with the rag_grader database role, which can read question logs
and chunk text and write grades, nothing else. It is reachable only through Tailscale Serve
on Yash's tailnet; the public API never imports this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field

PAGE = Path(__file__).with_name("grading_page.html")
IDENTITY_HEADER = "tailscale-user-login"


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grade: Literal["good", "ok", "bad"]
    note: str = Field(default="", max_length=2000)


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: Literal["a", "b", "tie", "both_bad"]
    note: str = Field(default="", max_length=2000)


# Cheap change detector the page polls; it reloads the full list only when this moves.
VERSION_SQL = """
SELECT concat_ws('|',
    (SELECT count(*) FROM query_logs), (SELECT max(completed_at) FROM query_logs),
    (SELECT count(*) FROM answer_grades), (SELECT max(graded_at) FROM answer_grades),
    (SELECT max(decided_at) FROM model_pairs)) AS version
"""

ANSWERS_SQL = """
SELECT q.id::text, q.created_at, q.question, q.answer, q.history, q.requested_embedder,
       q.requested_model, q.actual_model, q.retrieved_chunks, q.latencies, q.signals,
       q.retrieval, q.country, left(q.session_id, 8) AS session, q.status,
       g.grade, g.note, g.graded_at, g.graded_by
FROM query_logs q
LEFT JOIN answer_grades g ON g.query_log_id = q.id
WHERE (q.status = 'completed' AND q.answer IS NOT NULL)
   OR (q.status = 'started' AND q.created_at > now() - interval '10 minutes')
ORDER BY q.created_at DESC
LIMIT 300
"""


def _chunk_texts(connection, ids: list[int]) -> dict[str, dict[str, Any]]:
    """Current chunk text, falling back to the archive for chunks replaced by re-ingestion."""
    if not ids:
        return {}
    found: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT id::text AS id, source, chunk_index, content FROM chunks WHERE id = ANY(%s)",
        (ids,),
    ):
        found[row["id"]] = row
    missing = [value for value in ids if str(value) not in found]
    if missing:
        for row in connection.execute(
            "SELECT DISTINCT ON (chunk_id) chunk_id::text AS id, source, chunk_index, content "
            "FROM chunk_history WHERE chunk_id = ANY(%s) ORDER BY chunk_id, archived_at DESC",
            (missing,),
        ):
            found[row["id"]] = row
    return found


def _answer_item(row: dict[str, Any], texts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sources = []
    for number, chunk in enumerate(row["retrieved_chunks"] or [], start=1):
        text = texts.get(str(chunk.get("id")), {})
        sources.append(
            {
                "n": number,
                "source": chunk.get("source"),
                "chunkIndex": chunk.get("chunkIndex", text.get("chunk_index")),
                "score": chunk.get("score"),
                "content": text.get("content", "(chunk text unavailable)"),
            }
        )
    latencies = row["latencies"] or {}
    return {
        "id": row["id"],
        "askedAt": row["created_at"].isoformat(),
        "question": row["question"],
        "history": row["history"] or [],
        "answer": row["answer"] or "",
        "status": row["status"],
        "retriever": row["requested_embedder"],
        "model": row["actual_model"] or ("local refusal" if row["answer"] else None),
        "firstTokenMs": latencies.get("firstTokenMs"),
        "totalMs": latencies.get("totalMs"),
        "signals": row["signals"],
        "retrieval": row["retrieval"] or {},
        "country": row["country"],
        "session": row["session"],
        "sources": sources,
        "grade": row["grade"],
        "note": row["note"] or "",
        "gradedAt": row["graded_at"].isoformat() if row["graded_at"] else None,
        "gradedBy": row["graded_by"],
    }


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    holder: dict[str, ConnectionPool | None] = {"pool": pool}

    def db() -> ConnectionPool:
        if holder["pool"] is None:
            holder["pool"] = ConnectionPool(
                os.environ["DATABASE_URL"],
                min_size=1,
                max_size=3,
                kwargs={"row_factory": dict_row, "autocommit": True},
            )
        return holder["pool"]

    @app.middleware("http")
    async def tailnet_only(request: Request, call_next):
        # Tailscale Serve adds the signed-in tailnet user. A request without it did not come
        # through Serve, so it is refused even though the port is loopback-only.
        if request.url.path != "/healthz" and not request.headers.get(IDENTITY_HEADER):
            return JSONResponse({"detail": "tailnet only"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def page() -> HTMLResponse:
        return HTMLResponse(PAGE.read_text(encoding="utf-8"))

    @app.get("/api/version")
    def version() -> dict[str, str]:
        with db().connection() as connection:
            return {"version": connection.execute(VERSION_SQL).fetchone()["version"] or ""}

    @app.get("/api/answers")
    def answers() -> dict[str, Any]:
        with db().connection() as connection:
            rows = connection.execute(ANSWERS_SQL).fetchall()
            ids = sorted(
                {
                    int(chunk["id"])
                    for row in rows
                    for chunk in (row["retrieved_chunks"] or [])
                    if str(chunk.get("id", "")).isdigit()
                }
            )
            texts = _chunk_texts(connection, ids)
            unrecorded = connection.execute(
                "SELECT count(*) AS n FROM query_logs WHERE answer IS NULL"
            ).fetchone()["n"]
        items = [_answer_item(row, texts) for row in rows]
        return {"items": items, "unrecordedOlder": unrecorded}

    @app.put("/api/answers/{query_log_id}/grade")
    def grade(query_log_id: str, body: Grade, request: Request) -> dict[str, Any]:
        with db().connection() as connection:
            row = connection.execute(
                """
                INSERT INTO answer_grades (query_log_id, grade, note, graded_by)
                SELECT id, %s, %s, %s FROM query_logs WHERE id::text = %s
                ON CONFLICT (query_log_id) DO UPDATE
                SET grade = excluded.grade, note = excluded.note,
                    graded_by = excluded.graded_by, graded_at = now()
                RETURNING graded_at
                """,
                (body.grade, body.note.strip(), request.headers[IDENTITY_HEADER], query_log_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="unknown answer")
        return {"gradedAt": row["graded_at"].isoformat()}

    @app.get("/api/pairs")
    def pairs() -> dict[str, Any]:
        with db().connection() as connection:
            rows = connection.execute(
                "SELECT id, run, case_id, question, history, answer_a, answer_b, model_a, "
                "model_b, choice, note FROM model_pairs ORDER BY run DESC, id"
            ).fetchall()
        # Model names stay hidden until a choice is saved, so the comparison is blind.
        return {
            "items": [
                {
                    **{k: row[k] for k in ("id", "run", "question", "choice", "note")},
                    "history": row["history"] or [],
                    "answerA": row["answer_a"],
                    "answerB": row["answer_b"],
                    "models": {"a": row["model_a"], "b": row["model_b"]} if row["choice"] else None,
                }
                for row in rows
            ]
        }

    @app.put("/api/pairs/{pair_id}")
    def prefer(pair_id: int, body: Preference, request: Request) -> dict[str, Any]:
        with db().connection() as connection:
            row = connection.execute(
                "UPDATE model_pairs SET choice = %s, note = %s, decided_by = %s, "
                "decided_at = now() WHERE id = %s RETURNING model_a, model_b",
                (body.choice, body.note.strip(), request.headers[IDENTITY_HEADER], pair_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="unknown pair")
        return {"models": {"a": row["model_a"], "b": row["model_b"]}}

    return app


app = create_app()
