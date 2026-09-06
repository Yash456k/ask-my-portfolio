from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def _snapshot() -> dict:
    return {
        "generatedAt": "2026-07-16T05:55:09Z",
        "period": {"start": "2025-07-16", "end": "2026-07-16"},
        "codex": {
            "total": 123,
            "lifetimeTotal": 456,
            "peakDailyTokens": 78,
            "activeDays": 1,
            "peak": {"date": "2026-07-15", "count": 123},
            "days": [{"date": "2026-07-15", "tokens": 123, "private": "drop-me"}],
            "accessToken": "drop-me",
        },
        "github": {
            "username": "Yash456k",
            "total": 6,
            "activeDays": 1,
            "peak": {"date": "2026-07-16", "count": 6},
            "days": [{"date": "2026-07-16", "count": 6}],
        },
        "apiKey": "drop-me",
    }


def _settings(path: Path) -> Settings:
    return Settings(
        groq_api_key="test-groq-key-not-a-real-secret-000000",
        database_url="postgresql://test:test@127.0.0.1:55432/test",
        frontend_origins=["https://portfolio.example.test"],
        public_api_url="https://api.example.test",
        allowed_hosts=["testserver"],
        trusted_proxy_cidrs=["127.0.0.1/32"],
        ip_hash_salt="unit-test-ip-hash-salt-000000",
        verify_fallback_token="unit-test-fallback-token-000000",  # noqa: S106
        activity_cache_path=path,
    )


def test_activity_endpoint_sanitizes_and_caches(tmp_path: Path, pipeline) -> None:
    cache = tmp_path / "activity.json"
    cache.write_text(json.dumps(_snapshot()), encoding="utf-8")
    client = TestClient(create_app(_settings(cache), pipeline))

    response = client.get("/v1/activity")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, no-cache, must-revalidate"
    assert response.headers["etag"]
    assert response.json()["codex"]["days"][0] == {"date": "2026-07-15", "tokens": 123}
    rendered = response.text
    assert "accessToken" not in rendered
    assert "apiKey" not in rendered
    assert "drop-me" not in rendered

    cached = client.get("/v1/activity", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["cache-control"] == "public, no-cache, must-revalidate"

    # The collector atomically replaces its file. An old ETag must now yield
    # the new snapshot instead of trapping the browser on the previous data.
    updated = _snapshot()
    updated["generatedAt"] = "2026-07-17T05:55:09Z"
    updated["codex"]["lifetimeTotal"] = 789
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps(updated), encoding="utf-8")
    replacement.replace(cache)
    refreshed = client.get("/v1/activity", headers={"If-None-Match": response.headers["etag"]})
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != response.headers["etag"]
    assert refreshed.json()["codex"]["lifetimeTotal"] == 789


def test_activity_endpoint_fails_closed(tmp_path: Path, pipeline) -> None:
    client = TestClient(create_app(_settings(tmp_path / "missing.json"), pipeline))

    response = client.get("/v1/activity")

    assert response.status_code == 503
    assert response.json() == {"detail": "activity_cache_unavailable"}
    assert response.headers["cache-control"] == "no-store"
