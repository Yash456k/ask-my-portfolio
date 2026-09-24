"""Process-local limits before parsing/DB work; intended for one ASGI worker."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.security import get_client_ip, hash_ip
from app.settings import Settings

MAX_BODY_BYTES = 32 * 1024
BODY_READ_TIMEOUT_SECONDS = 10


@dataclass
class _Client:
    requests: int = 0
    chats: int = 0
    active: int = 0
    active_chats: int = 0


class AdmissionLimiter:
    """Bounded fixed-window counters, with no awaits between checking and reserving.

    Idle entries expire at the next window; active entries are never evicted. New
    identities are rejected when the table is full rather than evicting live limits.
    Keys are salted digests, not raw IP addresses. Limits are per process, not a
    replacement for the database's durable daily/monthly quotas.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.window_start = time.monotonic()
        self.requests = 0
        self.chats = 0
        self.active = 0
        self.active_chats = 0
        self.clients: dict[str, _Client] = {}

    def acquire(self, ip_digest: str, is_chat: bool) -> tuple[_Client | None, str, int]:
        now = time.monotonic()
        window = self.settings.admission_window_seconds
        if now - self.window_start >= window:
            self.window_start = now
            self.requests = self.chats = 0
            self.clients = {key: client for key, client in self.clients.items() if client.active}
            for client in self.clients.values():
                client.requests = client.chats = 0
        retry_after = max(1, math.ceil(self.window_start + window - now))
        if self.requests >= self.settings.admission_global_burst:
            return None, "global_burst_limit_exceeded", retry_after
        self.requests += 1
        client = self.clients.get(ip_digest)
        if client is None:
            if len(self.clients) >= self.settings.admission_max_clients:
                return None, "admission_capacity_exceeded", retry_after
            client = self.clients[ip_digest] = _Client()
        if client.requests >= self.settings.admission_per_ip_burst:
            return None, "ip_burst_limit_exceeded", retry_after
        client.requests += 1
        if is_chat:
            if self.chats >= self.settings.chat_global_burst:
                return None, "chat_global_burst_limit_exceeded", retry_after
            self.chats += 1
            if client.chats >= self.settings.chat_per_ip_burst:
                return None, "chat_ip_burst_limit_exceeded", retry_after
            client.chats += 1
        if self.active >= self.settings.admission_max_concurrent:
            return None, "admission_concurrency_exceeded", 1
        if is_chat and (
            self.active_chats >= self.settings.chat_max_concurrent
            or client.active_chats >= self.settings.chat_per_ip_concurrent
        ):
            return None, "chat_concurrency_exceeded", 1
        self.active += 1
        client.active += 1
        if is_chat:
            self.active_chats += 1
            client.active_chats += 1
        return client, "", 0

    def release(self, client: _Client, is_chat: bool) -> None:
        self.active -= 1
        client.active -= 1
        if is_chat:
            self.active_chats -= 1
            client.active_chats -= 1


class AdmissionMiddleware:
    """Pure ASGI wrapper: retain reservations through the *entire* response.

    Buffer at most 32 KiB before calling FastAPI (including chunked requests).
    A receive deadline prevents slow uploads from holding reservations forever.
    `finally` releases on validation errors, disconnects, cancellation, and send
    failures, not merely when StreamingResponse headers have been returned.
    """

    def __init__(self, app: ASGIApp, settings: Settings, limiter: AdmissionLimiter) -> None:
        self.app = app
        self.settings = settings
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        ip_digest = hash_ip(get_client_ip(request, self.settings), self.settings.ip_hash_salt)
        # Include slash redirects so they cannot create a second chat admission path.
        is_chat = scope["method"] == "POST" and scope["path"].rstrip("/") == "/v1/chat"
        client, reason, retry_after = self.limiter.acquire(ip_digest, is_chat)
        if client is None:
            await self._reject(scope, receive, send, 429, reason, retry_after)
            return
        try:
            lengths = request.headers.getlist("content-length")
            if lengths:
                # Also defend direct ASGI callers; the HTTP server normally rejects this.
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                    await self._reject(scope, receive, send, 400, "invalid_content_length")
                    return
                if len(lengths[0]) > 10 or int(lengths[0]) > MAX_BODY_BYTES:
                    await self._reject(scope, receive, send, 413, "request_body_too_large")
                    return
            body = bytearray()
            try:
                async with asyncio.timeout(BODY_READ_TIMEOUT_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > MAX_BODY_BYTES:
                            await self._reject(scope, receive, send, 413, "request_body_too_large")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await self._reject(scope, receive, send, 408, "request_body_timeout")
                return

            replayed = False

            async def replay_receive() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, send)
        finally:
            self.limiter.release(client, is_chat)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        reason: str,
        retry_after: int | None = None,
    ) -> None:
        headers = {"Cache-Control": "no-store"}
        if retry_after is not None:
            headers.update({"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"})
        response = JSONResponse({"detail": reason}, status_code=status_code, headers=headers)
        await response(scope, receive, send)
