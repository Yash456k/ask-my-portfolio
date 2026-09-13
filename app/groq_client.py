from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import PipelineConfig

logger = logging.getLogger(__name__)


class GroqStreamError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.attempts = attempts


class GroqClient:
    endpoints = {
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    }

    def __init__(
        self,
        api_key: str,
        pipeline: PipelineConfig,
        openrouter_api_key: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_keys = {"groq": api_key, "openrouter": openrouter_api_key}
        self.pipeline = pipeline
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(pipeline.generation.request_timeout_seconds),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def close(self) -> None:
        await self.client.aclose()

    def candidates(self, selected: str, force_failure: bool) -> list[str]:
        normal = [selected, *self.pipeline.fallback_order]
        candidates = list(dict.fromkeys(normal))
        if force_failure:
            return ["verification/forced-provider-error", *candidates]
        return candidates

    def _payload(
        self, model: str, system_prompt: str, user_prompt: str, provider: str = "groq"
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.pipeline.generation.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        payload["max_tokens" if provider == "openrouter" else "max_completion_tokens"] = (
            self.pipeline.generation.max_tokens
        )
        if provider == "groq" and model.startswith("openai/gpt-oss-"):
            payload.update({"reasoning_effort": "low", "include_reasoning": False})
        elif provider == "groq" and model.startswith("qwen/"):
            payload["reasoning_effort"] = "none"
        return payload

    def _provider(self, model: str) -> str:
        if model.startswith("verification/"):
            return "groq"
        return self.pipeline.llm(model).provider

    def _key(self, provider: str) -> str | None:
        keys = getattr(self, "api_keys", None)
        if isinstance(keys, dict):
            return keys.get(provider)
        return self.api_key if provider == "groq" else None

    async def stream(
        self,
        *,
        selected_model: str,
        system_prompt: str,
        user_prompt: str,
        force_failure: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        candidates = self.candidates(selected_model, force_failure)

        for candidate in candidates:
            provider = self._provider(candidate)
            api_key = self._key(provider)
            if not api_key:
                attempts.append(
                    {"model": candidate, "status": None, "reason": f"{provider}_not_configured"}
                )
                continue
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if provider == "openrouter":
                headers.update(
                    {
                        "HTTP-Referer": "https://www.yash456k.com",
                        "X-Title": "Yash Khambhatta RAG Playground",
                    }
                )
            emitted_content = False
            saw_done = False
            try:
                async with self.client.stream(
                    "POST",
                    self.endpoints[provider],
                    headers=headers,
                    json=self._payload(candidate, system_prompt, user_prompt, provider),
                ) as response:
                    if response.status_code != 200:
                        attempt = {
                            "model": candidate,
                            "status": response.status_code,
                            "reason": _provider_error_reason(response.status_code),
                        }
                        attempts.append(attempt)
                        can_fallback = (
                            candidate.startswith("verification/")
                            or response.status_code in {403, 404, 408, 409, 429}
                            or response.status_code >= 500
                        )
                        if response.status_code == 401 or not can_fallback:
                            raise GroqStreamError(f"{provider} rejected the request", attempts)
                        logger.warning("%s model %s failed; trying fallback", provider, candidate)
                        continue

                    stream_failed = False
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            saw_done = True
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError as exc:
                            attempts.append(
                                {"model": candidate, "status": 200, "reason": "malformed_sse"}
                            )
                            if emitted_content:
                                raise GroqStreamError(
                                    "Provider stream stopped after output began", attempts
                                ) from exc
                            stream_failed = True
                            break
                        if chunk.get("error"):
                            attempts.append(
                                {"model": candidate, "status": 200, "reason": "stream_error"}
                            )
                            if emitted_content:
                                raise GroqStreamError(
                                    "Provider stream stopped after output began", attempts
                                )
                            stream_failed = True
                            break
                        choices = chunk.get("choices") or []
                        if choices:
                            token = (choices[0].get("delta") or {}).get("content")
                            if token:
                                if not emitted_content:
                                    served_model = str(chunk.get("model") or candidate)
                                    yield {
                                        "type": "model",
                                        "requestedModel": selected_model,
                                        "servedModel": served_model,
                                        "fallbackUsed": (
                                            candidate != selected_model or bool(attempts)
                                        ),
                                        "attempts": attempts,
                                    }
                                emitted_content = True
                                yield {"type": "token", "token": token}
                        if chunk.get("usage"):
                            yield {"type": "usage", "usage": chunk["usage"]}
                    if emitted_content and saw_done:
                        return
                    if emitted_content:
                        attempts.append(
                            {"model": candidate, "status": 200, "reason": "truncated_stream"}
                        )
                        raise GroqStreamError(
                            "Provider stream stopped after output began", attempts
                        )
                    if not stream_failed:
                        attempts.append(
                            {"model": candidate, "status": 200, "reason": "empty_stream"}
                        )
                    logger.warning(
                        "%s model %s returned no answer; trying fallback", provider, candidate
                    )
                    continue
            except GroqStreamError:
                raise
            except httpx.TransportError as exc:
                reason = (
                    "provider_timeout" if isinstance(exc, httpx.TimeoutException) else "network_error"
                )
                attempts.append({"model": candidate, "status": None, "reason": reason})
                if emitted_content:
                    raise GroqStreamError(
                        "Provider stream stopped after output began", attempts
                    ) from exc
                logger.warning("%s network failure for %s; trying fallback", provider, candidate)
                continue
        raise GroqStreamError("No configured generation model was available", attempts)


def _provider_error_reason(status_code: int) -> str:
    """Public attempts never include provider-controlled bodies or diagnostics."""
    reasons = {
        401: "provider_authentication_failed",
        403: "provider_access_denied",
        404: "provider_model_unavailable",
        408: "provider_timeout",
        409: "provider_conflict",
        429: "provider_rate_limited",
    }
    if status_code >= 500:
        return "provider_unavailable"
    return reasons.get(status_code, "provider_request_rejected")
