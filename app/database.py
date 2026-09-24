from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import EmbedderConfig, load_pipeline


async def _configure_connection(connection) -> None:
    await register_vector_async(connection)


class Database:
    def __init__(
        self,
        database_url: str,
        embedders: Sequence[EmbedderConfig] | None = None,
        *,
        bootstrap_schema: bool = True,
    ) -> None:
        self.database_url = database_url
        self.bootstrap_schema = bootstrap_schema
        self.embedders = tuple(embedders or load_pipeline().embedders)
        self.pool = AsyncConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=6,
            open=False,
            configure=_configure_connection,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

    async def open(self) -> None:
        if self.bootstrap_schema:
            # Operator/development path only. Public runtime uses a restricted
            # account with bootstrap_schema=False against a pre-migrated DB.
            schema_path = Path(__file__).parents[1] / "sql" / "schema.sql"
            schema = schema_path.read_text(encoding="utf-8")
            connection = await AsyncConnection.connect(self.database_url, autocommit=True)
            async with connection:
                await connection.execute(schema)
        await self.pool.open(wait=True, timeout=30)

    async def close(self) -> None:
        await self.pool.close()

    async def health(self) -> dict[str, Any]:
        coverage_expressions = [
            sql.SQL("count(*) FILTER (WHERE {column} IS NOT NULL) AS {alias}").format(
                column=sql.Identifier(embedder.column),
                alias=sql.Identifier(embedder.column),
            )
            for embedder in self.embedders
        ]
        query = sql.SQL("SELECT count(*) AS chunks, {coverage} FROM chunks").format(
            coverage=sql.SQL(", ").join(coverage_expressions)
        )
        async with self.pool.connection() as connection:
            row = await (await connection.execute(query)).fetchone()
        chunks = int(row["chunks"]) if row else 0
        coverage = {
            embedder.id: int(row[embedder.column]) if row else 0
            for embedder in self.embedders
        }
        return {
            "ok": chunks > 0 and all(count == chunks for count in coverage.values()),
            "chunks": chunks,
            "vectorCoverage": coverage,
        }

    async def cleanup_retention(self, query_log_days: int = 0) -> None:
        async with self.pool.connection() as connection:
            if query_log_days > 0:
                await connection.execute(
                    "DELETE FROM query_logs WHERE created_at < now() - make_interval(days => %s)",
                    (query_log_days,),
                )
            await connection.execute(
                "DELETE FROM rate_limit_buckets WHERE bucket_date < current_date - 3"
            )
            await connection.execute(
                "DELETE FROM monthly_budget_buckets "
                "WHERE bucket_month < date_trunc('month', current_date)::date - interval '3 months'"
            )

    async def all_chunks(self) -> list[dict[str, Any]]:
        async with self.pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT id, source, title, chunk_index, content FROM chunks "
                "ORDER BY source, chunk_index"
            )
            rows = await cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "source": row["source"],
                "title": row["title"],
                "chunkIndex": row["chunk_index"],
                "content": row["content"],
            }
            for row in rows
        ]

    async def retrieve(
        self,
        embedder: EmbedderConfig,
        query_vector: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        # Column names come exclusively from EmbedderConfig's Literal allowlist.
        column = embedder.column
        query = sql.SQL("""
            SELECT id, source, title, chunk_index, content,
                   1 - ({column} <=> %s::vector) AS score
            FROM chunks
            WHERE {column} IS NOT NULL
            ORDER BY {column} <=> %s::vector
            LIMIT %s
        """).format(column=sql.Identifier(column))
        async with self.pool.connection() as connection:
            cursor = await connection.execute(query, (query_vector, query_vector, top_k))
            rows = await cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "source": row["source"],
                "title": row["title"],
                "chunkIndex": row["chunk_index"],
                "content": row["content"],
                "score": round(float(row["score"]), 5),
            }
            for row in rows
        ]

    async def reserve_request_limits(
        self,
        ip_hash: str,
        per_ip_limit: int,
        global_limit: int,
        monthly_budget_micro_usd: int,
        request_reserve_micro_usd: int,
        *,
        bypass_daily: bool = False,
    ) -> tuple[bool, int, str | None]:
        today = datetime.now(UTC).date()
        month = today.replace(day=1)
        global_key = "all"
        async with self.pool.connection() as connection, connection.transaction():
            # Stable locks make budget and daily counters atomic across workers.
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"budget:{month}",)
            )
            budget_cursor = await connection.execute(
                "SELECT reserved_micro_usd FROM monthly_budget_buckets WHERE bucket_month = %s",
                (month,),
            )
            budget_row = await budget_cursor.fetchone()
            reserved = int(budget_row["reserved_micro_usd"]) if budget_row else 0
            if reserved + request_reserve_micro_usd > monthly_budget_micro_usd:
                return False, 0, "monthly_budget"

            if bypass_daily:
                await connection.execute(
                    """
                    INSERT INTO monthly_budget_buckets (bucket_month, reserved_micro_usd)
                    VALUES (%s, %s)
                    ON CONFLICT (bucket_month) DO UPDATE
                    SET reserved_micro_usd =
                            monthly_budget_buckets.reserved_micro_usd
                            + EXCLUDED.reserved_micro_usd,
                        updated_at = now()
                    """,
                    (month, request_reserve_micro_usd),
                )
                return True, per_ip_limit, None

            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"global:{today}",)
            )
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"ip:{today}:{ip_hash}",)
            )
            cursor = await connection.execute(
                """
                SELECT scope, request_count
                FROM rate_limit_buckets
                WHERE bucket_date = %s
                  AND ((scope = 'global' AND key_hash = %s) OR (scope = 'ip' AND key_hash = %s))
                """,
                (today, global_key, ip_hash),
            )
            counts = {row["scope"]: row["request_count"] for row in await cursor.fetchall()}
            if counts.get("global", 0) >= global_limit:
                return False, 0, "global"
            if counts.get("ip", 0) >= per_ip_limit:
                return False, 0, "ip"
            await connection.execute(
                """
                INSERT INTO rate_limit_buckets (bucket_date, scope, key_hash, request_count)
                VALUES (%s, 'global', %s, 1), (%s, 'ip', %s, 1)
                ON CONFLICT (bucket_date, scope, key_hash) DO UPDATE
                SET request_count = rate_limit_buckets.request_count + 1, updated_at = now()
                """,
                (today, global_key, today, ip_hash),
            )
            await connection.execute(
                """
                INSERT INTO monthly_budget_buckets (bucket_month, reserved_micro_usd)
                VALUES (%s, %s)
                ON CONFLICT (bucket_month) DO UPDATE
                SET reserved_micro_usd =
                        monthly_budget_buckets.reserved_micro_usd
                        + EXCLUDED.reserved_micro_usd,
                    updated_at = now()
                """,
                (month, request_reserve_micro_usd),
            )
            remaining = per_ip_limit - counts.get("ip", 0) - 1
            return True, max(0, remaining), None

    async def start_query_log(
        self,
        request_id: UUID,
        ip_hash: str,
        question: str,
        embedder: str,
        model: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO query_logs
                    (id, ip_hash, question, requested_embedder, requested_model,
                     history, top_k, use_history, visitor_id, session_id, device_hash,
                     user_agent, country, client)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    request_id,
                    ip_hash,
                    question,
                    embedder,
                    model,
                    json.dumps(details.get("history", [])),
                    details.get("top_k"),
                    details.get("use_history"),
                    details.get("visitor_id"),
                    details.get("session_id"),
                    details.get("device_hash"),
                    details.get("user_agent"),
                    details.get("country"),
                    json.dumps(details.get("client", {})),
                ),
            )

    async def finish_query_log(
        self,
        request_id: UUID,
        *,
        status: str,
        actual_model: str | None = None,
        fallback_used: bool = False,
        fallback_attempts: list[dict[str, Any]] | None = None,
        chunks: list[dict[str, Any]] | None = None,
        latencies: dict[str, Any] | None = None,
        answer_characters: int | None = None,
        error_type: str | None = None,
        answer: str | None = None,
        retrieval: dict[str, Any] | None = None,
        signals: dict[str, Any] | None = None,
    ) -> None:
        chunk_log = [
            {
                "id": item["id"],
                "source": item["source"],
                "chunkIndex": item.get("chunkIndex"),
                "score": item["score"],
            }
            for item in (chunks or [])
        ]
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE query_logs
                SET completed_at = now(), status = %s, actual_model = %s,
                    fallback_used = %s, fallback_attempts = %s::jsonb,
                    retrieved_chunks = %s::jsonb, latencies = %s::jsonb,
                    answer_characters = %s, error_type = %s,
                    answer = %s, retrieval = %s::jsonb, signals = %s::jsonb
                WHERE id = %s
                """,
                (
                    status,
                    actual_model,
                    fallback_used,
                    json.dumps(fallback_attempts or []),
                    json.dumps(chunk_log),
                    json.dumps(latencies or {}),
                    answer_characters,
                    error_type,
                    answer,
                    json.dumps(retrieval or {}),
                    None if signals is None else json.dumps(signals),
                    request_id,
                ),
            )


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
