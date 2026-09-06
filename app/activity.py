from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response
from pydantic import ValidationError

from app.schemas import ActivitySnapshot

ACTIVITY_CACHE_CONTROL = "public, no-cache, must-revalidate"


class ActivityCacheUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=8)
def _load_activity(path: str, modified_ns: int, size: int) -> tuple[bytes, str]:
    del modified_ns, size
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        snapshot = ActivitySnapshot.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ActivityCacheUnavailable from error

    payload = snapshot.model_dump_json(by_alias=True).encode("utf-8")
    etag = f'"{hashlib.sha256(payload).hexdigest()}"'
    return payload, etag


def activity_response(request: Request, path: Path) -> Response:
    try:
        stat = path.stat()
        payload, etag = _load_activity(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    except OSError as error:
        raise ActivityCacheUnavailable from error

    headers = {
        "Cache-Control": ACTIVITY_CACHE_CONTROL,
        "ETag": etag,
        "Vary": "Origin",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(payload, media_type="application/json", headers=headers)
